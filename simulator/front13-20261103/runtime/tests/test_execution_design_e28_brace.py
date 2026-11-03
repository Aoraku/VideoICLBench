from types import SimpleNamespace
import numpy as np
from videoicl_isaaclab.execution_design_e28_brace import near_bottom


def test_near_bottom_tracks_actual_body_tilt_instead_of_requested_tool_pose():
    angle=np.radians(-10);c,s=np.cos(angle),np.sin(angle)
    rotation=np.array([[1.,0.,0.],[0.,c,-s],[0.,s,c]])
    p=SimpleNamespace(spec={'objects':[dict(id='bread',size=[.025,.018,.007])]},
        snapshot=lambda:({'bread':dict(pos=np.array([0.,0.,.807]),mat=rotation)},set()))
    actual=near_bottom(p,'bread',[0.,1.,0.])
    assert actual[2]>.803 and np.allclose(rotation.T@(actual-[0,0,.807]),[0,-.018,-.007])


def test_near_bottom_source_yaw_uses_measured_near_face():
    a=np.radians(30);c,s=np.cos(a),np.sin(a)
    rotation=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    p=SimpleNamespace(spec={'objects':[dict(id='bread',size=[.025,.018,.007])]},
        snapshot=lambda:({'bread':dict(pos=np.array([.05,-.09,.807]),mat=rotation)},set()))
    actual=near_bottom(p,'bread',[0.,1.,0.]);local=rotation.T@(actual-[.05,-.09,.807])
    assert abs(local[0])<=.025 and np.isclose(local[1],-.018)and np.isclose(actual[2],.8)
