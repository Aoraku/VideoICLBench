"""Offline, fail-closed cleanup after the native owner has sealed and closed.

Never query or reopen the closed owner. Only the exact held worker/bootstrap are
released; the original pool cleans its renderer and native processes itself.
"""
import hashlib,json,os,signal,time
from pathlib import Path


def need(ok,msg):
    if not ok:raise RuntimeError(msg)

def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):
    raw=Path(p).read_bytes();need(raw.endswith(b'\n'),'incomplete evidence line')
    return [json.loads(v)for v in raw.splitlines()if v.strip()]


def evidence(room,identity,session):
    from vic_sdk.api_timing import ApiTimingLedger
    from vic_sdk.native_structured_supervisor import provider_drained
    room=Path(room);out=room/'cli';connection=read(room.parent/'connection.private.json')
    need(connection['identity']==identity,'connection identity mismatch')
    result=read(out/'result.json');ev=result['evaluation'];snap=ev['terminal_snapshot']
    need(result.get('terminal')is True and result.get('scored')is True and result.get('benchmark_completed')is True,'unsealed result')
    need(result['identity']==identity and result['session_id']==session,'result/session mismatch')
    need(all(ev.get(k)==v for k,v in identity.items()),'evaluation identity mismatch')
    need(snap.get('sampling')=='sealed_runtime_final_native_check'and snap['status']in('done','give_up','max_actions','budget_exhausted'),'missing native terminal')
    binary_only = (ev.get('task_score_100') is None and ev.get('task_score') is None
        and ev.get('scoring_protocol') == 'videoicl-native-terminal-success-v1'
        and ev.get('score_definition') == 'terminal_native_success'
        and ev.get('native_success') is False and ev.get('success') is False
        and all(ev.get(k) == 0 for k in ('score','success_score','terminal_success_100'))
        and ev.get('progress_score_available') is False
        and ev.get('progress_unavailable_reason') == 'verified_native_task_ladder_not_implemented')
    need((ev.get('task_score_100')is not None or binary_only) and provider_drained(snap.get('api_timing')or{}),'unscored or undrained terminal')
    envpath=room.parent/'environment/environment.private.jsonl';events=rows(envpath)
    need(sum(e.get('event')=='sealed'for e in events)==1,'not uniquely sealed')
    starts=sum(e.get('event')=='action_started'for e in events);ends=sum(e.get('event')=='action_completed'for e in events)
    need(starts==ends==snap['action_count']==result['physical_actions_confirmed'],'physical actions incomplete')
    timing=Path(connection['api_timing_log']);need(timing.resolve()==(room.parent/'api-timing.jsonl').resolve(),'unexpected timing file')
    timings=rows(timing);begun=[x['request_id']for x in timings if x.get('event')=='request_start'];ended=[x['request_id']for x in timings if x.get('event')=='request_end']
    need(len(begun)==len(set(begun))and len(ended)==len(set(ended))and set(begun)==set(ended),'API incomplete or duplicate IDs')
    api=ApiTimingLedger(timing).snapshot()
    need(provider_drained(api)and not api.get('uncertain')and api.get('unknown_outcome_count')==0,'API not completely drained')
    journal=room/'native-structured/state.private.json';state=read(journal)
    need(state['identity']==identity and all(v['state']=='completed'for v in state['operations'].values()),'unresolved native operation')
    need(not(room/'gui-input-pending.private.json').exists()and not list((room/'program').glob('submission-*.private.json')),'pending public input')
    lease=room/'program/owner'
    if lease.exists():
        need(lease.is_dir()and not lease.is_symlink()and {p.name for p in lease.iterdir()}=={'identity.private.json'},'unexpected residual lease')
        value=read(lease/'identity.private.json')
        expected=hashlib.sha256(json.dumps({k:identity[k]for k in('run_id','task_id','variant','seed','suite','epoch')},sort_keys=True).encode()).hexdigest()
        need(value['episode_id']==expected and type(value['pid'])is int and value['pid']>1 and not(Path('/proc')/str(value['pid'])).exists(),'live or foreign residual lease')
    return dict(session=session,identity=identity,result_sha256=sha(out/'result.json'),environment_sha256=sha(envpath),timing_sha256=sha(timing),journal_sha256=sha(journal),action_count=ends,api_request_count=api['request_count'],task_score_100=ev.get('task_score_100'),native_binary_score=ev.get('score'),task_score_unavailable_reason=ev.get('progress_unavailable_reason') if binary_only else None)


def process(pid,ticks):
    p=Path('/proc')/str(pid);s=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
    need(int(s[19])==ticks and s[0]=='S','PID reused or target not sleeping')
    children=sorted({int(n)for t in p.joinpath('task').iterdir()for n in t.joinpath('children').read_text().split()})
    return dict(pid=pid,ticks=ticks,ppid=int(s[1]),argv=p.joinpath('cmdline').read_bytes().rstrip(b'\0').decode().split('\0'),children=children)


def finish(args,room,identity,session,relay=None):
    from migrate_zcode_session import worker,no_other_clients
    room=Path(room);out=room/'cli';pool=room.parents[2]
    # MCP may take a moment to leave after the CLI has completed.
    deadline=time.monotonic()+5
    while True:
        try:no_other_clients(room,allow=(args.worker_pid,));break
        except RuntimeError:
            need(time.monotonic()<deadline,'live room client after terminal');time.sleep(.2)
    proof=evidence(room,identity,session)
    worker(args,room);wp=process(args.worker_pid,args.worker_ticks);need(not wp['children'],'old worker has children')
    lifecycle=read(pool/'lifecycle.private.json');owner=lifecycle['owner'];op=process(owner['pid'],owner['start_ticks'])
    boot=next(c for c in lifecycle['children']if c['name']=='model-'+room.parent.name)
    bp=process(boot['pid'],boot['start_ticks'])
    attr=read(pool/'process-identities'/f"process-{boot['pid']}-{boot['start_ticks']}.private.json")
    av=attr['original_argv']
    need(attr['ppid']==owner['pid']and attr['role']=='model-'+room.parent.name and av[1]==str(args.campaign/'bootstrap_room.py')and av[av.index('--folder')+1]==str(room.parent),'bootstrap attribution mismatch')
    need(wp['ppid']==boot['pid']and bp['ppid']==owner['pid']and bp['argv']==['robodojo-embodiedevo']and bp['children']==[args.worker_pid],'wrong worker/bootstrap parent chain')
    need(read(out/'hold.json').get('preserve_world')is True,'original worker not held')
    claim=out/'sealed-holder-release';claim.mkdir(mode=0o700)
    def save(name,data):
        with(claim/name).open('x')as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
    save('admitted.json',dict(proof=proof,worker=wp,bootstrap=bp,pool_owner=op,pid=os.getpid(),time=time.time()))
    need(evidence(room,identity,session)==proof,'terminal evidence changed')
    if relay is not None:relay.shutdown();relay.server_close()
    fd=os.pidfd_open(args.worker_pid)
    try:
        worker(args,room);need(process(args.worker_pid,args.worker_ticks)==wp,'worker changed before release')
        need(evidence(room,identity,session)==proof,'terminal changed before worker release')
        save('worker-released.json',dict(pid=args.worker_pid,ticks=args.worker_ticks,session=session,signal='SIGTERM',time=time.time()))
        signal.pidfd_send_signal(fd,signal.SIGTERM)
    finally:os.close(fd)
    deadline=time.monotonic()+15
    while True:
        p=Path('/proc')/str(boot['pid'])
        if not p.exists():break
        st=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
        need(int(st[19])==boot['start_ticks'],'bootstrap PID reused')
        if st[0]=='Z':break
        now=process(boot['pid'],boot['start_ticks'])
        log=(pool/('model-'+room.parent.name+'.log')).read_text(errors='replace')
        if not now['children']and 'Room held: RuntimeError No verified terminal result from worker'in log:
            need(now['ppid']==owner['pid']and now['argv']==['robodojo-embodiedevo'],'bootstrap changed')
            need(evidence(room,identity,session)==proof,'terminal changed before bootstrap release')
            fd=os.pidfd_open(boot['pid'])
            try:
                need(process(boot['pid'],boot['start_ticks'])==now,'bootstrap changed during release')
                save('bootstrap-released.json',dict(pid=boot['pid'],ticks=boot['start_ticks'],session=session,signal='SIGTERM',time=time.time()))
                signal.pidfd_send_signal(fd,signal.SIGTERM)
            finally:os.close(fd)
            break
        need(time.monotonic()<deadline,'bootstrap did not reach expected closed-result hold');time.sleep(.2)
    save('completed.json',dict(session=session,time=time.time(),original_holders_released=True,result_sha256=proof['result_sha256']))
    return proof
