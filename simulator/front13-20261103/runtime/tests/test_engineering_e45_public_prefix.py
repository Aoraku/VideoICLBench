import json,copy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.engineering_checkpoint import _hash
from videoicl_isaaclab.engineering_e45_public_prefix import materialize
from videoicl_isaaclab.execution_design_e45_balls import NATIVE_SOURCE_MASS_PROPERTIES
from videoicl_isaaclab.realworld_scenes import load
V=Path(__file__).resolve().parents[2]/'verification/task-design-revision-20261102'

def setup(variant,monkeypatch):
    monkeypatch.setenv('VIC_ENGINEERING_E45_ANALYTIC_BALLS','1')
    r=json.loads((V/'e45-three-round-balls-held216-migration.fixture.private.json').read_text());r['schema']='engineering-e45-public-prefix-variant-v1';r['allow_render_only_from5_to1']=True
    c=json.loads((V.parents[1]/'runtime/configs/e39-franka-control-inherit-v1.json').read_text());c['physics']['render_hz']=5;r['source_profile_config']=copy.deepcopy(c);c['physics']['render_hz']=1
    spec=load('E45',variant,4201,V/'e38-e50-matrix/bindings-I.private.json',verify_files=False);spec['embodiment_config_sha256']=_hash(c)
    views={}
    for name in ['tray','cup','dark_green','red','light_green']:
        row=NATIVE_SOURCE_MASS_PROPERTIES.get(name,dict(masses_kg=[[.6]],inertias_kg_m2=[[0.]*9],centres_of_mass=[[0,0,0,0,0,0,1]]))
        tensor=lambda x:SimpleNamespace(cpu=lambda:np.asarray(x))
        views[name]=SimpleNamespace(root_physx_view=SimpleNamespace(get_masses=lambda x=row:tensor(x['masses_kg']),get_inertias=lambda x=row:tensor(x['inertias_kg_m2']),get_coms=lambda x=row:tensor(x['centres_of_mass'])))
    return SimpleNamespace(scene=SimpleNamespace(spec=spec,objects=views,embodiment=SimpleNamespace(config=c))),r

@pytest.mark.parametrize('variant',['B','C'])
def test_prefix_preserves_states_and_only_reviewed_goal_render_branch_changes(variant,monkeypatch):
    c,r=setup(variant,monkeypatch);old=copy.deepcopy(r['checkpoint']);new=materialize(c,r)
    assert new['objects']==old['objects']and new['robots']==old['robots']
    assert new['identity']['variant']==variant
    assert new['context']['e45_public_prefix_variant']['render_only_profile_migration']['changed_fields']==['physics.render_hz']

@pytest.mark.parametrize('field',['mass','physics','source'])
def test_prefix_rejects_unreviewed_physics_or_source(field,monkeypatch):
    c,r=setup('B',monkeypatch)
    if field=='mass':c.scene.spec['objects'][0]['mass']*=2
    if field=='physics':c.scene.embodiment.config['physics']['dt']=.01
    if field=='source':c.scene.spec['execution_design']['source_sha256']='bad'
    with pytest.raises(ValueError):materialize(c,r)
