from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.realworld_tool_expert import ToolAuthor,ToolExecutionError

class E09:
    def __init__(self, revision='embodied50-execution-v3-20261102',engineering=True):
        self.task='E09';self.spec={'execution_design':{'revision':revision}}
        self.a=SimpleNamespace(control_report={'engineering_reference_only':engineering},out=None,stage='blue-triangle')
        self.c=SimpleNamespace(steps=0);self.max_mm=8.;self.p=np.array([.075,.074,1.0]);self.calls=[]
    def point(self,ref):return self.p.copy()
    def tip(self,side):return self.p+np.array([.01,-.002,.03])
    def move(self,*args,**kwargs):raise AssertionError('fixed inner TCP chase invoked')
    def act(self,side,token,mm,follower):
        self.c.steps+=1;self.calls.append((token,mm))
        axis,sgn={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
        self.p[axis]+=sgn*mm*.00073
        if axis!=2:self.p[2]-=.0004

def test_e09_remeasures_payload_without_fixed_inner_tcp_chase():
    a=E09();target=np.array([.10,.10,1.02]);guard_calls=[]
    ToolAuthor.move_point(a,'right',{'actor':'blue_triangle'},target,lambda:guard_calls.append(a.c.steps),tolerance=.002)
    assert max(abs(a.p-target))<=.002
    assert len(guard_calls)==len(a.calls)+1
    assert 0<len(a.calls)<100 and all(mm<=8 for _,mm in a.calls)

@pytest.mark.parametrize('revision,engineering',[('old',True),('embodied50-execution-v3-20261102',False)])
def test_e09_legacy_and_formal_branch_unchanged(revision,engineering):
    a=E09(revision,engineering)
    with pytest.raises(AssertionError,match='fixed inner'):
        ToolAuthor.move_point(a,'right',{},[.10,.10,1.02])

def test_e09_lost_grip_stops_before_any_command():
    a=E09()
    def guard():raise ToolExecutionError('grip lost')
    with pytest.raises(ToolExecutionError,match='grip lost'):
        ToolAuthor.move_point(a,'right',{},[.10,.10,1.02],guard)
    assert not a.calls
