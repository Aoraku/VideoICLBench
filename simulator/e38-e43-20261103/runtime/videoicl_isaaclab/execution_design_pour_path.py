"""E45 engineering-only complete public-action cup path proposal.

Cup and TCP offsets are measured before acquisition. No object is moved here;
all grips, contained balls and delivery must later pass native physics checks.
"""
import numpy as np
from .execution_design_tool_pose_paths import grasp_and_travel_poses,append_public_move
from .execution_design_clip_handover import public_rotation_poses
from .realworld_tool_expert import _axis_rotation


def candidate_poses(position,current_rotation,hand_rotation,grip,approach_height,
                    transport_height,body_rotation,grip_local,rim_local,rim_target,
                    pour_token,maximum_step_m=.012,include_return=True,maximum_angle_deg=115,approach_staging=None):
    if pour_token not in ('ROLL_LEFT','ROLL_RIGHT','PITCH_UP','PITCH_DOWN'):
        raise ValueError('Reviewed public cup tilt token required')
    body=np.asarray(body_rotation,float);grip_local=np.asarray(grip_local,float)
    rim=np.asarray(rim_local,float);rim_target=np.asarray(rim_target,float)
    hand=np.asarray(hand_rotation,float);relative_hand=body.T@hand
    if approach_staging is None:
        poses,cursor=grasp_and_travel_poses(position,current_rotation,hand,grip,approach_height,[],maximum_step_m)
    else:
        from .execution_design_pour_acquire import approach_poses
        poses=public_rotation_poses(position,current_rotation,hand)
        approach,cursor=approach_poses(position,hand,grip,approach_staging,approach_height,maximum_step_m)
        poses+=approach
    cursor=append_public_move(poses,cursor,[*cursor[:2],transport_height],hand,maximum_step_m)
    cursor=append_public_move(poses,cursor,rim_target+body@(grip_local-rim),hand,maximum_step_m)
    axis=[1.,0.,0.]if pour_token.startswith('ROLL')else[0.,1.,0.]
    sign=1 if pour_token in('ROLL_LEFT','PITCH_UP')else-1
    for angle in range(5,int(maximum_angle_deg)+1,5):
        turned=_axis_rotation(axis,sign*np.deg2rad(angle))@body
        hand=turned@relative_hand
        # Actual code turns at fixed TCP, then corrects the measured rim.
        poses.append(dict(position=cursor.tolist(),rotation=hand.tolist()))
        cursor=append_public_move(poses,cursor,rim_target+turned@(grip_local-rim),hand,maximum_step_m)
    if include_return:
        poses+=public_rotation_poses(cursor,hand,hand_rotation)
        cursor=append_public_move(poses,cursor,[*cursor[:2],transport_height],hand_rotation,maximum_step_m)
        cursor=append_public_move(poses,cursor,[*np.asarray(grip)[:2],transport_height],hand_rotation,maximum_step_m)
        cursor=append_public_move(poses,cursor,np.asarray(grip)+[0,0,.001],hand_rotation,maximum_step_m)
        append_public_move(poses,cursor,cursor+[0,0,.06],hand_rotation,maximum_step_m)
    return poses
