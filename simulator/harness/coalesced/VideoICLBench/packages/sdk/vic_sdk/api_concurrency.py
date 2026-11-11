"""Distributed request admission using verified atomic directory creation.

Every relay for one credential scope must share this config and lock directory.
Legacy relays are not hot modified: reserve their capacity until verified drain.
Atomic mkdir must first be verified across the actual hosts/filesystem. flock is
intentionally not used: it did not exclude peers on the evaluation PFS.

No TTL, PID-based stealing or crash cleanup exists. A crash leaves its slot (and
possibly the short admission guard) reserved. An operator must verify process and
upstream-request termination before removing an abandoned directory. This favors
under-admission over exceeding the cap. Never unlink or replace live directories.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import socket
import threading
import time
import uuid

SCHEMA = 'videoicl-api-concurrency-v1'
MAX_SLOTS = 50
_FIELDS = {'schema', 'scope', 'limit', 'legacy_reserved', 'lock_directory',
           'filesystem_atomic_mkdir_verified'}


class GateConfigurationError(ValueError):
    """Invalid or unverified admission configuration; do not forward requests."""


class GateOwnershipError(RuntimeError):
    """Ownership could not be verified; preserve the reservation for audit."""


def validated_config(path):
    """Read one atomically published config; never print credential material."""
    path = Path(path)
    if not path.is_absolute():
        raise GateConfigurationError('Concurrency config must be an absolute path')
    try:
        raw = path.read_bytes()
        if len(raw) > 16384:
            raise ValueError('Oversized config')
        cfg = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise GateConfigurationError('Concurrency config is unavailable or invalid') from exc
    if not isinstance(cfg, dict) or set(cfg) != _FIELDS or cfg.get('schema') != SCHEMA:
        raise GateConfigurationError('Unexpected concurrency config schema or fields')
    if not isinstance(cfg['scope'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', cfg['scope']):
        raise GateConfigurationError('Concurrency scope must be a safe opaque identifier')
    if type(cfg['limit']) is not int or not 1 <= cfg['limit'] <= MAX_SLOTS:
        raise GateConfigurationError('Concurrency limit must be an integer from 1 to 50')
    if type(cfg['legacy_reserved']) is not int or not 0 <= cfg['legacy_reserved'] <= MAX_SLOTS:
        raise GateConfigurationError('Legacy reservation must be an integer from 0 to 50')
    if (not isinstance(cfg['lock_directory'], str)
            or not Path(cfg['lock_directory']).is_absolute()
            or '..' in Path(cfg['lock_directory']).parts):
        raise GateConfigurationError('An absolute stable shared lock directory is required')
    if cfg['filesystem_atomic_mkdir_verified'] is not True:
        raise GateConfigurationError('Cross-host atomic directory creation has not been verified')
    return cfg


def _claim_directory(path, scope):
    """mkdir is the arbiter; stale cached stat/list results are never used."""
    token = uuid.uuid4().hex
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        return None
    # If writing ownership fails, leave the directory reserved: do not guess.
    owner = dict(schema='videoicl-api-concurrency-owner-v1', token=token,
                 scope=scope, pid=os.getpid(), hostname=socket.gethostname(),
                 created_unix=time.time())
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path/'owner.private.json', flags, 0o600), 'w') as stream:
        json.dump(owner, stream)
    return token


def _release_directory(path, token, scope):
    owner_path = path/'owner.private.json'
    try:
        if path.is_symlink() or owner_path.is_symlink():
            raise ValueError('Symlink is not a lease')
        owner = json.loads(owner_path.read_bytes())
        if (owner.get('schema') != 'videoicl-api-concurrency-owner-v1'
                or owner.get('token') != token or owner.get('scope') != scope):
            raise ValueError('Ownership mismatch')
    except (OSError, ValueError, AttributeError) as exc:
        raise GateOwnershipError('Preserving concurrency directory with uncertain ownership') from exc
    owner_path.unlink()
    path.rmdir()


class ConcurrencyLease:
    """One request reservation, held until upstream consumption has finished."""
    def __init__(self, path, token, slot, queue_wait_seconds, scope):
        self._path, self._token = path, token
        self._release_lock = threading.Lock()
        self.slot = slot
        self.queue_wait_seconds = queue_wait_seconds
        self.scope = scope

    def release(self):
        with self._release_lock:
            if self._token is not None:
                _release_directory(self._path, self._token, self.scope)
                self._token = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


class FileConcurrencyGate:
    """Count all 50 atomic slot claims under one atomic admission guard.

    Config cap/reservation changes affect only new admission; existing streams
    retain their lease. Probing uses mkdir rather than stat to avoid treating a
    stale filesystem metadata cache as evidence that a slot is free.
    """
    def __init__(self, config_path, *, poll_seconds=1.0):
        if (type(poll_seconds) not in (int, float) or not math.isfinite(poll_seconds)
                or not 0.01 <= poll_seconds <= 5):
            raise ValueError('Polling interval must be between 0.01 and 5 seconds')
        self.config_path = Path(config_path)
        cfg = validated_config(self.config_path)
        self.scope = cfg['scope']
        self.lock_directory = Path(cfg['lock_directory'])
        self.poll_seconds = float(poll_seconds)
        self.lock_directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _config(self):
        cfg = validated_config(self.config_path)
        if cfg['scope'] != self.scope or Path(cfg['lock_directory']) != self.lock_directory:
            raise GateConfigurationError('Concurrency scope and lock directory cannot change in place')
        return cfg

    def acquire(self):
        started = time.monotonic()
        guard_path = self.lock_directory/'admission.guard'
        while True:
            self._config()
            guard = _claim_directory(guard_path, self.scope)
            if guard is not None:
                candidate = None
                try:
                    cfg = self._config()
                    if cfg['legacy_reserved'] < cfg['limit']:
                        occupied = 0
                        for slot in range(MAX_SLOTS):
                            path = self.lock_directory/f'slot-{slot:02d}.lease'
                            token = _claim_directory(path, self.scope)
                            if token is None:
                                occupied += 1
                            elif candidate is None:
                                candidate = (path, token, slot)
                            else:
                                _release_directory(path, token, self.scope)
                        if candidate is not None and occupied + cfg['legacy_reserved'] < cfg['limit']:
                            path, token, slot = candidate
                            lease = ConcurrencyLease(path, token, slot,
                                                     time.monotonic()-started, self.scope)
                            candidate = None
                            return lease
                finally:
                    try:
                        if candidate is not None:
                            _release_directory(candidate[0], candidate[1], self.scope)
                    finally:
                        _release_directory(guard_path, guard, self.scope)
            time.sleep(self.poll_seconds)
