from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_tool_tracking import move_material
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

class Measured:
    def __init__(self, stalled=False):
        self.p=np.zeros(3);self.c=SimpleNamespace(steps=0);self.a=SimpleNamespace(stage='test',out=None)
        self.max_mm=12;self.stalled=stalled;self.actions=[]
    def point(self,ref):return self.p.copy()
    def tip(self,side):return self.p+np.array([.01,0,.02])
    def act(self,side,token,mm,follower):
        self.c.steps+=1;self.actions.append(token)
        if self.stalled:return
        axis,sgn={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
        self.p[axis]+=sgn*mm*.0008
        # Gravity introduces measured cross-axis drift, so a fixed TCP
        # micro-waypoint cannot be assumed equivalent to payload arrival.
        if axis!=2:self.p[2]-=.0005

def test_measured_payload_with_cross_axis_drift_converges():
    a=Measured();target=np.array([.06,.02,.03]);move_material(a,'right',{},target)
    assert np.max(abs(a.p-target))<=.002
    assert 'UP' in a.actions and len(a.actions)<100

def test_stalled_payload_fails_bounded():
    a=Measured(True)
    with pytest.raises(ToolExecutionError,match='stalled'):move_material(a,'left',{},[.06,0,0])
    assert a.c.steps==24

def test_guard_runs_even_at_endpoint():
    a=Measured()
    def guard():raise ToolExecutionError('grip lost')
    with pytest.raises(ToolExecutionError,match='grip lost'):move_material(a,'left',{},[0,0,0],guard)
    assert a.c.steps==0

@pytest.mark.parametrize('target',[[float('nan'),0,0],[0,0],[float('inf'),0,0]])
def test_invalid_target_rejected_before_actuation(target):
    a=Measured()
    with pytest.raises(ToolExecutionError):move_material(a,'left',{},target)
    assert a.c.steps==0

from videoicl_isaaclab.execution_design_pour_handoff import choose_pour_hand

def test_pouring_hand_matches_actual_destination_side():
    tips={'left':[-.19,.3,.9],'right':[-.19,-.3,.9]}
    assert choose_pour_hand(tips,[-.05,-.13,.81])=='right'
    assert choose_pour_hand(tips,[-.05,.13,.81])=='left'

from videoicl_isaaclab.execution_design_tool_tracking import guide_intercept_outside_launcher

@pytest.mark.parametrize('yaw',[0.,.6,1.2])
def test_guide_rotating_envelope_stays_outside_launcher(yaw):
    r=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]])
    p=np.array([.04,.035,.8]);half=np.array([.1195,.11,.01734]);guide=np.array([.09,.003,.015]);direction=np.array([-1.,0,0])
    target=guide_intercept_outside_launcher([-.055,.035,.817],direction,p,r,half,guide)
    for g_yaw in np.linspace(0,np.pi,17):
        extent=abs(np.cos(g_yaw))*.09+abs(np.sin(g_yaw))*.003
        assert (target-p)@direction-extent >= abs(r.T@direction)@half+.009999
    assert target[1]==pytest.approx(.035) and target[2]==pytest.approx(.817)

from videoicl_isaaclab.execution_design_tool_tracking import handle_level_push_rotation

@pytest.mark.parametrize('angle',[0,.7,1.8,-2.])
def test_source_handle_level_keeps_grasp_above_ball_working_edge(angle):
    direction=np.array([np.cos(angle),np.sin(angle),0.])
    r=handle_level_push_rotation([1.,0,0],direction)
    edge=np.array([.133285976,-.000161392,-.013085432]);grip=np.array([-.09033606,-.00043158,-.00263704])
    assert np.allclose(r@[1.,0,0],direction)
    assert np.allclose(r@[0,0,1],[0,0,1])
    assert (r@(grip-edge))[2]>.010

def test_persistent_joint_limit_stops_before_spending_full_waypoint_budget():
    a=Measured(True);a.c.action_feedback=lambda:{'control_feedback':{'right':{'joint_limit_names':['joint6']}}}
    with pytest.raises(ToolExecutionError,match='joint limit'):move_material(a,'right',{},[.06,0,0])
    assert a.c.steps==12
