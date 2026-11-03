from copy import deepcopy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_debug_restore import build_measured_pose_fixture,matrix_quaternion,tcp_pose_from_fingers
from videoicl_isaaclab.engineering_checkpoint import SCHEMA,reseal
from videoicl_isaaclab.layout import rotation_matrix


def inputs():
    spec=dict(id='E31',variant='B',seed=4201,embodiment_config_sha256='profile',execution_design=dict(assignment_identity_sha256='assignment',source_sha256='source'),objects=[dict(id='plate'),dict(id='bowl')])
    profile=dict(layout=dict(id='test',task_rotation=[2**-.5,0,0,2**-.5],task_translation=[.1,.2,-.06]),robots={s:dict(position=[i,.3,.8],rotation=[1,0,0,0])for s,i in [('left',-.2),('right',.2)]})
    objects={n:dict(pos=[0,.1,.9],mat=np.eye(3).tolist())for n in ('plate','bowl')}
    robots={s:dict(joint_names=['a','b'],q=[.1,.2],qd=None,grip=.04,tcp_position_task=[0,0,1.],tcp_quaternion_task=[1,0,0,0])for s in ('left','right')}
    return spec,profile,objects,robots


def test_legacy_fixture_preserves_pose_declares_missing_state_and_uses_shared_schema():
    spec,profile,objects,robots=inputs();original=deepcopy((spec,profile,objects,robots))
    cp=build_measured_pose_fixture(spec,profile,object_states=objects,robot_states=robots,source=dict(steps=836,physics_ticks=84440,dt=.004),stage='release')
    assert cp['schema']==SCHEMA and cp['state_quality']=='measured_pose_fixture'and cp['diagnostic_only']
    assert cp==reseal(cp)and cp['assumptions']
    assert cp['objects']['plate']['root_state_task'][:3]==objects['plate']['pos']
    assert cp['robots']['right']['joint_vel']==[0.,0.]
    assert cp['robots']['right']['drive_targets']==dict(position=None,velocity=None,effort=None)
    assert cp['controller']['rolling_reference']==cp['controller']['rolling_reference_velocity']=={}
    assert (spec,profile,objects,robots)==original
    assert not set(cp)&{'evaluator','success','strict_success','task_score_100'}


def test_native_tcp_and_finger_origins_recover_proper_frame():
    r=np.array([[0,0,1],[1,0,0],[0,1,0.]])
    tip=np.array([.1,.2,.9]);mid=tip-r[:,2]*.05
    pose=tcp_pose_from_fingers(tip,mid+r[:,1]*.02,mid-r[:,1]*.02)
    assert np.allclose(rotation_matrix(pose['quaternion']),r)
    with pytest.raises(ValueError):tcp_pose_from_fingers(tip,mid,mid)
    with pytest.raises(ValueError):matrix_quaternion(np.ones((3,3)))


def test_missing_or_duplicate_native_actor_joint_identities_rejected():
    spec,profile,objects,robots=inputs();robots['right']['joint_names']=['a','a']
    with pytest.raises(ValueError,match='Unique full'):build_measured_pose_fixture(spec,profile,object_states=objects,robot_states=robots,source=dict(steps=0,physics_ticks=1,dt=.004),stage='release')
    robots=inputs()[-1];objects.pop('bowl')
    with pytest.raises(ValueError,match='Complete recorded rigid'):build_measured_pose_fixture(spec,profile,object_states=objects,robot_states=robots,source=dict(steps=0,physics_ticks=1,dt=.004),stage='release')
