"""Controller-only recovery policy. No robot actions, inference, or history reconstruction."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import time
import uuid

IDENTITY_FIELDS = ('run_id', 'task_id', 'variant', 'seed', 'suite', 'epoch')
TERMINAL = {'done', 'give_up', 'finished', 'budget_exhausted', 'cancelled'}


def _cli_group_members(pgid):
    """Read live group members with immutable PID/start-time identity; ignore zombies."""
    from .process_lifecycle import ProcessIdentity
    if not Path('/proc').is_dir():
        raise RuntimeError('Precise CLI tool retirement requires Linux /proc')
    result=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():continue
        try:
            text=(path/'stat').read_text();fields=text[text.rindex(')')+2:].split()
            if int(fields[2])==pgid and fields[0]!='Z':
                result.append(ProcessIdentity(int(path.name),int(fields[19])))
        except (FileNotFoundError,ProcessLookupError,PermissionError,ValueError):continue
    return result


def retire_exited_cli_tools(process, *, sleep=time.sleep, evidence_dir=None):
    """Ask precisely owned tools to exit, then wait for accepted callbacks to drain.

    Never KILL a tool after an arbitrary 200ms deadline. The MCP finally block
    releases its program owner after in-flight browser callbacks finish. A
    blocked tool stays observable here rather than being replaced or replayed.
    """
    from .process_lifecycle import alive,descendants,signal_owned,linux_process
    if process.poll() is None:
        raise RuntimeError('Cannot retire tools while a native CLI/API request is alive')
    owned=set(_cli_group_members(process.pid));signalled=set()
    if evidence_dir is not None:
        append_ledger(evidence_dir,'tool_graceful_retirement_started',cli_pid=process.pid,
            tools=[dict(pid=p.pid,start_ticks=p.start_ticks) for p in owned],force_kill=False)
    while True:
        # Capture live descendants before parents exit, including child sessions.
        for owner in tuple(owned):
            if alive(owner):owned.update(descendants(owner))
        active={p for p in owned if alive(p)}
        if not active:break
        # Signal tool roots first. Do not terminate Playwright/browser children
        # while their MCP parent is draining an accepted callback in finally.
        active_pids={p.pid for p in active}
        roots=set()
        for tool in active:
            row=linux_process(tool.pid)
            if row and row['start_ticks']==tool.start_ticks and row['ppid'] not in active_pids:
                roots.add(tool)
        for tool in roots-signalled:
            signal_owned(tool,signal.SIGTERM);signalled.add(tool)
        sleep(.1)
    if evidence_dir is not None:
        append_ledger(evidence_dir,'tool_graceful_retirement_finished',cli_pid=process.pid,
            signalled_tools=[dict(pid=p.pid,start_ticks=p.start_ticks) for p in signalled],force_kill=False)


def append_ledger(out, event, **data):
    with (Path(out) / 'recovery.private.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(time=time.time(), event=event, **data), allow_nan=False) + '\n')


def failure_class(summary, stderr='', environment_error=None):
    """Retry only known transient exits; authentication/configuration take priority."""
    text = (json.dumps(summary.get('errors', [])) + '\n' + stderr).lower()
    if any(value in text for value in ('invalid api key', 'incorrect api key', 'unauthorized',
            'authentication failed', 'invalid authentication', 'permission denied', 'invalid model',
            'model not found', 'model does not exist', 'unknown model', 'invalid configuration',
            'failed to parse config', 'unexpected argument', 'unsupported model', 'session not found',
            'identity mismatch')) or re.search(r'\b(?:400|401|403)\b', text):
        return None
    if environment_error:
        if environment_error.get('type') != 'gui_transport_error':
            return None
        if environment_error.get('error_class') in {'TargetClosedError', 'TimeoutError', 'ConnectionError', 'UnreconciledPendingInput'}:
            return 'gui_transport'
        return None
    if any(value in text for value in ('insufficient_quota', 'quota exceeded', 'usage limit',
            'exceeded your current quota', 'credits exhausted', 'out of credits', 'quota exhausted')):
        return 'quota'
    if re.search(r'\b(?:408|429|500|502|503|504|524|529)\b', text) or any(value in text for value in (
            'too many requests', 'rate limit', 'connection closed', 'connection reset',
            'connection failed', 'error sending request', 'stream disconnected', 'readerror',
            'connecterror', 'remoteprotocolerror', 'timed out', 'temporarily unavailable',
            'network error', 'reconnecting', 'broken pipe', 'http2 error', 'stream error',
            'overloaded_error', 'server_error', 'server overloaded', 'protocolerror', 'writeerror',
            'pooltimeout', 'http/2 stream', 'http2 stream reset')):
        return 'transport'
    return None


def stream_identity_and_completion(output):
    """Earlier reconnect errors do not override an acknowledged final successful turn."""
    sessions = set()
    terminal = None
    for line in Path(output).read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('type') == 'thread.started' and row.get('thread_id'):
            sessions.add(row['thread_id'])
        if row.get('type') in {'turn.completed', 'turn.failed', 'error'}:
            terminal = row['type']
    if len(sessions) > 1:
        raise ValueError('Multiple native session identities in one CLI attempt')
    return terminal == 'turn.completed'


def backoff_seconds(failure, consecutive):
    """Unbounded attempts with bounded frequency, including much longer quota waits."""
    if type(consecutive) is not int or consecutive < 1:
        raise ValueError('A positive consecutive failure count is required')
    base, cap = (300., 1800.) if failure == 'quota' else (5., 300.)
    return min(cap, base * (2 ** min(consecutive - 1, 10)))


def checked_barrier(value, identity, recovery_id=None):
    actual = value.get('identity') if isinstance(value, dict) else None
    if not isinstance(actual, dict) or any(type(actual.get(k)) is not type(identity[k]) or
                                          actual.get(k) != identity[k] for k in IDENTITY_FIELDS):
        raise ValueError('Recovery controller identity mismatch')
    barrier = value.get('owner_barrier', {})
    if (barrier.get('schema') != 'videoicl-owner-action-barrier-v1' or
            type(barrier.get('action_count')) is not int or barrier['action_count'] < 0 or
            value.get('state', {}).get('steps') != barrier['action_count'] or
            value.get('state', {}).get('status') != barrier.get('status')):
        raise ValueError('Missing authoritative owner action barrier')
    if recovery_id is not None and barrier['status'] == 'running' and barrier.get('recovery_id') != recovery_id:
        raise ValueError('Recovery lock is not held by this controller')
    timing = barrier.get('api_timing')
    if timing and timing.get('uncertain') and not timing.get('pending_log_write'):
        # An authenticated owner may explicitly allow reconnection with retained
        # closed unknown records and no time budget. This does not authorize an
        # action; the owner separately requires later success + fresh observe.
        allowed=(barrier.get('unknown_api_policy') == 'resume_closed_unknown'
            and barrier.get('time_limit_enabled') is False
            and timing.get('closed_unknown_recoverable') is True
            and timing.get('ledger_integrity_valid') is True
            and timing.get('transport_quiescent_confirmed') is True
            and timing.get('active') is False and timing.get('active_request_count') == 0)
        if not allowed:
            raise ValueError('Provider timing is unknown; recovery cannot silently reset its budget')
    return barrier


def resolve_session(profile, summary, expected=None):
    """Require native persisted session identity before resume; never create a substitute."""
    sessions = set()
    for path in (Path(profile) / 'sessions').rglob('*.jsonl'):
        with path.open() as stream:
            for _, line in zip(range(20), stream):
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('type') == 'session_meta':
                    value = row.get('payload', {}).get('id')
                    if isinstance(value, str) and value:
                        sessions.add(value)
                    break
    reported = summary.get('session_id')
    if reported is not None and (not isinstance(reported, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', reported)):
        raise ValueError('Invalid native session identity')
    if len(sessions) > 1 or (expected and reported and expected != reported):
        raise ValueError('Native recovery session identity mismatch')
    candidate = expected or reported or next(iter(sessions), None)
    if candidate is not None and sessions != {candidate}:
        raise ValueError('Native session cannot be verified from its persisted profile')
    if candidate is None and summary.get('model_response_observed'):
        raise ValueError('A model response without a verified native session cannot resume')
    return candidate


def reconcile_pending(out, barrier, attempt):
    """Resolve local GUI intent against a locked or sealed owner state, never replay."""
    out = Path(out)
    path = out / 'gui-input-pending.private.json'
    if not path.exists():
        return None
    pending = json.loads(path.read_text())
    logged = []
    log = out / 'computer.jsonl'
    if pending.get('input_id') and log.exists():
        logged = [json.loads(line) for line in log.read_text().splitlines()
                  if json.loads(line).get('input_id') == pending['input_id']]
    if barrier.get('status') == 'faulted' or not (
            barrier.get('recovery_id') or barrier.get('status') in TERMINAL):
        raise ValueError('Pending GUI input lacks a locked or sealed native completion barrier')
    count, before = barrier.get('action_count'), pending.get('before_action_count')
    if type(count) is not int or type(before) is not int or before < 0:
        raise ValueError('Pending GUI input lacks its before_action_count; no replay is safe')
    committed = pending.get('physical_commit') is True
    if committed:
        if count == before + 1:
            disposition = 'native_action_confirmed'
        elif count == before:
            disposition = 'native_action_not_executed'
        else:
            raise ValueError('Pending GUI action count is ambiguous; no replay is safe')
    elif count != before:
        raise ValueError('Unexpected native action while GUI editing was pending')
    elif pending.get('terminal_request'):
        expected = 'give_up' if pending['terminal_request'] == 'giveup' else 'done'
        disposition = 'native_terminal_confirmed' if barrier.get('model_stop') == expected else 'terminal_not_confirmed'
    else:
        disposition = 'gui_edit_discarded_observe_fresh'
    receipt = dict(attempt=attempt, disposition=disposition, pending=pending, owner_barrier=barrier,
                   replayed=False, requires_fresh_observation=True)
    archive = out / 'recovery-evidence'
    archive.mkdir(exist_ok=True, mode=0o700)
    dest = archive / f'pending-{attempt}-{uuid.uuid4().hex}.json'
    with dest.open('x') as stream:
        json.dump(receipt, stream, indent=2)
    # Preserve the original bytes as well as the reconciliation record.
    path.rename(dest.with_suffix('.original.json'))
    event = dict(time=time.time(), type='pending_reconciled', input_id=pending.get('input_id'), **receipt)
    if disposition == 'native_action_confirmed':
        event.update(type='action', interaction='gui_only', physical_commit=True,
                     reconciled_from_owner=True, gui_input=pending.get('gui_input'))
    elif disposition == 'native_terminal_confirmed':
        event.update(type='finish', interaction='gui_only', termination=barrier['model_stop'],
                     reconciled_from_owner=True)
    elif not pending.get('terminal_request'):
        # A failed widget edit still consumed one GUI input, never a robot action.
        event.update(type='action', interaction='gui_only', physical_commit=False,
                     reconciled_from_owner=True, gui_input=pending.get('gui_input'))
    if logged:
        event.update(type='pending_reconciled', already_logged=True, physical_commit=False)
    with (out / 'computer.jsonl').open('a') as stream:
        stream.write(json.dumps(event) + '\n')
    append_ledger(out, 'pending_reconciled', attempt=attempt, disposition=disposition,
                  action_count=count, archive=dest.name)
    return receipt


def archive_error(out, attempt):
    out = Path(out)
    for name in ('environment-error.json', 'gui-preflight-diagnostic.json'):
        source = out / name
        if source.exists():
            dest = out / 'recovery-evidence'
            dest.mkdir(exist_ok=True, mode=0o700)
            source.rename(dest / f'attempt-{attempt}-{name}')


def wait_for_recovery(control, identity, recovery_id, seconds, out, *, clock=time.monotonic, sleep=time.sleep):
    """No API calls during backoff; state reads honor owner drain without killing CLI."""
    end = clock() + seconds
    while True:
        response = control.get('/api/private/state')
        response.raise_for_status()
        barrier = checked_barrier(response.json(), identity, recovery_id)
        if barrier['status'] != 'running':
            append_ledger(out, 'recovery_wait_stopped', status=barrier['status'])
            return False
        remaining = end - clock()
        timing = barrier.get('api_timing') or {}
        if timing.get('active') or timing.get('pending_log_write'):
            sleep(.1)
            continue
        if remaining <= 0:
            return True
        sleep(min(5., remaining))


def recover_control(control, identity, out, *, attempt, failure, consecutive):
    recovery_id = uuid.uuid4().hex
    response = control.post('/api/private/recovery/begin', json=dict(identity=identity, recovery_id=recovery_id))
    response.raise_for_status()
    barrier = checked_barrier(response.json(), identity, recovery_id)
    held = barrier.get('recovery_id') == recovery_id
    should_continue = False
    try:
        reconcile_pending(out, barrier, attempt)
        if barrier['status'] == 'running':
            delay = backoff_seconds(failure, consecutive)
            append_ledger(out, 'backoff_started', attempt=attempt, failure=failure,
                          seconds=delay, recovery_id=recovery_id, action_count=barrier['action_count'])
            should_continue = wait_for_recovery(control, identity, recovery_id, delay, out)
            if should_continue:
                archive_error(out, attempt)
    finally:
        if held:
            response = control.post('/api/private/recovery/end', json=dict(identity=identity, recovery_id=recovery_id))
            response.raise_for_status()
            ended = checked_barrier(response.json(), identity)
            should_continue = should_continue and ended['status'] == 'running'
            append_ledger(out, 'backoff_ended', attempt=attempt, recovery_id=recovery_id)
    return should_continue
