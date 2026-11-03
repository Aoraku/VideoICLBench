"""Public engineering turns: finish accepted targets before the next delta."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def accepted_pose_task(policy,side):
    from .layout import rotation_matrix
    def array(x):return np.asarray(x.detach().cpu().numpy()if hasattr(x,'detach')else x,float)
    robot=policy.a.scene.robots[side];position,quaternion=policy.c.targets[side]
    bp=array(robot.data.root_pos_w)[0];br=rotation_matrix(array(robot.data.root_quat_w)[0])
    p=array(position).reshape(-1,3)[0];r=rotation_matrix(array(quaternion).reshape(-1,4)[0])
    return policy.a.scene.world_to_task(bp+br@p),np.asarray(policy.a.scene.layout.task_rotation).T@br@r


def finish_accepted_public_rotation(policy,side,guard,before_action=None):
    """Use native public tolerances; stop on actual persistent lack of progress."""
    history=[];actions=0
    while True:
        guard();row=policy.c.action_feedback()['control_feedback'][side]
        angle=float(row['orientation_error_rad']);position=float(row['position_error_m'])
        angular_tolerance=float(row['orientation_tolerance_rad']);position_tolerance=float(row['position_tolerance_m'])
        if not np.isfinite([angle,position,angular_tolerance,position_tolerance]).all()or min(angular_tolerance,position_tolerance)<=0:
            raise ToolExecutionError('Actual public rotation tolerance/feedback unavailable')
        if angle<=angular_tolerance and position<=position_tolerance:return actions
        target,r=accepted_pose_task(policy,side);current=np.asarray(policy.a.tcp_rotation_task(side))
        guard.check(target=target,rotation=r@current.T)
        metric=max(angle/angular_tolerance,position/position_tolerance);history.append(metric)
        if len(history)>=13 and history[-13]-min(history[-12:])<.02:
            raise ToolExecutionError('Accepted public rotation has no actual progress within12 continuation actions')
        if before_action:before_action()
        policy.act(side,'STILL');actions+=1


def turn_to_fixed_goal(policy,side,target,guard,tolerance_degrees,on_rotation,before_action=None):
    from .author_orientation import _axis_angle
    target=np.asarray(target,float)
    if target.shape!=(3,3)or not np.isfinite(target).all()or not np.allclose(target.T@target,np.eye(3),atol=1e-5)or np.linalg.det(target)<.999:
        raise ValueError('Saved proper absolute rotation goal required')
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'));holds=0;commands=0
    while True:
        holds+=finish_accepted_public_rotation(policy,side,guard,before_action)
        axis,angle=_axis_angle(target@np.asarray(policy.a.tcp_rotation_task(side)).T)
        if angle<=math.radians(tolerance_degrees):return dict(public_holds=holds,new_rotation_commands=commands,remaining_degrees=math.degrees(angle))
        k=int(np.argmax(abs(axis)))
        if before_action:before_action()
        on_rotation()
        policy.act(side,labels[k][int(axis[k]<0)],degrees=min(10.,max(.5,abs(math.degrees(angle*axis[k])))))
        commands+=1
