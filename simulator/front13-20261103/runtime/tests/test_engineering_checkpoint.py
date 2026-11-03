from types import SimpleNamespace
import copy
import math
import numpy as np
import pytest
from videoicl_isaaclab.engineering_checkpoint import capture,restore_startup,reseal
from videoicl_isaaclab.layout import Layout,multiply_quaternions
from videoicl_isaaclab.mechanical_asset_adapters import ElastoPlasticHinge


class Asset:
    def __init__(self,root,joints=None):
        self.writes=[];self.data=SimpleNamespace(root_state_w=np.array([root],float))
        if joints is not None:
            self.joint_names=list(joints);n=len(joints)
            self.data.joint_pos=np.full((1,n),.2);self.data.joint_vel=np.full((1,n),.03)
            self.data.joint_pos_target=np.full((1,n),.21);self.data.joint_vel_target=np.full((1,n),.01)
            self.data.joint_effort_target=np.full((1,n),.012)
            self.data.joint_pos_limits=np.array([[[-2.,2.]]*n])
    def write_root_state_to_sim(self,value):self.writes.append('root');self.data.root_state_w=value.copy()
    def write_joint_state_to_sim(self,q,qd):self.writes.append('q');self.data.joint_pos=q.copy();self.data.joint_vel=qd.copy()
    def set_joint_position_target(self,x):self.writes.append('pt');self.data.joint_pos_target=x.copy()
    def set_joint_velocity_target(self,x):self.writes.append('vt');self.data.joint_vel_target=x.copy()
    def set_joint_effort_target(self,x):self.writes.append('et');self.data.joint_effort_target=x.copy()


def controller(origin=(0.,0.,0.)):
    half=math.sqrt(.5);layout=Layout(dict(id='fixture',task_rotation=[half,0,0,half],task_translation=list(origin)))
    task=np.array([.12,.05,.82,math.cos(.3),0,0,math.sin(.3),.1,.2,.3,.03,.02,.01]);world=np.r_[layout.task_to_world(task[:3]),multiply_quaternions(layout.task_quat,task[3:7]),task[7:10]@layout.task_rotation.T,task[10:]@layout.task_rotation.T]
    spec=dict(id='E44',variant='A',seed=4201,embodiment_config_sha256='b'*64,execution_design=dict(assignment_identity_sha256='a'*64,source_sha256='c'*64),objects=[dict(id='object',size=[.1,.1,.01])],mechanisms=[dict(id='cardboard',kind='articulation')],fixtures=[])
    scene=SimpleNamespace(spec=spec,layout=layout,world_to_task=layout.world_to_task,task_to_world=layout.task_to_world,
        objects={'object':Asset(world)},robots={'left':Asset(world,['j1','j2'])},mechanisms={'cardboard':Asset(world,['crease'])},
        embodiment=SimpleNamespace(config=dict(gripper=dict(open=[.04,.04],closed=[0,0]))),
        passive_efforts={'cardboard':dict(joint='crease',model=ElastoPlasticHinge(plastic_rest_angle_rad=.17))})
    c=SimpleNamespace(scene=scene,steps=0,physics_ticks=0,dt=.004,started=False,_public_action=None,
        evaluator=SimpleNamespace(initial_sealed=False,completion_label='untouched'),grips={'left':.013},
        targets={'left':(np.array([[.1,.2,.3]]),np.array([[1.,0,0,0]]))},ids={'left':([0,1],[],0)},
        _public_reference={'left':np.array([[.1,.2]])},_public_reference_velocity={'left':np.array([[.01,.02]])})
    return c


def all_writes(c):return sum(len(a.writes)for group in(c.scene.objects,c.scene.robots,c.scene.mechanisms)for a in group.values())


def test_failure_boundary_keeps_the_last_accepted_state_without_another_action(tmp_path):
    import hashlib
    import json
    from videoicl_isaaclab.execution_design_probe import persist_engineering_failure_checkpoint
    c=controller();c.steps=37;c.physics_ticks=4200
    c.scene.robots['left'].data.joint_pos[0,0]=.375
    author=SimpleNamespace(c=c,out=tmp_path,stage='after-wrist-turn',
                           _engineering_stage_checkpoints=True,_engineering_failure_latched=True)
    receipt=persist_engineering_failure_checkpoint(author,'room-0')
    from pathlib import Path
    raw=Path(receipt['checkpoint']).read_bytes();saved=json.loads(raw)
    assert hashlib.sha256(raw).hexdigest()==receipt['sha256']
    assert saved['robots']['left']['joint_pos'][0]==.375
    assert saved['source']['steps']==37 and saved['source']['physics_ticks']==4200
    assert c.steps==37 and c.physics_ticks==4200 and all_writes(c)==0


def test_full_native_state_moves_between_room_origins_preserving_material_and_no_history():
    source=controller((2.,3.,0.));source.steps=215;source.physics_ticks=21700
    point=capture(source,'before-blade-insertion',{'tool':'spatula'})
    target=controller((-4.,7.,0.));target.scene.passive_efforts['cardboard']['model'].plastic_rest_angle_rad=0.
    evaluation=target.evaluator;receipt=restore_startup(target,point)
    assert receipt['requires_settle_and_contact_validation'] and receipt['diagnostic_only']
    assert receipt['physics_advanced'] is False and receipt['evaluator_history_restored']is False
    assert target.evaluator is evaluation and evaluation.completion_label=='untouched'
    assert target.steps==target.physics_ticks==0
    restored=capture(target,'restored')
    for group in ('objects','robots','mechanisms'):
        for name,row in point[group].items():
            assert np.allclose(row['root_state_task'],restored[group][name]['root_state_task'])
            if group!='objects':
                assert np.allclose(row['joint_pos'],restored[group][name]['joint_pos'])
                assert np.allclose(row['joint_vel'],restored[group][name]['joint_vel'])
                assert row['drive_targets']==restored[group][name]['drive_targets']
    assert target.scene.passive_efforts['cardboard']['model'].plastic_rest_angle_rad==.17
    assert point['controller']==restored['controller']
    with pytest.raises(ValueError,match='single-use'):restore_startup(target,point)


@pytest.mark.parametrize('state',['steps','started','sealed','inflight'])
def test_restore_is_allowed_only_before_any_start_or_initial_seal(state):
    c=controller();p=capture(c,'boundary')
    if state=='steps':c.steps=1
    if state=='started':c.started=True
    if state=='sealed':c.evaluator.initial_sealed=True
    if state=='inflight':c._engineering_action_in_flight=True
    with pytest.raises(ValueError):restore_startup(c,p)
    assert all_writes(c)==0


@pytest.mark.parametrize('case',['hash','source','geometry','profile','joint_names','joint_limit','drive_target','nonfinite','quaternion','plastic_parameters','plastic_rest','success_label'])
def test_entire_payload_is_validated_before_first_native_write(case):
    c=controller();p=capture(c,'boundary')
    if case=='hash':p['stage']='tampered'
    elif case=='source':p['identity']['source_sha256']='d'*64
    elif case=='geometry':p['identity']['physical_geometry_sha256']='d'*64
    elif case=='profile':p['identity']['embodiment_config_sha256']='d'*64
    elif case=='joint_names':p['robots']['left']['joint_names'].reverse()
    elif case=='joint_limit':p['mechanisms']['cardboard']['joint_pos']=[3.]
    elif case=='drive_target':p['robots']['left']['drive_targets']['position']=[3.,.2]
    elif case=='nonfinite':p['objects']['object']['root_state_task'][0]=float('nan')
    elif case=='quaternion':p['robots']['left']['root_state_task'][3:7]=[2.,0,0,0]
    elif case=='plastic_parameters':p['passive_material']['cardboard']['parameters']['yield_moment_nm']=10.
    elif case=='plastic_rest':p['passive_material']['cardboard']['plastic_rest_angle_rad']=100.
    elif case=='success_label':p['success']=True
    if case not in('hash','nonfinite'):p=reseal(p)
    with pytest.raises(ValueError):restore_startup(c,p)
    assert all_writes(c)==0 and not getattr(c,'_engineering_restore_attempted',False)


def test_measured_pose_fixture_requires_honest_zero_velocity_hold_assumptions():
    c=controller();p=capture(c,'failure-before-turn');p['state_quality']='measured_pose_fixture';p['assumptions']=[]
    with pytest.raises(ValueError,match='explicit velocity'):restore_startup(controller(),reseal(p))
    p['assumptions']=['Old pose/q readback lacks velocity; all root/q velocities assumed zero, drive targets hold measured q.']
    for group in ('objects','robots','mechanisms'):
        for row in p[group].values():
            row['root_state_task'][7:]=[0.]*6
            if group!='objects':
                row['joint_vel']=[0.]*len(row['joint_names']);row['drive_targets']={'position':row['joint_pos'],'velocity':None,'effort':None}
    target=controller();receipt=restore_startup(target,reseal(p))
    assert receipt['state_quality']=='measured_pose_fixture'and receipt['assumptions']
    assert np.allclose(target.scene.mechanisms['cardboard'].data.joint_vel_target,0)
    assert target.scene.passive_efforts['cardboard']['model'].plastic_rest_angle_rad==.17


def test_failed_native_write_consumes_admission_without_retrying_partial_world():
    c=controller();p=capture(c,'boundary')
    def fail(*args):raise RuntimeError('Native writer failed')
    c.scene.robots['left'].write_joint_state_to_sim=fail
    with pytest.raises(RuntimeError,match='Native writer'):restore_startup(c,p)
    assert all_writes(c)>0
    with pytest.raises(ValueError,match='single-use'):restore_startup(c,p)


@pytest.mark.parametrize('unreviewed_change',[None,'checkpoint','robot','large_slop'])
def test_reviewed_compliant_mechanism_state_keeps_robot_and_target_limits(monkeypatch,unreviewed_change):
    from videoicl_isaaclab import engineering_e40_native_readback as review
    source=controller();source.scene.spec['id']='E40'
    source.scene.mechanisms['clip1']=source.scene.mechanisms.pop('cardboard')
    source.scene.passive_efforts={}
    source.scene.mechanisms['clip1'].data.joint_pos[0,0]=2.04
    if unreviewed_change=='robot':source.scene.robots['left'].data.joint_pos[0,0]=2.01
    if unreviewed_change=='large_slop':source.scene.mechanisms['clip1'].data.joint_pos[0,0]=2.051
    point=capture(source,'actually-held-open')
    monkeypatch.setattr(review,'REVIEWED_CHECKPOINT',point['checkpoint_sha256'])
    if unreviewed_change=='checkpoint':point=reseal(dict(point,stage='different-native-state'))
    target=controller();target.scene.spec['id']='E40'
    target.scene.mechanisms['clip1']=target.scene.mechanisms.pop('cardboard')
    target.scene.passive_efforts={}
    if unreviewed_change is None:
        receipt=restore_startup(target,point)
        assert target.scene.mechanisms['clip1'].data.joint_pos[0,0]==2.04
        assert np.all(target.scene.mechanisms['clip1'].data.joint_pos_limits==[[[-2.,2.]]])
        assert receipt['measured_native_joint_readback_tolerances_rad']=={'mechanisms/clip1':.05}
    else:
        with pytest.raises(ValueError,match='joint position exceeds'):restore_startup(target,point)
        assert all_writes(target)==0


def test_validated_kinematic_rigid_restores_pose_without_velocity_api(monkeypatch):
    source=controller();source.scene.objects['object'].data.root_state_w[:,7:]=0.
    point=capture(source,'fixed-socket-boundary')
    target=controller();asset=target.scene.objects['object']
    def pose(value):asset.writes.append('pose-only');asset.data.root_state_w[:,:7]=value
    asset.write_root_pose_to_sim=pose
    monkeypatch.setattr('videoicl_isaaclab.engineering_checkpoint._native_kinematic_rigid',lambda value:value is asset)
    result=restore_startup(target,point)
    assert asset.writes==['pose-only']
    assert result['pose_only_native_kinematic_roots']==['objects/object']


def test_nonzero_velocity_for_kinematic_body_rejected_before_any_write(monkeypatch):
    source=controller();point=capture(source,'moving-kinematic-not-supported')
    target=controller();asset=target.scene.objects['object'];asset.write_root_pose_to_sim=lambda value:None
    monkeypatch.setattr('videoicl_isaaclab.engineering_checkpoint._native_kinematic_rigid',lambda value:value is asset)
    with pytest.raises(ValueError,match='Nonzero kinematic velocity'):restore_startup(target,point)
    assert all_writes(target)==0


def test_checkpoint_readback_measures_contacts_but_never_assigns_them_to_new_world():
    c=controller();pair=frozenset(('object','left_finger1'))
    c.snapshot=lambda:({'object':dict(grasp=(True,False))},{pair})
    c.contact_forces={pair:1.7}
    point=capture(c,'actual-held-boundary')
    assert point['readback']==dict(available=True,object_grasps={'object':[True,False]},contacts=[['left_finger1','object']],contact_forces_n=[dict(bodies=['left_finger1','object'],force_n=1.7)])
    target=controller();receipt=restore_startup(target,point)
    assert receipt['source_readback']==point['readback']
    assert not hasattr(target,'contact_forces')and not hasattr(target.evaluator,'object_grasps')


@pytest.mark.parametrize('overshoot',[1.1722212548193056e-5,9e-5,.001])
def test_e44_sealed_native_crease_solver_readback_keeps_original_q_and_limit(overshoot):
    source=controller();asset=source.scene.mechanisms['cardboard'];asset.joint_names=['Crease']
    source.scene.passive_efforts['cardboard']['joint']='Crease'
    source.scene.passive_efforts['cardboard']['model'].plastic_rest_angle_rad=0.
    asset.data.joint_pos_limits[0,0]=[-3.14159,0.]
    asset.data.joint_pos[0,0]=overshoot;asset.data.joint_pos_target[0,0]=0.
    point=capture(source,'native-before-failure')
    target=controller();target.scene.mechanisms['cardboard'].joint_names=['Crease'];target.scene.mechanisms['cardboard'].data.joint_pos_limits[0,0]=[-3.14159,0.]
    target.scene.passive_efforts['cardboard']['joint']='Crease'
    if overshoot>=.001:
        with pytest.raises(ValueError,match='joint position exceeds'):restore_startup(target,point)
        assert all_writes(target)==0
    else:
        result=restore_startup(target,point)
        assert target.scene.mechanisms['cardboard'].data.joint_pos[0,0]==overshoot
        assert target.scene.mechanisms['cardboard'].data.joint_pos_limits[0,0,1]==0.
        assert result['measured_native_joint_readback_tolerances_rad']['mechanisms/cardboard']==1e-4


def test_e44_crease_solver_tolerance_does_not_widen_robot_or_pose_fixture_gate():
    for kind in ('robot','pose_fixture'):
        source=controller();source.scene.mechanisms['cardboard'].joint_names=['Crease'];source.scene.passive_efforts['cardboard']['joint']='Crease'
        if kind=='robot':source.scene.robots['left'].data.joint_pos[0,0]=2.00005
        else:
            source.scene.mechanisms['cardboard'].data.joint_pos[0,0]=2.00005
        point=capture(source,'measured-boundary')
        if kind=='pose_fixture':point['state_quality']='measured_pose_fixture';point['assumptions']=['Fixture hold is explicit.'];point=reseal(point)
        target=controller();target.scene.mechanisms['cardboard'].joint_names=['Crease'];target.scene.passive_efforts['cardboard']['joint']='Crease'
        with pytest.raises(ValueError,match='joint position exceeds'):restore_startup(target,point)
        assert all_writes(target)==0
