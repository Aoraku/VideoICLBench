"""On-demand native pool + per-room GUI + native CLI, with owned cleanup.

No daemon or GPU allocation remains after this command exits. The native pool
and each room use their own immutable evidence directory. This engineering
entry point requires explicit validation-only operation until acceptance.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/sdk'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vic_sdk.process_lifecycle import ProcessIdentity, alive, identity, terminate_tree
from vic_sdk.process_identity import named_python_command
from native_collision_admission import assert_native_collision_admission
from vic_sdk.direct_tools import validate_context_window, validate_model_catalog, SUPPORTED_NATIVE_CLI_VERSIONS
from vic_sdk import native_cli_engines


class Stopped(RuntimeError):
    pass


def start_room_budgets(connection_paths, *, started_monotonic=None):
    """Open every ready room's budget on one same-host monotonic timestamp."""
    started = time.monotonic() if started_monotonic is None else started_monotonic
    def start(path):
        path=Path(path)
        connection=json.loads(path.read_text())
        token_path=Path(connection['admin_token_file'])
        if not token_path.is_absolute():token_path=path.parent/token_path
        body=dict(identity=connection['identity'],started_monotonic=started)
        request=urllib.request.Request(connection['control_url'].rstrip('/')+'/api/private/start',
            data=json.dumps(body).encode(),method='POST',
            headers={'Authorization':'Bearer '+token_path.read_text().strip(),
                     'Content-Type':'application/json'})
        # The controller is local to this GPU pod; never route its admin token
        # or loopback request through a user-configured HTTP proxy.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request,timeout=30) as response:
            value=json.loads(response.read())
        if value.get('budget_started') is not True or value.get('started_monotonic') != started:
            raise ValueError('Room did not acknowledge the shared budget start')
        return dict(identity=connection['identity'],started_monotonic=started)
    with ThreadPoolExecutor(max_workers=len(connection_paths)) as executor:
        return list(executor.map(start,connection_paths))


def request_room_drain(sidecars):
    for case,_,folder,_,_ in sidecars:
        path=folder/'drain-request.private.json'
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:continue
        with os.fdopen(fd,'w') as stream:
            json.dump(dict(requested=True,mode='graceful_drain',room_id=case['episode_id'],requested_unix_s=time.time()),stream)


def wait_for_room_processes(children, *, stop, probe_only, probe_timeout_seconds,
                            drain_requested=lambda: False,on_drain=lambda: None,on_exited=lambda index,code: None,
                            clock=time.monotonic,sleep=time.sleep):
    """Keep model/API work alive through shared-pool waits and graceful stop."""
    deadline=clock()+probe_timeout_seconds if probe_only else None
    draining=False;reported_exits=set()
    while True:
        codes=[child.poll() for child in children]
        for index,code in enumerate(codes):
            if code is not None and index not in reported_exits:
                on_exited(index,code);reported_exits.add(index)
        if all(code is not None for code in codes):return codes
        if stop.is_set() or drain_requested():
            if probe_only:raise Stopped('stop requested')
            if not draining:on_drain();draining=True
        if deadline is not None and clock()>=deadline:
            raise RuntimeError('Pool diagnostic completion deadline exceeded')
        sleep(.2)


def drain_relay(relay):
    if relay is not None:
        if relay.poll() is None:relay.terminate()
        relay.wait()  # SIGTERM closes admission and drains accepted API requests.


def write_room_provider(credentials, folder, engine, route):
    """Bind a private CLI endpoint to exactly one owner's API timing journal."""
    providers = json.loads(Path(credentials).read_text())
    provider = providers[engine]
    base = provider['base_url']
    if not base.startswith('http://127.0.0.1:') or not base.endswith('/v1'):
        raise ValueError('Per-episode API timing requires the local verified relay')
    if not re.fullmatch(r'[a-f0-9]{32}', route['route_id']):
        raise ValueError('Invalid private episode route')
    provider['base_url'] = base[:-3] + '/episodes/' + route['route_id'] + '/v1'
    provider['api_failure_budget_policy'] = 'per_episode_failed_request_and_retry_wait_v1'
    provider['api_timing_log'] = str(Path(route['timing_log']).resolve())
    target = Path(folder) / 'provider.private.json'
    with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(providers,stream)
    return target


def room_agent_command(args, package, folder, condition, credentials):
    command = [args.gui_python,ROOT/'scripts/harbor/run_embodied.py',args.engine,
        '--embodied-task-dir',package,'--embodied-connection',folder/'connection.private.json',
        '--condition',condition,'--max-actions',args.max_actions,'--timeout',args.timeout,
        '--credentials',credentials,'--binary',args.binary,'--model',args.model,
        '--effort',args.effort,'--codex-compact-tokens',args.codex_compact_tokens,'--output-root',folder/'agent','--allow-unvalidated-environment']
    if getattr(args, 'codex_context_window', None) is not None:
        command += ['--codex-context-window', args.codex_context_window]
    for option, name in [('--native-context-window', 'native_context_window'), ('--native-compact-tokens', 'native_compact_tokens')]:
        value = getattr(args, name, None)
        if value is not None:
            command += [option, value]
    if not getattr(args, 'lean_text_projection', True):
        command += ['--no-lean-text-projection']
    if args.embodied_auto_recover:
        command += ['--embodied-auto-recover']
    if args.engine == 'codex':
        command += ['--codex-model-catalog',args.codex_model_catalog.resolve(),
                    '--codex-model-catalog-sha256',args.codex_model_catalog_sha256]
    if args.browser_path:
        command += ['--browser-path',args.browser_path]
    if args.embodied_harness != 'gui':
        command += ['--embodied-harness',args.embodied_harness]
    return command


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-python', type=Path, required=True)
    p.add_argument('--gui-python', type=Path, required=True)
    p.add_argument('--runtime-root', type=Path, required=True)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--task-root', type=Path, default=ROOT / 'tasks/embodied-realworld50')
    p.add_argument('--credentials', type=Path)
    p.add_argument('--api-concurrency-config', type=Path,
                   help='Shared provider-scope request admission; queued time is infrastructure waiting')
    p.add_argument('--probe-only', action='store_true', help='Real GUI/native validation with no model or API')
    p.add_argument('--probe-profile', choices=['basic','e31_rgb_motion_v1','e31_rgbd_motion_v2','sensor_only_gui_v1','inference_motion_v1'], default='basic')
    p.add_argument('--provider-ca-bundle', type=Path,
                   help='Use a temporary loopback relay to the same verified HTTPS provider')
    p.add_argument('--provider-proxy', help='Explicit HTTP(S) egress proxy for the verified provider relay')
    p.add_argument('--provider-proxy-env', choices=['HTTPS_PROXY','HTTP_PROXY','ALL_PROXY'],
                   help='Read private proxy credentials from an existing environment variable')
    p.add_argument('--binary', type=Path)
    p.add_argument('--browser-path', type=Path)
    p.add_argument('--model')
    p.add_argument('--condition', choices=['real','sim','text_rule'], default='text_rule')
    p.add_argument('--engine', choices=native_cli_engines.ENGINES, default='codex')
    p.add_argument('--native-context-window', type=int)
    p.add_argument('--native-compact-tokens', type=int)
    p.add_argument('--embodied-harness', choices=['gui','program_gui'], default='gui',
                   help='Opt-in episode-local GUI programs; default: gui')
    p.add_argument('--effort', default='high')
    p.add_argument('--codex-compact-tokens',type=int,default=32768)
    p.add_argument('--codex-context-window', type=int, help='Explicit native Codex context window; requires compatible pinned catalog')
    p.add_argument('--lean-text-projection', action=argparse.BooleanOptionalAction, default=True, help='Compact JSON output for new program_gui episodes; images and fields unchanged')
    p.add_argument('--codex-model-catalog',type=Path)
    p.add_argument('--codex-model-catalog-sha256')
    p.add_argument('--embodied-auto-recover', action='store_true',
                   help='Resume the same native Codex session after recoverable provider failures')
    p.add_argument('--max-actions', type=int, default=8)
    p.add_argument('--timeout', type=int, default=300)
    p.add_argument('--unknown-api-policy', choices=['retire_unscored','preserve_world','resume_closed_unknown'], default='retire_unscored')
    p.add_argument('--startup-timeout', type=int, default=600)
    p.add_argument('--barrier-timeout', type=int, default=300)
    p.add_argument('--capture-passes', type=int, default=64)
    p.add_argument('--native-kit-args', help='Explicit process-local Kit diagnostic arguments')
    p.add_argument('--experience', type=Path, help='Version-matched native Kit experience')
    p.add_argument('--defer-stage-creation', action='store_true')
    p.add_argument('--epoch', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--allow-unvalidated-environment', action='store_true', required=True)
    args = p.parse_args()
    if args.unknown_api_policy == 'resume_closed_unknown' and (args.timeout != 0 or args.probe_only or not args.embodied_auto_recover or args.engine != 'codex'):
        p.error('Closed unknown recovery requires timeout 0 and an auto-recovering Codex model run')
    if args.embodied_harness == 'program_gui' and args.probe_only:
        p.error('program_gui requires a native model run')
    if args.api_concurrency_config:
        if args.probe_only or not args.provider_ca_bundle:
            p.error('API concurrency admission requires a model run through the verified provider relay')
        from vic_sdk.api_concurrency import validated_config
        try:
            validated_config(args.api_concurrency_config)
        except (ValueError, OSError) as exc:
            p.error(str(exc))
    if args.embodied_auto_recover and (args.probe_only or args.engine != 'codex'):
        p.error('Automatic session recovery requires a Codex model run')
    if args.embodied_auto_recover and not args.provider_ca_bundle:
        p.error('Automatic recovery requires the verified per-episode API timing relay')
    if args.codex_compact_tokens <= 0: p.error('codex-compact-tokens must be positive')
    if not args.probe_only and not all((args.credentials,args.binary,args.model)):
        p.error('Model execution requires explicit --credentials, --binary and --model')
    if not args.probe_only and args.engine in native_cli_engines.EXTRA_ENGINES:
        # Validate local installation and protocol before allocating a world.
        from vic_sdk.native_agent import clean_env
        try:
            providers = json.loads(args.credentials.read_text())
            provider = providers[args.engine]
            native_cli_engines.preflight(args.engine, args.model, provider,
                native_cli_engines.options_from_args(args, provider), binary=args.binary,
                server={'command': str(args.gui_python), 'args': []}, env=clean_env())
        except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
            p.error('Native CLI preflight failed (' + type(error).__name__ + '); no world created')
    if not args.probe_only and args.engine == 'codex':
        if args.codex_model_catalog is None:
            p.error('Codex execution requires a pinned model catalog before native startup')
        try:
            validate_model_catalog(args.codex_model_catalog,args.codex_model_catalog_sha256,args.model)
            validate_context_window(args.codex_model_catalog,args.codex_model_catalog_sha256,args.model,
                args.codex_context_window,args.codex_compact_tokens)
            version=subprocess.check_output([str(args.binary),'--version'],text=True,timeout=15).strip()
            if version not in SUPPORTED_NATIVE_CLI_VERSIONS:
                raise ValueError('Native CLI version has not passed blocking GUI tool validation')
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            p.error(str(exc))
    if args.probe_only and (args.provider_ca_bundle or args.provider_proxy or args.provider_proxy_env):
        p.error('A no-model probe must not create a provider relay')
    if args.provider_proxy and args.provider_proxy_env:
        p.error('Use one explicit proxy source')
    if (args.provider_proxy or args.provider_proxy_env) and not args.provider_ca_bundle:
        p.error('Provider proxy requires --provider-ca-bundle')
    if args.provider_ca_bundle and args.engine!='codex':
        p.error('The current verified TLS relay implements the Codex Responses transport')
    if sys.platform != 'linux':
        p.error('On-demand process ownership uses Linux /proc; execute on the RTX host')
    # Adopt a native CLI's orphaned MCP/browser descendants, so shutdown still
    # owns them after an unexpected intermediate process exit.
    if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0) != 0:
        raise OSError(ctypes.get_errno(),'Could not enable child subreaper')
    cases = json.loads(args.cases.read_text())
    cases = cases['cases'] if isinstance(cases, dict) else cases
    if not isinstance(cases, list) or not 1 <= len(cases) <= 15:
        p.error('Supply one to fifteen explicitly assigned room cases')
    rooms = [case.get('episode_id') for case in cases]
    if not all(isinstance(r, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', r)
               for r in rooms) or len(set(rooms)) != len(rooms):
        p.error('Each assigned case requires a unique episode_id')
    for case in cases:
        if (case.get('task') not in {f'E{i:02d}' for i in range(1,51)}
                or case.get('variant') not in {'A','B','C'}
                or case.get('input_condition',args.condition) not in {'real','sim','text_rule'}):
            p.error('Every case requires a valid task, variant and input condition')
    if args.timeout < 0 or (args.probe_only and args.timeout == 0) or any(x <= 0 for x in [args.startup_timeout,args.max_actions,args.barrier_timeout,args.capture_passes]):
        p.error('Positive explicit budgets required')
    out = args.out.resolve()
    # A card controller may request drain before this child finishes startup.
    if not (out.is_dir() and {p.name for p in out.iterdir()}=={'drain-request.private.json'}):
        out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out / 'rooms').mkdir(mode=0o700)
    api_routes = {}
    if args.embodied_auto_recover:
        (out / 'api-timing').mkdir(mode=0o700)
        api_routes = {room: dict(route_id=uuid.uuid4().hex,
            timing_log=str(out / 'api-timing' / (room + '.private.jsonl'))) for room in rooms}
    owned, streams = [], []
    models=[];sidecars=[];relay=None
    stop = threading.Event()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, lambda *_: stop.set())
    state = dict(schema='videoicl-on-demand-pool-v1', owner=asdict(identity(os.getpid())),
        started_unix=time.time(), status='starting', validation_only=True,
        scientific_evaluation=False, assigned_rooms=rooms, children=[], results=[])

    def save():
        temporary = out / 'lifecycle.tmp'
        temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        temporary.replace(out / 'lifecycle.private.json')

    def launch(name, command, *, extra_env=None):
        log = (out / (name+'.log')).open('w')
        streams.append(log)
        command = named_python_command(command, out/'process-identities', name)
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True,
                                 env=dict(os.environ,**extra_env) if extra_env else None)
        owner = identity(child.pid)
        if owner is None:
            child.wait()
            raise RuntimeError('Child exited before process ownership was recorded: '+name)
        owned.append((child,owner))
        state['children'].append(dict(name=name,**asdict(owner)))
        save()
        return child

    def drain_requested(): return (out/'drain-request.private.json').exists()
    def drain_rooms():
        state['status']='draining';state['drain_requested']=True;save()
        request_room_drain(sidecars)

    def wait_ready(path, process, deadline):
        while not path.is_file():
            if stop.is_set() or drain_requested():
                raise Stopped('stop requested')
            if process.poll() is not None:
                raise RuntimeError('Environment exited before ready: '+str(path))
            if time.monotonic() >= deadline:
                raise RuntimeError('Environment startup deadline exceeded')
            time.sleep(.1)

    native_response_timeout = args.barrier_timeout + max(120.,len(cases)*120.*args.capture_passes/64.)
    code = 1
    try:
        if stop.is_set() or drain_requested():raise Stopped('stop requested before native startup')
        native_command = [args.native_python,
            args.runtime_root / 'scripts/serve_realworld_room_pool.py',
            '--cases',args.cases.resolve(),'--out',out/'native','--epoch',args.epoch,
            '--barrier-timeout',args.barrier_timeout,'--barrier-policy',
            'fail_after_timeout' if args.probe_only else 'wait','--capture-passes',args.capture_passes,
            '--headless','--enable_cameras','--device','cpu']
        if args.experience:
            native_command += ['--experience',args.experience]
        if args.native_kit_args:
            native_command += ['--kit_args',args.native_kit_args]
        if args.defer_stage_creation:
            native_command += ['--defer-stage-creation']
        native = launch('native', native_command)
        rpc = out / 'native/rpc'
        wait_ready(rpc/'ready.json',native,time.monotonic()+max(args.startup_timeout,native_response_timeout+120))
        assert_native_collision_admission(out/'native.log')
        state['status'] = 'starting_gui'
        save()
        sidecars = []
        for case in cases:
            room = case['episode_id']
            package = args.task_root / f"embodied-{case['task'].lower()}-{case['variant'].lower()}"
            folder = out / 'rooms' / room
            condition = case.get('input_condition',args.condition)
            room_command = [args.gui_python,ROOT/'scripts/harbor/serve_embodied_pool_room.py',
                '--task-dir',package,'--rpc-root',rpc,'--room-id',room,'--condition',condition,
                '--max-actions',args.max_actions,'--timeout',args.timeout,
                '--unknown-api-policy',args.unknown_api_policy,
                '--out',folder,'--allow-unvalidated-environment','--defer-budget-start']
            if args.embodied_auto_recover:
                room_command += ['--embodied-auto-recover']
            if room in api_routes:
                room_command += ['--api-timing-log',api_routes[room]['timing_log']]
            child = launch('gui-'+room,room_command)
            sidecars.append((case,package,folder,condition,child))
        gui_ready_deadline=time.monotonic()+native_response_timeout+120
        for _,_,folder,_,child in sidecars:
            wait_ready(folder/'connection.private.json',child,gui_ready_deadline)
        # Waiting model transports intentionally publish None. Warmup remains
        # bounded by the finite diagnostic allowance before any model launches.
        for _,_,folder,_,_ in sidecars:
            supplied=json.loads((folder/'connection.private.json').read_text()).get('native_response_timeout_seconds')
            if supplied is not None:
                native_response_timeout=max(native_response_timeout,float(supplied))
        credentials = args.credentials
        if args.provider_ca_bundle:
            providers = json.loads(credentials.read_text())
            provider = providers[args.engine]
            relay_folder = out/'provider-relay'
            relay_command=[args.gui_python,'-m','vic_sdk.tls_relay',
                '--upstream',provider['base_url'],'--ca-bundle',args.provider_ca_bundle,
                '--out',relay_folder,'--timeout',args.timeout or 300]
            if args.api_concurrency_config:
                relay_command += ['--concurrency-config', str(args.api_concurrency_config)]
            if api_routes:
                routes_file = out / 'api-timing-routes.private.json'
                with os.fdopen(os.open(routes_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
                    json.dump({r['route_id']:r['timing_log'] for r in api_routes.values()},stream)
                relay_command += ['--episode-timing-routes',routes_file]
            if args.provider_proxy: relay_command += ['--proxy',args.provider_proxy]
            if args.provider_proxy_env: relay_command += ['--proxy-env',args.provider_proxy_env]
            relay = launch('provider-relay',relay_command,
                extra_env={'PYTHONPATH':str(ROOT/'packages/sdk')})
            wait_ready(relay_folder/'ready.private.json',relay,time.monotonic()+30)
            relay_ready = json.loads((relay_folder/'ready.private.json').read_text())
            provider.update(base_url=relay_ready['base_url'],native_auth=False,
                service=provider.get('service','existing_sub2api'),
                transport_adapter='strict_tls_loopback_relay_v1')
            credentials = out/'provider.private.json'
            descriptor = os.open(credentials,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w') as stream:
                json.dump(providers,stream)
        state['status'] = 'starting_room_budgets'
        save()
        state['room_budget_starts'] = (start_room_budgets(
            [folder/'connection.private.json' for _,_,folder,_,_ in sidecars]) if args.probe_only
            else 'deferred_to_native_cli_admission')
        state['status'] = 'gui_probe_running' if args.probe_only else 'model_running'
        state['probe_only'] = args.probe_only
        save()
        models = []
        for case,package,folder,condition,_ in sidecars:
            if stop.is_set() or drain_requested():
                if args.probe_only:raise Stopped('stop requested before room execution')
                drain_rooms();break
            if args.probe_only:
                command=[args.gui_python,ROOT/'scripts/harbor/probe_embodied_gui.py',
                    '--connection',folder/'connection.private.json','--task-dir',package,'--out',folder/'probe',
                    '--timeout',args.timeout,'--profile',args.probe_profile]
                if args.browser_path: command+=['--browser-path',args.browser_path]
                models.append(launch('probe-'+case['episode_id'],command))
                continue
            room_credentials = credentials
            if case['episode_id'] in api_routes:
                route = api_routes[case['episode_id']]
                room_credentials = write_room_provider(credentials,folder,args.engine,route)
            command = room_agent_command(args, package, folder, condition, room_credentials)
            models.append(launch('model-'+case['episode_id'],command))
        diagnostic_limit=args.timeout+2*native_response_timeout+180 if args.probe_only else None
        state['model_completion_timeout_seconds']=None if not args.probe_only else diagnostic_limit
        state['completion_wait_policy']='effective_episode_budget_or_explicit_stop' if not args.probe_only else 'bounded_probe'
        save()
        wait_for_room_processes(models,stop=stop,probe_only=args.probe_only,
            probe_timeout_seconds=diagnostic_limit,drain_requested=drain_requested,on_drain=drain_rooms,
            on_exited=(lambda index,code:request_room_drain([sidecars[index]]))
                if not args.probe_only else (lambda index,code:None))
        for index,(case,_,folder,condition,_) in enumerate(sidecars):
            if index>=len(models):
                state['results'].append(dict(room_id=case['episode_id'],status='cancelled_before_model_launch',scored=False))
                continue
            if args.probe_only:
                path=folder/'probe/probe-result.json'
                report=json.loads(path.read_text()) if path.is_file() else {}
                connection=json.loads((folder/'connection.private.json').read_text())
                probe_passed=(models[index].returncode==0 and report.get('status')=='passed'
                    and report.get('identity')==connection['identity']
                    and report.get('condition')==condition
                    and report.get('model_requests')==0
                    and report.get('probe_profile')==args.probe_profile
                    and report.get('physical_commits')==(3 if args.probe_profile in {'e31_rgb_motion_v1','e31_rgbd_motion_v2','inference_motion_v1'} else 1)
                    and report.get('validation_only') is True
                    and report.get('scientific_evaluation') is False)
                state['results'].append(dict(room_id=case['episode_id'],condition=condition,
                    probe_passed=probe_passed,process_exit_code=models[index].returncode,model_requests=0,
                    gui_inputs=report.get('gui_inputs'),physical_actions=report.get('physical_commits'),
                    result_path=str(path),error_type=report.get('error_type')))
                continue
            reports = list((folder/'agent').glob('*/result.json'))
            if len(reports)!=1:
                state['results'].append(dict(room_id=case['episode_id'],status='missing_result'))
                continue
            report = json.loads(reports[0].read_text())
            state['results'].append(dict(room_id=case['episode_id'],condition=condition,
                outcome=report.get('outcome'),scored=report.get('scored'),
                benchmark_completed=(report.get('scored') is True and
                    report.get('benchmark_completed', report.get('outcome') in {'success', 'fail'}) is True),
                evaluation_scope=report.get('evaluation_scope'),
                gui_inputs=report.get('gui_inputs'),physical_actions=report.get('physical_actions_confirmed'),
                model_session_id=report.get('session_id'),result_path=str(reports[0])))
        success_key='probe_passed' if args.probe_only else 'benchmark_completed'
        code = 0 if len(state['results'])==len(cases) and all(r.get(success_key) is True for r in state['results']) else 1
        state['status'] = 'stopped' if state.get('drain_requested') else ('completed' if code==0 else 'incomplete')
    except Stopped:
        state['status'] = 'stopped'
        code = 130
    except Exception as exc:
        state['status'] = 'infrastructure_error'
        state['error'] = dict(type=type(exc).__name__,message=str(exc))
    finally:
        if not args.probe_only:
            if any(model.poll() is None for model in models):
                drain_rooms()
                for model in models:model.wait()
            drain_relay(relay)
        # API owners and the relay have finished before residual cleanup.
        # Signal all descendants together. Cleanup time does not multiply by
        # the number of rooms, and CLI-created process groups are included.
        state['cleanup'] = terminate_tree(identity(os.getpid()),grace_seconds=5.,include_owner=False)
        for child,owner in reversed(owned):
            try:
                child.wait(timeout=2.)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
        for stream in streams:
            stream.close()
        state['finished_unix'] = time.time()
        remaining = [r for r in state['cleanup'] if alive(ProcessIdentity(**r))]
        state['remaining_owned_processes'] = remaining
        state['cleanup_confirmed'] = not remaining
        if remaining:
            state['status'] = 'cleanup_error'
            code = 1
        elif state.get('drain_requested'):state['status']='stopped'
        save()
    print(json.dumps(dict(artifacts=str(out),status=state['status'],results=state['results'])))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
