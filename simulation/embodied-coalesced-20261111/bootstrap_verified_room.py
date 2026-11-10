"""Bootstrap the reference GUI and public input before admitting its native CLI."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

root=Path(__file__).resolve().parent
sys.path[:0]=[str(root/'VideoICLBench/scripts/harbor'),str(root/'VideoICLBench/packages/sdk')]
from run_embodied_pool import start_room_budgets
from serve_embodied import load_assignment
from vic_sdk.embodied_codex_mcp import NativeStructuredTools, NATIVE_TOOL_INSTRUCTIONS, NATIVE_MODEL_INSTRUCTIONS
from vic_sdk.native_agent import private_json

def worker_for_new_room(engine, room):
    """Pin the released worker before the first CLI attempt in this world."""
    if (room/'cli').exists():
        raise RuntimeError('Room already has a CLI attempt')
    worker = root/'worker'
    selector = root/'verified-workers'/(engine+'.json')
    version = None
    if selector.is_file():
        record = json.loads(selector.read_text())
        version = record['sha256']
        if record['engine'] != engine or not re.fullmatch(r'[0-9a-f]{64}', version):
            raise ValueError('Invalid verified worker selector')
        if engine in ('dsh', 'zcode') and version == 'bd56c6883f078ae308d35d8238cceff4067c48809f678a3f56669fc782e80a8d':
            version = '2ff6baa4010970479330ac130445551baeae35ce4838f43b1f455ca1e84debfb'
        worker = root/('worker-'+version)
        index = (worker/'files.json').read_bytes()
        if hashlib.sha256(index).hexdigest() != version:
            raise ValueError('Worker release index mismatch')
        files = json.loads(index)
        if 'run.py' not in files:
            raise ValueError('Missing worker entry point')
        for name, expected in files.items():
            path = worker/name
            if not path.resolve().is_relative_to(worker.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Worker release file mismatch')
    expected = os.environ.get('VIC_VERIFIED_WORKER_VERSION')
    verified_glm_upgrade = (engine in ('dsh', 'zcode') and expected == 'bd56c6883f078ae308d35d8238cceff4067c48809f678a3f56669fc782e80a8d' and version == '2ff6baa4010970479330ac130445551baeae35ce4838f43b1f455ca1e84debfb')
    if expected is not None and expected != version and not verified_glm_upgrade:
        raise ValueError('Admitted worker version changed before room startup')
    script = worker/'run.py'
    with (room/'worker-version.private.json').open('x') as receipt:
        json.dump(dict(engine=engine, version=version, script=str(script),
                       runner_sha256=hashlib.sha256(script.read_bytes()).hexdigest()), receipt)
    return script

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser()
    p.add_argument('--case',type=Path,required=True)
    p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--condition',required=True)
    p.add_argument('--engine',required=True)
    a=p.parse_args()
    room=a.folder/'agent'
    room.mkdir(mode=0o700)
    connection_file=a.folder/'connection.private.json'
    conn=json.loads(connection_file.read_text())
    browser_path=os.environ.get('VIC_BROWSER_PATH')
    spec,instruction,media,rule=load_assignment(a.case,a.condition)
    identity=conn['identity']
    if (spec['task_id'],spec['variant'],spec['seed'])!=(identity['task_id'],identity['variant'],identity['seed']):
        raise RuntimeError('Assignment mismatch')
    if spec.get('qa_enabled') is not False or spec['budget']['max_actions']!=500 or spec['budget']['timeout_sec']!=0:
        raise RuntimeError('Assignment budget or QA mismatch')
    if (a.condition=='text_rule') != bool(rule) or (a.condition in ('real','sim')) != bool(media):
        raise RuntimeError('Assignment modality mismatch')
    if conn['pool_room_id'] != a.folder.name or conn['condition'] != a.condition:
        raise RuntimeError('GUI connection belongs to a different room or condition')
    if conn['max_actions'] != 500 or conn['timeout_seconds'] != 0 or conn['budget_start_deferred'] is not True:
        raise RuntimeError('GUI connection budget mismatch')
    if conn['demo'] != media:
        raise RuntimeError('GUI and model assigned different demonstrations')
    demo_path = None
    if media:
        assigned = room / 'assigned-input'
        assigned.mkdir(mode=0o700)
        demo_path = assigned / Path(media['path']).name
        shutil.copyfile(media['path'], demo_path)
        if hashlib.sha256(demo_path.read_bytes()).hexdigest() != media['sha256']:
            raise ValueError('Assigned video changed while freezing native CLI input')
    native_timeout = conn['native_response_timeout_seconds']
    browser_ms = 0 if native_timeout is None else math.ceil((native_timeout + 30) * 1000)
    actor=a.folder/conn['actor_token_file']
    cfg=dict(control_url=conn['control_url'],actor_token=actor.read_text().strip(),run_id=identity['run_id'],
        output_dir=str(room),condition=a.condition,max_actions=500,timeout_seconds=0,deadline_unix=None,
        demo_video=str(demo_path) if demo_path else None,budget_policy=conn['budget_policy'],agent_interaction='gui_only',
        api_failure_budget_policy=conn.get('api_failure_budget_policy'),agent_protocol='roboprobe_gui_v1',
        gui_viewport=[1440,1280],max_gui_inputs=10000,browser_path=browser_path,
        gui_settle_timeout_ms=browser_ms,gui_observation_timeout_ms=browser_ms,rule_diagnostic=False,embodied_harness='program_gui',
        native_structured_tools=True,program_episode_identity=identity,lean_text_projection=True,lean_text_mode='compact')
    private_json(room/'computer-private.json',cfg)
    private_json(room/'worker-owner.json',dict(connection=str(connection_file)))
    tool=NativeStructuredTools(cfg)
    try:
        _,public=tool.bootstrap_files()
    finally:
        tool.close()
    if public['observation']['step']!=0: raise RuntimeError('World already advanced')
    if rule: instruction+='\n\n'+rule
    if a.engine != 'qwen':
        # Claude Code already supplies both native contracts in its system prompt.
        tools = NATIVE_TOOL_INSTRUCTIONS.replace('The attached first GUI and public state are the initial observation.',
                                                 'Call observe for the initial GUI alongside the supplied public state.')
        instruction += '\n\n' + NATIVE_MODEL_INSTRUCTIONS + '\n' + tools
    (room/'prompt-1.txt').write_text(instruction+'\n\nInitial public observation and assigned demonstration metadata:\n'+json.dumps(public,ensure_ascii=False,separators=(',',':')))
    script = worker_for_new_room(a.engine, room)
    start_room_budgets([connection_file])
    key_file=Path(os.environ.pop('VIC_POOL_AUTHFILE'))
    with key_file.open('rb') as key:
        child=subprocess.run([sys.executable,str(script),'--engine',a.engine,
            '--room',str(room),'--out',str(room/'cli')],stdin=key)
    if child.returncode or not (room/'cli/result.json').exists():
        raise RuntimeError('No verified terminal result from worker')
if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Room held:',type(e).__name__,str(e)[:300],flush=True)
        threading.Event().wait()
