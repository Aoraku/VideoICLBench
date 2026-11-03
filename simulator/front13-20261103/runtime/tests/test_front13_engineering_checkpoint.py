from types import SimpleNamespace
import copy
import json
import numpy as np
import pytest
import torch
from test_engineering_checkpoint import controller as fixture_controller,all_writes
from videoicl_isaaclab import front13_engineering_checkpoint as cp
from videoicl_isaaclab.layout import rotation_matrix


def controller():
    c=fixture_controller();c.scene.spec['id']='E01';c.scene.mechanisms={};c.scene.passive_efforts={}
    c._engineering_branch_authorized=True;c.device='cpu'
    c.sim=SimpleNamespace(current_time=0.,forward=lambda:None)
    c.scene.update_physics=lambda dt:None
    c.public_feedback=lambda:{'arms':{'left':{'tcp_position':[.1,.2,.3]}}}
    c.pose=lambda side:(np.array([[.1,.2,.3]]),np.array([[1.,0,0,0.]]))
    c.scene.embodiment.gripper_values=lambda fraction:[.04*fraction]
    c.ids={'left':([0],[1],0)}
    c._public_reference={'left':np.array([[.1]])}
    c._public_reference_velocity={'left':np.array([[.01]])}
    return c


def test_roundtrip_keeps_native_and_controller_state_without_history(tmp_path):
    a=controller();a.steps=225;a.physics_ticks=23340
    a._public_rotation_intent={'left':True};a._public_failures={'left':torch.tensor([2])}
    a._public_tolerances={'left':(.002,.005)}
    author=SimpleNamespace(stage='held-before-yaw',control_report={'engineering_reference_only':True})
    p=cp.capture(a,author,{'entry':'yaw','source_cumulative_steps':225})
    path=tmp_path/'checkpoint.json';receipt=cp.save(p,path)
    assert receipt['sha256'] and cp.load(path)==p
    b=controller();target_author=SimpleNamespace(stage='startup')
    result=cp.restore(b,p,target_author)
    assert result['native_readback_verified'] and result['eligible_full_acceptance']is False
    assert b.steps==225 and b.physics_ticks==23340
    assert b._public_rotation_intent=={'left':True}
    assert b._public_tolerances['left']==(.002,.005)
    assert b._public_failures['left'].tolist()==[2]
    assert target_author.stage=='held-before-yaw'
    assert b.evaluator.completion_label=='untouched'
    with pytest.raises(ValueError,match='single-use'):cp.restore(b,p)


@pytest.mark.parametrize('change',['authorize','scope','source','joint','hash','forward'])
def test_reject_before_any_state_write(change,tmp_path):
    a=controller();p=cp.capture(a);b=controller()
    if change=='authorize':b._engineering_branch_authorized=False
    elif change=='scope':p['debug_only']=False
    elif change=='source':b.scene.spec['execution_design']['source_sha256']='e'*64
    elif change=='joint':p['robots']['left']['joint_names'].reverse();p=cp.native.reseal(p)
    elif change=='hash':p['stage']='tampered'
    elif change=='forward':b.sim.forward=None
    with pytest.raises(ValueError):cp.restore(b,p)
    assert all_writes(b)==0


def legacy(c):
    p=cp.capture(c);root=p['objects']['object']['root_state_task']
    return {'schema':'videoicl-engineering-legacy-boundary-v1',
        'identity':dict(id='E01',variant='A',seed=4201,assignment_identity_sha256='a'*64,source_sha256='c'*64),
        'native_state':{'actions':224,'native_physics_tick':23339,
                        'state':{'object':{'pos':root[:3],'mat':rotation_matrix(root[3:7]).tolist(),'grasp':[True,False]}}},
        'action_receipt':{'step_after':225,'shared_tick_after':23340,'stage':'held-before-yaw',
                         'tips':{'left':[.1,.2,.3]},'robot_diagnostics':{'left':{
                             'arm_joints':{'names':['j1'],'positions_rad':[.2]},
                             'finger_joints':{'names':['j2'],'positions_m':[.01]}}}},
        'context':{'source_cumulative_steps':225}}


def test_legacy_import_declares_missing_dynamics_and_rebuilds_actual_start():
    c=controller();p=cp.from_legacy(c,legacy(c))
    assert p['state_quality']=='measured_pose_fixture' and p['reset_servo_to_measured']
    assert p['assumptions'] and p['source']['steps']==225
    assert p['robots']['left']['joint_vel']==[0.,0.]
    assert p['robots']['left']['drive_targets']['position']==[.2,0.]
    b=controller();result=cp.restore(b,p)
    assert result['source_actions']==225 and b._public_action is None
    assert b._public_reference=={} and b.grips=={'left':0.}
    assert b.evaluator.completion_label=='untouched'


@pytest.mark.parametrize('field',['step_after','shared_tick_after'])
def test_legacy_mismatched_tick_or_action_boundary_is_refused(field):
    c=controller();old=legacy(c);old['action_receipt'][field]+=1
    with pytest.raises(ValueError,match='same boundary'):cp.from_legacy(c,old)
    assert all_writes(c)==0


def test_modified_saved_payload_fails_integrity(tmp_path):
    p=tmp_path/'point.json';cp.save(cp.capture(controller()),p)
    value=json.loads(p.read_text());value['source']['steps']=999;p.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='SHA mismatch'):cp.load(p)


def test_native_fixed_rigid_restore_uses_pose_only(monkeypatch):
    source=controller();source.scene.objects['object'].data.root_state_w[:,7:]=0.
    point=cp.capture(source);target=controller();asset=target.scene.objects['object']
    asset.data.root_state_w[:,7:]=0.
    def pose(value):asset.writes.append('pose-only');asset.data.root_state_w[:,:7]=value
    asset.write_root_pose_to_sim=pose
    monkeypatch.setattr(cp.native,'_native_kinematic_rigid',lambda value:value is asset)
    result=cp.restore(target,point)
    assert asset.writes==['pose-only'] and result['native_readback_verified']


def test_nonzero_fixed_velocity_rejected_before_any_writes(monkeypatch):
    source=controller();point=cp.capture(source);target=controller();asset=target.scene.objects['object']
    asset.write_root_pose_to_sim=lambda value:None
    monkeypatch.setattr(cp.native,'_native_kinematic_rigid',lambda value:value is asset)
    with pytest.raises(ValueError,match='Nonzero kinematic velocity'):cp.restore(target,point)
    assert all_writes(target)==0


def test_legacy_retains_available_finger_velocity_instead_of_zeroing_it():
    c=controller();row=legacy(c);row['action_receipt']['robot_diagnostics']['left']['finger_joints']['velocities_m_s']=[.067]
    p=cp.from_legacy(c,row)
    assert p['robots']['left']['joint_vel']==[0.,.067]
    assert p['state_quality']=='measured_pose_fixture'
    assert any('finger joint velocities restored'in text for text in p['assumptions'])


def new_design_case():
    c=controller();c.scene.spec['id']='E09';obj=c.scene.objects['object']
    names=['piece'+str(i)for i in range(9)]
    c.scene.objects={name:copy.deepcopy(obj)for name in names}
    c.scene.spec['objects']=[dict(id=name,size=[.02,.02,.003],source_asset={'sha256':'f'*63+str(i)})for i,name in enumerate(names)]
    d=c.scene.spec['execution_design'];d.update(target_members=names,
        operable_packaging=dict(revision='e09-operable-packaging-v1-20261103',geometry_sha256='d'*64))
    request=dict(schema='videoicl-engineering-new-design-fixture-v1',
        identity=dict(id='E09',variant='A',seed=4201,assignment_identity_sha256='a'*64,source_sha256='c'*64),
        geometry_sha256='d'*64,source_asset_sha256={name:'f'*63+str(i)for i,name in enumerate(names)},
        context=dict(policy_start_step=0,policy_action_budget=12000),
        object_root_overrides={'piece0':[.12,.05,.82,1,0,0,0]},
        parent_evidence={'old_geometry_episode':'old-design-only-not-reproduced'})
    return c,request


def test_new_design_fixture_is_explicit_current_geometry_and_ineligible_without_history():
    c,d=new_design_case();p=cp.from_new_design_fixture(c,d)
    assert all_writes(c)==0
    assert p['source']['steps']==0 and p['context']['new_design_fixture']
    assert p['context']['not_old_checkpoint_continuation'] and not p['eligible_full_acceptance']
    assert p['objects']['piece0']['root_state_task']==[.12,.05,.82,1,0,0,0,0,0,0,0,0,0]
    target,_=new_design_case();result=cp.restore(target,p)
    assert result['native_readback_verified'] and target.evaluator.completion_label=='untouched'


@pytest.mark.parametrize('mutation',['geometry','asset','labels','held'])
def test_new_design_fixture_rejects_wrong_geometry_source_or_labels_before_writes(mutation):
    c,d=new_design_case()
    if mutation=='geometry':d['geometry_sha256']='0'*64
    elif mutation=='asset':d['source_asset_sha256']['piece0']='0'*64
    elif mutation=='labels':d['success']=True
    else:d['object_root_overrides']['piece0']={'root_state_task':[.12,.05,.82,1,0,0,0,0,0,0,0,0,0],'grasp':True}
    with pytest.raises(ValueError):cp.from_new_design_fixture(c,d)
    assert all_writes(c)==0


def test_new_geometry_fixture_retains_original_robot_bases_and_native_joint_dynamics():
    c,d=new_design_case();source=cp.capture(c);robot=source['robots']['left']
    fields=('joint_names','joint_pos','joint_vel','drive_targets')
    d['robot_joint_overrides']={'left':{k:copy.deepcopy(robot[k])for k in fields}}
    d['robot_source_embodiment_sha256']=c.scene.spec['embodiment_config_sha256']
    d['gripper_initial_widths']={'left':0.}
    d['robot_source_tcp_task_positions']=source['tcp_task_positions']
    p=cp.from_new_design_fixture(c,d)
    assert p['robots']['left']==source['robots']['left']
    assert p['controller']['grips']=={'left':0.}
    assert p['context']['not_old_checkpoint_continuation'] and p['source']['steps']==0
    assert all_writes(c)==0 and not p['eligible_full_acceptance']


@pytest.mark.parametrize('bad',['profile','root','joint','nonfinite','width'])
def test_new_robot_fixture_rejects_other_profile_roots_bad_joints_or_grip_before_writes(bad):
    c,d=new_design_case();r=cp.capture(c)['robots']['left']
    d['robot_joint_overrides']={'left':{k:copy.deepcopy(r[k])for k in ('joint_names','joint_pos','joint_vel','drive_targets')}}
    d['robot_source_embodiment_sha256']=c.scene.spec['embodiment_config_sha256'];d['gripper_initial_widths']={'left':0.}
    if bad=='profile':d['robot_source_embodiment_sha256']='wrong'
    elif bad=='root':d['robot_joint_overrides']['left']['root_state_task']=r['root_state_task']
    elif bad=='joint':d['robot_joint_overrides']['left']['joint_names'].reverse()
    elif bad=='nonfinite':d['robot_joint_overrides']['left']['joint_pos'][0]=float('nan')
    else:d['gripper_initial_widths']['left']=1.
    with pytest.raises(ValueError):cp.from_new_design_fixture(c,d)
    assert all_writes(c)==0
