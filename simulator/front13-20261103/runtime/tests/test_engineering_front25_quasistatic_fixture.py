"""CPU adapter-contract tests; synthetic task identity is not native acceptance."""
from copy import deepcopy
import numpy as np
import pytest
from test_engineering_front25_fixture import fixture as measured_fixture
from test_engineering_checkpoint import all_writes
from videoicl_isaaclab import engineering_checkpoint as core
from videoicl_isaaclab.engineering_front25_quasistatic_fixture import (
    convert,require_retarget_and_readback,RESTORE_POLICY,RETARGET_POLICY)


def fixture(task='E25',missing=True):
    c,r=measured_fixture((4.,-3.,.2))
    # Reuse the CPU asset/profile harness with an explicitly synthetic identity.
    # This tests gates and field mapping, never an E23/E25 physical scene.
    c.scene.spec['id']=task;r['scene_input']=deepcopy(c.scene.spec)
    r['identity']=task+'-A-I-s4201';r['restore_policy']=deepcopy(RESTORE_POLICY)
    if missing:r['robot_feedback_same_tick']={'arms':{}}
    return c,r


@pytest.mark.parametrize('task',['E23','E25'])
def test_missing_arm_qd_is_assumed_and_tcp_placeholder_requires_later_native_retarget(task):
    c,r=fixture(task);record=deepcopy(r);before=core.capture(c,'unchanged');p=convert(c,r);after=core.capture(c,'unchanged')
    assert r==record and before==after and all_writes(c)==0 and c.steps==c.physics_ticks==0
    assert p['state_quality']=='measured_pose_fixture'and p['diagnostic_only']
    ctx=p['context'];assert ctx['requires_native_fk_retarget']and ctx['mandatory_native_fk_retarget']
    assert ctx['native_fk_retarget_completed']is False and ctx['historical_grasp_flags_restored']is False
    assert ctx['mandatory_physical_readback']==['pose','support_contacts','actual_grasps']
    assert p['controller']['tcp_targets_base']==before['controller']['tcp_targets_base']
    for side,row in p['robots'].items():
        d=r['robot_diagnostics'][side];finger=dict(zip(d['finger_joints']['names'],d['finger_joints']['velocities_m_s']))
        for name,value in zip(row['joint_names'],row['joint_vel']):
            assert value==(finger[name]if name in finger else 0.)
        assert ctx['arm_velocity_provenance'][side]=='ASSUMED_zero_quasistatic_debug'
    text='\n'.join(p['assumptions'])
    assert 'ASSUMED zero for quasistatic debug' in text and 'NOT measured' in text
    assert 'STARTUP PLACEHOLDERS ONLY'in text and 'MANDATORY'in text
    assert 'historical arm qd MEASURED'not in text


def test_available_measured_arm_qd_remains_measured_and_is_never_zeroed():
    c,r=fixture(missing=False);before=core.capture(c,'before');p=convert(c,r)
    for side,row in p['robots'].items():
        fb=r['robot_feedback_same_tick']['arms'][side];values=dict(zip(fb['joint_names'],fb['measured_sensors']['joint_velocities_rad_s']['value']))
        for name,value in values.items():assert row['joint_vel'][row['joint_names'].index(name)]==value
        assert p['context']['arm_velocity_provenance'][side]=='measured'
    assert p['controller']['tcp_targets_base']==before['controller']['tcp_targets_base']
    assert all_writes(c)==0


def test_partial_missing_tcp_and_one_missing_velocity_keep_provenance_separate():
    c,r=fixture(missing=False)
    r['robot_feedback_same_tick']['arms']['left']['tcp_quaternion_wxyz']=None
    r['robot_feedback_same_tick']['arms']['right']['measured_sensors']['joint_velocities_rad_s']={'available':False,'value':None}
    before=deepcopy(r);p=convert(c,r)
    assert r==before and p['context']['arm_velocity_provenance']=={'left':'measured','right':'ASSUMED_zero_quasistatic_debug'}


@pytest.mark.parametrize('absent',[False,True])
def test_entirely_absent_or_null_same_tick_feedback_is_explicitly_assumed(absent):
    c,r=fixture()
    if absent:r.pop('robot_feedback_same_tick')
    else:r['robot_feedback_same_tick']=None
    p=convert(c,r)
    assert set(p['context']['arm_velocity_provenance'].values())=={'ASSUMED_zero_quasistatic_debug'}


def test_server_local_original_provenance_is_verified_without_reconstruction_claim():
    c,r=fixture();r['scene_input_provenance'].update(literal_remote_scene_input_readback=True,server_local_source_verified=True)
    p=convert(c,r)
    assert 'literal source scene SERVER-LOCAL'in '\n'.join(p['assumptions'])
    r['scene_input_provenance']['server_local_source_verified']=False
    with pytest.raises(ValueError,match='provenance'):convert(c,r)


def test_explicit_diagnostic_arm_velocity_is_preserved_without_invented_feedback():
    c,r=fixture();r['robot_diagnostics']['left']['arm_joints']['velocities_rad_s']=[.012]*7
    p=convert(c,r)
    assert r['robot_feedback_same_tick']['arms']=={}
    assert p['context']['arm_velocity_provenance']['left']=='measured'
    assert all(p['robots']['left']['joint_vel'][p['robots']['left']['joint_names'].index('panda_joint'+str(i))]==.012 for i in range(1,8))


def test_disagreeing_measured_velocity_sources_are_not_replaced_by_zero():
    c,r=fixture(missing=False)
    r['robot_diagnostics']['left']['arm_joints']['velocities_rad_s']=[.5]*7
    with pytest.raises(ValueError,match='velocity sources disagree'):convert(c,r)


@pytest.mark.parametrize('task',['E14','E19','E24','E26'])
def test_scope_rejects_unregistered_task_families(task):
    c,r=fixture(task)
    with pytest.raises(ValueError,match='registered front25'):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('task',['E17','E20','E23','E25'])
def test_registered_families_still_require_native_retarget(task):
    c,r=fixture(task)
    checkpoint=convert(c,r)
    assert checkpoint['state_quality']=='measured_pose_fixture'
    assert checkpoint['context']['requires_native_fk_retarget']is True
    assert all_writes(c)==0


@pytest.mark.parametrize('change',['missing','wrong_velocity','wrong_tcp','extra','full_checkpoint','not_debug','history'])
def test_quasistatic_assumptions_require_exact_explicit_policy(change):
    c,r=fixture()
    if change=='missing':r.pop('restore_policy')
    elif change=='wrong_velocity':r['restore_policy']['arm_velocity']='measured'
    elif change=='wrong_tcp':r['restore_policy']['tcp_target']='default'
    elif change=='extra':r['restore_policy']['allow_score']=True
    elif change=='full_checkpoint':r['schema']=core.SCHEMA
    elif change=='not_debug':r['debug_only']=False
    else:r['history_reconstructed']=True
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['assignment','source','profile','geometry','catalog','case','objects','robot','arm_joint','finger_joint','finger_qd','mechanisms'])
def test_all_identity_inventory_and_measured_finger_guards_are_retained(field):
    c,r=fixture()
    if field=='assignment':r['scene_input']['execution_design']['assignment_identity_sha256']='d'*64
    elif field=='source':r['scene_input']['execution_design']['source_sha256']='d'*64
    elif field=='profile':r['scene_input']['embodiment_config_sha256']='d'*64
    elif field=='geometry':r['scene_input']['objects'][0]['size'][0]+=.001
    elif field=='catalog':r['scene_input_provenance']['catalog_sha256']='d'*64
    elif field=='case':r['identity']='E25-B-I-s4201'
    elif field=='objects':r['state_task'].pop('lid')
    elif field=='robot':r['robot_diagnostics'].pop('right')
    elif field=='arm_joint':r['robot_diagnostics']['left']['arm_joints']['names'][0]='panda_joint2'
    elif field=='finger_joint':r['robot_diagnostics']['right']['finger_joints']['names'].pop()
    elif field=='finger_qd':r['robot_diagnostics']['right']['finger_joints'].pop('velocities_m_s')
    else:r['mechanisms']['unknown']={}
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['arm_q','finger_q','finger_qd','measured_qd','contradictory_qd','null_measured_qd','tcp','feedback_q'])
def test_nonfinite_or_contradictory_measurements_cannot_be_replaced_by_assumptions(field):
    c,r=fixture(missing=False);d=r['robot_diagnostics']['left'];fb=r['robot_feedback_same_tick']['arms']['left']
    if field=='arm_q':d['arm_joints']['positions_rad'][0]=np.nan
    elif field=='finger_q':d['finger_joints']['positions_m'][0]=np.inf
    elif field=='finger_qd':d['finger_joints']['velocities_m_s'][0]=np.nan
    elif field=='measured_qd':fb['measured_sensors']['joint_velocities_rad_s']['value'][0]=np.nan
    elif field=='contradictory_qd':fb['measured_sensors']['joint_velocities_rad_s']['available']=False
    elif field=='null_measured_qd':fb['measured_sensors']['joint_velocities_rad_s']['value']=None
    elif field=='tcp':fb['tcp_quaternion_wxyz']=[0,0,0,0]
    else:fb['joint_positions_rad'][0]+=.0001
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('field',['evaluator','history','success','task_score_100','initial_sealed','grasp','grasp_flags','controller'])
def test_no_history_score_or_grasp_injection(field):
    c,r=fixture();r[field]=True
    with pytest.raises(ValueError):convert(c,r)
    assert all_writes(c)==0


def test_historical_grasp_observation_is_not_assigned_to_fresh_fixture():
    c,r=fixture();baseline=convert(c,r)
    for state in r['state_task'].values():state['grasp']=[True,True]
    p=convert(c,r)
    assert p['objects']==baseline['objects']and p['controller']==baseline['controller']
    assert p['context']['historical_grasp_flags_restored']is False


@pytest.mark.parametrize('problem',['missing_receipt','zero_ticks','two_ticks','boolean_ticks','not_retargeted','wrong_policy','not_readback','missing_contact','missing_grasp'])
def test_mandatory_retarget_and_actual_readback_gate(problem):
    c,r=fixture();p=convert(c,r)
    receipt={'quasi_static_retarget_physics_ticks':1,'native_fk_retarget_completed':True,'stage_entry_controller_policy':RETARGET_POLICY}
    readback={'diagnostic_only':True,'passed':True,'missing_contacts':[],'missing_grasps':[]}
    if problem=='missing_receipt':receipt={}
    elif problem=='zero_ticks':receipt['quasi_static_retarget_physics_ticks']=0
    elif problem=='two_ticks':receipt['quasi_static_retarget_physics_ticks']=2
    elif problem=='boolean_ticks':receipt['quasi_static_retarget_physics_ticks']=True
    elif problem=='not_retargeted':receipt['native_fk_retarget_completed']=False
    elif problem=='wrong_policy':receipt['stage_entry_controller_policy']='default_tcp'
    elif problem=='not_readback':readback['passed']=False
    elif problem=='missing_contact':readback['missing_contacts']=[['lid','table']]
    else:readback['missing_grasps']=[['lid','left']]
    with pytest.raises(ValueError):require_retarget_and_readback(p,receipt,readback)


def test_completed_native_retarget_and_warmup_allow_only_unscored_segment():
    c,r=fixture();p=convert(c,r)
    receipt={'quasi_static_retarget_physics_ticks':1,'native_fk_retarget_completed':True,'stage_entry_controller_policy':RETARGET_POLICY}
    readback={'diagnostic_only':True,'passed':True,'missing_contacts':[],'missing_grasps':[]}
    assert require_retarget_and_readback(p,receipt,readback)==dict(ready_for_local_segment=True,diagnostic_only=True,full_task_acceptance=False)
    p['objects']['lid']['root_state_task'][0]+=.001
    with pytest.raises(ValueError,match='integrity'):core.restore_startup(c,p)
    assert all_writes(c)==0
