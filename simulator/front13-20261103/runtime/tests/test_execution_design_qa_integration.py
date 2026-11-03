"""Real exported SDK + GUI/MCP service integration, no browser/model/native launch."""
import asyncio
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from videoicl_isaaclab.execution_design_qa import prepare_assignment,write_assignment,export_sdk,sha,export_public_task,bind_native_spec
from videoicl_isaaclab.execution_design import REVISION,REVISION_V2,metadata

BANK=Path(__file__).parents[2]/'evaluation/rule_qa'


@pytest.fixture
def sdk(tmp_path,monkeypatch):
    root=tmp_path/'sdk';export_sdk(root)
    for name in list(sys.modules):
        if name=='vic_sdk' or name.startswith('vic_sdk.'):del sys.modules[name]
    monkeypatch.syspath_prepend(str(root))
    gate=importlib.import_module('vic_sdk.rule_qa_gate')
    gui=importlib.import_module('vic_sdk.embodied_gui_mcp')
    assert Path(gate.__file__).is_relative_to(root)
    yield gate,gui,root
    for name in list(sys.modules):
        if name=='vic_sdk' or name.startswith('vic_sdk.'):del sys.modules[name]


def assignment(tmp_path,condition,mode):
    source=tmp_path/(condition+'-'+mode+'.mp4');source.write_bytes(b'unit-test-media-not-a-real-demo')
    keys=json.loads((BANK/'answer_key.private.json').read_text())
    key=next(k for k in keys['questions']if k['task_id']=='E01')
    review=dict(status='reviewed',task_id='E01',variant='A',sha256=sha(source),source_sha256=key['sources']['A']['sha256'],
        rule_preserving_transcode=True,rule_matches_source=True,reviewer='test_fixture_only',evidence='CPU test fixture')
    return prepare_assignment('E01','A',4201,condition,mode,bank_dir=BANK,media_path=source,review=review)


def spec_for(a):
    return bind_native_spec(dict(task_id=a['task_id'],variant=a['variant'],seed=a['seed']),[a])


@pytest.mark.parametrize('condition',['I','E'])
@pytest.mark.parametrize('mode',['text_rule','real','sim'])
def test_exported_sdk_checks_new_identity_and_real_gui_action_gate(sdk,tmp_path,condition,mode):
    gate,gui,_=sdk;a,grading=assignment(tmp_path,condition,mode)
    task_dir=tmp_path/'task';write_assignment(task_dir,a)
    assert gate.load_assignment(task_dir,spec_for(a),mode,dict(sha256=a['source_sha256']))==a
    assert 'correct_option' not in json.dumps(a)
    config=dict(run_id='isolated-test-session',output_dir=str(tmp_path/'session'),condition=mode,rule_qa=a)
    g=gate.RuleQAGate(config)
    browser=gui.GuiBrowser.__new__(gui.GuiBrowser);browser.lock=threading.RLock();browser.qa_gate=g
    with pytest.raises(ValueError,match='Answer'):browser.act('frame',[dict(kind='wait',wait_ms=0)])
    for stop in ('done','giveup'):
        with pytest.raises(ValueError,match='Answer'):browser.terminal(stop,'','frame')
    with pytest.raises(ValueError):browser.qa_question()
    g.delivered(source_sha256=a['source_sha256'],seconds=None if mode=='text_rule' else 0.)
    with pytest.raises(ValueError):browser.qa_answer('A')
    question=browser.qa_question();assert question['question']==a['packet']
    assert not browser.qa_answer('invalid')['action_allowed']
    assert browser.qa_answer('D')['action_allowed']  # Correctness is never consulted.
    first=g.answer.read_bytes()
    assert browser.qa_answer('A')['reused_first_answer']
    assert g.answer.read_bytes()==first
    # Execute the actual exported GuiBrowser.act body against a fake GUI page.
    # No native simulator/browser/model is launched; successful dispatch after
    # the QA boundary is verified, not merely require_answer in isolation.
    calls=[];browser.check=lambda:None;browser._check_pending_input=lambda:None;browser._actor_activity=lambda:None
    browser._status=lambda:'running';browser.frame='frame';browser.actions=0;browser.max_gui_inputs=10
    browser._validate=lambda value:None;browser._input_button=lambda value:None
    browser.output=tmp_path;browser._visible_action_count=lambda:0
    browser.page=SimpleNamespace(wait_for_timeout=lambda delay:calls.append(delay));browser._settled=lambda:None
    browser.log=lambda value:None;browser._picture=lambda:dict(gui_action_allowed=True)
    assert browser.act('frame',[dict(kind='wait',wait_ms=0)])==dict(gui_action_allowed=True)
    assert calls==[0]
    resumed=gate.RuleQAGate(config);resumed.require_answer();assert resumed.answer.read_bytes()==first
    for field,value in [('run_id','other-session')]:
        changed=deepcopy(config);changed[field]=value
        with pytest.raises(ValueError,match='identity'):gate.RuleQAGate(changed)
    changed=deepcopy(config);changed['rule_qa']['revision']='different-revision'
    with pytest.raises(ValueError,match='identity'):gate.RuleQAGate(changed)


def test_mcp_service_exposes_qa_without_private_answer(sdk,tmp_path):
    gate,gui,_=sdk;a,_=assignment(tmp_path,'I','text_rule')
    g=gate.RuleQAGate(dict(run_id='service-test',output_dir=str(tmp_path/'service'),rule_qa=a))
    class Browser:
        condition='text_rule'
        config={'rule_qa':a}
        def qa_question(self):return g.question()
        def qa_answer(self,answer):return g.submit(answer)
    server=gui.make_server(Browser());tools=asyncio.run(server.list_tools())
    assert {'qa_question','qa_answer'}<={t.name for t in tools}
    assert 'correct_option' not in str(tools)
    async def call_flow():
        g.delivered(source_sha256=a['source_sha256'])
        question=await server.call_tool('qa_question',{})
        answer=await server.call_tool('qa_answer',{'answer':'C'})
        return question,answer
    question,answer=asyncio.run(call_flow())
    assert 'awaiting_answer' in str(question) and 'submitted' in str(answer)
    g.require_answer()
    assert 'correct_option' not in str(question)+str(answer)


def test_concurrent_first_answer_and_legacy_assignments_unchanged(sdk,tmp_path):
    gate,_,_=sdk;a,_=assignment(tmp_path,'I','text_rule')
    old={k:v for k,v in a.items() if k not in ('revision','generalization_condition','assignment_identity_sha256','seed','environment_base','paired_input_identity')}
    old['schema']='rule-qa-assignment-v1'
    task_dir=tmp_path/'legacy';write_assignment(task_dir,old)
    assert gate.load_assignment(task_dir,dict(task_id='E01',variant='A'),'text_rule',None)==old
    with pytest.raises(ValueError,match='legacy'):gate.load_assignment(task_dir,spec_for(a),'text_rule',None)
    c=dict(run_id='legacy-session',output_dir=str(tmp_path/'legacy-output'),rule_qa=old)
    g=gate.RuleQAGate(c);g.delivered(source_sha256=old['source_sha256']);g.question()
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(g.submit,'ABCDABCD'))
    first=g.answer.read_bytes();g.submit('A');assert g.answer.read_bytes()==first


def test_revision_and_private_answer_cannot_bypass_assignment_loader(sdk,tmp_path):
    gate,_,_=sdk;a,_=assignment(tmp_path,'I','text_rule');task_dir=tmp_path/'task';p=write_assignment(task_dir,a)
    wrong=spec_for(a);wrong['generalization_condition']='E'
    with pytest.raises(ValueError,match='identity'):gate.load_assignment(task_dir,wrong,'text_rule',None)
    bad=deepcopy(a);bad['packet']['correct_option']='B';p.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='four-option'):gate.load_assignment(task_dir,spec_for(a),'text_rule',None)


@pytest.mark.parametrize('condition',['I','E'])
def test_actual_agent_load_inputs_uses_exported_native_binding(sdk,tmp_path,condition):
    gate,_,_=sdk
    agent=importlib.import_module('vic_sdk.embodied_agent')
    assignments=[assignment(tmp_path,condition,m)[0] for m in ('text_rule','real','sim')]
    media={m:dict(path=str(tmp_path/(condition+'-'+m+'.mp4'))) for m in ('real','sim')}
    task=tmp_path/'public-task'
    spec=export_public_task(task,task='E01',variant='A',seed=4201,condition=condition,
        public_task=dict(task='E01',revision=REVISION,title='完整公开任务',instruction='按订单完成并送到指定区域。'),
        assignments=assignments,media=media)
    assert set(spec['qa_assignment_identities'])=={'text_rule','real','sim'}
    assert len(set(spec['qa_assignment_identities'].values()))==3
    assert not list(task.rglob('*private*'))
    for mode in ('text_rule','real','sim'):
        connection=dict(control_url='http://127.0.0.1:12345',actor_token_file='unused-actor',admin_token_file='unused-admin',
            condition=mode,identity=dict(run_id='no-server-started',task_id='E01',variant='A',seed=4201,suite='isolated-test',epoch='v2'),
            max_actions=500,timeout_seconds=0,budget_policy='effective_time_graceful_v1')
        path=tmp_path/'connection.private.json';path.write_text(json.dumps(connection))
        args=SimpleNamespace(embodied_task_dir=task,embodied_connection=path,condition=mode,max_actions=500,timeout=0,codex_compact_tokens=1000000)
        loaded=agent.load_inputs(args)  # Actual SDK preflight, no connection or model call.
        assert loaded[1]['generalization_condition']==condition
        assert gate.load_assignment(task,loaded[1],mode,loaded[-1])==next(a for a in assignments if a['source']==mode)
    native=task/'environment/native.json';bad=json.loads(native.read_text())
    bad['qa_assignment_identities']['sim']=bad['qa_assignment_identities']['real'];native.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='identity'):agent.load_inputs(args)


def test_all50_v3_legal_conditions_and_explicit_v2_sdk_compatibility(sdk,tmp_path):
    gate,_,_=sdk;count=0
    for task in [f'E{i:02}' for i in range(1,51)]:
        for condition in metadata(task)['support_mask']:
            a,_=prepare_assignment(task,'A',4201,condition,'text_rule',bank_dir=BANK)
            directory=tmp_path/(task+'-'+condition);write_assignment(directory,a)
            assert gate.load_assignment(directory,spec_for(a),'text_rule',None)==a
            count+=1
    assert count==137
    v2,_=prepare_assignment('E01','A',4201,'I','text_rule',bank_dir=BANK,revision=REVISION_V2)
    directory=tmp_path/'v2';write_assignment(directory,v2)
    assert gate.load_assignment(directory,spec_for(v2),'text_rule',None)==v2
    v3,_=prepare_assignment('E01','A',4201,'I','text_rule',bank_dir=BANK)
    with pytest.raises(ValueError,match='revision'):gate.load_assignment(directory,spec_for(v3),'text_rule',None)
    r,_=prepare_assignment('E12','A',4201,'R','text_rule',bank_dir=BANK)
    e,_=prepare_assignment('E12','A',4201,'E','text_rule',bank_dir=BANK)
    assert r['paired_input_identity']==e['paired_input_identity'] and r['assignment_identity_sha256']!=e['assignment_identity_sha256']
    with pytest.raises(ValueError,match='Incomplete source demo'):
        prepare_assignment('E05','A',4201,'I','real',bank_dir=BANK,media_path=tmp_path/'absent.mp4')
