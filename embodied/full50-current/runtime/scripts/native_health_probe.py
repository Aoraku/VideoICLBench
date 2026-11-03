"""On-demand native API health check, separate from all model evaluations.

``prepare`` writes one E05/A/seed4201 plan without importing Isaac or touching
CUDA. ``run`` starts only that plan, executes one bounded native action, seals
the room, reads immutable private evaluation, and checks owned GPU PID release.
"""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from videoicl_isaaclab.pool_rpc import atomic_json

IDENTITY_KEYS = {'run_id', 'task_id', 'variant', 'seed', 'suite', 'epoch'}
ROOM = 'native-health-e05-a-s4201'


def exact_identity(actual, expected):
    return isinstance(actual, dict) and set(actual) == set(expected) == IDENTITY_KEYS and all(
        type(actual[key]) is type(value) and actual[key] == value for key, value in expected.items())


def read_json(path):
    def invalid(value):raise ValueError('Nonfinite private JSON')
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def prepare(out, *, native_python, bindings, experience, runtime_root=ROOT, robot='franka',
            expected_gpu_uuid=None, deadline_seconds=300, asset_roots=None):
    if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or not 60 <= deadline_seconds <= 300:
        raise ValueError('Native API health deadline must be 60 to 300 seconds')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    identity = dict(run_id='native-health-'+uuid.uuid4().hex, task_id='E05', variant='A', seed=4201,
        suite='native-api-health-not-model-evaluation', epoch=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    case = dict(episode_id=ROOM, task='E05', variant='A', seed=4201,
        bindings=str(Path(bindings).resolve()), robot=robot, identity=identity)
    atomic_json(out/'cases.private.json', [case])
    kit = out/'kit';kit.mkdir(mode=0o700)
    command = [str(Path(native_python).resolve()), str(Path(runtime_root).resolve()/'scripts/serve_realworld_room_pool.py'),
        '--cases', str(out/'cases.private.json'), '--out', str(out/'pool'), '--epoch', identity['epoch'],
        '--suite', identity['suite'], '--barrier-timeout', str(deadline_seconds), '--capture-passes', '64',
        '--experience', str(Path(experience).resolve()), '--defer-stage-creation',
        '--headless', '--enable_cameras', '--device', 'cpu', '--kit_args',
        '--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 '
        '--/plugins/carb.tasking.plugin/threadCount=4 --/plugins/omni.tbb.globalcontrol/maxThreadCount=4 '
        f'--/app/userConfigPath={kit}/user.config.json --/app/cachePath={kit}/cache '
        f'--/app/dataPath={kit}/data --/app/logPath={kit}/logs --/log/file={kit}/kit.log']
    assets=Path(asset_roots).resolve() if asset_roots is not None else Path(native_python).resolve().parent/'asset_roots'
    environment={name:str(assets/name) for name in ('VIC_FULL50_RIGID_ASSETS','VIC_ROBODOJO_ASSETS','VIC_MECHANISM_ASSETS')}
    configuration=dict(native_python=str(Path(native_python).resolve()),bindings=str(Path(bindings).resolve()),
        experience=str(Path(experience).resolve()),runtime_root=str(Path(runtime_root).resolve()),robot=robot,
        expected_gpu_uuid=expected_gpu_uuid,deadline_seconds=deadline_seconds,asset_roots=str(assets))
    plan = dict(schema='videoicl-native-api-health-plan-v1', prepared_only=True, auto_start=False,
        counts_toward_450=False, is_model_evaluation=False, room_id=ROOM, identity=identity, out=str(out),
        deadline_seconds=deadline_seconds, expected_gpu_uuid=expected_gpu_uuid, minimum_free_mib=4096,
        command=command, environment=environment,configuration=configuration,
        action=dict(left='UP', right='STILL', step_mm=7.5, rotation_deg=10.))
    atomic_json(out/'plan.private.json', plan)
    return plan


def gpu_snapshot():
    def query(fields, source):
        result = subprocess.run(['nvidia-smi', source+'='+fields, '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=3, check=True)
        return [[part.strip() for part in line.split(',')] for line in result.stdout.splitlines() if line.strip()]
    gpus = [dict(uuid=row[0], used_mib=int(row[1]), free_mib=int(row[2]))
            for row in query('uuid,memory.used,memory.free', '--query-gpu')]
    contexts = [dict(pid=int(row[0]), gpu_uuid=row[1], used_mib=row[2])
                for row in query('pid,gpu_uuid,used_gpu_memory', '--query-compute-apps')]
    return dict(observed_unix=time.time(), gpus=gpus, contexts=contexts, scope='whole_visible_gpu')


def process_stamp(pid):
    try:
        # comm may contain spaces; fields after ')' start at process state.
        values=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()
        if values[0] == 'Z':return None
        return dict(pid=pid, parent=int(values[1]), start_ticks=int(values[19]))
    except (OSError, ValueError, IndexError):return None


def descendants(pid):
    records = {int(path.name): process_stamp(int(path.name)) for path in Path('/proc').iterdir() if path.name.isdigit()}
    selected={pid};changed=True
    while changed:
        added={p for p,r in records.items() if r is not None and r['parent'] in selected}-selected
        changed=bool(added);selected|=added
    return {p:records[p] for p in selected if records.get(p) is not None}


def owned_alive(records):
    return {pid for pid,stamp in records.items() if (current:=process_stamp(pid)) is not None
            and current['start_ticks']==stamp['start_ticks']}


def cleanup(process, owned):
    if process is None:return []
    owned.update(descendants(process.pid))
    if process.poll() is None:
        # This group was created by this controller with start_new_session.
        try:os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=3)
    for pid in owned_alive(owned):
        try:os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:pass
    until=time.monotonic()+1
    while owned_alive(owned) and time.monotonic()<until:time.sleep(.02)
    for pid in owned_alive(owned):
        try:os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:pass
    return sorted(owned_alive(owned))


def rpc_request(root, room, identity, op, deadline, process, **fields):
    identifier=uuid.uuid4().hex
    request=dict(request_id=identifier,room_id=room,identity=identity,op=op,**fields)
    atomic_json(Path(root)/'requests'/room/(identifier+'.json'), request)
    path=Path(root)/'responses'/room/(identifier+'.json')
    while not path.exists():
        if time.monotonic()>=deadline:raise TimeoutError('Native API health deadline at '+op)
        if process.poll() is not None:raise RuntimeError('Native engine exited before '+op+' response')
        time.sleep(.02)
    value=read_json(path)
    if value.get('request_id')!=identifier or value.get('room_id')!=room or not exact_identity(value.get('identity'),identity):
        raise RuntimeError('Native API health response identity mismatch')
    if value.get('ok') is not True:raise RuntimeError('Native API health RPC failed: '+str(value.get('error')))
    return value['result']


def image_evidence(images, out):
    from PIL import Image, ImageStat
    if not isinstance(images,dict) or set(images)!={'head','left_wrist','right_wrist'}:
        raise ValueError('Three actual native RGB cameras are required')
    out.mkdir(exist_ok=False,mode=0o700)
    result={}
    for name,encoded in images.items():
        raw=base64.b64decode(encoded,validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            image.load();size=list(image.size);mode=image.mode
            deviation=sum(ImageStat.Stat(image.convert('RGB')).stddev)/3
        if mode!='RGB' or size!=[640,480] or deviation<=1:
            raise ValueError('Native RGB content/dimensions rejected for '+name)
        (out/(name+'.jpg')).write_bytes(raw)
        result[name]=dict(size=size,mode=mode,spatial_stddev=deviation,sha256=hashlib.sha256(raw).hexdigest())
    return result


def checked_position(observation, side):
    value=observation['robot_feedback']['arms'][side]['tcp_position']
    if not isinstance(value,list) or len(value)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in value):
        raise ValueError('Finite measured native robot TCP is required')
    return value


def verify_action(before, result, after, ready):
    receipt=result['receipt'];initial_tick=before['shared_tick']
    settings=ready['metadata']['global_signature']['settings']
    dt=settings['global_physics']['dt'];duration=settings['cohort_timing']['action_seconds']
    expected_ticks=round(duration/dt)
    if any(type(receipt.get(key)) is not int for key in ('step_before','step_after','shared_tick_before','shared_tick_after')) or \
            type(initial_tick) is not int or type(after.get('shared_tick')) is not int or \
            receipt.get('step_before')!=0 or receipt.get('step_after')!=1 or \
            receipt.get('shared_tick_before')!=initial_tick or \
            receipt.get('shared_tick_after')!=initial_tick+expected_ticks or \
            after['shared_tick']!=receipt['shared_tick_after'] or \
            abs(receipt['simulation_seconds']-duration)>1e-5:
        raise ValueError('One real native action and its physical clock were not confirmed')
    left=[b-a for a,b in zip(checked_position(before,'left'),checked_position(after,'left'))]
    right=[b-a for a,b in zip(checked_position(before,'right'),checked_position(after,'right'))]
    error=math.sqrt(sum((v-target)**2 for v,target in zip(left,[0.,0.,.0075])))
    if left[2]<=.001 or error>.003 or math.sqrt(sum(v*v for v in right))>.001:
        raise ValueError('Measured UP7.5mm/STILL movement did not satisfy native health bounds')
    return dict(left_tcp_delta_m=left,right_tcp_delta_m=right,tracking_error_m=error,receipt=receipt)


def run(plan):
    if plan.get('schema')!='videoicl-native-api-health-plan-v1' or plan.get('counts_toward_450') is not False:
        raise ValueError('Explicit native health plan required')
    # Reserve 20 seconds for bounded TERM/KILL and GPU-release checks inside
    # the declared total 300-second ceiling.
    out=Path(plan['out']);deadline=time.monotonic()+plan['deadline_seconds']-20;process=None;owned={};before_gpu=None
    report=dict(schema='videoicl-native-api-health-result-v1',health_passed=False,counts_toward_450=False,
        is_model_evaluation=False,identity=plan['identity'],phases=[],started_unix=time.time())
    marker=os.open(out/'started.private.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(marker,'w') as stream:json.dump(dict(controller_pid=os.getpid(),started=report['started_unix']),stream)
    old={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
    def interrupted(sig,frame):raise RuntimeError('Native health controller interrupted by signal '+str(sig))
    for sig in old:signal.signal(sig,interrupted)
    try:
        before_gpu=gpu_snapshot();report['gpu_before']=before_gpu
        expected=plan.get('expected_gpu_uuid')
        visible={row['uuid'] for row in before_gpu['gpus']}
        if expected is not None and visible!={expected}:raise RuntimeError('Native health GPU UUID differs from admission')
        if len(visible)!=1 or before_gpu['gpus'][0]['free_mib']<plan['minimum_free_mib']:
            raise RuntimeError('Native health needs one admitted GPU with sufficient current free memory')
        log=(out/'native.private.log').open('x')
        env=dict(os.environ,**plan['environment'],VIC_SKIP_APP_CLOSE='1')
        command=['timeout','--signal=TERM','--kill-after=5s',str(max(1,int(plan['deadline_seconds']-20))),*plan['command']]
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True);log.close()
        atomic_json(out/'process.private.json',dict(pid=process.pid,process_group=process.pid,command=command))
        rpc=out/'pool/rpc';ready_path=rpc/'ready.json'
        while not ready_path.exists():
            if time.monotonic()>=deadline:raise TimeoutError('Native health startup exceeded total deadline')
            if process.poll() is not None:raise RuntimeError('Native engine exited before ready')
            time.sleep(.05)
        owned.update(descendants(process.pid));ready=read_json(ready_path);room=plan['room_id'];identity=plan['identity']
        if ready.get('pid') not in owned or not exact_identity(ready['rooms'][room].get('identity'),identity):
            raise RuntimeError('Native ready does not belong to this process tree and case')
        report['native_pid']=ready['pid'];report['phases'].append('native_ready')
        before=rpc_request(rpc,room,identity,'observe',deadline,process)
        report['initial_images']=image_evidence(before['images'],out/'initial-images')
        report['phases'].append('native_observe')
        action=rpc_request(rpc,room,identity,'action',deadline,process,action_index=0,action=plan['action'])
        after=rpc_request(rpc,room,identity,'observe',deadline,process)
        report['action']=verify_action(before,action,after,ready)
        report['after_images']=image_evidence(after['images'],out/'after-images')
        report['phases'].append('native_physical_action_verified')
        sealed=rpc_request(rpc,room,identity,'seal',deadline,process,reason='native_api_health_complete')
        terminal=read_json(rpc/'terminal'/(room+'.private.json'))
        if (rpc/'terminal'/(room+'.unscored.json')).exists() or sealed!=terminal or \
                terminal.get('room_id')!=room or not exact_identity(terminal.get('identity'),identity) or \
                terminal['receipt'].get('steps')!=1 or terminal['receipt'].get('terminal_shared_tick')!=after['shared_tick'] or \
                terminal.get('images')!=after['images'] or terminal.get('robot_feedback')!=after['robot_feedback']:
            raise RuntimeError('Native seal is not an exact immutable terminal snapshot')
        native=deepcopy(terminal['receipt']['native'])
        if type(native.get('success')) is not bool or native.get('history_valid') is False or native.get('errors'):
            raise RuntimeError('Native private evaluation has no valid evidence')
        # The last seal stops Kit. This is the same immutable-file evaluation
        # boundary used by NativePoolProxy.evaluate(), not a post-exit RPC.
        atomic_json(out/'evaluation.private.json',native)
        report.update(terminal_tick=after['shared_tick'],native_success=native['success'])
        report['phases']+=['native_seal_verified','immutable_private_evaluation_read']
        process.wait(timeout=max(.01,deadline-time.monotonic()))
        if process.returncode!=0:raise RuntimeError('Native engine did not exit cleanly after final seal')
        monitor=read_json(out/'pool/gpu-monitor.private.json')
        report['gpu_peak_observed_mib']=monitor.get('peak_used_mib')
        report['gpu_peak_scope']=monitor.get('scope')
        report['phases'].append('native_engine_exited')
        report['health_passed']=True
    except BaseException as exc:
        report['error']=dict(kind='infrastructure_error',error_class=type(exc).__name__,message=str(exc),scored=False)
    finally:
        report['owned_processes_remaining']=cleanup(process,owned)
        try:
            report['gpu_after']=gpu_snapshot()
            remaining_gpu={row['pid'] for row in report['gpu_after']['contexts']}&set(owned)
            report['owned_gpu_contexts_remaining']=sorted(remaining_gpu)
            report['gpu_context_released']=not remaining_gpu and not report['owned_processes_remaining']
            if before_gpu is not None and {r['pid'] for r in before_gpu['contexts']}=={r['pid'] for r in report['gpu_after']['contexts']}:
                report['gpu_memory_restored_to_baseline']=abs(before_gpu['gpus'][0]['used_mib']-report['gpu_after']['gpus'][0]['used_mib'])<=128
        except Exception as exc:
            report['gpu_context_released']=False;report['release_check_error']=repr(exc)
        report['health_passed']=bool(report['health_passed'] and report['gpu_context_released'])
        report['ended_unix']=time.time();report['wall_seconds']=report['ended_unix']-report['started_unix']
        atomic_json(out/'result.private.json',report)
        for sig,handler in old.items():signal.signal(sig,handler)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='operation',required=True)
    prep=commands.add_parser('prepare',help='Write plan only; no native process or CUDA')
    for option in ('native-python','bindings','experience','out'):prep.add_argument('--'+option,type=Path,required=True)
    prep.add_argument('--runtime-root',type=Path,default=ROOT);prep.add_argument('--robot',default='franka')
    prep.add_argument('--asset-roots',type=Path)
    prep.add_argument('--expected-gpu-uuid');prep.add_argument('--deadline-seconds',type=float,default=300)
    execute=commands.add_parser('run',help='Execute one previously prepared health plan')
    execute.add_argument('--plan',type=Path,required=True)
    start=commands.add_parser('start',help='Create a fresh attempt from a slot template, then run once')
    start.add_argument('--template',type=Path,required=True);start.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.operation=='prepare':
        plan=prepare(args.out,native_python=args.native_python,bindings=args.bindings,experience=args.experience,
            runtime_root=args.runtime_root,robot=args.robot,expected_gpu_uuid=args.expected_gpu_uuid,
            deadline_seconds=args.deadline_seconds,asset_roots=args.asset_roots)
        print(json.dumps(dict(prepared_only=True,plan=str(Path(plan['out'])/'plan.private.json'),counts_toward_450=False)))
        return 0
    if args.operation=='start':
        template=read_json(args.template)
        if template.get('schema')!='videoicl-native-api-health-plan-v1':raise ValueError('Native health slot template required')
        plan=prepare(args.out,**template['configuration'])
    else:plan=read_json(args.plan)
    report=run(plan);print(json.dumps({key:report[key] for key in ('health_passed','phases','wall_seconds','gpu_context_released')}))
    return 0 if report['health_passed'] else 2


if __name__=='__main__':raise SystemExit(main())
