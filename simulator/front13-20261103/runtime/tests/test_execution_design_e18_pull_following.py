"""Actual handle-relative and retained-target measurements are never assumed."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_reference import E18MeasuredAuthor
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError


def worker():
    w=E18MeasuredAuthor.__new__(E18MeasuredAuthor)
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=np.array([[.0014,.0015]]),joint_vel=np.array([[.0001,-.0001]])),
        find_joints=lambda _:([0,1],['panda_finger_joint1','panda_finger_joint2']))
    w.a=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot}),tcp_rotation_task=lambda _:np.eye(3));w.operations=[];w.min_mm=.5
    w.roles={'drawer':dict(mechanism='cabinet',joint='LeftSlide',contact_body='cabinet/left',direction=1)}
    w.points={'drawer':{}};w.mechanisms=lambda:{'cabinet':dict(joint_names=['LeftSlide'],joint_vel=[.0018])}
    w.point=lambda *args:np.array([.1,.2,.3]);w.axis=lambda *args:np.array([-1.,0,0])
    w.frame=lambda *args:(np.zeros(3),np.eye(3));tip=np.array([.09,.2005,.301]);w.tip=lambda _:tip.copy()
    w.displacement=lambda *args:.0085;w.touching=lambda *args,**kwargs:True
    forces={frozenset(('cabinet/left',f'left_finger{i}')):1.3 for i in (1,2)}
    w.c=SimpleNamespace(steps=166,contact_forces=forces,action_feedback=lambda:dict(control_feedback=dict(left=dict(
        requested_delta_m=[.003,0,0],actual_delta_m=[.002,0,0]))))
    calls=[]
    def act(*args,**kwargs):
        calls.append(args if not kwargs else args+(kwargs,))
        if args[1]=='FWD':tip[0]+=kwargs['mm']/1000
        elif args[1]=='DOWN':tip[2]-=kwargs['mm']/1000
        elif args[1]=='UP':tip[2]+=kwargs['mm']/1000
    w.act=act
    return w,calls


def test_actual_handle_offsets_and_unfinished_cartesian_goal_are_measured():
    w,_=worker();row=w._public_pull_observation('drawer','left',0)
    assert row['tcp_axial_offset_m']==pytest.approx(.01)
    assert row['tcp_lateral_offset_m']==pytest.approx(np.hypot(.0005,.001))
    np.testing.assert_allclose(row['retained_tcp_goal_error_task_m'],[.001,0,0])
    assert row['drawer_velocity_m_s']==pytest.approx(.0018)
    w.c.action_feedback=lambda:dict(control_feedback=dict(left={}))
    assert w._public_pull_observation('drawer','left',0)['retained_tcp_goal_error_task_m']is None


def test_exactly_one_real_grasp_is_used_without_velocity_wait_or_target_write():
    w,calls=worker();result=w.prepare_drawer_public_pull('drawer','left')
    assert calls==[('left','GRASP')]
    assert [row['phase_index']for row in w.operations]==[0,1]
    assert result['after']['bilateral_contact']
    assert not hasattr(w.c,'targets')


def test_actual_axial_drift_gets_only_one_public_inward_follow_before_grasp():
    w,calls=worker();w._e18_pull_reference={('drawer','left'):dict(axial_m=.007781968128777326,
        lateral_m=.0003404816092280285,source_action=162,engineering_calibration=True)}
    result=w.prepare_drawer_public_pull('drawer','left')
    assert calls==[('left','FWD',{'mm':1.}),('left','GRASP')]
    assert result['inward_follow']['requested_inward_mm']==1.
    assert [row['phase_index']for row in w.operations]==[0,3,1]
    assert result['after']['tcp_axial_offset_m']<result['before']['tcp_axial_offset_m']


def test_vertical_pad_follow_is_one_bounded_public_step_with_real_hand_floor_guard(monkeypatch):
    from videoicl_isaaclab import execution_design_e18_geometry as geometry
    w,calls=worker()
    monkeypatch.setattr(geometry,'actual_hand_clouds',lambda *args:dict(source='actual_native_collision_mesh_current_body_pose',
        clouds_tcp=[np.array([[0,0,-.05],[0,0,.01]])]*3,table_top=0.))
    result=w.follow_drawer_pad_z_once('drawer','left')
    assert len(calls)==1 and calls[0][1]=='DOWN'and .5<=calls[0][2]['mm']<=1.
    assert result['after']['tcp_minus_handle_task_m'][2]==pytest.approx(result['reference_z_m'])
    assert [row['phase_index']for row in w.operations]==[0,4]
    w,calls=worker()
    monkeypatch.setattr(geometry,'actual_hand_clouds',lambda *args:dict(source='actual_native_collision_mesh_current_body_pose',
        clouds_tcp=[np.array([[0,0,-.299]])]*3,table_top=0.))
    with pytest.raises(MechanismExecutionError,match='hand/table clearance'):w.follow_drawer_pad_z_once('drawer','left')
    assert calls==[]
