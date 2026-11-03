"""Production tick must shift measured COM Jacobians to the actual TCP."""
import math
import pytest
import torch
from test_control_smoothness_cpu import NS, linearized_test_plant, qz


def skew(v):
    x,y,z=v.unbind(-1);zero=torch.zeros_like(x)
    return torch.stack((zero,-z,y,z,zero,-x,-y,x,zero),dim=-1).reshape(-1,3,3)


def test_rotated_native_com_is_subtracted_before_world_jacobian_shift(monkeypatch):
    c,_,_=linearized_test_plant()
    robot=c.scene.robots['left'];robot.data.body_quat_w=qz(90)[:,None]
    c.scene.embodiment.tcp=[0.,0.,.1]
    com=torch.tensor([[[.02,-.01,.024,0.,0.,0.,1.]]]);reads=[]
    robot.root_physx_view.get_coms=lambda:(reads.append(1) or com)
    raw=robot.root_physx_view.get_jacobians().clone()
    # An independently known 90-degree wrist rotation maps local (x,y,z)
    # to world (-y,x,z), while the base remains unchanged.
    monkeypatch.setitem(NS,'quat_apply',lambda q,v:torch.stack((-v[:,1],v[:,0],v[:,2]),dim=-1))
    monkeypatch.setitem(NS,'skew_symmetric_matrix',skew)
    seen=[]
    def guard(jac,residual,lo,hi,rotation):
        seen.append(jac.clone());return torch.zeros_like(lo),torch.tensor([False])
    monkeypatch.setitem(NS,'guarded_cartesian_delta',guard)
    NS['begin_action'](c,left='UP',step_mm=2.)
    NS['tick'](c,phase='write');NS['tick'](c,phase='write')
    lever=torch.tensor([-.01,-.02,.076])
    for column in range(7):
        expected=raw[0,0,:3,column]+torch.cross(raw[0,0,3:,column],lever,dim=0)
        torch.testing.assert_close(seen[0][0,:3,column],expected)
    torch.testing.assert_close(seen[0][0,3:],raw[0,0,3:,:7])
    torch.testing.assert_close(robot.root_physx_view.get_jacobians(),raw)
    assert reads==[1]  # Fixed robot mass properties are read once, not every tick.
    assert torch.isfinite(seen[1]).all()


@pytest.mark.parametrize('bad',[float('nan'),float('inf')])
def test_invalid_native_com_refuses_before_actuation(bad):
    c,_,_=linearized_test_plant();robot=c.scene.robots['left'];writes=[]
    robot.root_physx_view.get_coms=lambda:torch.tensor([[[bad,0.,0.,0.,0.,0.,1.]]])
    robot.set_joint_position_target=lambda *a,**k:writes.append(1)
    NS['begin_action'](c,left='UP',step_mm=2.)
    with pytest.raises(RuntimeError,match='Invalid native hand COM'):
        NS['tick'](c,phase='write')
    assert writes==[]


def test_missing_com_api_does_not_silently_assume_link_origin():
    c,_,_=linearized_test_plant();robot=c.scene.robots['left'];writes=[]
    del robot.root_physx_view.get_coms
    robot.set_joint_position_target=lambda *a,**k:writes.append(1)
    NS['begin_action'](c,left='UP',step_mm=2.)
    with pytest.raises(AttributeError):NS['tick'](c,phase='write')
    assert writes==[]
