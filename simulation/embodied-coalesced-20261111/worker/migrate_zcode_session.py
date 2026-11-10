"""One-room original-session GLM image migration. Dry-run unless --apply.

The stopped original CLI is terminated only after its actual supervisor has been
shown to classify that exit as permanent hold, with all API/actions drained.
No episode/bootstrap/start endpoint is used. Never run this on terminal worlds.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import sys
import threading
import time

import run
from adapters import zcode
from transport import make_relay


def need(ok, why):
    if not ok: raise RuntimeError(why)


def read(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def proc(pid, ticks):
    p=Path('/proc')/str(pid)
    stat=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
    need(int(stat[19])==ticks and stat[0]!='Z','process identity changed')
    return p,stat[0],int(stat[1]),p.joinpath('cmdline').read_bytes().rstrip(b'\0').decode().split('\0')


def childs(pid):
    out=set()
    for task in (Path('/proc')/str(pid)/'task').iterdir():
        out.update(map(int,(task/'children').read_text().split()))
    return out


def worker(args,room):
    path=args.campaign/'worker/run.py';v=room/'worker-version.private.json'
    if v.exists():
        r=read(v);path=Path(r['script'])
        need(r['engine']=='zcode' and path.is_relative_to(args.campaign),'wrong worker version')
    p,state,ppid,argv=proc(args.worker_pid,args.worker_ticks)
    need(argv[1:]==[str(path),'--engine','zcode','--room',str(room),'--out',str(room/'cli')],'wrong supervisor argv')
    need(state!='T','original supervisor must drain naturally')
    return p


def session_proven(out,sid):
    ids=set()
    for f in out.glob('attempt-*.jsonl'):
        for l in f.read_bytes().splitlines(keepends=True):
            if not l.endswith(b'\n'):continue
            x=json.loads(l);v=x.get('sessionId')or x.get('session_id')
            if v:ids.add(v)
    need(ids=={sid},'CLI session identity is missing or ambiguous')
    database=out/'profile/home/.zcode/cli/db/db.sqlite'
    need(database.is_file(),'native session database absent')
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    try:
        hit=False
        for (table,) in db.execute("select name from sqlite_master where type='table'"):
            if 'session' not in table.lower() or not table.replace('_','').isalnum():continue
            cols=[r[1]for r in db.execute('pragma table_info("'+table+'")')]
            for col in ('id','sessionId','session_id'):
                if col in cols and db.execute('select 1 from "'+table+'" where "'+col+'"=? limit 1',(sid,)).fetchone():hit=True
        need(hit,'native database does not contain original session')
    finally:db.close()


def no_other_clients(room,allow=()):
    workspace=str(room/'cli/workspace');profile=str(room/'cli/profile');cfg=str(room/'computer-private.json')
    for p in Path('/proc').glob('[0-9]*'):
        if int(p.name) in {*allow,os.getpid()}:continue
        try:
            args=p.joinpath('cmdline').read_bytes().rstrip(b'\0').decode(errors='replace').split('\0')
            if not args:continue
            relevant=cfg in args or profile in args or workspace in args or os.readlink(p/'cwd')==workspace
            need(not relevant,'another room CLI or MCP still alive: '+p.name)
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue


@contextmanager
def checked(args,phase='before'):
    import httpx
    from vic_sdk.embodied_recovery import checked_barrier,failure_class
    from vic_sdk.native_structured_supervisor import provider_drained,unresolved_tool_input
    need(socket.gethostname()==args.host,'wrong slot hostname')
    root=args.campaign.resolve(strict=True);room=root/'pools'/args.pool/'rooms'/args.case/'agent';out=room/'cli'
    need(root==args.campaign and room==room.resolve(strict=True),'invalid canonical campaign or room')
    cases=read(root/'manifest.json')['pools'][args.pool]
    need(len([c for c in cases if c['episode_id']==args.case])==1,'manifest case identity mismatch')
    case=next(c for c in cases if c['episode_id']==args.case)
    cfg=read(room/'computer-private.json');connpath=Path(read(room/'worker-owner.json')['connection'])
    need(connpath.resolve()==room.parent/'connection.private.json','connection path changed')
    conn=read(connpath);identity=conn['identity']
    need(cfg['program_episode_identity']==identity and cfg['control_url']==conn['control_url'] and conn['pool_room_id']==args.case,'world mismatch')
    need(identity['epoch']==root.name+'-'+args.pool and conn['condition']==case['input_condition'],'campaign epoch or condition mismatch')
    need((identity['task_id'],identity['variant'],identity['seed'])==(case['task'],case['variant'],case['seed']),'manifest/native task mismatch')
    need(not(out/'result.json').exists(),'already terminal')
    state=read(room/'native-structured/state.private.json')
    need(state['identity']==identity and not unresolved_tool_input(room),'native transaction unresolved')
    need(not(room/'gui-input-pending.private.json').exists(),'pending physical input')
    lease=None
    lease_path=room/'program/owner/identity.private.json'
    if lease_path.exists():
        need(phase=='before','old MCP lease has not naturally released')
        lease=read(lease_path)
        expected=hashlib.sha256(json.dumps({k:identity[k]for k in ('run_id','task_id','variant','seed','suite','epoch')},sort_keys=True).encode()).hexdigest()
        need(lease['episode_id']==expected,'MCP lease world mismatch')
        p=Path('/proc')/str(lease['pid']);stat=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
        lease['start_ticks']=int(stat[19])
        a=p.joinpath('cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
        need(str(room/'computer-private.json')in a and any('lazy_mcp_gui.py'in x for x in a),'lease is not original MCP')
        ancestor=lease['pid'];seen=set()
        while ancestor not in (args.client_pid,1):
            need(ancestor not in seen,'invalid MCP ancestry');seen.add(ancestor)
            ancestor=int((Path('/proc')/str(ancestor)/'stat').read_text().rsplit(')',1)[1].split()[1])
        need(ancestor==args.client_pid,'MCP lease not owned by original CLI')
    session_proven(out,args.session)
    worker(args,room)
    attempts=sorted(int(f.stem.split('-')[1])for f in out.glob('attempt-*.jsonl'))
    need(attempts==list(range(1,max(attempts)+1)),'attempt sequence missing')
    attempt=max(attempts)
    if phase=='before':
        need(not(out/'vision-migration-claim').exists(),'migration already claimed')
        p,status,ppid,argv=proc(args.client_pid,args.client_ticks)
        need(status=='T' and ppid==args.worker_pid and argv==['zcode-cli'],'original CLI is not the pinned stopped client')
        try:
            env=dict(s.split('=',1)for s in p.joinpath('environ').read_bytes().decode().split('\0')if '='in s)
            need(env.get('ZCODE_SESSION_DB_PATH')==str(out/'profile/home/.zcode/cli/db/db.sqlite'),'CLI profile mismatch')
        except PermissionError:
            # Restricted /proc: unique pinned supervisor child plus that child's
            # own MCP config/lease and native DB identity independently bind room.
            need(lease is not None,'cannot prove room ownership without environ or MCP lease')
        need(childs(args.worker_pid)=={args.client_pid},'ambiguous supervisor children')
        summary=zcode.summarize(out/f'attempt-{attempt}.jsonl',out/'profile',session_id=args.session)
        stderr=(out/f'attempt-{attempt}.stderr').read_text(errors='replace')
        need(summary['is_error'] and not any(e.get('type')!='missing_native_result'for e in summary['errors']),'CLI stream has other failure needing separate review')
        need(not(room/'environment-error.json').exists() and failure_class(summary,stderr,None) is None,'supervisor may auto-resume this exit')
    else:
        need(not childs(args.worker_pid),'original worker has a live child')
        hold=read(out/'hold.json');need(hold.get('reason')=='unclassified_cli_exit' and hold.get('preserve_world') is True,'original supervisor not safely held')
        receipt=read(out/f'attempt-{attempt}-receipt.json');need(receipt['session_id']==args.session and receipt['exit_code']==-signal.SIGKILL,'unexpected old exit receipt')
        no_other_clients(room,allow=(args.worker_pid,))
    with httpx.Client(base_url=conn['control_url'],trust_env=False,timeout=30,headers={'Authorization':'Bearer '+(connpath.parent/conn['admin_token_file']).read_text().strip()})as owner:
        r=owner.get('/api/private/state');r.raise_for_status();value=r.json();barrier=checked_barrier(value,identity)
        need(value['identity']==identity and barrier['status']=='running' and not barrier.get('recovery_id'),'owner not idle running')
        need(Path(barrier['api_timing_log']).resolve()==Path(conn['api_timing_log']).resolve(),'API ledger mismatch')
        need(provider_drained(barrier.get('api_timing')or{}),'upstream not fully drained')
        need(not any(barrier.get(k)for k in ('pending_action','action_in_flight','in_flight','active_action','terminal')),'owner has pending action')
        snapshot=dict(campaign=str(root),pool=args.pool,case=args.case,host=args.host,session=args.session,identity=identity,action_count=barrier['action_count'],attempt=attempt,worker_pid=args.worker_pid,worker_ticks=args.worker_ticks,client_pid=args.client_pid,client_ticks=args.client_ticks,journal_sha256=digest(room/'native-structured/state.private.json'),worker_release=str(Path(run.__file__).resolve().parent),original_mcp_lease=lease)
        yield snapshot,owner,room


def apply(args):
    # No credentials are needed or read for dry-run.
    room=args.campaign/'pools'/args.pool/'rooms'/args.case/'agent'
    out=room/'cli';claim=out/'vision-migration-claim'
    if args.resume_claim:
        before=read(claim/'admitted.json')
        prior=Path('/proc')/str(before['pid'])
        need(not prior.exists() or prior.joinpath('stat').read_text().rsplit(')',1)[1].split()[0]=='Z','prior migration process is still executing')
        need(not(claim/'relay.json').exists() and not(out/f"attempt-{before['attempt']+1}.jsonl").exists(),'continuation already admitted')
        need(all(before[k]==getattr(args,k)for k in ('pool','case','session','host','worker_pid','worker_ticks','client_pid','client_ticks')),'claim identity differs')
        with checked(args,'held')as(now,_,_):
            need(now['identity']==before['identity'] and now['action_count']==before['action_count'] and now['attempt']==before['attempt'],'claimed world changed')
        if not args.apply:print(json.dumps(dict(eligible=True,apply=False,resume_claim=True,**now)));return
        secret=sys.stdin.readline().strip();need(bool(secret),'upstream credential missing on private stdin')
        (claim/'continuation-claim').mkdir(mode=0o700)
        run.save(claim/'continuation-claim/admitted.json',dict(pid=os.getpid(),time=time.time()))
    else:
        with checked(args)as(before,_,_):pass
        if not args.apply:print(json.dumps(dict(eligible=True,apply=False,**before)));return
        secret=sys.stdin.readline().strip();need(bool(secret),'upstream credential missing on private stdin')
        with checked(args)as(now,_,room):
            need(now==before,'owner changed during admission')
            claim.mkdir(mode=0o700)
            run.save(claim/'admitted.json',dict(**now,time=time.time(),pid=os.getpid()))
            # pidfd prevents PID reuse. Only the stopped, drained native CLI exits.
            fd=os.pidfd_open(args.client_pid)
            try:
                p,status,parent,_=proc(args.client_pid,args.client_ticks)
                need(status=='T'and parent==args.worker_pid,'CLI changed at exit boundary')
                signal.pidfd_send_signal(fd,signal.SIGKILL)
            finally:os.close(fd)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                if (out/'hold.json').exists() and not childs(args.worker_pid) and not(room/'program/owner').exists():
                    no_other_clients(room,allow=(args.worker_pid,));break
            except RuntimeError:pass
            time.sleep(.1)
    with checked(args,'held')as(after,owner,room):
        need(after['identity']==before['identity'] and after['action_count']==before['action_count'] and after['attempt']==before['attempt'],'world changed at CLI exit')
        provider=out/'profile/home/.zcode/v2/provider_config.json';conf=read(provider)
        need(conf['config']['defaultModelSelection']==dict(providerId='vic',modelId=run.MODELS['zcode']),'native model selection changed')
        rules=conf['config']['providerConfigRules']['providerRules'];need(len(rules)==1 and rules[0]['providerId']=='vic','unexpected provider config')
        settings=rules[0]['config'];need(settings['api']['type']=='anthropic-messages','wrong native protocol')
        token=settings['access']['apiKey'];oldbase=settings['api']['baseUrl']
        need(oldbase.startswith('http://127.0.0.1:') and len(token)>=32,'original local relay invalid')
        relay=make_relay('zcode',run.MODELS['zcode'],token,secret,out,Path(read(Path(read(room/'worker-owner.json')['connection']))['api_timing_log']))
        secret=None
        threading.Thread(target=relay.serve_forever,daemon=True).start()
        settings['api']['baseUrl']=f'http://127.0.0.1:{relay.server_port}'
        run.save(provider,conf)
        runtime=out/'profile/home/.zcode/cli/config.json';rc=read(runtime)
        mcp=rc['mcp']['servers']['vic'];mcp['args'][0]=str(Path(run.__file__).with_name('lazy_mcp_gui.py'))
        if '--compact-depth'not in mcp['args']:mcp['args'].append('--compact-depth')
        if '--image-ledger'not in mcp['args']:mcp['args']+=['--image-ledger',str(out/'image-ledger.jsonl')]
        run.save(runtime,rc)
        run.save(claim/'relay.json',dict(pid=os.getpid(),old_url=oldbase,new_url=settings['api']['baseUrl'],session=args.session,code_sha256=digest(Path(run.__file__).with_name('zcode_vision.py')),time=time.time()))
        module,binary=run.adapter_runtime('zcode')
        try:
            run.attempt_loop(engine='zcode',room=room,out=out,owner=owner,identity=before['identity'],binary=binary,module=module,prompt='Continue the same task and original world. Observe the current GUI. Never repeat accepted or uncertain actions. '+run.BATCH_INSTRUCTIONS,session=args.session,start_attempt=before['attempt']+1,relay=relay)
            result=read(out/'result.json');need(result.get('terminal')is True and result['identity']==before['identity'] and result['session_id']==args.session,'original terminal missing')
            from sealed_zcode_cleanup import finish as finish_sealed
            finish_sealed(args,room,before['identity'],args.session)
            run.save(claim/'completed.json',dict(session=args.session,time=time.time(),original_worker_released=True))
        except Exception as error:
            run.save(claim/'blocked.json',dict(time=time.time(),error_class=type(error).__name__,preserve_world=True))
            # Preserve the listener even if a new request is still draining.
            # Never exit this companion underneath an uncertain API/action.
            threading.Event().wait()
        finally:
            relay.shutdown();relay.server_close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    for key in ('pool','case','host','session'):p.add_argument('--'+key,required=True)
    for key in ('worker-pid','worker-ticks','client-pid','client-ticks'):p.add_argument('--'+key,type=int,required=True)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--resume-claim',action='store_true',help='Continue a claimed pre-relay migration only after its process exited')
    args=p.parse_args();os.umask(0o077)
    try:apply(args)
    except Exception as e:
        # Failure evidence is deliberately class-only: no credential-bearing configs.
        print(json.dumps(dict(eligible=False,error_class=type(e).__name__,reason=str(e))),flush=True)
        raise SystemExit(1)

if __name__=='__main__':main()
