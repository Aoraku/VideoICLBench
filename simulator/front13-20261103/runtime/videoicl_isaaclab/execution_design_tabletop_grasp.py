"""Measured empty-palm alignment for E08/E13 independent v3 controls.

Finger-axis alignment alone leaves a wrist-tilt degree of freedom. This
candidate removes it with ordinary public rotations before tabletop descent.
It is not a grasp/physics acceptance certificate.
"""
import math
import numpy as np
from .author_orientation import panda_downward_grasp_delta, _axis_angle


def level_empty_palm(author, side, desired_axis):
    spec=author.scene.spec
    if (spec.get('id') not in ('E08','E13') or
            spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102' or
            not author.control_report.get('engineering_reference_only') or
            author.scene.embodiment.name!='franka' or getattr(author,'smooth',False)):
        raise ValueError('Reviewed E08/E13 v3 public-action engineering control required')
    if side not in ('left','right'):raise ValueError('Actual hand identity required')
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    initial_tip=np.asarray(author.tip(side),float)
    if not np.isfinite(initial_tip).all() or initial_tip[2]<.94:
        raise RuntimeError('Level the empty palm above the tabletop before descending')
    for _ in range(32):
        state,_=author.c.snapshot()
        if any(body['grasp'][0 if side=='left' else 1] for body in state.values()):
            raise RuntimeError('Empty-palm rotation refused while actually holding an object')
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose':
            raise ValueError('Actual finger-body geometry required')
        fingers=geometry['fingers']
        jaw=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
        current=author.tcp_rotation_task(side)
        delta=panda_downward_grasp_delta(current,jaw,desired_axis)
        axis,angle=_axis_angle(delta)
        if angle<math.radians(.75):
            author.control_report['empty_palm_alignment']=dict(task=spec['id'],side=side,
                measured_orientation_error_rad=float(angle),public_rotations_only=True,
                native_grasp_validated=False)
            return
        tip=np.asarray(author.tip(side),float)
        if tip[2]<.92 or np.linalg.norm(tip-initial_tip)>.025:
            raise RuntimeError('Actual palm position left the empty-hand rotation envelope')
        index=int(np.argmax(np.abs(axis)));token=labels[index][int(axis[index]<0)]
        degrees=min(5.,max(.5,abs(math.degrees(angle*axis[index]))))
        author.act(token if side=='left' else 'STILL',token if side=='right' else 'STILL',rotation_deg=degrees)
    raise RuntimeError('Actual empty-palm orientation did not converge through public rotations')


def prepare_e08_empty_palm(policy,side,desired_axis):
    """Lift through public actions before the existing strict rotation guard."""
    author=policy.a
    if policy.task!='E08':raise ValueError('E08 empty-palm staging only')
    state,_=policy.snapshot()
    if any(body['grasp'][0 if side=='left'else 1]for body in state.values()):
        raise RuntimeError('E08 staging requires an actually empty hand')
    tip=np.asarray(policy.tip(side),float)
    floor=float(author.floor_clear_tcp(side,floor=.82))
    if not np.isfinite(np.r_[tip,floor]).all():raise ValueError('Finite E08 measured staging geometry required')
    policy.move(side,[float(tip[0]),float(tip[1]),max(.96,float(tip[2]),floor)])
    geometry=author.finger_geometry(side)
    if (geometry.get('source')!='actual_collision_mesh_current_body_pose'
            or not np.isfinite(geometry.get('lowest_z_task_m',float('nan')))
            or geometry['lowest_z_task_m']<.82):
        raise RuntimeError('E08 actual fingers did not clear the tabletop before rotation')
    level_empty_palm(author,side,desired_axis)


def require_e08_table_clearance(author,side):
    """Check actual toes after descent; a planned grasp point is not evidence."""
    spec=author.scene.spec
    if (spec.get('id')!='E08'
        or spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
        or not author.control_report.get('engineering_reference_only')):
        raise ValueError('E08 v3 engineering reference required')
    actual=author.finger_geometry(side)
    lowest=float(actual.get('lowest_z_task_m',float('nan')))
    if (actual.get('source')!='actual_collision_mesh_current_body_pose'
        or not math.isfinite(lowest) or lowest<.8003):
        raise RuntimeError('Actual E08 fingers lack table clearance before grasp')
