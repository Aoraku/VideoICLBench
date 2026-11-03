import numpy as np
from scipy.spatial.transform import Rotation
from videoicl_isaaclab.execution_design_e31_planned_place import held_normal_spin_goal

def test_measured_attachment_and_down_normal_preserved():
    p=np.array([.1,.2,1.]);R=Rotation.from_euler('xyz',[170,12,5],degrees=True).as_matrix()
    tip=p+np.array([-.08,0,.03]);H=Rotation.from_euler('xyz',[80,20,15],degrees=True).as_matrix()
    points=p+np.array([[-.1,-.1,-.03],[.1,.1,.01],[.1,-.1,-.02],[-.1,.1,.04]])
    target,goal,gap=held_normal_spin_goal(p,R,tip,H,points,[-.018,.12],.03,.90,-45)
    T=goal@H.T;root=target-T@(tip-p)
    np.testing.assert_allclose(T@R[:,2],R[:,2],atol=1e-12)
    np.testing.assert_allclose(root[:2],[-.018,.12],atol=1e-12)
    projected=(points-p)@T.T+root
    assert abs(projected[:,2].min()-.90-.03)<1e-12

def test_zero_spin_matches_existing_translation():
    p=np.array([.1,.2,1.]);tip=p+[-.08,.01,.03];points=p+np.array([[-.1,-.1,-.03],[.1,.1,.01]])
    target,goal,gap=held_normal_spin_goal(p,np.eye(3),tip,np.eye(3),points,[-.018,.12],.03,.90,0)
    np.testing.assert_allclose(target,tip+np.array([-.118,-.08,-.04]),atol=1e-12)
    np.testing.assert_allclose(goal,np.eye(3),atol=1e-12)
