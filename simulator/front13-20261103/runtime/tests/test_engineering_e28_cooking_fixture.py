from copy import deepcopy
from types import SimpleNamespace as N
import pytest
from videoicl_isaaclab.engineering_checkpoint import identity,reseal
from videoicl_isaaclab.execution_design_e28_cooking import configure_spec,SOURCE_SHA
from videoicl_isaaclab.engineering_e28_cooking_fixture import materialize


class Native:
    def __init__(self,value):self.value=value
    def cpu(self):return self
    def tolist(self):return self.value


def fixture(tmp_path,monkeypatch):
    old=dict(id='E28',variant='B',seed=4201,execution_design=dict(
        assignment_identity_sha256='a',source_sha256='b'),embodiment_config_sha256='c',
        objects=[dict(id='spatula',mass=.085,source_asset=dict(sha256=SOURCE_SHA)),dict(id='round_food',mass=.02)],
        table_surface={'z':.8},semantic={'native_rule':'retained'})
    cp=reseal(dict(schema='engineering-native-checkpoint-v1',diagnostic_only=True,
        identity=identity(N(scene=N(spec=old))),context={},limitations=[],
        robots={'right':{'joint_pos':[1,2,3],'joint_vel':[.1,.2,.3],'drive_targets':{'position':[2,3,4]}}},
        objects={'spatula':{'root_state_task':[1,2,3]}},readback={'object_grasps':{'spatula':[False,True]}}))
    new=deepcopy(old);configure_spec(new)
    def asset(mass):return N(root_physx_view=N(get_masses=lambda:Native([mass]),
        get_inertias=lambda:Native([[1.]*9]),get_coms=lambda:Native([[0.,0.,0.,0.,0.,0.,1.]])))
    c=N(scene=N(spec=new,objects={'spatula':asset(.085),'round_food':asset(.02)}))
    recipe=dict(schema='engineering-e28-cooking-migration-v1',diagnostic_only=True,
        checkpoint=cp,source_scene=old,rebuild_spatula_grasp_with_public_close=True)
    request=dict(parameters={'rebuild_source_fidelity_grasp':True})
    monkeypatch.setenv('VIC_ENGINEERING_CHECKPOINT_REQUEST',str(tmp_path/'request.json'))
    return c,recipe,request,cp,asset


def test_cooking_migration_retains_real_state_and_declares_new_physics(tmp_path,monkeypatch):
    c,recipe,request,cp,_=fixture(tmp_path,monkeypatch);got=materialize(c,recipe,request)
    assert got['objects']==cp['objects']and got['robots']==cp['robots']
    assert got['identity']['physical_geometry_sha256']!=cp['identity']['physical_geometry_sha256']
    assert 'spatula'not in got['readback']['object_grasps']
    assert cp['readback']['object_grasps']['spatula']==[False,True]
    assert got['context']['e28_source_cooking_migration']['requires_three_public_grasp_samples']


def test_rejects_food_mass_changes_old_contact_claims_and_wrong_actual_mass(tmp_path,monkeypatch):
    c,recipe,request,_,asset=fixture(tmp_path,monkeypatch)
    c.scene.spec['objects'][1]['mass']+=.001
    with pytest.raises(ValueError,match='another physical input'):materialize(c,recipe,request)
    c.scene.spec['objects'][1]['mass']-=.001
    request['required_contacts']=[['spatula','right_finger1']]
    with pytest.raises(ValueError,match='Old hull grasp'):materialize(c,recipe,request)
    request.pop('required_contacts');c.scene.objects['spatula']=asset(.09)
    with pytest.raises(ValueError,match='nominal spatula mass'):materialize(c,recipe,request)
