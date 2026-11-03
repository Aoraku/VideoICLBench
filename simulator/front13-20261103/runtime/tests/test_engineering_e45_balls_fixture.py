import copy
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e45_balls as balls
from videoicl_isaaclab.engineering_e45_balls_fixture import materialize
from videoicl_isaaclab.engineering_checkpoint import identity,reseal,PHYSICAL_KEYS


def setup():
    objects=[dict(id=n,kind='sphere',source_asset=dict(root_env='VIC_FULL50_RIGID_ASSETS',relative_path='sphere_white.usda',sha256=balls.SOURCE_SHA),size=[.01316]*3,mass=.002491752,static_friction=.8,dynamic_friction=.6,restitution=0)for n in balls.BALLS]
    objects.append(dict(id='cup',kind='source_mesh',mass=.06))
    old=dict(id='E45',variant='A',seed=4201,objects=objects,execution_design=dict(assignment_identity_sha256='a'*64,source_sha256='b'*64),embodiment_config_sha256='c'*64)
    base=SimpleNamespace(scene=SimpleNamespace(spec=old));cp=reseal(dict(identity=identity(base),context={},limitations=[],diagnostic_only=True))
    new=copy.deepcopy(old);balls.configure_spec(new);baseline={n:copy.deepcopy(balls.NATIVE_MASS_PROPERTIES)for n in balls.BALLS}
    baseline['cup']=copy.deepcopy(balls.NATIVE_SOURCE_MASS_PROPERTIES['cup'])
    def tensor(x):return SimpleNamespace(cpu=lambda:np.asarray(x))
    views={}
    for n,props in baseline.items():
        views[n]=SimpleNamespace(root_physx_view=SimpleNamespace(get_masses=lambda p=props:tensor(p['masses_kg']),get_inertias=lambda p=props:tensor(p['inertias_kg_m2']),get_coms=lambda p=props:tensor(p['centres_of_mass'])))
    c=SimpleNamespace(scene=SimpleNamespace(spec=new,objects=views))
    recipe=dict(schema='engineering-e45-balls-migration-v1',diagnostic_only=True,checkpoint=cp,source_scene=old,native_mass_properties=baseline,native_mass_baseline_sha256=balls.BASELINE_ARTIFACT_SHA)
    return c,recipe


def test_only_three_source_round_ball_colliders_change_and_native_properties_match():
    c,r=setup();before=copy.deepcopy(r);x=materialize(c,r)
    assert r==before and x['identity']==identity(c)
    migration=x['context']['e45_ball_migration']
    assert migration['changed_objects']==list(balls.BALLS)and migration['post_settle_ball_motion_is_new_geometry']
    for k in PHYSICAL_KEYS:
        if k!='objects':assert c.scene.spec.get(k)==r['source_scene'].get(k)
    assert c.scene.spec['objects'][-1]==r['source_scene']['objects'][-1]


@pytest.mark.parametrize('bad',['radius','mass','material','cup','goal','profile','checkpoint','baseline'])
def test_scope_and_original_checkpoint_binding_fail_closed(bad):
    c,r=setup()
    if bad=='radius':c.scene.spec['objects'][0]['size'][0]*=1.01
    if bad=='mass':c.scene.spec['objects'][0]['mass']*=2
    if bad=='material':c.scene.spec['objects'][1]['dynamic_friction']=.1
    if bad=='cup':c.scene.spec['objects'][-1]['mass']=.061
    if bad=='goal':c.scene.spec['goals']=[{'modified':True}]
    if bad=='profile':c.scene.spec['embodiment_config_sha256']='d'*64
    if bad=='checkpoint':r['checkpoint']['context']['tampered']=True
    if bad=='baseline':r['native_mass_properties']['cup']['inertias_kg_m2'][0][0]*=2
    with pytest.raises(ValueError):materialize(c,r)
