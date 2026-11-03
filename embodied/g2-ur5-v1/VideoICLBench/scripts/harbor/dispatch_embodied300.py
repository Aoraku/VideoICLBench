#!/usr/bin/env python3
"""Persistent local SSH dispatcher for the bound real/text 300 campaign.

Each start is sent once unless the gateway positively rejected session creation
before executing it. Ambiguous results require status reconciliation, never replay.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import uuid

from control_embodied300 import atomic, load_deployment, validate_provider_transport

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = 'real-text300-20261030'
REMOTE_ROOT = '/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/campaigns/' + CAMPAIGN
GATEWAY_REJECTION = b'robo-gateway: too many open sessions'

# This wrapper validates both the remote configuration and the existing launch
# identity before allowing even a status/stop call into the controller.
REMOTE_CHECK = '''import json,pathlib,socket,subprocess,sys
request=json.loads(sys.argv[1])
path=pathlib.Path(request['deployment'])
cfg=json.loads(path.read_text())
if cfg.get('campaign_id')!=request['campaign_id'] or cfg.get('plan_sha256')!=request['plan_sha256']:
 raise RuntimeError('Remote campaign/plan identity differs from dispatch lock')
expected=request['binding'];logical=expected['logical_gpu_index']
rows=[r for r in cfg.get('bindings',[]) if r.get('logical_gpu_index')==logical]
if len(rows)!=1 or any(rows[0].get(k)!=expected[k] for k in ('physical_slot','ssh_user','hostname','gpu_uuid')):
 raise RuntimeError('Remote physical card binding differs from dispatch lock')
if socket.gethostname()!=expected['hostname']:
 raise RuntimeError('SSH gateway reached a different pod')
if cfg.get('repo_root')!=request['repo_root'] or cfg.get('state_root')!=request['state_root']:
 raise RuntimeError('Remote campaign paths differ from dispatch lock')
launch=pathlib.Path(cfg['state_root'])/f'card-{logical:02d}'/'launch.private.json'
if launch.exists():
 record=json.loads(launch.read_text())
 if record.get('campaign_id')!=request['campaign_id'] or record.get('logical_gpu_index')!=logical:
  raise RuntimeError('Existing launch belongs to another campaign/card')
controller=pathlib.Path(cfg['repo_root'])/'scripts/harbor/control_embodied300.py'
launcher=pathlib.Path(cfg['repo_root']).parent/'process_launcher.py'
python=pathlib.Path(cfg['gui_python'])
if not python.is_file():raise RuntimeError('Configured CPython controller interpreter is unavailable')
command=[str(python),str(launcher),'--identity-dir',str(pathlib.Path(cfg['state_root'])/'process-identities'),'--role','controller-command','--',str(controller)]+request['controller_args']
raise SystemExit(subprocess.call(command))
'''


def selected_bindings(cfg, selection):
    rows=sorted(cfg.get('bindings',[]),key=lambda r:r['logical_gpu_index'])
    if 'panel_contract' in cfg:
        from panel_contract import validate_deployment_contract
        validate_deployment_contract(cfg)
    elif cfg.get('campaign_id')!=CAMPAIGN or len(rows)!=24:
        raise ValueError('Exact real-text300 campaign and 24 bindings required')
    if 'panel_contract' not in cfg and ([r['logical_gpu_index'] for r in rows]!=list(range(24)) or [r['physical_slot'] for r in rows]!=list(range(1,25))):
        raise ValueError('Expected logical cards 0..23 bound to physical slots 1..24')
    if len({r['gpu_uuid'] for r in rows})!=len(rows):
        raise ValueError('Physical GPU identities must be unique')
    for r in rows:
        if r.get('ssh_user')!=f"jiemingli.{r['physical_slot']}" or not r.get('hostname'):
            raise ValueError('Explicit slot login and pod hostname required')
    if selection is None:return rows
    selected=[int(value) for value in selection.split(',')]
    if len(set(selected))!=len(selected) or not selected or any(i not in {r['logical_gpu_index'] for r in rows} for i in selected):
        raise ValueError('logical-gpus must list unique assigned indices')
    return [rows[i] for i in sorted(selected)]


def remote_request(cfg, binding, args):
    if 'panel_contract' in cfg:
        from panel_contract import validate_deployment_contract
        validate_deployment_contract(cfg)
        deployment=cfg['remote_deployment_path']
    else:
        if cfg['repo_root']!=REMOTE_ROOT+'/VideoICLBench' or cfg['state_root']!=REMOTE_ROOT+'/on-demand':
            raise ValueError('Deployment paths must point into the explicit 300 campaign')
        deployment=REMOTE_ROOT+'/config/deployment.private.json'
    argv=[args.action,'--deployment',deployment,'--logical-gpu',str(binding['logical_gpu_index']),
          '--run-mode',args.run_mode]
    ca_bundle=getattr(args,'provider_ca_bundle',None);proxy=getattr(args,'provider_proxy',None)
    proxy_env=getattr(args,'provider_proxy_env',None)
    validate_provider_transport(ca_bundle,proxy,proxy_env)
    if args.action=='start' and args.run_mode=='model':
        if args.model!='gpt-6-astra' or args.effort!='high':
            raise ValueError('This model panel requires explicit --model gpt-6-astra --effort high')
        if not args.credentials or not args.binary or not all(Path(p).is_absolute() for p in (args.credentials,args.binary)):
            raise ValueError('Explicit absolute remote credential and native CLI binary paths required')
        compact_tokens=getattr(args,'codex_compact_tokens',None)
        if compact_tokens is None: compact_tokens=cfg['model'].get('codex_compact_tokens',32768)
        if type(compact_tokens) is not int or compact_tokens<=0: raise ValueError('Codex compaction threshold must be positive')
        argv += ['--codex-compact-tokens',str(compact_tokens)]
        catalog=getattr(args,'codex_model_catalog',None) or cfg['model'].get('codex_model_catalog')
        digest=getattr(args,'codex_model_catalog_sha256',None) or cfg['model'].get('codex_model_catalog_sha256')
        if (not isinstance(catalog,(str,Path)) or not Path(catalog).is_absolute()
                or not isinstance(digest,str) or len(digest)!=64
                or any(c not in '0123456789abcdefABCDEF' for c in digest)):
            raise ValueError('Model dispatch requires an explicit absolute pinned catalog path and SHA256')
        argv += ['--codex-model-catalog',str(catalog),'--codex-model-catalog-sha256',digest]
        argv += ['--credentials',args.credentials,'--model',args.model,'--effort',args.effort,
                 '--binary',args.binary,'--engine','codex']
        if ca_bundle: argv += ['--provider-ca-bundle',str(ca_bundle)]
        if proxy: argv += ['--provider-proxy',proxy]
        if proxy_env: argv += ['--provider-proxy-env',proxy_env]
    elif any((args.credentials,args.model,args.binary,args.effort,ca_bundle,proxy,proxy_env,
              getattr(args,'codex_model_catalog',None),getattr(args,'codex_model_catalog_sha256',None))):
        raise ValueError('Provider/model arguments are accepted only for model start')
    return dict(campaign_id=cfg['campaign_id'],plan_sha256=cfg['plan_sha256'],
        binding={k:binding[k] for k in ('logical_gpu_index','physical_slot','ssh_user','hostname','gpu_uuid')},
        deployment=deployment,repo_root=cfg['repo_root'],state_root=cfg['state_root'],controller_args=argv)


def ssh_command(request):
    remote=shlex.join(['python3','-c',REMOTE_CHECK,json.dumps(request,separators=(',',':'))])
    return ['ssh','-o','ConnectTimeout=20','-o','StrictHostKeyChecking=accept-new',
            '-o','ConnectionAttempts=1','-l',request['binding']['ssh_user'],'rtx',remote]


def parse_result(completed, request):
    raw=completed.stdout or b''
    try: result=json.loads(raw)
    except (ValueError,UnicodeDecodeError): result=None
    valid=(isinstance(result,dict) and result.get('campaign_id')==request['campaign_id']
           and result.get('logical_gpu_index')==request['binding']['logical_gpu_index'])
    if completed.returncode==0 and valid:
        if request['controller_args'][0]=='start' and result.get('launched') is not True:
            return 'unknown',result
        return 'confirmed',result
    # Even nonzero return codes may follow a partially executed start.
    return 'unknown' if request['controller_args'][0]=='start' else 'failed',result


def dispatch_one(request, args, folder, *, run=subprocess.run, pause=time.sleep):
    row=dict(schema='videoicl300-dispatch-card-v1',campaign_id=request['campaign_id'],
        logical_gpu_index=request['binding']['logical_gpu_index'],physical_slot=request['binding']['physical_slot'],
        action=args.action,run_mode=args.run_mode,request=request,attempts=[],outcome='not_sent')
    path=folder/f"card-{row['logical_gpu_index']:02d}.private.json"
    env=dict(os.environ,SSH_ASKPASS=str(args.ssh_askpass.resolve()),SSH_ASKPASS_REQUIRE='force',DISPLAY='codex')
    for retry in range(args.gateway_retries+1):
        attempt=dict(number=retry+1,started_unix_s=time.time(),outcome='sent_result_pending')
        row['attempts'].append(attempt);row['outcome']='unknown';atomic(path,row)
        try:
            completed=run(ssh_command(request),capture_output=True,timeout=args.ssh_timeout,
                          env=env,stdin=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired,OSError) as exc:
            attempt.update(outcome='unknown',error_class=type(exc).__name__,finished_unix_s=time.time())
            row['reconciliation']='Run status for this card before deciding any new start; do not replay.'
            atomic(path,row);return row
        rejected=(completed.returncode==255 and not completed.stdout and GATEWAY_REJECTION in (completed.stderr or b''))
        attempt.update(exit_code=completed.returncode,finished_unix_s=time.time(),
            stderr_tail=(completed.stderr or b'').decode(errors='replace')[-2000:])
        if rejected:
            attempt['outcome']='rejected_before_execution';row['outcome']='rejected_before_execution';atomic(path,row)
            if retry<args.gateway_retries:pause(1+retry);continue
            return row
        outcome,result=parse_result(completed,request)
        attempt['outcome']=outcome;row.update(outcome=outcome,result=result)
        if result is None:
            row['stdout_sha256']=hashlib.sha256(completed.stdout or b'').hexdigest()
        if outcome!='confirmed':row['reconciliation']='Inspect status and remote receipts; no automatic replay.'
        atomic(path,row);return row
    raise AssertionError('Unreachable')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['start','status','stop'])
    p.add_argument('--deployment',type=Path,required=True,help='Local copy of the frozen deployment configuration')
    p.add_argument('--out',type=Path,required=True,help='Local receipt parent; a fresh dispatch directory is created')
    p.add_argument('--logical-gpus',help='Comma separated logical indices; default all frozen bindings')
    p.add_argument('--run-mode',choices=['probe','model'],default='probe')
    p.add_argument('--ssh-askpass',type=Path,default=ROOT/'.local/rtx/askpass.py')
    p.add_argument('--ssh-timeout',type=float,default=75.)
    p.add_argument('--gateway-retries',type=int,choices=range(4),default=2)
    p.add_argument('--codex-compact-tokens',type=int)
    p.add_argument('--codex-model-catalog')
    p.add_argument('--codex-model-catalog-sha256')
    p.add_argument('--credentials');p.add_argument('--model');p.add_argument('--effort');p.add_argument('--binary')
    p.add_argument('--provider-ca-bundle');p.add_argument('--provider-proxy');p.add_argument('--provider-proxy-env')
    p.add_argument('--preview',action='store_true',help='Write reviewable commands without contacting SSH')
    args=p.parse_args(argv)
    if args.ssh_timeout<=0:p.error('ssh-timeout must be positive')
    if not args.ssh_askpass.is_file():p.error('Existing SSH askpass helper is required; this tool never writes credentials')
    cfg,_=load_deployment(args.deployment)
    requests=[remote_request(cfg,row,args) for row in selected_bindings(cfg,args.logical_gpus)]
    folder=args.out.resolve()/('dispatch-'+args.action+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,mode=0o700)
    summary=dict(schema='videoicl300-dispatch-v1',campaign_id=cfg['campaign_id'],action=args.action,
        run_mode=args.run_mode,preview=args.preview,started_unix_s=time.time(),requested_cards=len(requests),rows=[])
    atomic(folder/'summary.private.json',summary)
    for request in requests:
        if args.preview:
            row=dict(logical_gpu_index=request['binding']['logical_gpu_index'],outcome='preview',request=request,
                     ssh_argv=ssh_command(request),remote_commands_executed=0)
            atomic(folder/f"card-{row['logical_gpu_index']:02d}.private.json",row)
        else:row=dispatch_one(request,args,folder)
        summary['rows'].append(row);atomic(folder/'summary.private.json',summary)
        print(json.dumps(dict(logical_gpu_index=row['logical_gpu_index'],outcome=row['outcome'],receipt_dir=str(folder))),flush=True)
        if args.action=='start' and row['outcome'] not in ('confirmed','preview'):break
    summary['finished_unix_s']=time.time()
    summary['complete']=len(summary['rows'])==len(requests) and all(r['outcome'] in ('confirmed','preview') for r in summary['rows'])
    atomic(folder/'summary.private.json',summary)
    return 0 if summary['complete'] else 2


if __name__=='__main__':
    raise SystemExit(main())
