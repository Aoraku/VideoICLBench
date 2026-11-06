#!/usr/bin/env python3
"""Per-card on-demand start/status/stop for the exact real/text 300 panel.

Run on the explicitly bound GPU pod. No SSH, idle worker, provider defaults,
GPU reservation at prepare time, or reuse of the old E05-only health controller.
"""
from __future__ import annotations
import argparse
import ctypes
from dataclasses import asdict
import fcntl
import json
import importlib.util
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('videoicl_owned_lifecycle', ROOT / 'packages/sdk/vic_sdk/process_lifecycle.py')
_lifecycle = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _lifecycle
_spec.loader.exec_module(_lifecycle)
ProcessIdentity, alive, identity, terminate_tree = (_lifecycle.ProcessIdentity, _lifecycle.alive, _lifecycle.identity, _lifecycle.terminate_tree)
_catalog_spec = importlib.util.spec_from_file_location('videoicl_direct_tools', ROOT / 'packages/sdk/vic_sdk/direct_tools.py')
_catalog = importlib.util.module_from_spec(_catalog_spec)
_catalog_spec.loader.exec_module(_catalog)
validate_model_catalog = _catalog.validate_model_catalog
_admission_spec = importlib.util.spec_from_file_location('videoicl_api_admission_config', ROOT / 'packages/sdk/vic_sdk/api_concurrency.py')
_admission = importlib.util.module_from_spec(_admission_spec)
sys.modules[_admission_spec.name] = _admission
_admission_spec.loader.exec_module(_admission)
validate_api_concurrency_config = _admission.validated_config
from preflight_embodied300 import file_sha, preflight, validate_panel


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with tmp.open('x') as stream:
        os.chmod(tmp, 0o600); json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
    tmp.replace(path)


def load_deployment(path):
    path = Path(path).resolve(); cfg = json.loads(path.read_text())
    if cfg.get('schema') not in ('videoicl-real-text300-deployment-v1', 'videoicl-frozen-panel-deployment-v1'):
        raise ValueError('Versioned 300 deployment required')
    for key in ('repo_root', 'task_root', 'runtime_root', 'native_python', 'gui_python', 'audit_root', 'state_root'):
        if not isinstance(cfg.get(key), str) or not Path(cfg[key]).is_absolute() or '${' in cfg[key]:
            raise ValueError('Explicit absolute deployment path required: ' + key)
    if not Path(cfg['state_root']).resolve().is_relative_to(Path(cfg['audit_root']).resolve()):
        raise ValueError('State directory must stay inside the isolated audit root')
    plan_path = Path(cfg['plan_path'])
    if not plan_path.is_absolute(): plan_path = path.parent / plan_path
    if file_sha(plan_path) != cfg.get('plan_sha256'):
        raise ValueError('Plan bytes differ from the deployment lock')
    plan = json.loads(plan_path.read_text())
    if 'panel_contract' in cfg:
        from panel_contract import validate_deployment_contract
        validate_deployment_contract(cfg, plan)
    elif 'panel_contract' in plan or cfg['schema'] != 'videoicl-real-text300-deployment-v1':
        raise ValueError('Extension plan requires an explicit deployment panel contract')
    validate_panel(plan)
    if plan['campaign_id'] != cfg.get('campaign_id'):
        raise ValueError('Campaign ID mismatch')
    validate_model_attempt_exemptions(cfg)
    return cfg, plan


def card_binding(cfg, logical_gpu):
    bindings = cfg.get('bindings', [])
    if len({b.get('logical_gpu_index') for b in bindings}) != len(bindings) or len({b.get('gpu_uuid') for b in bindings}) != len(bindings):
        raise ValueError('Duplicate logical card or physical GPU binding')
    matches = [b for b in bindings if b.get('logical_gpu_index') == logical_gpu]
    if len(matches) != 1:
        raise ValueError('No explicit physical binding for this logical card; fresh inventory required')
    b = matches[0]
    if not re.fullmatch(r'GPU-[A-Za-z0-9-]+', b.get('gpu_uuid', '')) or not b.get('hostname'):
        raise ValueError('Explicit GPU UUID and hostname required')
    return b


def state_folder(cfg, logical_gpu):
    return Path(cfg['state_root']) / f'card-{logical_gpu:02d}'


def process_live(record):
    return bool(record and record.get('hostname') == socket.gethostname()
        and record.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        and alive(ProcessIdentity(record['pid'], record['start_ticks'])))


def status(cfg, logical_gpu):
    folder = state_folder(cfg, logical_gpu)
    record = json.loads((folder / 'launch.private.json').read_text()) if (folder / 'launch.private.json').exists() else None
    active = (process_live(record) if sys.platform == 'linux' and record.get('hostname') == socket.gethostname() else None) if record else False
    result = dict(campaign_id=cfg['campaign_id'], logical_gpu_index=logical_gpu,
        active=active, idle_worker=False, allocation_reserved=False,
        native_live_rooms=None if record else 0, model_requests=None if record else 0)
    if record:
        result['last_attempt'] = record['attempt_id']
        report = Path(record['attempt_dir']) / 'lifecycle.private.json'
        if report.exists():
            result['lifecycle'] = json.loads(report.read_text())
            if active is False and result['lifecycle'].get('cleanup_confirmed') is True:
                result['native_live_rooms'] = 0
            if result['lifecycle'].get('run_mode') == 'probe':
                result['model_requests'] = 0
        drain=Path(record['attempt_dir'])/'drain-request.private.json'
        if drain.exists():
            result['drain_receipt']=json.loads(drain.read_text())
            if active is True:result['status']='draining'
        stopped = Path(record['attempt_dir']) / 'stop.private.json'
        if stopped.exists():
            result['stop_receipt'] = json.loads(stopped.read_text())
            if active is False and result['stop_receipt'].get('cleanup_confirmed') is True:
                result['native_live_rooms'] = 0
    return result


def worker_deadline_seconds(cfg, plan, logical_gpu, run_mode):
    if run_mode == 'model':
        return None  # Model completion is governed by effective episode budgets.
    # Native startup, serialized warmup, active episode, then terminal RPC and
    # cleanup. Queue allowance is a protection limit pending native measurement.
    rooms = max(len(p['episode_keys']) for p in plan['pools'] if p['logical_gpu_index'] == logical_gpu)
    rpc = cfg['barrier_timeout_seconds'] + max(120., rooms * 120. * cfg['capture_passes'] / 64.)
    return max(cfg['startup_timeout_seconds'], rpc + 120) + 3 * rpc + cfg[run_mode]['timeout_seconds'] + 420


def wait_for_pool_processes(children, *, run_mode, timeout_seconds, stop_requested,
                            progress=lambda codes: None, on_drain=lambda: None, clock=time.monotonic, sleep=time.sleep):
    """One model pool failing never cancels its sibling's in-flight API calls."""
    deadline=clock()+timeout_seconds if run_mode=='probe' and timeout_seconds is not None else None
    previous=None;draining=False
    while True:
        codes=[child.poll() for child in children]
        if codes!=previous:
            progress(codes);previous=list(codes)
        if all(code is not None for code in codes):return codes
        if stop_requested():
            if run_mode=='probe':raise InterruptedError('Explicit user stop')
            if not draining:on_drain();draining=True
        if deadline is not None and clock()>=deadline:raise TimeoutError('Card probe deadline exceeded')
        if run_mode=='probe' and any(code not in (None,0) for code in codes):
            raise RuntimeError('A probe pool failed; release both diagnostic pools on this card')
        sleep(.2)


def request_model_drain(record):
    """Acknowledge a request, never claim the still-running worker is stopped."""
    receipt=dict(requested=True,mode='graceful_drain',requested_unix_s=time.time(),
        campaign_id=record['campaign_id'],logical_gpu_index=record['logical_gpu_index'],
        attempt_id=record['attempt_id'],stopped=False,cleanup_confirmed=False)
    atomic(Path(record['attempt_dir'])/'drain-request.private.json',receipt)
    return receipt


def stop_owned_worker(record, *, grace_seconds=15.):
    """Snapshot descendants while their authenticated owner still exists."""
    if not process_live(record):
        return dict(owner_was_live=False, cleanup_confirmed=False, remaining_owned_processes=[])
    owner = ProcessIdentity(record['pid'], record['start_ticks'])
    snapshot = _lifecycle.descendants(owner)
    _lifecycle.signal_owned(owner, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and alive(owner):
        snapshot = list(set(snapshot + _lifecycle.descendants(owner)))
        time.sleep(.1)
    # Preserve descendants even if the worker died before writing its receipt.
    if alive(owner):
        snapshot = list(set(snapshot + _lifecycle.descendants(owner)))
    for process in snapshot:
        _lifecycle.signal_owned(process, signal.SIGKILL)
    deadline = time.monotonic() + 3.
    while time.monotonic() < deadline and any(alive(p) for p in snapshot):
        time.sleep(.05)
    remaining = [asdict(p) for p in snapshot if alive(p)]
    return dict(owner_was_live=True, cleanup_confirmed=not remaining,
        captured_owned_processes=[asdict(p) for p in snapshot], remaining_owned_processes=remaining)


def fresh_gpu(binding, min_free_mib):
    if socket.gethostname() != binding['hostname']:
        raise ValueError('Run this controller on the bound GPU pod, not a shared-PFS neighbour')
    g = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid,memory.free,memory.total', '--format=csv,noheader,nounits'], text=True, timeout=15)
    matches = [line.split(',') for line in g.splitlines() if line.split(',')[0].strip() == binding['gpu_uuid']]
    if len(matches) != 1: raise ValueError('Bound GPU UUID is not visible on this pod')
    p = subprocess.check_output(['nvidia-smi', '-i', binding['gpu_uuid'], '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True, timeout=15)
    lines = [s.strip() for s in p.splitlines() if s.strip()]
    if lines: raise ValueError('GPU has existing compute processes; no co-occupancy or termination attempted')
    free = int(matches[0][1].strip())
    if free < min_free_mib: raise ValueError('GPU free memory is below the explicit two-pool admission minimum')
    return dict(observed_unix_s=time.time(), hostname=socket.gethostname(), gpu_uuid=binding['gpu_uuid'],
        memory_free_mib=free, memory_total_mib=int(matches[0][2].strip()), existing_compute_pids=[])


def preflight_robot_asset(cfg, *, environ=None):
    """Resolve the declared robot USD exactly as the child runtime will, before Kit.

    This checks the top-level local file, not its USD syntax or referenced assets.
    No native runtime/Isaac import is needed for this inexpensive admission check.
    """
    profile_path = Path(cfg['robot_profile_path'])
    profile = json.loads(profile_path.read_text())
    if not isinstance(profile, dict) or not isinstance(profile.get('asset'), dict):
        raise ValueError('Robot profile must declare an asset object')
    asset = profile['asset']
    env_name, default = asset.get('env', ''), asset.get('path', '')
    if (not isinstance(env_name, str) or (env_name and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', env_name))
            or not isinstance(default, str)):
        raise ValueError('Robot asset env and path must be valid strings')
    if asset.get('format') != 'usd':
        raise ValueError('Robot asset format must be usd')
    configured = cfg.get('native_environment', {})
    if not isinstance(configured, dict):
        raise ValueError('native_environment must be an object')
    inherited = os.environ if environ is None else environ
    # An explicitly empty child environment value masks the inherited value,
    # then falls back to asset.path, matching Embodiment.asset_path().
    source = 'profile.asset.path'
    override = ''
    if env_name:
        if env_name in configured:
            override, source = configured[env_name], 'native_environment'
        elif env_name in inherited:
            override, source = inherited[env_name], 'process_environment'
    if not isinstance(override, str):
        raise ValueError('Robot asset environment override must be a string')
    selected = override or default
    if not override:
        source = 'profile.asset.path'
    if not selected or '\x00' in selected:
        raise ValueError('Robot asset path is empty or invalid; configure its declared environment or path')
    resolved = Path(selected).expanduser()
    if not resolved.is_absolute():
        resolved = Path(cfg['runtime_root']) / resolved
    resolved = resolved.resolve()
    if not resolved.is_file():
        raise ValueError('Robot asset must exist as a regular file before Kit startup: ' + str(resolved))
    if resolved.stat().st_size == 0:
        raise ValueError('Robot asset must not be empty before Kit startup: ' + str(resolved))
    return dict(profile_path=str(profile_path.resolve()), asset_env=env_name or None,
        source=source, resolved_path=str(resolved), size_bytes=resolved.stat().st_size,
        sha256=file_sha(resolved), format='usd', native_or_gpu_started=False)


def task_robot_profile(cfg, task):
    """Explicit, hash-pinned per-task rigs; legacy campaigns keep their default."""
    overrides = cfg.get('task_robot_profiles', {})
    if not isinstance(overrides, dict):
        raise ValueError('task_robot_profiles must be an object')
    if task not in overrides:
        return cfg['robot_profile_path']
    item = overrides[task]
    if (not isinstance(item, dict) or set(item) != {'path', 'sha256'}
            or not isinstance(item['path'], str) or not Path(item['path']).is_absolute()
            or not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])):
        raise ValueError('Task robot profile requires an absolute path and SHA256')
    if file_sha(item['path']) != item['sha256']:
        raise ValueError('Task robot profile hash mismatch: ' + task)
    return item['path']


def make_cases(plan, logical_gpu, cfg):
    rows = {r['episode_key']: r for r in plan['episodes']}
    pools = [p for p in plan['pools'] if p['logical_gpu_index'] == logical_gpu]
    return {p['pool_id']: [dict(episode_id=k, task=rows[k]['task_id'], variant=rows[k]['variant'],
        seed=rows[k]['seed'], input_condition=rows[k]['input_condition'],
        bindings=cfg['native_bindings_path'], robot=task_robot_profile(cfg, rows[k]['task_id'])) for k in p['episode_keys']] for p in pools}


def validate_provider_transport(ca_bundle, proxy, proxy_env=None):
    if proxy_env is not None:
        if proxy_env not in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY'):
            raise ValueError('Provider proxy environment name is not allowlisted')
        if proxy or not ca_bundle:
            raise ValueError('Provider proxy environment requires a CA bundle and excludes an explicit proxy URL')
    if ca_bundle and not Path(ca_bundle).is_absolute():
        raise ValueError('Provider CA bundle must be an explicit absolute path')
    if proxy:
        parsed=urlsplit(proxy)
        if (not ca_bundle or parsed.scheme not in ('http','https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('','/') or parsed.query or parsed.fragment):
            raise ValueError('Provider proxy requires a CA bundle and a credential-free HTTP(S) authority URL')
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError('Invalid provider proxy port')


def embodied_harness(cfg, args):
    configured = cfg.get('model', {}).get('embodied_harness', 'gui')
    override = getattr(args, 'embodied_harness', None)
    if configured not in ('gui', 'program_gui') or override not in (None, 'gui', 'program_gui'):
        raise ValueError('embodied_harness must be gui or program_gui')
    # Probe runs do not execute an agent; model configuration has no effect there.
    selected = override or (configured if args.run_mode == 'model' else 'gui')
    if selected == 'program_gui' and (args.run_mode != 'model' or args.engine != 'codex'):
        raise ValueError('program_gui requires a Codex model run')
    return selected


def command(cfg, cases, out, epoch, args):
    harness = embodied_harness(cfg, args)
    values = [cfg['gui_python'], str(Path(cfg['repo_root'])/'scripts/harbor/run_embodied_pool.py'),
        '--native-python', cfg['native_python'], '--gui-python', cfg['gui_python'],
        '--runtime-root', cfg['runtime_root'], '--task-root', cfg['task_root'],
        '--cases', str(cases), '--epoch', epoch, '--out', str(out),
        '--max-actions', str(cfg['probe']['max_actions'] if args.run_mode == 'probe' else cfg['model']['max_actions']),
        '--timeout', str(cfg['probe']['timeout_seconds'] if args.run_mode == 'probe' else cfg['model']['timeout_seconds']),
        '--startup-timeout', str(cfg['startup_timeout_seconds']),
        '--barrier-timeout', str(cfg['barrier_timeout_seconds']),
        '--capture-passes', str(cfg['capture_passes']), '--allow-unvalidated-environment']
    for flag, key in (('--experience','experience'),('--browser-path','browser_path')):
        if cfg.get(key): values += [flag,cfg[key]]
    if cfg.get('defer_stage_creation'): values += ['--defer-stage-creation']
    if cfg.get('native_kit_args'):
        if not isinstance(cfg['native_kit_args'],str): raise ValueError('native_kit_args must be a string')
        values += ['--native-kit-args',cfg['native_kit_args']]
    ca_bundle=getattr(args,'provider_ca_bundle',None);proxy=getattr(args,'provider_proxy',None)
    proxy_env=getattr(args,'provider_proxy_env',None)
    validate_provider_transport(ca_bundle,proxy,proxy_env)
    if args.run_mode == 'probe':
        if ca_bundle or proxy or proxy_env: raise ValueError('Provider transport arguments are only valid for model runs')
        profile=cfg['probe'].get('profile','basic')
        if profile not in {'basic','e31_rgb_motion_v1','e31_rgbd_motion_v2','sensor_only_gui_v1','inference_motion_v1'}:raise ValueError('Unknown engineering probe profile')
        if profile in {'e31_rgb_motion_v1','e31_rgbd_motion_v2','inference_motion_v1'} and cfg['probe']['max_actions']<4:raise ValueError('Three-action engineering probe requires separate Done headroom')
        if profile=='sensor_only_gui_v1' and cfg['probe']['max_actions']<2:raise ValueError('Sensor probe needs action and Done headroom')
        values += ['--probe-only','--probe-profile',profile]
    else:
        if harness != 'gui': values += ['--embodied-harness',harness]
        if not cfg.get('model_launch_enabled'):
            raise ValueError('Model launch gate remains disabled pending new API and acceptance')
        if not all((args.credentials, args.model, args.binary)):
            raise ValueError('Model execution requires explicit credentials, model and native CLI binary; no provider default')
        concurrency_config = cfg['model'].get('api_concurrency_config')
        if concurrency_config is None and cfg.get('audit_root'):
            shared_policy = Path(cfg['audit_root'])/'api-concurrency/provider.private.json'
            if shared_policy.exists():
                concurrency_config = str(shared_policy)
        if concurrency_config:
            if not ca_bundle:
                raise ValueError('API concurrency admission requires the verified provider relay')
            validate_api_concurrency_config(concurrency_config)
            values += ['--api-concurrency-config', str(concurrency_config)]
        if not Path(args.credentials).is_file() or not Path(args.binary).is_file():
            raise ValueError('Explicit credential file and native CLI binary must exist')
        compact_tokens=getattr(args,'codex_compact_tokens',None)
        if compact_tokens is None: compact_tokens=cfg['model'].get('codex_compact_tokens',32768)
        if type(compact_tokens) is not int or compact_tokens <= 0: raise ValueError('Codex compaction threshold must be positive')
        values += ['--codex-compact-tokens',str(compact_tokens)]
        auto_recover = cfg['model'].get('auto_recover', False)
        if type(auto_recover) is not bool:
            raise ValueError('model.auto_recover must be a boolean')
        if auto_recover:
            if args.engine != 'codex':
                raise ValueError('Automatic session recovery requires Codex')
            values += ['--embodied-auto-recover']
        if args.engine == 'codex':
            catalog = getattr(args,'codex_model_catalog',None) or cfg['model'].get('codex_model_catalog')
            digest = getattr(args,'codex_model_catalog_sha256',None) or cfg['model'].get('codex_model_catalog_sha256')
            if not catalog:
                raise ValueError('Codex model launch requires a pinned direct GUI model catalog')
            validate_model_catalog(catalog,digest,args.model)
            values += ['--codex-model-catalog',str(Path(catalog).resolve()),'--codex-model-catalog-sha256',digest]
        values += ['--credentials',str(Path(args.credentials).resolve()), '--model',args.model,
            '--binary',str(Path(args.binary).resolve()), '--engine',args.engine, '--effort',args.effort]
        if ca_bundle:
            if not Path(ca_bundle).is_file(): raise ValueError('Explicit provider CA bundle must exist')
            values += ['--provider-ca-bundle',str(Path(ca_bundle).resolve())]
        if proxy: values += ['--provider-proxy',proxy]
        if proxy_env:
            if proxy_env not in os.environ: raise ValueError('Named provider proxy environment variable is unavailable')
            values += ['--provider-proxy-env',proxy_env]
    return values


def worker_command(args, attempt):
    argv=[sys.executable,str(Path(__file__).resolve()),'_worker','--deployment',str(args.deployment.resolve()),
        '--logical-gpu',str(args.logical_gpu),'--run-mode',args.run_mode,'--attempt',str(attempt),
        '--engine',args.engine,'--effort',args.effort]
    for flag,value in (('--credentials',args.credentials),('--model',args.model),('--binary',args.binary),
                       ('--provider-ca-bundle',args.provider_ca_bundle),('--provider-proxy',args.provider_proxy),
                       ('--provider-proxy-env',args.provider_proxy_env),('--codex-compact-tokens',args.codex_compact_tokens),
                       ('--codex-model-catalog',args.codex_model_catalog),('--codex-model-catalog-sha256',args.codex_model_catalog_sha256),
                       ('--embodied-harness',args.embodied_harness)):
        if value is not None:argv += [flag,str(value)]
    return argv


def worker(args, cfg, plan):
    if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0) != 0:
        raise OSError(ctypes.get_errno(),'Could not enable owned-child subreaper')
    attempt = Path(args.attempt).resolve()
    if not attempt.is_relative_to(state_folder(cfg,args.logical_gpu).resolve()/'attempts'):
        raise ValueError('Attempt directory escapes this campaign/card')
    record = dict(campaign_id=cfg['campaign_id'], logical_gpu_index=args.logical_gpu,
        attempt_id=attempt.name, status='preflight', run_mode=args.run_mode,
        scientific_evaluation=False, counts_toward_300=False,
        gpu_lease_held=False, actual_model_requests=0 if args.run_mode=='probe' else None,
        started_unix_s=time.time(), children=[])
    stop=[False]
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:stop.__setitem__(0,True))
    children=[];streams=[];lease=None
    def save(): atomic(attempt/'lifecycle.private.json',record)
    def drain_requested(): return stop[0] or (attempt/'drain-request.private.json').exists()
    def drain_pools():
        record['status']='draining';record['drain_requested']=True;save()
        for child_record in record['children']:
            atomic(attempt/child_record['pool_id']/'drain-request.private.json',
                dict(requested=True,campaign_id=cfg['campaign_id'],attempt_id=attempt.name,
                     requested_unix_s=time.time(),mode='graceful_drain'))
    save();code=1
    try:
        if cfg.get('deployment_ready') is not True: raise ValueError('Deployment has not been bound and preflighted')
        binding=card_binding(cfg,args.logical_gpu)
        locks=Path(cfg['audit_root'])/'campaign-leases';locks.mkdir(parents=True,exist_ok=True)
        lease=(locks/(binding['gpu_uuid']+'.lock')).open('a+')
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record['gpu_lease_held']=True;save()
        check=preflight(plan,cfg['task_root'],logical_gpu=args.logical_gpu,verify_media=True)
        atomic(attempt/'input-preflight.json',check)
        if not check['ready']: raise ValueError('Assigned real/text inputs are missing or fail frozen hashes')
        for field in ('native_bindings_path','robot_profile_path'):
            if file_sha(cfg[field]) != cfg[field+'_sha256']:
                raise ValueError('Native runtime input hash mismatch: '+field)
        assets = [preflight_robot_asset(cfg)]
        for task in sorted({e['task_id'] for e in plan['episodes'] if e['logical_gpu_index']==args.logical_gpu}):
            selected = task_robot_profile(cfg, task)
            if selected != cfg['robot_profile_path']:
                assets.append(dict(task=task, **preflight_robot_asset(dict(cfg, robot_profile_path=selected))))
        atomic(attempt/'robot-asset-preflight.private.json', assets[0])
        if len(assets)>1: atomic(attempt/'task-robot-assets-preflight.private.json', dict(profiles=assets))
        native_tasks=json.loads(Path(cfg['native_bindings_path']).read_text()).get('tasks',{})
        if set(native_tasks)!={f'E{i:02d}' for i in range(1,51)}:
            raise ValueError('Native bindings must cover all 50 tasks')
        sample=fresh_gpu(binding,cfg['min_free_vram_mib']);atomic(attempt/'gpu-admission.json',sample)
        if drain_requested(): raise InterruptedError('Stopped before launch')
        for pool_id,cases in make_cases(plan,args.logical_gpu,cfg).items():
            if drain_requested():
                if args.run_mode=='model': break
                raise InterruptedError('Stopped before pool launch')
            path=attempt/(pool_id+'-cases.json');atomic(path,dict(cases=cases))
            argv=command(cfg,path,attempt/pool_id,attempt.name+'-'+pool_id,args)
            atomic(attempt/(pool_id+'-command.private.json'),dict(argv=argv,model_api_enabled=args.run_mode=='model'))
            stream=(attempt/(pool_id+'.log')).open('w');streams.append(stream)
            child=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,
                env=dict(os.environ,**cfg.get('native_environment',{}),CUDA_VISIBLE_DEVICES=binding['gpu_uuid']))
            children.append(child);record['children'].append(dict(pool_id=pool_id,pid=child.pid))
        record['status']='probe_running' if args.run_mode=='probe' else 'model_running';save()
        limit=worker_deadline_seconds(cfg,plan,args.logical_gpu,args.run_mode)
        record['worker_timeout_seconds']=limit
        record['sibling_failure_policy']='preserve_other_model_pool' if args.run_mode=='model' else 'abort_diagnostic_card'
        save()
        def progress(codes):
            record['pool_exit_codes']=codes
            if args.run_mode=='model' and not record.get('drain_requested') and any(code not in (None,0) for code in codes) and None in codes:
                record['status']='model_running_with_failed_pool'
            save()
        record['pool_exit_codes']=wait_for_pool_processes(children,run_mode=args.run_mode,
            timeout_seconds=limit,stop_requested=drain_requested,progress=progress,on_drain=drain_pools)
        code=0 if all(c.returncode==0 for c in children) else 1
        record['status']='stopped' if record.get('drain_requested') else ('completed' if code==0 else 'incomplete')
    except InterruptedError as exc:
        record['status']='stopped';record['reason']=str(exc);code=130
    except Exception as exc:
        record['status']='blocked_or_infrastructure_error';record['reason']=type(exc).__name__+': '+str(exc)
    finally:
        if args.run_mode=='model':
            if any(c.poll() is None for c in children):
                drain_pools()
                for c in children:c.wait()  # Preserve all already-issued model/API work.
            # Model pools own graceful relay draining. An unexpected orphan is
            # reported for investigation instead of indiscriminately killed.
            record['cleanup']=[asdict(who) for who in _lifecycle.descendants(identity(os.getpid())) if who.pid!=os.getpid()]
        else:
            record['cleanup']=terminate_tree(identity(os.getpid()),grace_seconds=5.,include_owner=False)
        for c in children:
            try:c.wait(timeout=2.)
            except subprocess.TimeoutExpired:c.kill();c.wait()
        for stream in streams:stream.close()
        reap_deadline=time.monotonic()+3.
        while time.monotonic()<reap_deadline and any(alive(ProcessIdentity(**r)) for r in record['cleanup']):
            time.sleep(.05)
        # As a Linux subreaper, also reap adopted native/browser grandchildren.
        while True:
            try:
                reaped,_=os.waitpid(-1,os.WNOHANG)
                if not reaped: break
            except ChildProcessError: break
        record['remaining_owned_processes']=[r for r in record['cleanup'] if alive(ProcessIdentity(**r))]
        record['cleanup_confirmed']=not record['remaining_owned_processes']
        if not record['cleanup_confirmed']:
            record['status']='cleanup_error';code=1
        elif record.get('drain_requested'):record['status']='stopped'
        if lease:lease.close()
        record['gpu_lease_held']=False;record['finished_unix_s']=time.time();save()
    return code


def validate_model_attempt_exemptions(cfg):
    """Explicit exact historical attempt basenames; absence preserves legacy300."""
    if 'model_attempt_exemptions' not in cfg:
        return None
    if 'panel_contract' in cfg:
        raise ValueError('Frozen extension panels do not permit model attempt exemptions')
    exemptions = cfg['model_attempt_exemptions']
    if not isinstance(exemptions, dict):
        raise ValueError('model_attempt_exemptions must map logical card strings to exact basename lists')
    allowed = {b['logical_gpu_index'] for b in cfg.get('bindings', [])}
    for logical, names in exemptions.items():
        if not isinstance(logical, str) or not re.fullmatch(r'0|[1-9][0-9]*', logical) or int(logical) not in allowed:
            raise ValueError('Model attempt exemption key must be an assigned canonical logical card string')
        if not isinstance(names, list) or any(not isinstance(name, str) or not re.fullmatch(r'model-[A-Za-z0-9][A-Za-z0-9_-]{0,159}', name) for name in names):
            raise ValueError('Model attempt exemptions require exact model-* basenames; no paths, patterns, or time ranges')
        if len(set(names)) != len(names):
            raise ValueError('Duplicate model attempt exemption basename')
    return exemptions


def reject_frozen_model_replay(cfg, logical_gpu, run_mode):
    exemptions = validate_model_attempt_exemptions(cfg)
    if run_mode != 'model' or ('panel_contract' not in cfg and exemptions is None):
        return
    allowed = set((exemptions or {}).get(str(logical_gpu), []))
    attempts = state_folder(cfg, logical_gpu) / 'attempts'
    # Inspect all old attempts, not merely launch.private.json or the newest one.
    # Even an exempt basename cannot authorize a symlink to replaced evidence.
    blocked = sorted(path.name for path in attempts.glob('model-*')
                     if path.name not in allowed or path.is_symlink() or not path.is_dir())
    if blocked:
        raise ValueError('Existing non-exempt model attempts; reconcile evidence, never replay start: ' + ', '.join(blocked))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['preview','preflight','start','status','stop','_worker'])
    p.add_argument('--deployment',type=Path,required=True)
    p.add_argument('--logical-gpu',type=int,required=True)
    p.add_argument('--run-mode',choices=['probe','model'],default='probe')
    p.add_argument('--credentials',type=Path);p.add_argument('--model');p.add_argument('--binary',type=Path)
    p.add_argument('--engine',choices=['codex','claude'],default='codex');p.add_argument('--effort',default='high')
    p.add_argument('--embodied-harness',choices=['gui','program_gui'],default=None,
                   help='Override model.embodied_harness; defaults to gui when not configured')
    p.add_argument('--attempt',type=Path)
    p.add_argument('--codex-compact-tokens',type=int)
    p.add_argument('--codex-model-catalog',type=Path)
    p.add_argument('--codex-model-catalog-sha256')
    p.add_argument('--provider-ca-bundle',type=Path);p.add_argument('--provider-proxy');p.add_argument('--provider-proxy-env')
    args=p.parse_args()
    cfg,plan=load_deployment(args.deployment)
    if args.logical_gpu not in {r['logical_gpu_index'] for r in plan['episodes']}:
        p.error('logical-gpu must be assigned in the frozen panel')
    if args.action=='preview':
        print(json.dumps(dict(campaign_id=cfg['campaign_id'], logical_gpu_index=args.logical_gpu,
            cases=make_cases(plan,args.logical_gpu,cfg), gpu_bound=any(b.get('logical_gpu_index')==args.logical_gpu for b in cfg.get('bindings',[])),
            model_launch_enabled=cfg.get('model_launch_enabled',False), started_processes=0),ensure_ascii=False));return 0
    if args.action=='preflight':
        result=preflight(plan,cfg['task_root'],logical_gpu=args.logical_gpu)
        print(json.dumps(result,ensure_ascii=False));return 0 if result['ready'] else 2
    if args.action=='status':print(json.dumps(status(cfg,args.logical_gpu),ensure_ascii=False));return 0
    if sys.platform!='linux':p.error('start/stop require Linux process identity on the bound GPU pod')
    if args.action=='_worker':return worker(args,cfg,plan)
    if card_binding(cfg,args.logical_gpu)['hostname'] != socket.gethostname():
        raise ValueError('Start/stop must execute on the bound pod; shared-PFS state cannot establish foreign process ownership')
    folder=state_folder(cfg,args.logical_gpu);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=(folder/'control.lock').open('a+')
    with lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=status(cfg,args.logical_gpu)
        if args.action=='stop':
            if current['active']:
                record=json.loads((folder/'launch.private.json').read_text())
                if record.get('campaign_id')!=cfg['campaign_id'] or record.get('logical_gpu_index')!=args.logical_gpu:
                    raise ValueError('Refusing to stop another campaign/card')
                mode=record.get('run_mode',current.get('lifecycle',{}).get('run_mode'))
                if mode=='model':
                    receipt=request_model_drain(record)
                    result=status(cfg,args.logical_gpu);result.update(status='draining',drain_receipt=receipt)
                    print(json.dumps(result,ensure_ascii=False));return 0
                if mode!='probe':raise ValueError('Unknown worker mode; refusing forced cleanup')
                receipt=stop_owned_worker(record)
                atomic(Path(record['attempt_dir'])/'stop.private.json',receipt)
                result=status(cfg,args.logical_gpu);result['stop_receipt']=receipt
                print(json.dumps(result,ensure_ascii=False));return 0 if receipt['cleanup_confirmed'] else 2
            print(json.dumps(status(cfg,args.logical_gpu),ensure_ascii=False));return 0 if current['native_live_rooms']==0 else 2
        if current['active']:raise ValueError('Card already active; stop or wait before a fresh attempt')
        reject_frozen_model_replay(cfg,args.logical_gpu,args.run_mode)
        if cfg.get('deployment_ready') is not True:raise ValueError('Explicit physical bindings and remote paths are still pending')
        card_binding(cfg,args.logical_gpu)
        # Resolve model permission/explicit inputs before starting any worker.
        command(cfg,Path('/unused-cases'),Path('/unused-output'),'preview',args)
        attempt=folder/'attempts'/(args.run_mode+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:10])
        attempt.mkdir(parents=True,exist_ok=False,mode=0o700)
        argv=worker_command(args, attempt)
        with (attempt/'worker.log').open('w') as log:
            child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        who=identity(child.pid)
        if who is None:raise RuntimeError('Worker exited before identity capture; inspect preserved worker.log')
        record=dict(**asdict(who),campaign_id=cfg['campaign_id'],logical_gpu_index=args.logical_gpu,
            attempt_id=attempt.name,attempt_dir=str(attempt),run_mode=args.run_mode,hostname=socket.gethostname(),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        atomic(attempt/'launch.private.json',record);atomic(folder/'launch.private.json',record)
        print(json.dumps(dict(launched=True,**record),ensure_ascii=False));return 0

if __name__=='__main__':
    raise SystemExit(main())
