from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_pickup_clearance import rim_plan,grasp_position

def mesh(lo,hi):return np.array([[x,y,z]for x in (lo[0],hi[0])for y in (lo[1],hi[1])for z in (lo[2],hi[2])])

def test_rim_grasp_uses_finger_pad_below_lip_and_palm_above_lip():
    tcp=np.array([0,0,1.]);palm=mesh([-.05,-.05,1.035],[.05,.05,1.1])
    fingers=[mesh([-.05,-.01,.99],[-.03,.01,1.04]),mesh([.03,-.01,.99],[.05,.01,1.04])]
    bowl=mesh([-.063,-.063,.802],[.063,.063,.854])
    plan=rim_plan([-.062,0,.85],bowl,tcp,palm,fingers,.8)
    assert plan['tcp_target_task_m'][2]==pytest.approx(.822)
    assert .802<plan['finger_pad_center_z']<.854
    assert plan['palm_clearance_m']==pytest.approx(.003)
    assert .99+plan['tcp_target_task_m'][2]-1.>.8
    assert plan['native_grasp_verified']is False

def test_thin_plate_has_no_pad_overlap_and_is_not_claimed_graspable():
    tcp=np.array([0,0,1.]);palm=mesh([-.05,-.05,1.035],[.05,.05,1.1])
    fingers=[mesh([-.05,-.01,.99],[-.03,.01,1.04]),mesh([.03,-.01,.99],[.05,.01,1.04])]
    with pytest.raises(ValueError,match='No real rim'):rim_plan([0,0,.802],mesh([-.05,-.05,.8],[.05,.05,.803]),tcp,palm,fingers,.8)

def test_no_formal_route_optin():
    with pytest.raises(ValueError,match='Explicit'):grasp_position(SimpleNamespace(scene=SimpleNamespace(spec={})), 'left',{})
