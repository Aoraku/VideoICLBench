from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e08_reference import MeasuredShoeAuthor,solve_e08_reference
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Shoe:
    def __init__(self):
        self.a=SimpleNamespace(out=None,stage='shoe-label-end-left');self.c=SimpleNamespace(steps=0)
        self.p=np.array([-.11,.076,.87]);self.max_mm=10.;self.calls=[]
    def point(self,ref):return self.p.copy()
    def tip(self,side):return self.p+[-.08,0,.04]
    def move(self,*args,**kwargs):raise AssertionError('obsolete fixed TCP inner chase')
    def act(self,side,token,mm,follower):
        self.c.steps+=1;self.calls.append((token,mm));axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
        self.p[axis]+=sign*mm*.00073
        if axis!=2:self.p[2]-=.0004


def test_shoe_material_feedback_handles_measured_slip_without_inner_tcp_chase():
    p=Shoe();target=np.array([.08,.02,1.05]);guards=[]
    MeasuredShoeAuthor.move_point(p,'left',{'actor':'left_shoe'},target,lambda:guards.append(p.c.steps))
    assert np.max(abs(p.p-target))<=.002
    assert len(guards)==len(p.calls)+1 and all(mm<=10 for _,mm in p.calls)


def test_shoe_actual_lost_grip_stops_before_any_public_command():
    p=Shoe()
    def guard():raise ToolExecutionError('Actual grip lost')
    with pytest.raises(ToolExecutionError,match='grip lost'):
        MeasuredShoeAuthor.move_point(p,'left',{'actor':'left_shoe'},[0,0,1.05],guard)
    assert not p.calls


@pytest.mark.parametrize('task,revision,engineering,smooth',[('E09','embodied50-execution-v3-20261102',True,False),('E08','legacy',True,False),('E08','embodied50-execution-v3-20261102',False,False),('E08','embodied50-execution-v3-20261102',True,True)])
def test_reference_refuses_other_task_or_unapproved_contract(task,revision,engineering,smooth):
    a=SimpleNamespace(scene=SimpleNamespace(spec={'id':task,'execution_design':{'revision':revision},'author_smooth_recording':smooth}),control_report={'engineering_reference_only':engineering})
    with pytest.raises(ValueError,match='E08 v3'):solve_e08_reference(a)
