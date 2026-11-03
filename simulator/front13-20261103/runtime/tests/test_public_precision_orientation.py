from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_public_precision_orientation import orient


def rotation(axis,degrees):
    v=np.eye(3)[axis];a=np.deg2rad(degrees);k=np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
    return np.eye(3)+np.sin(a)*k+(1-np.cos(a))*(k@k)


@pytest.mark.parametrize('response',(1.,.95,.9))
def test_subminimum_net_error_uses_legal_legs_and_measured_response(response):
    target=np.diag([1.,-1.,-1.]);state=[rotation(2,.37)@rotation(0,.2)@rotation(1,-20)@target];calls=[]
    a=SimpleNamespace(control_report={'engineering_reference_only':True},scene=SimpleNamespace(robots={'left':object()},embodiment=SimpleNamespace(config={'control':{'rotation_deg':[.5,20.]}})),tcp_rotation_task=lambda side:state[0].copy())
    signs={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
    def act(left,right,mm,rotation_deg):
        assert right=='STILL'and .5<=rotation_deg<=20
        if left=='STILL':return
        calls.append((left,rotation_deg));i,s=signs[left];state[0]=rotation(i,s*rotation_deg*response)@state[0]
    a.act=act;orient(a,'left',target)
    assert len(calls)<=24 and np.linalg.norm(state[0]-target)<.001
    assert any(name.startswith('ROLL_') for name, _ in calls)


def test_final_measured_alignment_also_survives_retained_goal_settle():
    target=np.diag([1.,-1.,-1.]);state=[rotation(0,.2)@target];goal=[state[0].copy()]
    a=SimpleNamespace(control_report={'engineering_reference_only':True},scene=SimpleNamespace(robots={'left':object()},embodiment=SimpleNamespace(config={'control':{'rotation_deg':[.5,20.]}})),tcp_rotation_task=lambda side:state[0].copy())
    signs={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
    def act(left,right,mm,rotation_deg):
        if left=='STILL':state[0]=goal[0].copy();return
        i,s=signs[left];goal[0]=rotation(i,s*rotation_deg)@state[0];state[0]=rotation(i,s*rotation_deg*.9)@state[0]
    a.act=act;orient(a,'left',target)
    assert np.linalg.norm(state[0]-target)<.001 and np.allclose(state[0],goal[0])
