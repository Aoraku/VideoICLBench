from types import SimpleNamespace
import copy
import numpy as np
import pytest
from videoicl_isaaclab import engineering_tool_suffix as suffix
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
from videoicl_isaaclab.execution_design import REVISION_V3


def setup_case(tmp_path,monkeypatch,task='E42',entry='e42-push-remaining',context=None):
    events=[];native_semantic=dict(groups=dict(balls=['pink_ball','red_ball']),tools=dict(main=dict(actor='spatula',grasp_local=[0,0,0],jaw_axis_local=[1,0,0],hand='right')))
    spec=dict(id=task,variant='A',seed=4201,execution_design=dict(revision=REVISION_V3),semantic=native_semantic)
    c=SimpleNamespace(steps=0,_engineering_diagnostic_only=True)
    author=SimpleNamespace(c=c,out=tmp_path,scene=SimpleNamespace(spec=spec),control_report=dict(engineering_reference_only=True))
    checkpoint=dict(diagnostic_only=True,identity={'case':task},context={},checkpoint_sha256='a'*64)
    request=dict(entry=entry,context=context or dict(remaining_balls=['red_ball']))
    monkeypatch.setattr(suffix,'identity',lambda c:{'case':task})
    monkeypatch.setattr(suffix,'capture',lambda c,stage,ctx:dict(stage=stage,context=ctx))
    class Policy:
        def __init__(self,a):
            self.a=a;self.c=a.c;self.spec=a.scene.spec;self.s=self.spec['semantic'];self.operations=[]
        def require_held(self,grip,side):events.append(('held',grip['actor'],side))
        def tool(self):pytest.fail('Repeated source tool acquisition')
        def push(self):
            self.tool();events.append(('push',list(self.s['groups']['balls'])));self.c.steps+=1
    monkeypatch.setattr(suffix,'ToolAuthor',Policy)
    return author,checkpoint,request,events


def test_e42_restored_tool_skips_acquisition_and_only_executes_declared_remaining_ball(tmp_path,monkeypatch):
    a,c,r,events=setup_case(tmp_path,monkeypatch);before=copy.deepcopy(a.scene.spec)
    result=suffix.solve(a,c,r)
    assert ('push',['red_ball'])in events
    assert a.scene.spec==before
    assert result['diagnostic_only']and not result['source_initial_full_positive']
    assert result['suffix_completed']and result['actions']==1
    assert len(list(tmp_path.glob('suffix-*.checkpoint.private.json')))==2


def test_unknown_or_unvalidated_entry_cannot_act(tmp_path,monkeypatch):
    a,c,r,events=setup_case(tmp_path,monkeypatch)
    for bad in (dict(r,entry='replay_entire_task'),):
        with pytest.raises(ToolExecutionError,match='validated tool'):suffix.solve(a,c,bad)
    a.c._engineering_diagnostic_only=False
    with pytest.raises(ToolExecutionError,match='validated tool'):suffix.solve(a,c,r)
    assert not events and a.c.steps==0


def test_remaining_case_identity_is_required(tmp_path,monkeypatch):
    a,c,r,events=setup_case(tmp_path,monkeypatch,context={'remaining_balls':['other_episode_ball']})
    with pytest.raises(ToolExecutionError,match='remaining source'):suffix.solve(a,c,r)
    assert a.c.steps==0 and not any(e[0]=='push'for e in events)


def test_e43_dispatches_only_existing_guide_to_gate_stage(tmp_path,monkeypatch):
    from videoicl_isaaclab import execution_design_e43_trigger as trigger
    a,c,r,events=setup_case(tmp_path,monkeypatch,'E43','e43-open-gate',{})
    a.scene.spec['semantic']['tools']['main']['actor']='guide'
    monkeypatch.setattr(trigger,'open_upper_gate',lambda p,g,s:events.append(('open_gate',g['actor'],s)))
    result=suffix.solve(a,c,r)
    assert ('open_gate','guide','right')in events
    assert result['actions']==0 and result['physics_success_not_asserted']


@pytest.mark.parametrize('task,entry,function',[
    ('E43','e43-cooked-ball-audit','ball_support_audit'),
    ('E45','e45-sweep-audit','pour_sweep_audit'),
])
def test_restored_geometry_audit_dispatch_issues_no_public_action(tmp_path,monkeypatch,task,entry,function):
    from videoicl_isaaclab import engineering_tool_geometry_audit as audit
    a,c,r,events=setup_case(tmp_path,monkeypatch,task,entry,{'cup_side':'right'})
    def read_only(*args):events.append(('geometry_read',function))
    monkeypatch.setattr(audit,function,read_only)
    result=suffix.solve(a,c,r)
    assert events==[('geometry_read',function)]
    assert result['actions']==0 and result['native_validation_required']
    assert not result['source_initial_full_positive']


def test_e45_receive_suffix_does_not_repeat_original_cup_acquisition_or_handoff(tmp_path,monkeypatch):
    from videoicl_isaaclab import execution_design_pour_handoff as handoff
    a,c,r,events=setup_case(tmp_path,monkeypatch,'E45','e45-receive-and-pour',{'cup_side':'right'})
    semantic=a.scene.spec['semantic'];semantic.update(containers=dict(cup=dict(object='cup',grasp_local=[0,0,.03],jaw_axis_local=[1,0,0],lower=[-.04,-.04,-.03872],upper=[.04,.04,.044])),tool_expert=dict(hand='left'))
    a.scene.spec['objects']=[dict(id='cup',size=[.04,.04,.04])];held=[False]
    class Policy:
        def __init__(self,a):self.a=a;self.c=a.c;self.spec=a.scene.spec;self.s=self.spec['semantic'];self.operations=[];self.clearance=1.06;self.task='E45'
        def tip(self,s):return np.array([-.19,.30 if s=='left' else 0.,.95])
        def destination(self,n):return np.array([-.05,-.13,.81])
        def snapshot(self):return({'cup':dict(pos=np.array([-.19,0,.84]),mat=np.eye(3),grasp=[False,held[0]])},set())
        def contact(self,*args):return True
        def acquire(self,ref,side):events.append(('actual_acquire',side));held[0]=True
        def require_held(self,ref,side):assert held[0]and side=='right'
        def pour(self):
            self.acquire({'actor':'cup'},self.s['tool_expert']['hand'])
            events.append(('pour',self.s['tool_expert']['hand']))
    monkeypatch.setattr(suffix,'ToolAuthor',Policy)
    monkeypatch.setattr(handoff,'orient_empty_pour_hand',lambda *args,**kwargs:events.append(('select_pour_frame',kwargs['transport_clearance'])))
    result=suffix.solve(a,c,r)
    assert events.count(('actual_acquire','right'))==1
    assert ('pour','right')in events
    assert semantic['tool_expert']['hand']=='left'
    assert result['diagnostic_only']
