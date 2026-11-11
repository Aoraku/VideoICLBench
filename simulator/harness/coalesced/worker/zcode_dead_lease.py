"""Reconcile a dead program-GUI lease only under the original native owner lock.

This does not repair unknown actions. Only empty ProgramRuntime submissions,
fully completed native operations, a dead lease PID and exact room identity qualify.
The original lease directory is archived intact; no receipt/score is invented.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import time
import uuid


def need(ok,why):
    if not ok:raise RuntimeError(why)


def proof(room,identity):
    from vic_sdk.native_structured_supervisor import unresolved_tool_input
    room=Path(room).resolve(strict=True);lease=room/'program/owner'
    need(lease.is_dir() and not lease.is_symlink(),'not a plain original lease')
    files=list(lease.iterdir());need(len(files)==1 and files[0].name=='identity.private.json','unexpected lease contents')
    need(files[0].is_file() and not files[0].is_symlink(),'lease identity is not a regular file')
    raw=files[0].read_bytes();value=json.loads(raw)
    need(isinstance(value.get('nonce'),str)and re.fullmatch('[a-f0-9]{32}',value['nonce']),'invalid original lease nonce')
    expected=hashlib.sha256(json.dumps({k:identity[k]for k in ('run_id','task_id','variant','seed','suite','epoch')},sort_keys=True).encode()).hexdigest()
    need(value['episode_id']==expected and type(value['pid'])is int and value['pid']>1,'lease identity mismatch')
    need(not(Path('/proc')/str(value['pid'])).exists(),'lease PID is still present; do not steal')
    need(not list((room/'program').glob('submission-*.private.json')),'program submissions require separate reconciliation')
    need(not(room/'gui-input-pending.private.json').exists() and not unresolved_tool_input(room),'unknown physical input')
    journal=room/'native-structured/state.private.json';state=json.loads(journal.read_bytes())
    need(state['identity']==identity and all(v['state']=='completed'for v in state['operations'].values()),'native operation pending')
    # Confirm no surviving client/MCP can acquire or still act on this room.
    for proc in Path('/proc').glob('[0-9]*'):
        if int(proc.name)==os.getpid():continue
        try:
            argv=proc.joinpath('cmdline').read_bytes().rstrip(b'\0').decode(errors='replace').split('\0')
            need(str(room/'computer-private.json')not in argv and str(room/'cli/workspace')not in argv,'room client/MCP still alive')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    return dict(lease=value,lease_sha256=hashlib.sha256(raw).hexdigest(),journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest(),action_count=max([e.get('step')or 0 for e in state['events']]+[0]))


def reconcile(owner,identity,room,*,expected):
    from vic_sdk.embodied_recovery import checked_barrier
    from vic_sdk.native_structured_supervisor import provider_drained
    need(proof(room,identity)==expected,'lease/journal changed before lock')
    recovery_id=uuid.uuid4().hex
    r=owner.post('/api/private/recovery/begin',json=dict(identity=identity,recovery_id=recovery_id));r.raise_for_status()
    held=False
    try:
        b=checked_barrier(r.json(),identity,recovery_id);held=b.get('recovery_id')==recovery_id
        need(held and b['status']=='running' and b['action_count']==expected['action_count'] and provider_drained(b.get('api_timing')or{}),'owner not safely locked and drained')
        need(not any(b.get(k)for k in ('pending_action','action_in_flight','in_flight','active_action','terminal')),'owner physical input not quiescent')
        need(proof(room,identity)==expected,'lease/journal changed under lock')
        archive=Path(room)/'recovery-evidence';archive.mkdir(exist_ok=True,mode=0o700)
        target=archive/('dead-program-owner-'+recovery_id)
        need(not target.exists(),'archive already exists')
        (Path(room)/'program/owner').rename(target)
        record=dict(time=time.time(),identity=identity,recovery_id=recovery_id,disposition='dead_mcp_lease_archived_no_program_submissions_no_pending_native_actions',original=expected,archived=str(target),replayed=False)
        with (archive/('dead-program-owner-'+recovery_id+'.json')).open('x')as f:json.dump(record,f,indent=2)
        return record
    finally:
        if held:
            r=owner.post('/api/private/recovery/end',json=dict(identity=identity,recovery_id=recovery_id));r.raise_for_status();b=checked_barrier(r.json(),identity)
            need(not b.get('recovery_id'),'owner recovery lock not released')
