from copy import deepcopy
from types import SimpleNamespace as N
import pytest
from videoicl_isaaclab.engineering_checkpoint import identity,reseal
from videoicl_isaaclab.execution_design_e37_cooking import configure_spec,SOURCE_SHA
from videoicl_isaaclab.engineering_e37_cooking_fixture import materialize


class Native:
    def __init__(self,value):self.value=value
    def cpu(self):return self
    def tolist(self):return self.value


def test_source_driver_mass_is_checked_without_rejecting_kinematic_sentinel(tmp_path,monkeypatch):
    old=dict(id='E37',variant='A',seed=4201,execution_design=dict(
        assignment_identity_sha256='a',source_sha256='b'),embodiment_config_sha256='c',
        objects=[dict(id='driver',mass=.04,source_asset=dict(sha256=SOURCE_SHA)),dict(id='socket_left',mass=.1)])
    cp=reseal(dict(identity=identity(N(scene=N(spec=old))),context={},limitations=[],
        objects={'driver':{'root_state_task':[1,2,3]}},readback={'object_grasps':{'driver':[True,False]}}))
    new=deepcopy(old);configure_spec(new)
    def asset(mass):return N(root_physx_view=N(get_masses=lambda:Native([mass]),
        get_inertias=lambda:Native([[1.]*9]),get_coms=lambda:Native([[0.,0.,0.,0.,0.,0.,1.]])))
    c=N(scene=N(spec=new,objects={'driver':asset(.04),'socket_left':asset(0.)}))
    recipe=dict(schema='engineering-e37-cooking-migration-v1',diagnostic_only=True,
        checkpoint=cp,source_scene=old,rebuild_driver_grasp_with_public_close=True)
    request=dict(parameters={'rebuild_source_fidelity_grasp':True})
    monkeypatch.setenv('VIC_ENGINEERING_CHECKPOINT_REQUEST',str(tmp_path/'request.json'))
    got=materialize(c,recipe,request)
    assert got['objects']==cp['objects']
    assert got['identity']['physical_geometry_sha256']!=cp['identity']['physical_geometry_sha256']
    assert 'driver'not in got['readback']['object_grasps']
    assert cp['readback']['object_grasps']['driver']==[True,False]
    c.scene.objects['driver']=asset(.05)
    with pytest.raises(ValueError,match='declared mass: driver'):materialize(c,recipe,request)
