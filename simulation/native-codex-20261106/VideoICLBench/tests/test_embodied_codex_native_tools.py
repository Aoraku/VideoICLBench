"""Real native CLI tool contract, synthetic executor only: no API/browser/world."""
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

from vic_sdk.embodied_codex_mcp import NativeStructuredTools, make_server
from vic_sdk.native_agent import codex_config
from vic_sdk.direct_tools import freeze_direct_model_catalog

IDENTITY=dict(run_id='native-one',task_id='E22',variant='C',seed=4201,suite='test',epoch=1)
IMAGE=dict(type='input_image',image_url='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode(),detail='high')

def observation(step=0):
    return dict(frame_id='gui-'+str(step),step=step,max_robot_actions=500,episode_status='running',
        image=deepcopy(IMAGE),camera_views={'head':{'width':960,'height':720}},
        public_observation={'native_frame_id':'native-'+str(step),'action_schema':{'tokens':['UP','HOLD']}})

def pair(): return dict(left='UP',right='HOLD',step_mm=10,rotation_deg=5)

class FakeExecutor:
    def __init__(self): self.calls=[];self.fail=False;self.closed=False;self.invalid=False
    def initialize(self):
        return dict(observation=observation(),demo_info=dict(available=True,source_sha256='a'*64,duration_seconds=10,on_demand=True))
    def _validate(self, commands):
        if self.invalid: raise ValueError('remaining budget exhausted')
        assert len(commands)==1
        if commands[0]['type']=='action_batch' and not 1<=len(commands[0]['actions'])<=24: raise ValueError('24 maximum')
        return deepcopy(commands)
    def execute(self, commands,decision_id):
        self.calls.append((deepcopy(commands),decision_id))
        if self.fail: raise ConnectionError('unknown accepted request')
        command=commands[0]
        if command['type']=='depth_points':
            return dict(results=[dict(command=command,ok=True,physical_commit=False,measurements=[dict(
                camera='head',frame_id='n1',pixel=[2,3],depth_m=.123456789,valid=True,
                xyz_task_m=[.1,.2,.3],xyz_world_m=[1,2,3],camera_calibration={'K':[[1,0,0],[0,1,0],[0,0,1]]})])],
                observation=observation(),physical_commits=0,pending=False,uncertain=False,terminal=False)
        n=len(command.get('actions',[]))
        receipts=[dict(index=i,step=i+1,status='completed',action=action,receipt={'control_feedback':{
            'left':{'status':'blocked' if i==0 else 'reached','reason':'IK' if i==0 else None,
                'actual_delta_m':[0,0,0] if i==0 else [0,0,.01],'position_error_m':.01 if i==0 else 0},'right':None}})
            for i,action in enumerate(command.get('actions',[]))]
        batch=dict(batch_id=decision_id,status='completed',requested_count=n,completed_count=n,physical_action_count=n,receipts=receipts)
        obs=observation(n);obs['action_batch']=deepcopy(batch)
        return dict(results=[dict(ok=True,physical_commit=bool(n),physical_action_count=n,receipt=batch)],
            observation=obs,physical_commits=int(bool(n)),physical_action_count=n,pending=False,uncertain=False,terminal=False)
    def close(self): self.closed=True

@pytest.fixture
def backend(tmp_path):
    return NativeStructuredTools(dict(output_dir=str(tmp_path),program_episode_identity=IDENTITY),executor=FakeExecutor())

def text(reply): return json.loads(reply.content[0].text)

def test_24_ordered_pairs_one_executor_commit_and_exact_feedback_archive(backend):
    reply=backend.action_batch('batch-one',[pair() for _ in range(24)])
    assert len(backend.executor.calls)==1
    assert len(backend.executor.calls[0][0][0]['actions'])==24
    payload=text(reply)
    assert payload['physical_commits']==1 and payload['physical_action_count']==24
    assert 'action_batch' not in payload['observation']
    raw=backend.state['events'][-1]['results'][0]['receipt']['receipts']
    assert raw[0]['receipt']['control_feedback']['left']['status']=='blocked'
    assert raw[0]['receipt']['control_feedback']['left']['actual_delta_m']==[0,0,0]
    shown=reply.content[0].text
    assert 'blocked' in shown and 'IK' in shown and len(shown.encode())<24000
    assert [x.type for x in reply.content]==['text','image']
    assert 'base64' not in shown


def test_25_rejected_without_claim_or_execute(backend):
    with pytest.raises(ValueError,match='24'): backend.action_batch('too-many',[pair()]*25)
    assert backend.executor.calls==[] and backend.state['operations']=={}


def test_duplicate_completed_id_is_lookup_before_budget_validation(backend):
    backend.action_batch('same',[pair()])
    backend.executor.invalid=True
    assert not backend.action_batch('same',[pair()]).isError
    assert len(backend.executor.calls)==1
    with pytest.raises(ValueError,match='different'): backend.action_batch('same',[dict(pair(),step_mm=5)])


def test_unknown_claim_survives_restart_and_blocks_all_new_physical_and_done(backend):
    backend.executor.fail=True
    with pytest.raises(ConnectionError): backend.action_batch('unknown',[pair()])
    recovered=NativeStructuredTools(backend.config,executor=FakeExecutor())
    with pytest.raises(ValueError,match='unresolved'): recovered.action_batch('unknown',[pair()])
    with pytest.raises(ValueError,match='reconciliation'): recovered.action_batch('new',[pair()])
    with pytest.raises(ValueError,match='Unresolved'): recovered.terminal('done','claim')
    assert recovered.executor.calls==[]


def test_depth_exact_coordinates_calibration_ref_no_unchanged_gui(backend):
    reply=backend.information('depth_points',camera='head',pixels=[[2,3]])
    payload=text(reply);measurement=payload['results'][0]['measurements'][0]
    assert measurement['depth_m']==.123456789
    assert measurement['xyz_task_m']==[.1,.2,.3]
    assert measurement['xyz_world_m']==[1,2,3]
    assert measurement['calibration_ref'] in payload['measurement_calibrations']
    assert 'observation' not in payload and [x.type for x in reply.content]==['text']
    assert backend.executor.calls[0][0][0]['type']=='depth_points'


def test_bootstrap_once_and_same_episode_public_history_only(backend):
    file,metadata=backend.bootstrap_files();second,again=backend.bootstrap_files()
    assert file==second and metadata==again and len(backend.state['events'])==1
    assert file.read_bytes()==base64.b64decode(IMAGE['image_url'].split(',')[1])
    history=backend.history(1,include_images=True)
    assert len(history.content)==2 and len(backend.state['events'])==1
    with pytest.raises(ValueError): backend.history(2)
    cfg=dict(backend.config,program_episode_identity=dict(IDENTITY,run_id='different'))
    with pytest.raises(ValueError,match='different episode'): NativeStructuredTools(cfg,executor=FakeExecutor())


def test_only_seven_structured_tools_no_program_or_workspace(backend):
    tools=asyncio.run(make_server(backend).list_tools())
    assert {tool.name for tool in tools}=={'action_batch','observe','depth_points','demo_frames','history','done','giveup'}


def test_native_config_real_compaction_not_host_history(tmp_path):
    server=dict(command=sys.executable,args=['absolute-entry.py','--config','private.json'])
    cfg=tomllib.loads(codex_config('gpt-6-astra','https://invalid.test/v1',server,
        context_window=262144,compact_tokens=120000,tool_output_tokens=32768,isolated_tools=True,effort='high'))
    assert cfg['model_context_window']==262144
    assert cfg['model_auto_compact_token_limit']==120000
    assert cfg['tool_output_token_limit']==32768
    assert cfg['model_reasoning_effort']=='high' and cfg['features']['shell_tool'] is False
    source=tmp_path/'catalog.json';source.write_text(json.dumps({'models':[{'slug':'gpt-6-astra','tool_mode':'code_mode_only','supports_parallel_tool_calls':True}]}))
    pin=hashlib.sha256(source.read_bytes()).hexdigest();profile=tmp_path/'profile';profile.mkdir()
    receipt=freeze_direct_model_catalog(profile,source,pin,'gpt-6-astra',cli_version='codex-cli 0.163.0',serial_tools=True)
    target=json.loads(Path(receipt['catalog_path']).read_text())['models'][0]
    assert target['supports_parallel_tool_calls'] is False and target['tool_mode']=='direct'


def test_absolute_entry_help_ignores_ambient_old_sdk(tmp_path):
    old=tmp_path/'vic_sdk';old.mkdir();(old/'__init__.py').write_text("raise RuntimeError('wrong SDK')")
    entry=Path(__file__).parents[1]/'packages/sdk/vic_sdk/embodied_codex_mcp_entry.py'
    import os
    env=dict(os.environ,PYTHONPATH=str(tmp_path))
    result=subprocess.run([sys.executable,str(entry),'--help'],capture_output=True,text=True,env=env,timeout=20)
    assert result.returncode==0,result.stderr
    assert '--config' in result.stdout


def test_real_embodied_entry_routes_native_profile_without_legacy_stop_hook(tmp_path,monkeypatch):
    from test_embodied_native_agent import inputs,artifacts
    from vic_sdk import embodied_agent,native_structured_supervisor
    args=inputs(tmp_path,{'url':'http://127.0.0.1:1'},condition='real')
    args.native_structured_tools=True;args.embodied_harness='program_gui'
    args.codex_context_window=262144;args.codex_compact_tokens=120000
    catalog=json.loads(args.codex_model_catalog.read_text())
    catalog['models'][0].update(context_window=262144,max_context_window=1050000,auto_compact_token_limit=120000)
    args.codex_model_catalog.write_text(json.dumps(catalog));args.codex_model_catalog_sha256=hashlib.sha256(args.codex_model_catalog.read_bytes()).hexdigest()
    seen={}
    def fake_supervise(args,**kwargs): seen.update(kwargs);return 73
    monkeypatch.setattr(native_structured_supervisor,'run',fake_supervise)
    assert embodied_agent.run(args)==73
    out=artifacts(args);profile=out/'profile'
    cfg=tomllib.loads((profile/'config.toml').read_text())
    assert cfg['model_context_window']==262144 and cfg['model_auto_compact_token_limit']==120000
    assert cfg['tool_output_token_limit']==32768 and cfg['model_reasoning_effort']=='high'
    assert not (profile/'hooks.json').exists()
    assert '--dangerously-bypass-hook-trust' not in seen['command']
    assert Path(cfg['model_instructions_file']).read_text().startswith('Control this embodied episode')
    assert 'embodied_codex_mcp_entry.py' in cfg['mcp_servers']['vic']['args'][0]
    assert Path(cfg['mcp_servers']['vic']['args'][0]).is_absolute()
    assert 'PROGRAM' not in cfg['developer_instructions']
    assert seen['metadata']['compaction']['implementation']=='native Codex automatic compaction'
    assert seen['metadata']['compaction']['tool_output_token_limit']==32768
    assert json.loads((out/'computer-private.json').read_text())['native_structured_tools'] is True


def test_cached_completed_batch_is_explicitly_historical_and_no_old_image(backend):
    backend.action_batch('id',[pair()])
    reply=backend.action_batch('id',[pair()]);payload=text(reply)
    assert payload['cached_receipt'] is True and payload['observation_is_current'] is False
    assert [block.type for block in reply.content]==['text']
    assert len(backend.executor.calls)==1


def test_actual_mcp_action_pair_schema_is_explicit_and_closed(backend):
    tools=asyncio.run(make_server(backend).list_tools())
    schema=next(tool.inputSchema for tool in tools if tool.name=='action_batch')
    actions=schema['properties']['actions']
    assert actions['minItems']==1 and actions['maxItems']==24
    pair_schema=schema['$defs'][actions['items']['$ref'].rsplit('/',1)[-1]]
    assert set(pair_schema['required'])=={'left','right','step_mm','rotation_deg'}
    assert set(pair_schema['properties'])=={'left','right','step_mm','rotation_deg'}
    assert pair_schema['additionalProperties'] is False
    assert pair_schema['properties']['step_mm']['type']=='number'
    assert pair_schema['properties']['rotation_deg']['type']=='number'
    assert 'millimetres' in pair_schema['properties']['step_mm']['description']


def test_actual_mcp_validates_pair_before_any_backend_commit(backend):
    server=make_server(backend)
    good=asyncio.run(server.call_tool('action_batch',{'operation_id':'typed','actions':[pair()]}))
    assert len(backend.executor.calls)==1
    for invalid in (dict(pair(),extra='no'),{'left':'UP'},dict(pair(),step_mm=float('inf')),dict(pair(),rotation_deg=True)):
        try:
            reply=asyncio.run(server.call_tool('action_batch',{'operation_id':'invalid','actions':[invalid]}))
        except Exception:
            pass  # FastMCP rejects malformed arguments before invoking the tool.
        else:
            assert getattr(reply,'isError',False)
    assert len(backend.executor.calls)==1
