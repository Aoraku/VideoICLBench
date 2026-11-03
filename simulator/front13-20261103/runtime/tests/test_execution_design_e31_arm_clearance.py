import json
from pathlib import Path
import numpy as np
from videoicl_isaaclab.execution_design_e31_arm_clearance import transformed_meshes
from videoicl_isaaclab.execution_design_drawer_ik_probe import forward_at_delta


def measured():
    return json.loads((Path(__file__).parent/'fixtures/e31_return_yaw_cp110.json').read_text())['measured']


def test_zero_delta_preserves_every_actual_collision_vertex():
    m=measured();points=np.array([[0.,0.,.8],[.1,.2,.9],[-.1,.2,1.]])
    meshes={'panda_link0':points,'panda_link6':points,'panda_hand':points}
    after=transformed_meshes(m,meshes,m['q'])
    assert all(np.allclose(points,after[name],atol=1e-12)for name in meshes)


def test_hand_collision_geometry_follows_independently_checked_tcp_poe():
    m=measured();p=np.array(m['position']);r=np.array(m['rotation_task']);delta=np.array([.02,-.03,.01,.04,0.,.02,-.02])
    points=np.r_[p[None],(p+r[:,0]*.03)[None],(p+r[:,1]*.02)[None]]
    after=transformed_meshes(m,{'panda_hand':points},np.array(m['q'])+delta)['panda_hand']
    ep,er=forward_at_delta(p,r,np.array(m['jacobian']),delta)
    assert np.allclose(after[0],ep,atol=1e-10)
    assert np.allclose(after[1]-after[0],er[:,0]*.03,atol=1e-10)
    assert np.allclose(after[2]-after[0],er[:,1]*.02,atol=1e-10)


def test_forearm_link6_does_not_falsely_move_with_joint7():
    m=measured();p=np.array(m['position']);points=np.r_[(p+[.03,.02,.04])[None],(p+[.01,0.,.02])[None]]
    joints=np.array(m['q']);joints[6]+=.3
    after=transformed_meshes(m,{'panda_link6':points,'panda_hand':points},joints)
    assert np.allclose(after['panda_link6'],points,atol=1e-12)
    assert not np.allclose(after['panda_hand'],points,atol=1e-5)
