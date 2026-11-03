"""The E23/E24 planner must use the measured hand COM-to-TCP shift."""
import sys
from types import SimpleNamespace,ModuleType
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e24_transit as module


class Tensor(np.ndarray):
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return np.asarray(self)


def tensor(value):return np.asarray(value,float).view(Tensor)


def test_capture_model_uses_com_to_tcp_instead_of_adding_link_tcp_twice(monkeypatch):
    fake=ModuleType('isaaclab.utils.math')
    fake.matrix_from_quat=lambda q:tensor(np.tile(np.eye(3),(len(q),1,1)))
    monkeypatch.setitem(sys.modules,'isaaclab.utils.math',fake)
    names=['panda_link'+str(i)for i in range(8)]+['panda_hand','panda_leftfinger','panda_rightfinger']
    hand=8;count=len(names);position=np.tile([1.,2,3],(1,count,1));quaternion=np.tile([1.,0,0,0],(1,count,1))
    coms=np.tile([0.,0,.024,0,0,0,1],(1,count,1));jac=np.zeros((1,count-1,6,7));jac[:,:,4,:]=1.
    robot=SimpleNamespace(is_fixed_base=True,joint_names=['panda_joint'+str(i)for i in range(1,8)],
        root_physx_view=SimpleNamespace(get_coms=lambda:tensor(coms),get_jacobians=lambda:tensor(jac)),
        data=SimpleNamespace(body_pos_w=tensor(position),body_quat_w=tensor(quaternion),
            body_link_pos_w=tensor(position),body_com_pos_w=tensor(position+[0,0,.024]),
            joint_pos=tensor(np.zeros((1,7))),joint_pos_limits=tensor([[[-2,2]]*7])))
    author=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot},embodiment=SimpleNamespace(tcp=[0,0,.1]),
        layout=SimpleNamespace(task_rotation=np.eye(3)),world_to_task=lambda p:p),
        tip=lambda _:np.array([1.,2,3.1]),tcp_rotation_task=lambda _:np.eye(3))
    author._e23_robot_collision_cache=({'left':[(i,name,np.array([[0.,0,0],[.01,.01,.01]]))for i,name in enumerate(names)]},[])
    monkeypatch.setattr(module,'actual_robot_collision_geometry',lambda _:dict(complete=True))
    policy=SimpleNamespace(a=author,c=SimpleNamespace(ids={'left':(list(range(7)),[],hand)}))
    model,_=module.capture_model(policy,'left')
    assert model['jacobian'][0,0]==pytest.approx(.076)
    assert model['jacobian'][0,0]!=pytest.approx(.1)
    np.testing.assert_allclose(model['position'],[1,2,3.1])
    assert len(model['clouds'])==11
