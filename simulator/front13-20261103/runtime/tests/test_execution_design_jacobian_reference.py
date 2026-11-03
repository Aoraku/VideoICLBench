import numpy as np
import pytest
from types import SimpleNamespace
from videoicl_isaaclab.execution_design_jacobian_reference import shift_to_tcp,capture


def test_shift_uses_tcp_minus_com_not_link_origin():
    j=np.zeros((6,7));j[4,0]=1
    actual=shift_to_tcp(j,[0,0,.024],[0,0,.1])
    assert actual[0,0]==pytest.approx(.076)
    assert actual[4,0]==1
    assert j[0,0]==0


def test_native_com_pose_is_cross_checked_and_recorded():
    robot=SimpleNamespace(is_fixed_base=True,root_physx_view=SimpleNamespace(
        get_coms=lambda:np.array([[[0,0,0,0,0,0,1],[0,0,.024,0,0,0,1]]]),
        get_jacobians=lambda:np.zeros((1,1,6,7))),data=SimpleNamespace(
        body_pos_w=np.array([[[0,0,0],[1,2,3]]]),body_quat_w=np.array([[[1,0,0,0],[1,0,0,0]]]),
        body_com_pos_w=np.array([[[0,0,0],[1,2,3.024]]]),body_link_pos_w=np.array([[[0,0,0],[1,2,3]]]),
        joint_pos=np.zeros((1,7)),joint_pos_limits=np.array([[[-2,2]]*7])))
    a=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot},embodiment=SimpleNamespace(tcp=[0,0,.1]),
        layout=SimpleNamespace(task_rotation=np.eye(3)),world_to_task=lambda p:p),tip=lambda side:np.array([1,2,3.1]),tcp_rotation_task=lambda side:np.eye(3))
    c=SimpleNamespace(ids={'left':(list(range(7)),[],1)})
    row=capture(a,c,'left');assert row['reference']['native_com_local']==[0,0,.024]
    assert row['reference']['body_com_pos_w_agreement_m']==pytest.approx(0)
    robot.data.body_com_pos_w[0,1,0]+=.001
    with pytest.raises(ValueError,match='mismatch'):capture(a,c,'left')
