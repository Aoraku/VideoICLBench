from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_thin_cooking import configure_spec,verify_only_cooking_change
from videoicl_isaaclab.engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from videoicl_isaaclab.engineering_thin_cooking_fixture import materialize

BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'


def source(task='E50',variant='A'):
    spec=apply_execution_inputs(load(task,variant,0,BINDINGS,verify_files=False),condition='R',seed=4201,revision=REVISION_V3)
    spec['embodiment_config_sha256']='test-profile'
    return spec


@pytest.mark.parametrize('task',('E47','E48','E49','E50'))
@pytest.mark.parametrize('variant','ABC')
def test_only_sha_pinned_original_thin_cards_receive_cpu_cooking_settings(task,variant):
    old=source(task,variant);new=deepcopy(old);changed=configure_spec(new)
    assert verify_only_cooking_change(old,new)==changed
    assert len(changed)==(1 if task=='E50'else 5)
    for a,b in zip(old['objects'],new['objects']):
        settings=b.pop('reviewed_collision_settings',None)
        assert a==b
        if settings:
            assert settings['min_thickness_m']==pytest.approx(.000035)
            assert settings['hull_vertex_limit']==255


def migration_case():
    old=source();new=deepcopy(old);configure_spec(new)
    native=dict(masses_kg=[[.0018]],inertias_kg_m2=[[1e-7,0,0,0,2e-7,0,0,0,3e-7]],centres_of_mass=[[[0,0,0,0,0,0,1]]])
    def tensor(value):return SimpleNamespace(cpu=lambda:np.asarray(value))
    asset=SimpleNamespace(root_physx_view=SimpleNamespace(get_masses=lambda:tensor(native['masses_kg']),get_inertias=lambda:tensor(native['inertias_kg_m2']),get_coms=lambda:tensor(native['centres_of_mass'])))
    c=SimpleNamespace(scene=SimpleNamespace(spec=old,objects={'card':asset}))
    checkpoint=reseal(dict(identity=identity(c),context={},limitations=[]));c.scene.spec=new
    recipe=dict(schema='engineering-thin-cooking-migration-v1',diagnostic_only=True,checkpoint=checkpoint,source_scene=old,native_mass_properties={'card':deepcopy(native)})
    return c,recipe


def test_cooking_migration_keeps_original_integrity_and_explicit_old_new_binding():
    c,r=migration_case();out=materialize(c,r)
    audit=out['context']['thin_cooking_migration']
    assert audit['old_identity']==r['checkpoint']['identity']
    assert audit['new_identity']==identity(c)
    assert audit['source_geometry_mass_inertia_unchanged']
    assert r['checkpoint']['identity']['physical_geometry_sha256']!=out['identity']['physical_geometry_sha256']


def test_coordinate_flag_is_wired_only_to_actual_thin_card_input_adapter(monkeypatch):
    monkeypatch.setenv('VIC_ENGINEERING_THIN_COOKING_FIDELITY','1')
    monkeypatch.setenv('VIC_ENGINEERING_THIN_COLLISION_COORDINATES','100')
    card=source('E50')['objects'][0]
    assert card['reviewed_collision_settings']['coordinate_factor']==100
    # E10 has a different source-bound collision adapter with a one-argument
    # interface; thin-card numerical flags must not affect it.
    load('E10','A',0,BINDINGS,verify_files=False)
    apply_execution_inputs(load('E10','A',0,BINDINGS,verify_files=False),condition='R',seed=4201,revision=REVISION_V3)


@pytest.mark.parametrize('mutation',('geometry','mass','source','checkpoint','inertia'))
def test_cooking_migration_rejects_unrelated_geometry_identity_or_dynamics_change(mutation):
    c,r=migration_case()
    if mutation=='geometry':c.scene.spec['objects'][0]['size'][2]*=2
    elif mutation=='mass':c.scene.spec['objects'][0]['mass']*=2
    elif mutation=='source':c.scene.spec['objects'][0]['source_asset']['sha256']='other'
    elif mutation=='checkpoint':r['checkpoint']['context']['forged']=True
    else:r['native_mass_properties']['card']['inertias_kg_m2'][0][0]*=2
    with pytest.raises(ValueError):materialize(c,r)
