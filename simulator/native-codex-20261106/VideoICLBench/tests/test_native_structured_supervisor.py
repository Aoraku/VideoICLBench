"""Process/HTTP mocks only: ordinary CLI exits never seal a physical world."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from vic_sdk import native_structured_supervisor as s

IDENTITY=dict(run_id='native-one',task_id='E22',variant='C',seed=4201,suite='test',epoch=1)
TIMING=dict(transport_quiescent_confirmed=True,ledger_integrity_valid=True,active=False,active_request_count=0,pending_log_write=False)

def owner(status='running',model_stop=None,snapshot=False,timing=None):
    return dict(identity=deepcopy(IDENTITY),state=dict(condition='real',steps=0,status=status),owner_barrier=dict(
        schema='videoicl-owner-action-barrier-v1',action_count=0,status=status,
        terminal_snapshot_ready=snapshot,model_stop=model_stop,api_timing_log='/fixed/provider.jsonl',
        api_timing=deepcopy(TIMING if timing is None else timing)))

@pytest.mark.parametrize('status,stop,expected',[
    ('running',None,False),('finished',None,False),('budget_paused',None,False),
    ('stopped',None,False),('sealed',None,False),('closed',None,False),
    ('done','done',True),('give_up','give_up',True),('budget_exhausted',None,True)])
def test_only_true_native_terminal_with_snapshot_identity_and_drain(status,stop,expected):
    value=owner(status,stop,True)
    assert s.native_terminal_proven(value,IDENTITY) is expected
    value['owner_barrier']['api_timing']['active']=True
    assert not s.native_terminal_proven(value,IDENTITY)
    value=owner(status,stop,True);value['identity']['run_id']='different'
    assert not s.native_terminal_proven(value,IDENTITY)
    value=owner(status,stop,True);value['owner_barrier']['action_count']=1
    assert not s.native_terminal_proven(value,IDENTITY)

class HoldStop(BaseException): pass

class Response:
    def __init__(self,value): self.value=value
    def raise_for_status(self): return self
    def json(self): return deepcopy(self.value)

class Client:
    def __init__(self,after): self.after=after;self.calls=[];self.states=0
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def get(self,path):
        self.calls.append(('get',path));self.states+=1
        return Response(owner() if self.states==1 else self.after)
    def post(self,path,**kwargs):
        self.calls.append(('post',path));return Response(dict(success=True))

class Bootstrap:
    def __init__(self,config): self.out=config['output_dir']
    def bootstrap_files(self):
        from pathlib import Path
        path=Path(self.out)/'initial.png';path.write_bytes(b'fake PNG')
        return path,dict(observation={'frame_id':'first'},demo_info={'source_sha256':'a'*64})
    def close(self): pass


def setup(tmp_path,monkeypatch,after,*,errors=None,exit_code=0):
    client=Client(after);commands=[];prompts=[];recoveries=[]
    monkeypatch.setattr(s.httpx,'Client',lambda **kwargs:client)
    monkeypatch.setattr(s,'NativeStructuredTools',Bootstrap)
    class Process:
        returncode=exit_code
        def __init__(self,cmd,**kwargs): commands.append(cmd)
        def communicate(self,prompt): prompts.append(prompt)
    monkeypatch.setattr(s.subprocess,'Popen',Process)
    monkeypatch.setattr(s,'summarize',lambda *a:dict(session_id='stable-native-session',errors=errors or [],usage={}))
    monkeypatch.setattr(s,'resolve_session',lambda profile,summary,session: 'stable-native-session')
    monkeypatch.setattr(s,'retire_exited_cli_tools',lambda p: recoveries.append('retire'))
    monkeypatch.setattr(s,'recover_control',lambda *a,**k:recoveries.append(k['failure']) or False)
    profile=tmp_path/'profile';profile.mkdir();workspace=tmp_path/'workspace';workspace.mkdir()
    args=SimpleNamespace(condition='real',embodied_auto_recover=True,codex_context_window=262144,
        codex_compact_tokens=120000,model='gpt-6-astra',binary='/fixed/codex')
    result=dict(native_attempts=[],recovery=dict(attempt_count=0,resume_count=0))
    def hold(out,reason): raise HoldStop(reason)
    def invoke(): return s.run(args,out=tmp_path,profile=profile,workspace=workspace,identity=IDENTITY,
        connection=dict(control_url='http://invalid.test',api_timing_log='/fixed/provider.jsonl'),
        computer=dict(output_dir=str(tmp_path)),instruction='TASK ONCE',server={},
        command=['/fixed/codex','exec','-C',str(workspace),'-'],env={},model_key='DUMMY',admin_key='DUMMY',
        ready=False,metadata={},result=result,hold=hold)
    return invoke,client,commands,prompts,recoveries,result


def test_clean_cli_final_without_done_preserves_and_recovers_same_session_no_seal(tmp_path,monkeypatch):
    invoke,client,commands,prompts,recoveries,result=setup(tmp_path,monkeypatch,owner())
    with pytest.raises(HoldStop): invoke()
    assert all(path not in ('/api/private/seal','/api/private/close','/api/private/evaluate') for _,path in client.calls)
    assert recoveries==['retire','native_exit_without_terminal']
    assert commands[0][-3:]==['--image',str(tmp_path/'initial.png'),'-']
    assert prompts[0].count('TASK ONCE')==1


def test_provider_502_exit_never_seals_or_closes(tmp_path,monkeypatch):
    invoke,client,_,_,recoveries,_=setup(tmp_path,monkeypatch,owner(),errors=['502 gateway'],exit_code=1)
    with pytest.raises(HoldStop): invoke()
    assert recoveries==['retire','transport']
    assert not any(path.endswith(('/seal','/close','/evaluate')) for _,path in client.calls)


def test_unresolved_accepted_input_or_non_drained_api_blocks_retire_and_recovery(tmp_path,monkeypatch):
    value=owner();value['owner_barrier']['api_timing']['active']=True
    invoke,client,_,_,recoveries,_=setup(tmp_path,monkeypatch,value)
    with pytest.raises(HoldStop,match='fully_drained'): invoke()
    assert recoveries==[] and not any(path.endswith('/close') for _,path in client.calls)


def test_true_terminal_still_waits_for_drain_no_cleanup(tmp_path,monkeypatch):
    value=owner('done','done',True);value['owner_barrier']['api_timing']['pending_log_write']=True
    invoke,client,_,_,recoveries,_=setup(tmp_path,monkeypatch,value)
    with pytest.raises(HoldStop,match='fully_drained'): invoke()
    assert recoveries==[] and not any(path.endswith(('/close','/evaluate','/seal')) for _,path in client.calls)


def test_proven_native_terminal_evaluates_then_closes_never_seals(tmp_path,monkeypatch):
    from vic_sdk import embodied_agent
    monkeypatch.setattr(embodied_agent,'checked_evaluation',lambda value,identity:dict(success=True,score=100))
    invoke,client,commands,_,recoveries,result=setup(tmp_path,monkeypatch,owner('done','done',True))
    assert invoke()==0
    assert [path for method,path in client.calls if method=='post']==['/api/private/start','/api/private/evaluate','/api/private/close']
    assert result['scored'] is True and result['cleanup_confirmed'] is True and recoveries==[]


def test_unknown_tool_claim_blocks_infrastructure_resume(tmp_path,monkeypatch):
    directory=tmp_path/'native-structured';directory.mkdir()
    (directory/'state.private.json').write_text(json.dumps({'operations':{'a':{'state':'unknown'}}}))
    invoke,client,_,_,recoveries,_=setup(tmp_path,monkeypatch,owner())
    with pytest.raises(HoldStop,match='unresolved'): invoke()
    assert recoveries==[] and not any(path.endswith('/close') for _,path in client.calls)


def test_authentication_error_with_zero_cli_exit_is_not_misclassified_as_early_final(tmp_path,monkeypatch):
    invoke,client,_,_,recoveries,_=setup(tmp_path,monkeypatch,owner(),errors=['401 invalid API key'],exit_code=0)
    with pytest.raises(HoldStop,match='nonrecoverable'): invoke()
    assert recoveries==[] and not any(path.endswith(('/seal','/close')) for _,path in client.calls)
