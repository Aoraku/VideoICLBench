import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e37_regrip import winding_room,predicted_turn_room


def test_reverse_wrist_winding_uses_directional_not_unsigned_limit_margin():
    limits=np.array([[-2.8973,2.8973]]*7)
    q=np.zeros(7);q[-1]=2.5
    forward=winding_room(q,limits,np.eye(3),[0.,0.,1.],1.)
    reverse=winding_room(q,limits,np.eye(3),[0.,0.,1.],-1.)
    assert forward['wrist_room_rad']==pytest.approx(.3973)
    assert not forward['admissible']
    assert reverse['wrist_room_rad']==pytest.approx(5.3973)
    assert reverse['admissible']


def test_rewinding_wrist_does_not_license_another_joint_already_at_its_stop():
    limits=np.array([[-2.8973,2.8973]]*7)
    q=np.zeros(7);q[2]=2.85
    result=winding_room(q,limits,np.eye(3),[0.,0.,1.],1.)
    assert result['wrist_room_rad']>2.
    assert not result['admissible']
    with pytest.raises(ValueError,match='original limits'):
        winding_room(q+10.,limits,np.eye(3),[0.,0.,1.],1.)
    with pytest.raises(ValueError,match='Nonzero'):
        winding_room(q,limits,np.eye(3),[0.,0.,0.],1.)


def test_signed_turn_predictor_only_limits_joints_moving_towards_the_stop():
    jacobian=np.column_stack((np.eye(6),np.zeros(6)))
    limits=np.array([[-2.,2.]]*7);q=np.zeros(7);q[0]=1.98
    positive=predicted_turn_room(jacobian,q,limits,[1.,0,0,0,0,0],.05)
    negative=predicted_turn_room(jacobian,q,limits,[-1.,0,0,0,0,0],.05)
    assert positive['safe_angle_rad']==0.
    assert negative['safe_angle_rad']>3.9
    assert positive['limiting_joint']==negative['limiting_joint']==0
    assert negative['prediction_only']
