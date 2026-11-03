"""Private projected-axis yaw goal without inventing roll/pitch constraints."""
import math
import numpy as np


def working_axis_yaw_target(actual_rotation,working_axis_local,yaw):
    rotation=np.asarray(actual_rotation,float);axis=np.asarray(working_axis_local,float)
    if (rotation.shape!=(3,3) or axis.shape!=(3,) or not np.isfinite(rotation).all()
            or not np.isfinite(axis).all() or not math.isfinite(yaw)
            or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5)
            or not np.isclose(np.linalg.det(rotation),1.,atol=1e-5)):
        raise ValueError('Expected a proper actual rotation, finite axis and yaw')
    world=rotation@axis
    if np.linalg.norm(world[:2])<1e-6:
        raise ValueError('Working axis has no measured horizontal heading')
    delta=math.atan2(math.sin(yaw-math.atan2(world[1],world[0])),
                     math.cos(yaw-math.atan2(world[1],world[0])))
    c,s=math.cos(delta),math.sin(delta)
    return np.array([[c,-s,0],[s,c,0],[0,0,1.]])@rotation
