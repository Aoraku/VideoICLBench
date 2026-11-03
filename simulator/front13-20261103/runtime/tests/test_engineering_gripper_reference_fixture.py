from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from videoicl_isaaclab.engineering_checkpoint import identity,reseal
from videoicl_isaaclab.engineering_gripper_reference_fixture import materialize,OLD_PROFILE,NEW_PROFILE,FIELDS


def fixture():
    old=json.loads((Path(__file__).parents[1]/'configs/e39-franka-control-inherit-v1.json').read_text());old['physics']['render_hz']=5
    new=deepcopy(old);new['control'].update(FIELDS)
    spec=dict(id='E50',variant='A',seed=4201,embodiment_config_sha256=OLD_PROFILE,execution_design=dict(assignment_identity_sha256='a'*64,source_sha256='b'*64),objects=[dict(id='card',mass=.0018,size=[.044,.0315,.000175])],mechanisms=[],fixtures=[],goals=[])
    c=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config=new)))
    checkpoint=reseal(dict(identity=identity(c),controller=dict(grips={'left':.04,'right':0}),readback=dict(available=True,object_grasps={'card':[False,False]},contacts=[['card','table']]),context={},assumptions=[],limitations=[]))
    c.scene.spec['embodiment_config_sha256']=NEW_PROFILE
    return c,dict(schema='engineering-gripper-reference-profile-migration-v1',diagnostic_only=True,checkpoint=checkpoint,source_profile=old)


def test_only_original_binary_goal_and_state_are_retained_across_exact_profile_migration():
    c,r=fixture();out=materialize(c,r)
    assert out['identity']==identity(c)
    assert out['controller']==r['checkpoint']['controller']
    assert out['context']['public_gripper_reference_migration']['only_added_control_fields']==FIELDS


@pytest.mark.parametrize('fault',('profile_effort','physics','geometry','source_profile','checkpoint','source_identity'))
def test_unrelated_profile_geometry_or_identity_changes_cannot_use_migration(fault):
    c,r=fixture()
    if fault=='profile_effort':c.scene.embodiment.config['actuators']['gripper']['effort_limit']*=2
    elif fault=='physics':c.scene.embodiment.config['physics']['dt']*=2
    elif fault=='geometry':c.scene.spec['objects'][0]['size'][2]*=2
    elif fault=='source_profile':r['source_profile']['control']['step_mm'][0]=.1
    elif fault=='checkpoint':r['checkpoint']['controller']['grips']['left']=0
    else:c.scene.spec['execution_design']['source_sha256']='c'*64
    with pytest.raises(ValueError):materialize(c,r)


@pytest.mark.parametrize('holding',('object','mechanism'))
def test_old_holding_checkpoint_cannot_drop_its_captured_grip_preload(holding):
    c,r=fixture();checkpoint=r['checkpoint']
    if holding=='object':checkpoint['readback']['object_grasps']['card']=[True,False]
    else:checkpoint['readback']['contacts']+=[['left_finger1','clip/positive_jaw'],['left_finger2','clip/negative_jaw']]
    r['checkpoint']=reseal(checkpoint)
    with pytest.raises(ValueError,match='held payload|no payload'):materialize(c,r)
