import copy
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e43_ball as ball
from videoicl_isaaclab.engineering_e43_ball_fixture import materialize
from videoicl_isaaclab.engineering_checkpoint import PHYSICAL_KEYS,identity,reseal


def setup():
    obj=dict(id='ball',kind='sphere',source_asset=dict(root_env='VIC_FULL50_RIGID_ASSETS',relative_path='sphere_white.usda',sha256=ball.SOURCE_SHA),size=[.013652941818490449,.014,.013857428965220098],mass=.008,static_friction=.8,dynamic_friction=.6,restitution=0)
    old=dict(id='E43',variant='A',seed=4201,objects=[obj],execution_design=dict(assignment_identity_sha256='a'*64,source_sha256='b'*64),embodiment_config_sha256='c'*64)
    base=SimpleNamespace(scene=SimpleNamespace(spec=old));cp=reseal(dict(identity=identity(base),context={},limitations=[],diagnostic_only=True))
    new=copy.deepcopy(old);ball.configure_spec(new);mass=copy.deepcopy(ball.NATIVE_MASS_PROPERTIES)
    def tensor(x):return SimpleNamespace(cpu=lambda:np.asarray(x))
    view=SimpleNamespace(get_masses=lambda:tensor(mass['masses_kg']),get_inertias=lambda:tensor(mass['inertias_kg_m2']),get_coms=lambda:tensor(mass['centres_of_mass']))
    c=SimpleNamespace(scene=SimpleNamespace(spec=new,objects={'ball':SimpleNamespace(root_physx_view=view)}))
    recipe=dict(schema='engineering-e43-ball-migration-v1',diagnostic_only=True,checkpoint=cp,source_scene=old,native_mass_properties={'ball':copy.deepcopy(mass)},native_mass_baseline_sha256=ball.BASELINE_ARTIFACT_SHA)
    return c,recipe,mass


def test_e43_only_collision_adapter_preserves_all_other_physical_keys():
    c,r,m=setup();before=copy.deepcopy(r);x=materialize(c,r)
    assert x['identity']==identity(c)and r==before
    assert x['context']['e43_ball_migration']['only_collision_approximation_changed']
    assert x['context']['e43_ball_migration']['new_native_mass_properties']['ball']==m
    for key in PHYSICAL_KEYS:
        if key!='objects':assert c.scene.spec.get(key)==r['source_scene'].get(key)


@pytest.mark.parametrize('bad',['mass','goal','profile','digest','source'])
def test_e43_migration_cannot_hide_unrelated_changes_or_unbound_mass(bad):
    c,r,m=setup()
    if bad=='mass':m['inertias_kg_m2'][0][0]*=1.01
    if bad=='goal':c.scene.spec['goals']=[{'different':'target'}]
    if bad=='profile':c.scene.spec['embodiment_config_sha256']='d'*64
    if bad=='digest':r['checkpoint']['context']['forged']=True
    if bad=='source':r['source_scene']['objects'][0]['mass']=.009
    with pytest.raises(ValueError):materialize(c,r)
