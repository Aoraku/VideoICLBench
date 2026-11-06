"""Independent native Codex video QA candidate. Default is plan only.

Root-owned fixed manifest supplies the original video and public question. No
physical runtime/controller is imported. A relay shares the EXECUTION gate50.
The first-answer key is never read by this process. Review before --execute.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w')as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def validate(cfg):
    allowed={'schema','identity','video_path','video_sha256','question','output_dir','sdk_root',
        'binary','credentials','credentials_sha256','ca_bundle','api_gate_config','api_gate_sha256',
        'model_catalog','model_catalog_sha256','model','effort','expected_cli_version'}
    if set(cfg)!=allowed or cfg['schema']!='standalone-native-video-qa-run-v1':raise ValueError('Explicit reviewed QA config fields required')
    if cfg['model']!='gpt-6-astra'or cfg['effort']!='high'or cfg['expected_cli_version']!='codex-cli 0.163.0':raise ValueError('Fixed native model/effort/version contract')
    from standalone_qa_tools import public_question
    public_question(cfg['question'])
    if digest(cfg['video_path'])!=cfg['video_sha256']:raise ValueError('Assigned video mismatch')
    for path,expected in [('credentials','credentials_sha256'),('api_gate_config','api_gate_sha256'),('model_catalog','model_catalog_sha256')]:
        if digest(cfg[path])!=cfg[expected]:raise ValueError('Pinned QA dependency changed: '+path)
    sdk=Path(cfg['sdk_root']).resolve()
    for rel in ('vic_sdk/tls_relay_entry.py','vic_sdk/direct_tools.py','vic_sdk/native_agent.py','vic_sdk/api_concurrency.py'):
        if not(sdk/rel).is_file():raise ValueError('Complete pinned native SDK required')
    # Never resolve through a previously imported or installed SDK.
    for name in list(sys.modules):
        if name=='vic_sdk'or name.startswith('vic_sdk.'):del sys.modules[name]
    sys.path.insert(0,str(sdk))
    gate=importlib.import_module('vic_sdk.api_concurrency')
    if not Path(gate.__file__).resolve().is_relative_to(sdk):raise ValueError('Ambient SDK rejected')
    policy=gate.validated_config(cfg['api_gate_config'])
    if policy['limit']!=50:raise ValueError('Same reviewed hard50 execution/QA gate is required')
    from vic_sdk.direct_tools import validate_context_window
    validate_context_window(cfg['model_catalog'],cfg['model_catalog_sha256'],cfg['model'],262144,120000)
    return dict(ready_for_root_review=True,execute=False,identity=cfg['identity'],simulation_starts=0,
        model_requests=0,shared_gate_scope_sha256=hashlib.sha256(policy['scope'].encode()).hexdigest(),
        shared_gate_lock_directory_sha256=hashlib.sha256(policy['lock_directory'].encode()).hexdigest(),
        note='Root must match this gate path/scope/digest with every execution relay; no independent QA gate.')


def execute(cfg):
    validate(cfg)
    out=Path(cfg['output_dir']).resolve();out.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (out/'first-valid-answer.private.json').exists():
        return dict(status='existing_first_answer_no_new_model_request',simulation_starts=0)
    claim=out/'launch-claim.private.json';write(claim,dict(identity=cfg['identity'],pid=os.getpid(),automatic_replay=False))
    version=subprocess.check_output([cfg['binary'],'--version'],text=True,timeout=15).strip()
    if version!=cfg['expected_cli_version']:raise ValueError('Actual CLI version differs')
    from vic_sdk.native_agent import codex_config,cli_command,summarize
    from vic_sdk.direct_tools import freeze_direct_model_catalog
    from vic_sdk.embodied_recovery import resolve_session
    from vic_sdk.api_timing import ApiTimingLedger
    profile=out/'profile';profile.mkdir(mode=0o700);workspace=out/'workspace';workspace.mkdir(mode=0o700)
    timing=out/'api-timing.private.jsonl';route=secrets.token_hex(16);routes=out/'timing-routes.private.json';write(routes,{route:str(timing)})
    relay_dir=out/'provider-relay';relay_log=(out/'relay.private.log').open('x')
    provider=json.loads(Path(cfg['credentials']).read_text())['codex']
    if not provider.get('base_url','').startswith('https://')or not provider.get('api_key'):raise ValueError('Original provider unavailable')
    command=[sys.executable,str(Path(cfg['sdk_root'])/'vic_sdk/tls_relay_entry.py'),
        '--upstream',provider['base_url'],'--ca-bundle',cfg['ca_bundle'],'--out',str(relay_dir),
        '--episode-timing-routes',str(routes),'--concurrency-config',cfg['api_gate_config'],'--request-metadata']
    relay=subprocess.Popen(command,stdout=relay_log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
    try:
        deadline=time.monotonic()+60
        while not(relay_dir/'ready.private.json').is_file():
            if relay.poll()is not None or time.monotonic()>deadline:raise ValueError('QA relay bootstrap failed before model')
            time.sleep(.1)
        ready=json.loads((relay_dir/'ready.private.json').read_text());base=ready['base_url'][:-3]+'/episodes/'+route+'/v1'
        tools={k:cfg[k]for k in ('identity','video_path','video_sha256','question','output_dir')};tools['schema']='standalone-video-qa-v1'
        tools['api_timing_log']=str(timing)
        toolpath=out/'public-qa-tools.private.json';write(toolpath,tools)
        server=dict(command=sys.executable,args=[str(HERE/'standalone_qa_tools.py'),'--config',str(toolpath),'--sdk-root',cfg['sdk_root']],startup_timeout_sec=120,tool_timeout_sec=86400)
        catalog=freeze_direct_model_catalog(profile,cfg['model_catalog'],cfg['model_catalog_sha256'],cfg['model'],cli_version=version,serial_tools=True)
        instructions='Watch the assigned video using vic demo tools. Then request its four-option rule QA and submit exactly one uppercase letter through qa_answer. No simulator, robot actions, task-rule text, coding task or answer feedback is available. First valid answer is final.'
        role=profile/'model-instructions.md';role.write_text(instructions+'\n');role.chmod(0o600)
        text='model_instructions_file = '+json.dumps(str(role))+'\nmodel_catalog_json = '+json.dumps(catalog['catalog_path'])+'\ndeveloper_instructions = '+json.dumps(instructions)+'\n'+codex_config(cfg['model'],base,server,compact_tokens=120000,context_window=262144,effort='high',isolated_tools=True,tool_output_tokens=32768)
        (profile/'config.toml').write_text(text);(profile/'config.toml').chmod(0o600)
        hook=shlex.join([sys.executable,str(HERE/'qa_stop_hook.py'),'--answer',str(out/'first-valid-answer.private.json')])
        write(profile/'hooks.json',{'hooks':{'Stop':[{'hooks':[{'type':'command','command':hook,'timeout':10}]}]}})
        cmd,env=cli_command('codex',profile,workspace,cfg['model'],server,binary=cfg['binary'],serial_tools=True);env['VIC_MODEL_API_KEY']=provider['api_key']
        prompt='This is standalone video-rule QA. Use demo_info and demo_frames to inspect the original assigned video, call qa_question, then submit one A/B/C/D with qa_answer. No physical episode exists.'
        with(out/'stdout.jsonl').open('x')as stdout,(out/'stderr.private.log').open('x')as stderr:
            child=subprocess.Popen(cmd,env=env,cwd=workspace,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True,start_new_session=True)
            child.communicate(prompt)  # No timeout, no cancellation of accepted API.
        summary=summarize('codex',out/'stdout.jsonl',profile);session=resolve_session(profile,summary)
        ledger=ApiTimingLedger(timing).snapshot()
        answer=out/'first-valid-answer.private.json'
        result=dict(identity=cfg['identity'],session_id=session,CLI_exit_code=child.returncode,
            answer_recorded=answer.is_file(),answer_sha256=digest(answer)if answer.is_file()else None,
            api_timing=ledger,provider_transport=str(relay_dir/'transport.private.jsonl'),
            native_profile=str(profile),simulation_starts=0,graded=False,
            infrastructure_resume_implemented=False)
        write(out/'result.private.json',result)
        return result
    finally:
        # Stop admission and wait for the existing relay's graceful drain. No
        # timeout or kill, and no model/accepted work is replayed.
        if relay.poll()is None:relay.terminate()
        relay.wait();relay_log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();cfg=json.loads(a.config.read_text())
    print(json.dumps(execute(cfg)if a.execute else validate(cfg)))
