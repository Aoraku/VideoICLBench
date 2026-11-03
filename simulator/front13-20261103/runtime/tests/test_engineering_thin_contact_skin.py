from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest
from videoicl_isaaclab.engineering_checkpoint import PHYSICAL_KEYS, _hash, reseal
from videoicl_isaaclab.engineering_thin_contact_skin import configure_spec, OFFSET, PROFILE_FIELD
from videoicl_isaaclab.engineering_thin_contact_skin_fixture import materialize

BASELINE = dict(masses_kg=[[.0018000000854954123]],
    inertias_kg_m2=[[5.936302045483899e-7,1.3238036535023756e-11,0.,1.3238036535023756e-11,1.1662136785162147e-6,0.,0.,0.,1.7598075601199525e-6]],
    centres_of_mass=[[-2.631544759879034e-7,-1.9103285353594401e-7,-1.0858176580086365e-9,0.,0.,-1.1559918675629888e-5,1.]])


def fixture(monkeypatch):
    monkeypatch.setattr('videoicl_isaaclab.engineering_thin_contact_skin_fixture.verify_native_finger_geometry',lambda c:dict(left=dict(passed=True),right=dict(passed=True)))
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
    from videoicl_isaaclab.execution_design import REVISION_V3
    monkeypatch.setenv('VIC_ENGINEERING_THIN_COOKING_FIDELITY','1')
    monkeypatch.setenv('VIC_ENGINEERING_THIN_COLLISION_COORDINATES','100')
    monkeypatch.delenv('VIC_ENGINEERING_THIN_CONTACT_SKIN_UM',raising=False)
    rt=Path(__file__).parents[1]
    old=apply_execution_inputs(load('E50','A',0,rt/'configs/realworld_full50_bindings.json',verify_files=False),condition='R',seed=4201,revision=REVISION_V3)
    profile=json.loads((rt/'configs/thin-franka-gripper-reference-v1.json').read_text());profile['physics']['render_hz']=5
    old['embodiment_config_sha256']=_hash(profile)
    ident=dict(task='E50',variant='A',seed=4201,assignment_identity_sha256=old['execution_design']['assignment_identity_sha256'],source_sha256=old['execution_design']['source_sha256'],embodiment_config_sha256=_hash(profile),physical_geometry_sha256=_hash({k:old.get(k)for k in PHYSICAL_KEYS}))
    cp=reseal(dict(schema='engineering-native-checkpoint-v1',identity=ident,controller=dict(grips=dict(left=.04,right=.04)),readback=dict(available=True,object_grasps=dict(card=[False,False])),context={},limitations=[]))
    recipe=dict(schema='engineering-thin-skin50-migration-v1',diagnostic_only=True,checkpoint=cp,source_scene=deepcopy(old),source_profile=deepcopy(profile),native_card_properties=deepcopy(BASELINE))
    new=deepcopy(old);configure_spec(new);profile['physics'][PROFILE_FIELD]=OFFSET;new['embodiment_config_sha256']=_hash(profile)
    props=SimpleNamespace(get_masses=lambda:np.asarray(BASELINE['masses_kg']),get_inertias=lambda:np.asarray(BASELINE['inertias_kg_m2']),get_coms=lambda:np.asarray(BASELINE['centres_of_mass']))
    rigid=SimpleNamespace(count=1,get_contact_offsets=lambda:np.array([[OFFSET]]),get_rest_offsets=lambda:np.array([[0.]]))
    physics=SimpleNamespace(create_rigid_body_view=lambda path:rigid)
    scene=SimpleNamespace(spec=new,embodiment=SimpleNamespace(config=profile,fingers=('panda_leftfinger','panda_rightfinger')),objects=dict(card=SimpleNamespace(root_physx_view=props)),contacts={'card':(SimpleNamespace(_physics_sim_view=physics),[])},root_path='/World/Room')
    return SimpleNamespace(scene=scene,steps=0),recipe,rigid


def test_skin_migration_preserves_entire_checkpoint_state_and_binary_goals(monkeypatch):
    c,r,_=fixture(monkeypatch);before=deepcopy(r)
    result=materialize(c,r)
    assert r==before and result['controller']==r['checkpoint']['controller']
    assert result['context']['contact_skin_numeric_diagnostic']['public_actions']==0
    assert result['identity']['embodiment_config_sha256']==_hash(c.scene.embodiment.config)


@pytest.mark.parametrize('change',('thickness','friction','gains','other_robot_setting','missing_offset','rest_offset','old_grasp','wrong_source_digest'))
def test_unrelated_changes_or_unverified_numeric_skin_are_rejected_before_restore(monkeypatch,change):
    c,r,rigid=fixture(monkeypatch)
    if change=='thickness':c.scene.spec['objects'][0]['size'][2]*=2
    elif change=='friction':c.scene.spec['objects'][0]['static_friction']=.9
    elif change=='gains':c.scene.embodiment.config['actuators']['gripper']['stiffness']*=2
    elif change=='other_robot_setting':c.scene.embodiment.config['physics']['dt']=.002
    elif change=='missing_offset':rigid.get_contact_offsets=lambda:np.array([[.000417]])
    elif change=='rest_offset':rigid.get_rest_offsets=lambda:np.array([[.00001]])
    elif change=='old_grasp':r['checkpoint']['readback']['object_grasps']['card'][0]=True;r['checkpoint']=reseal(r['checkpoint'])
    else:r['checkpoint']['checkpoint_sha256']='invalid'
    with pytest.raises(ValueError):materialize(c,r)


def test_source_skin_diagnostic_cannot_cross_task_variant_or_seed(monkeypatch):
    c,r,_=fixture(monkeypatch)
    for field,value in(('id','E49'),('variant','B'),('seed',4202)):
        scene=deepcopy(r['source_scene']);scene[field]=value
        with pytest.raises(ValueError,match='E50 A4201'):configure_spec(scene)
