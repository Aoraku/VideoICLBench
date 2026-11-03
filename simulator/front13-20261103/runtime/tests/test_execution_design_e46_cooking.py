import copy
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e46_cooking import configure_spec,verify_only_cooking_change,SOURCE_SHA
from videoicl_isaaclab.engineering_checkpoint import identity,reseal
from videoicl_isaaclab.engineering_e46_cooking_fixture import materialize


def setup():
    old=dict(id='E46',variant='A',seed=4201,objects=[dict(id='spatula',size=[.14,.03761496517,.01481387076],mass=.05,source_asset={'sha256':SOURCE_SHA})],execution_design=dict(assignment_identity_sha256='a'*64,source_sha256='b'*64),embodiment_config_sha256='c'*64)
    cp=reseal(dict(identity=identity(SimpleNamespace(scene=SimpleNamespace(spec=old))),context={},limitations=[],diagnostic_only=True))
    new=copy.deepcopy(old);configure_spec(new)
    def t(x):return SimpleNamespace(cpu=lambda:np.asarray(x))
    view=SimpleNamespace(get_masses=lambda:t([[.05]]),get_inertias=lambda:t([[1e-5,0,0,0,1e-5,0,0,0,1e-5]]),get_coms=lambda:t([[0,0,0,0,0,0,1]]))
    c=SimpleNamespace(scene=SimpleNamespace(spec=new,objects={'spatula':SimpleNamespace(root_physx_view=view)}))
    r=dict(schema='engineering-e46-cooking-migration-v1',diagnostic_only=True,audit_native_dynamics_only=True,checkpoint=cp,source_scene=old)
    return c,r


def test_only_exact_e46_spatula_source_cooking_changes():
    c,r=setup();assert verify_only_cooking_change(r['source_scene'],c.scene.spec)==['spatula']
    assert c.scene.spec['objects'][0]['reviewed_collision_settings']['coordinate_factor']==100.
    for bad in ('task','mass','shape'):
        new=copy.deepcopy(c.scene.spec)
        if bad=='task':new['id']='E28'
        if bad=='mass':new['objects'][0]['mass']=.06
        if bad=='shape':new['objects'][0]['size'][0]=.15
        with pytest.raises(ValueError):verify_only_cooking_change(r['source_scene'],new)


def test_native_dynamics_preflight_can_only_restore_for_zero_action_audit(tmp_path,monkeypatch):
    c,r=setup();monkeypatch.setenv('VIC_ENGINEERING_CHECKPOINT_REQUEST',str(tmp_path/'request.json'))
    with pytest.raises(ValueError,match='zero-action'):materialize(c,r,{'entry':'e46-relative-insert'})
    x=materialize(c,r,{'entry':'e46-cooked-blade-audit'})
    assert x['identity']==identity(c)
    assert x['context']['e46_cooking_migration']['audit_only']
    assert (tmp_path/'e46-cooking-native-dynamics-preflight.private.json').exists()
    r['audit_native_dynamics_only']=False
    with pytest.raises(ValueError,match='corrected cooking audit'):materialize(c,r,{'entry':'e46-relative-insert'})
