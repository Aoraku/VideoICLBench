"""Engineering path proposals for the same axiswise public robot actions.

These functions only build pose lists. They never actuate or certify contact.
"""
import numpy as np
from .execution_design_clip_handover import public_rotation_poses


def append_public_move(poses, position, goal, rotation, maximum_step_m=.012):
    current=np.asarray(position,float).copy();goal=np.asarray(goal,float)
    if current.shape!=(3,)or goal.shape!=(3,)or not np.isfinite([current,goal]).all():
        raise ValueError('Finite public translation endpoints required')
    if not np.isfinite(maximum_step_m)or maximum_step_m<=0:
        raise ValueError('Positive public translation bound required')
    for _ in range(400):
        delta=goal-current
        if max(abs(delta))<=.002:return current
        i=int(np.argmax(abs(delta)));current[i]+=np.sign(delta[i])*min(maximum_step_m,abs(delta[i]))
        poses.append(dict(position=current.tolist(),rotation=np.asarray(rotation).tolist()))
    raise ValueError('Engineering public path exceeds bounded translation count')


def grasp_and_travel_poses(current, current_rotation, rotation, grip, height, travel, maximum_step_m=.012):
    poses=public_rotation_poses(current,current_rotation,rotation)
    cursor=np.asarray(current,float).copy()
    for goal in ([*cursor[:2],height],[*np.asarray(grip)[:2],height],grip,*travel):
        cursor=append_public_move(poses,cursor,goal,rotation,maximum_step_m)
    return poses,cursor
