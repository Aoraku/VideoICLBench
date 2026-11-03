"""Historical pose fixtures keep assumptions and never inject task results."""
from copy import deepcopy
from pathlib import Path
import json
import math
import numpy as np
import pytest
from test_engineering_checkpoint import Asset,controller as native_controller,all_writes
from videoicl_isaaclab import engineering_checkpoint as core
from videoicl_isaaclab.engineering_front25_fixture import convert
from videoicl_isaaclab.layout import rotation_matrix,multiply_quaternions


RECORD=Path(__file__).parents[2]/'verification/task-design-revision-20261102/native-e24-measured-empty-transit-slot15-v8/historical-checkpoint-829.private.json'


def fixture(origin=(0.,0.,0.)):
    record=json.loads(RECORD.read_text());c=native_controller(origin)
    c.scene.spec=deepcopy(record['scene_input'])
    root=deepcopy(c.scene.objects['object'].data.root_state_w[0])
    c.scene.objects={name:Asset(root)for name in record['state_task']}
    c.scene.mechanisms={};c.scene.passive_efforts={}
    arm=['panda_joint'+str(i)for i in range(1,8)];fingers=['panda_finger_joint1','panda_finger_joint2']
    c.scene.embodiment.config={'gripper':{'joints':fingers,'open':[.04,.04],'closed':[0.,0.]}}
    c.scene.robots={};c.targets={};c.grips={};c.ids={}
    for side,y in [('left',.3),('right',-.3)]:
        # Deliberately nontrivial base rotation and native name order.
        task_root=[-.65,y,.81,math.cos(.2),0,math.sin(.2),0,*([0.]*6)]
        world=core._root_to_world(c.scene,task_root)
        names=arm+fingers if side=='left'else [fingers[1],arm[3],*arm[:3],*arm[4:],fingers[0]]
        asset=Asset(world,names)
        asset.data.joint_pos_limits=np.array([[([0.,.04]if n in fingers else[-4.,4.])for n in names]])
        c.scene.robots[side]=asset
        c.ids[side]=([names.index(n)for n in arm],[names.index(n)for n in fingers],0)
        c.targets[side]=(np.array([[99.,88.,77.]]),np.array([[1.,0.,0.,0.]]));c.grips[side]=.04
    return c,record


def test_real_829_fixture_preserves_measured_velocities_and_declares_new_holds():
    c,r=fixture((5.,-3.,.2));before=core.capture(c,'before');p=convert(c,r);after=core.capture(c,'after')
    assert p['state_quality']=='measured_pose_fixture'and p['diagnostic_only']
    assert p['source']=={'steps':829,'physics_ticks':83740,'dt':.004}
    assert p['stage']=='E24-lid-public-push-setup'
    for group in ('objects','robots','mechanisms','controller'):assert before[group]==after[group]
    assert all_writes(c)==0 and c.steps==c.physics_ticks==0
    for name,row in p['objects'].items():
        assert set(row)=={'root_state_task'}
        assert row['root_state_task'][:3]==r['state_task'][name]['pos']
        assert np.allclose(rotation_matrix(row['root_state_task'][3:7]),r['state_task'][name]['mat'],atol=2e-6)
        assert row['root_state_task'][7:]==[0.]*6
    for side,row in p['robots'].items():
        diag=r['robot_diagnostics'][side];fb=r['robot_feedback_same_tick']['arms'][side]
        q=dict(zip(diag['arm_joints']['names'],diag['arm_joints']['positions_rad']))
        q.update(zip(diag['finger_joints']['names'],diag['finger_joints']['positions_m']))
        qd=dict(zip(fb['joint_names'],fb['measured_sensors']['joint_velocities_rad_s']['value']))
        qd.update(zip(diag['finger_joints']['names'],diag['finger_joints']['velocities_m_s']))
        assert row['joint_pos']==[q[n]for n in row['joint_names']]
        assert row['joint_vel']==[qd[n]for n in row['joint_names']]
        assert row['drive_targets']['velocity']==row['drive_targets']['effort']==[0.]*9
        for n in diag['arm_joints']['names']:
            assert row['drive_targets']['position'][row['joint_names'].index(n)]==q[n]
    assert p['controller']['grips']['left']==0.
    measured_mean=np.mean(r['robot_diagnostics']['right']['finger_joints']['positions_m'])
    assert p['controller']['grips']['right']==pytest.approx(measured_mean)
    assert p['controller']['rolling_reference']==p['controller']['rolling_reference_velocity']=={}
    text='\n'.join(p['assumptions'])
    assert 'historical public grip command UNKNOWN' in text and 'NEW debug hold' in text
    assert 'NOT literal remote' in text and 'velocities are MISSING' in text
    assert p['context']['source_evidence']==r['source_evidence']
    assert p['context']['scene_input_provenance']['literal_remote_scene_input_readback']is False
    evaluation=c.evaluator;core.restore_startup(c,p)
    assert c.evaluator is evaluation and evaluation.completion_label=='untouched'
    assert c.steps==c.physics_ticks==0 and c._engineering_diagnostic_only


def test_measured_tcp_converts_into_fresh_base_and_ignores_default_target():
    c,r=fixture((4.,-7.,.3));p=convert(c,r)
    for side,target in p['controller']['tcp_targets_base'].items():
        base=np.asarray(p['robots'][side]['root_state_task']);fb=r['robot_feedback_same_tick']['arms'][side]
        expected=rotation_matrix(base[3:7]).T@(np.asarray(fb['tcp_position'])-base[:3])
        inverse=base[3:7]*[1,-1,-1,-1];expected_q=multiply_quaternions(inverse,fb['tcp_quaternion_wxyz'])
        assert np.allclose(target['position'],expected,atol=1e-12)
        assert abs(np.dot(target['quaternion'],expected_q))==pytest.approx(1.)
        assert not np.allclose(target['position'],[99,88,77])
    c2,_=fixture((-8.,12.,-.1));p2=convert(c2,r)
    for side in p['controller']['tcp_targets_base']:
        assert np.allclose(p['controller']['tcp_targets_base'][side]['position'],p2['controller']['tcp_targets_base'][side]['position'])


def test_new_unknown_hold_maps_profile_endpoints_to_the_correct_finger_names():
    c,r=fixture();c.scene.embodiment.config['gripper']={
        'joints':['panda_finger_joint2','panda_finger_joint1'],'open':[.039,.038],'closed':[.001,.002]}
    r['robot_diagnostics']['right']['finger_joints']['positions_m']=[.01,.0115]
    p=convert(c,r);right=p['robots']['right'];left=p['robots']['left']
    assert p['controller']['grips']['right']==pytest.approx(.01)
    assert right['drive_targets']['position'][right['joint_names'].index('panda_finger_joint2')]==pytest.approx(.0105)
    assert right['drive_targets']['position'][right['joint_names'].index('panda_finger_joint1')]==pytest.approx(.011)
    assert left['drive_targets']['position'][left['joint_names'].index('panda_finger_joint2')]==pytest.approx(.001)
    assert left['drive_targets']['position'][left['joint_names'].index('panda_finger_joint1')]==pytest.approx(.002)


@pytest.mark.parametrize('field',['debug_only','engineering_only','history_reconstructed'])
def test_fixture_cannot_promote_historical_measurements_to_native_history(field):
    c,r=fixture();r[field]=not r[field]
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['assignment_identity_sha256','source_sha256','embodiment_config_sha256','physical','catalog','case'])
def test_identity_hash_mismatch_rejected_without_writes(field):
    c,r=fixture()
    if field in ('assignment_identity_sha256','source_sha256'):r['scene_input']['execution_design'][field]='d'*64
    elif field=='embodiment_config_sha256':r['scene_input'][field]='d'*64
    elif field=='physical':r['scene_input']['objects'][0]['size'][0]+=.001
    elif field=='catalog':r['scene_input_provenance']['catalog_sha256']='d'*64
    else:r['identity']='E24-B-I-s4201'
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['object','robot','arm_joint','finger_joint','duplicate_joint','arm_velocity','finger_velocity','mechanism'])
def test_missing_or_duplicate_native_inventory_rejected(field):
    c,r=fixture()
    if field=='object':r['state_task'].pop('lid')
    elif field=='robot':r['robot_diagnostics'].pop('right')
    elif field=='arm_joint':r['robot_diagnostics']['left']['arm_joints']['names'][0]='absent_joint'
    elif field=='finger_joint':r['robot_diagnostics']['right']['finger_joints']['names'].pop()
    elif field=='duplicate_joint':r['robot_diagnostics']['left']['arm_joints']['names'][0]='panda_joint2'
    elif field=='arm_velocity':r['robot_feedback_same_tick']['arms']['left']['measured_sensors']['joint_velocities_rad_s']['available']=False
    elif field=='finger_velocity':r['robot_diagnostics']['right']['finger_joints'].pop('velocities_m_s')
    else:r['mechanisms']['unknown']={}
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['object_pos','object_rotation','arm_q','arm_qd','finger_qd','tcp','grip'])
def test_nonfinite_measurements_are_not_silently_filled(field):
    c,r=fixture()
    if field=='object_pos':r['state_task']['lid']['pos'][0]=np.nan
    elif field=='object_rotation':r['state_task']['lid']['mat'][0][0]=np.inf
    elif field=='arm_q':r['robot_diagnostics']['left']['arm_joints']['positions_rad'][0]=np.nan
    elif field=='arm_qd':r['robot_feedback_same_tick']['arms']['left']['measured_sensors']['joint_velocities_rad_s']['value'][0]=np.nan
    elif field=='finger_qd':r['robot_diagnostics']['right']['finger_joints']['velocities_m_s'][0]=np.nan
    elif field=='tcp':r['robot_feedback_same_tick']['arms']['right']['tcp_position'][0]=np.nan
    else:r['grips']['right']=np.nan
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['evaluator','history','success','task_score_100','initial_sealed','grasp','grasp_flags','controller'])
def test_score_history_or_grasp_injection_is_rejected(field):
    c,r=fixture();r[field]=True
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


def test_historical_grasp_flags_do_not_become_grip_commands_or_restored_flags():
    c,r=fixture();baseline=convert(c,r)
    for state in r['state_task'].values():state['grasp']=[True,True]
    for name in r['robot_diagnostics']['object_grasps']:r['robot_diagnostics']['object_grasps'][name]=[True,True]
    p=convert(c,r)
    assert p['controller']==baseline['controller']and p['objects']==baseline['objects']
    assert all('grasp'not in row for row in p['objects'].values())
    assert p['context']['historical_grasp_flags_restored']is False


def test_resealed_output_has_real_core_integrity_validation():
    c,r=fixture();p=convert(c,r);p['objects']['lid']['root_state_task'][0]+=.001
    with pytest.raises(ValueError,match='integrity'):core.restore_startup(c,p)
    assert all_writes(c)==0


def test_mechanism_measured_q_qd_mapped_by_native_joint_names():
    c,r=fixture();root=c.scene.robots['left'].data.root_state_w[0]
    c.scene.mechanisms={'hinge':Asset(root,['hinge2','hinge1'])}
    c.scene.spec['mechanisms']=[{'id':'hinge','kind':'articulation'}]
    r['scene_input']=deepcopy(c.scene.spec)
    r['mechanisms']={'hinge':{'joint_names':['hinge1','hinge2'],'joint_pos':[.1,.2],'joint_vel':[-.03,.04]}}
    p=convert(c,r);row=p['mechanisms']['hinge']
    assert row['joint_pos']==[.2,.1]and row['joint_vel']==[.04,-.03]
    assert row['drive_targets']=={'position':[.2,.1],'velocity':[0.,0.],'effort':[0.,0.]}
    assert all_writes(c)==0
