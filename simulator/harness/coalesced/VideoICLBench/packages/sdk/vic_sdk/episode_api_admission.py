"""Serialize episode API admission against terminal sealing on shared storage.

Atomic mkdir is used instead of flock: the deployment's PFS did not provide
cross-pod flock exclusion. Unknown/crash-held guards are never stolen by age.
This module never cancels or forwards a request.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
import uuid

from .api_timing import append_timing_event


class EpisodeApiClosed(RuntimeError):
    code = 'episode_closed'

    def __init__(self):
        super().__init__('This episode has closed API admission after its terminal decision.')


class EpisodeApiAdmission:
    def __init__(self, timing_path, *, poll_seconds=.02):
        self.timing_path = Path(timing_path).resolve()
        self.guard_path = self.timing_path.with_name(self.timing_path.name + '.admission-guard')
        self.closed_path = self.timing_path.with_name(self.timing_path.name + '.admission-closed.json')
        self.poll_seconds = poll_seconds

    @contextmanager
    def guard(self):
        self.guard_path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        while True:
            try:
                self.guard_path.mkdir(mode=0o700)
                break
            except FileExistsError:
                time.sleep(self.poll_seconds)
        owner = self.guard_path / 'owner'
        # Failure before ownership is written leaves the guard fail-closed.
        owner.write_text(token)
        try:
            yield self
        finally:
            if owner.read_text() != token:
                raise RuntimeError('Episode API admission guard ownership changed; preserve it for audit')
            owner.unlink()
            self.guard_path.rmdir()

    def close_locked(self, *, reason, monotonic=None):
        """Caller holds guard and has verified a fresh quiescent API ledger."""
        if self.closed_path.exists():
            return
        stamp = time.monotonic() if monotonic is None else monotonic
        tmp = self.closed_path.with_name(self.closed_path.name + '.' + uuid.uuid4().hex + '.tmp')
        with tmp.open('x') as stream:
            os.chmod(tmp, 0o600)
            json.dump(dict(schema='videoicl-episode-api-admission-v1',closed=True,
                           reason=reason,monotonic=stamp),stream)
            stream.write('\n')
        tmp.replace(self.closed_path)

    def register_request_start(self, request_id, *, monotonic=None):
        with self.guard():
            if self.closed_path.exists():
                raise EpisodeApiClosed()
            append_timing_event(self.timing_path, 'request_start', monotonic=monotonic,
                                request_id=request_id)


def register_api_request_start(timing_path, request_id, *, monotonic=None):
    EpisodeApiAdmission(timing_path).register_request_start(request_id, monotonic=monotonic)
