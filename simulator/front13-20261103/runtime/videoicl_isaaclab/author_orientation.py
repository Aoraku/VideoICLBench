"""Private physical orientation trajectories through native robot actuators.

The measured TCP is held fixed while a task-frame rotation is interpolated in
robot-base coordinates. Only native controller pose/velocity targets are sent;
no object pose, robot joint state, evaluator answer or physics clock is assigned.
This module imports neither Isaac nor torch until a native tensor is needed.
"""
import math
import numpy as np

from .author_feedforward import minimum_jerk_phase_rate
from .recording_trajectory import minimum_jerk, trajectory_ticks, frame_due


def _numpy(value):
    if hasattr(value, 'detach'):
        value = value.detach()
    if hasattr(value, 'cpu'):
        value = value.cpu()
    return np.asarray(value.numpy() if hasattr(value, 'numpy') else value, dtype=float)


def _copy(value):
    return value.clone() if hasattr(value, 'clone') else value.copy()


def _rotation(value, label):
    matrix = _numpy(value)
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
            or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-5, rtol=0)
            or not math.isclose(float(np.linalg.det(matrix)), 1., abs_tol=1e-5)):
        raise ValueError('Finite proper rotation matrix required: ' + label)
    return matrix


def _unit_quaternion(value):
    q = _numpy(value)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-10:
        raise ValueError('Finite nonzero wxyz quaternion required')
    return q / np.linalg.norm(q)


def _quaternion_matrix(value):
    w, x, y, z = _unit_quaternion(value)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def _quaternion_product(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return np.array([w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                     w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v])


def _axis_angle(matrix):
    # Use a stable matrix-to-quaternion branch at pi, where a skew/sin(angle)
    # formula is singular. Exact pi has two equivalent axes: select the sign
    # whose largest component is positive, deterministically.
    trace = float(np.trace(matrix))
    if trace > 0:
        scale = 2*math.sqrt(max(0., trace+1))
        q = np.array([scale/4, (matrix[2, 1]-matrix[1, 2])/scale,
                      (matrix[0, 2]-matrix[2, 0])/scale,
                      (matrix[1, 0]-matrix[0, 1])/scale])
    else:
        i = int(np.argmax(np.diag(matrix)))
        j, k = (i+1) % 3, (i+2) % 3
        scale = 2*math.sqrt(max(0., 1+matrix[i, i]-matrix[j, j]-matrix[k, k]))
        q = np.zeros(4)
        q[0] = (matrix[k, j]-matrix[j, k])/scale
        q[i+1] = scale/4
        q[j+1] = (matrix[i, j]+matrix[j, i])/scale
        q[k+1] = (matrix[i, k]+matrix[k, i])/scale
    q = _unit_quaternion(q)
    if q[0] < 0:
        q = -q
    if abs(q[0]) < 1e-10 and q[1+int(np.argmax(np.abs(q[1:])))] < 0:
        q = -q
    sine = float(np.linalg.norm(q[1:]))
    if sine < 1e-12:
        return np.array([1., 0., 0.]), 0.
    return q[1:]/sine, 2*math.atan2(sine, max(0., float(q[0])))


def _quaternion_distance(a, b):
    dot = float(_unit_quaternion(a) @ _unit_quaternion(b))
    return 2*math.acos(float(np.clip(abs(dot), 0., 1.)))


def panda_downward_grasp_delta(current_task_matrix, jaw_axis_task, desired_axis_task, *, joint7_state=None):
    """Align Panda's finger axis and palm approach before a tabletop pinch.

    Matching only the finger separation axis leaves an unconstrained wrist
    tilt. On millimetre-thick pieces that tilt lets one real fingertip hit the
    table before the other reaches the piece. This returns a rotation target;
    the caller must execute and verify it through native actuator motion.
    """
    current = _rotation(current_task_matrix, 'measured Panda hand')
    jaw = _numpy(jaw_axis_task)
    desired = _numpy(desired_axis_task)
    if (jaw.shape != (3,) or desired.shape != (3,)
            or not np.isfinite(jaw).all() or not np.isfinite(desired).all()
            or np.linalg.norm(jaw) < 1e-8 or np.linalg.norm(desired) < 1e-8):
        raise ValueError('Finite nonzero measured and desired finger axes required')
    jaw = jaw / np.linalg.norm(jaw)
    desired = desired / np.linalg.norm(desired)
    # Settled source props can lean slightly on their real collision mesh.
    # Preserve the measured horizontal heading while keeping both fingertips
    # level; a genuinely vertical reviewed pinch is still incompatible.
    if abs(desired[2]) > math.sin(math.radians(6)):
        raise ValueError('Downward tabletop pinch requires a horizontal finger axis; measured task axis='+repr(desired.tolist()))
    desired[2] = 0.
    desired /= np.linalg.norm(desired)
    # Select either physically equivalent finger assignment by actual wrist
    # rotation length. Near orthogonal axes use a deterministic tie break.
    down = np.array([0., 0., -1.])
    candidates = []
    for direction in (desired, -desired):
        target = np.column_stack((np.cross(direction, down), direction, down))
        delta = target @ current.T
        candidates.append((_axis_angle(delta)[1], delta, direction))
    if joint7_state is not None:
        joint=np.asarray(joint7_state,float)
        if (joint.shape!=(3,) or not np.isfinite(joint).all()
                or not joint[1]<=joint[0]<=joint[2] or joint[1]>=joint[2]):
            raise ValueError('Actual joint7 position and native limits required')
        if float(current[:,2]@down)>.98:
            def predicted_limit_violation(candidate):
                axis,angle=_axis_angle(candidate[1])
                predicted=joint[0]+angle*float(axis@current[:,2])
                return max(joint[1]-predicted,predicted-joint[2],0.)
            violations=[predicted_limit_violation(candidate) for candidate in candidates]
            if abs(violations[0]-violations[1])>1e-6:
                return _rotation(candidates[int(violations[1]<violations[0])][1],
                                 'native-limit-aware equivalent finger assignment')
    a, b = candidates
    if abs(a[0]-b[0]) < 1e-7:
        selected = a if float(jaw @ desired) >= -1e-7 else b
    else:
        selected = min(candidates, key=lambda item: item[0])
    return _rotation(selected[1], 'downward Panda grasp delta')


def native_rotate(controller, side, delta_task_matrix, guard=None, done=None, *,
                  max_angular_speed=None, max_angular_acceleration=None,
                  position_tolerance=.002, orientation_tolerance=math.radians(2),
                  array_module=None, pivot_task=None, axial_translation_task=None):
    """Apply one private task-frame rotation, starting at the measured TCP.

    ``delta_task_matrix`` premultiplies the measured task-frame orientation.
    Exact pi chooses a deterministic positive-largest-component task axis.
    ``guard`` is called before/after every physical tick, including settling;
    ``done`` can freeze the measured pose at an early contact stop. The result
    reports actuator tracking, never task success. Residual orientation targets
    are removed by freezing the measured pose on return or an in-motion error.

    Velocity feedforward is opt-in on Controller. Its base-frame angular twist
    is routed through Controller.tick's native Jacobian and joint speed caps.
    Without it, requested angular speed is capped at .25rad/s for the old PD
    controller. ``array_module=np`` enables an independent CPU actuator adapter.
    """
    if side not in controller.scene.robots:
        raise ValueError('Unknown physical robot hand: ' + str(side))
    delta = _rotation(delta_task_matrix, 'task delta')
    task_rotation = _rotation(controller.scene.layout.task_rotation, 'task-to-world')
    ff = bool(getattr(controller, 'author_joint_velocity_feedforward', False))
    speed = (1.2 if ff else .25) if max_angular_speed is None else float(max_angular_speed)
    acceleration = (3. if ff else .6) if max_angular_acceleration is None else float(max_angular_acceleration)
    if (not all(math.isfinite(v) for v in (speed, acceleration, position_tolerance, orientation_tolerance))
            or min(speed, acceleration, position_tolerance, orientation_tolerance) <= 0
            or position_tolerance > .05 or orientation_tolerance > math.pi):
        raise ValueError('Invalid private angular motion or tracking limits')
    if not ff:
        speed = min(speed, .25)
    if ff and (not hasattr(controller, '_author_ff_twists')
               or not callable(getattr(controller, 'clear_author_velocity_feedforward', None))):
        raise ValueError('Feedforward controller must expose native velocity cleanup')
    start_pos, start_quat = controller.pose(side)
    if tuple(start_pos.shape) != (1, 3) or tuple(start_quat.shape) != (1, 4):
        raise ValueError('Private rotation requires one measured native TCP')
    if not np.isfinite(_numpy(start_pos)).all():
        raise ValueError('Finite measured TCP required')
    start_pos = _copy(start_pos)
    start_q = _unit_quaternion(_numpy(start_quat)[0])
    base_q = _numpy(controller.scene.robots[side].data.root_quat_w)
    if base_q.shape != (1, 4):
        raise ValueError('One measured native robot-base quaternion required')
    base_rotation = _quaternion_matrix(base_q[0])
    pivot = None
    if pivot_task is not None:
        point=np.asarray(pivot_task,float)
        if point.shape!=(3,) or not np.isfinite(point).all():raise ValueError('Finite physical pivot required')
        world=np.asarray(controller.scene.task_to_world(point),float)
        root=_numpy(controller.scene.robots[side].data.root_pos_w)[0]
        pivot=base_rotation.T@(world-root)
    task_axis, angle = _axis_angle(delta)
    base_axis = base_rotation.T @ task_rotation @ task_axis
    base_axis /= np.linalg.norm(base_axis)
    feed_task=np.zeros(3)
    if axial_translation_task is not None:
        feed_task=np.asarray(axial_translation_task,float)
        if (feed_task.shape!=(3,) or not np.isfinite(feed_task).all()
                or np.linalg.norm(feed_task)>.005
                or np.linalg.norm(np.cross(feed_task,task_axis))>1e-8):
            raise ValueError('Private helical feed must be finite, axial and at most5mm')
    feed_base=base_rotation.T@task_rotation@feed_task
    ticks = trajectory_ticks(angle, controller.dt, speed, acceleration)
    if np.linalg.norm(feed_task)>0:
        ticks=max(ticks,trajectory_ticks(float(np.linalg.norm(feed_task)),controller.dt,.0225,.18))
    if ticks*controller.dt > 30.+1e-9:
        raise ValueError('Private orientation trajectory exceeds 30s physical plan')
    xp = array_module
    if xp is None:
        import torch
        xp = torch

    def tensor(value):
        if xp is np:
            return np.asarray(value, dtype=getattr(start_quat, 'dtype', float))
        return xp.as_tensor(value, dtype=start_quat.dtype, device=start_quat.device)

    def quaternion(phase):
        half = .5*angle*minimum_jerk(phase)
        return _quaternion_product(np.r_[math.cos(half), base_axis*math.sin(half)], start_q)

    def position(phase):
        translation=feed_base*minimum_jerk(phase)
        if pivot is None:
            if axial_translation_task is None:return _copy(start_pos)
            return tensor((_numpy(start_pos)[0]+translation)[None])
        half=.5*angle*minimum_jerk(phase)
        rotation=_quaternion_matrix(np.r_[math.cos(half),base_axis*math.sin(half)])
        return tensor((pivot+rotation@(_numpy(start_pos)[0]-pivot)+translation)[None])

    def freeze():
        actual_pos, actual_quat = controller.pose(side)
        controller.targets[side] = (_copy(actual_pos), _copy(actual_quat))

    before = float(controller.sim.current_time)
    previous_steps = controller.steps
    fps = controller.scene.embodiment.config['physics']['render_hz']
    end_q = quaternion(1.)
    end_pos = position(1.)
    motion_ticks = settle_ticks = 0
    done_reached = started = False
    desired_q = end_q
    try:
        if guard is not None:
            guard()
        controller.evaluator.event_enabled = True
        started = True
        for index in range(1, ticks+1):
            if guard is not None:
                guard()
            if done is not None and done():
                done_reached = True
                break
            phase = index/ticks
            controller.targets[side] = (position(phase), tensor(quaternion(phase)[None]))
            if ff:
                omega = base_axis*angle*minimum_jerk_phase_rate(phase, ticks*controller.dt)
                velocity=np.zeros(3) if pivot is None else np.cross(omega,_numpy(controller.targets[side][0])[0]-pivot)
                velocity+=feed_base*minimum_jerk_phase_rate(phase,ticks*controller.dt)
                controller._author_ff_twists[side] = tensor(np.r_[velocity, omega][None])
            controller.tick(render=frame_due(controller.physics_ticks+1, controller.dt, fps))
            motion_ticks += 1
            if guard is not None:
                guard()
            if done is not None and done():
                done_reached = True
                break
        if done_reached:
            freeze()
            desired_q = _unit_quaternion(_numpy(controller.targets[side][1])[0])
        if ff:
            controller.clear_author_velocity_feedforward((side,))
        minimum_settle = round(.12/controller.dt)
        maximum_settle = round(.8/controller.dt)
        stopped_at = 0 if done_reached else None
        # A delayed servo can first reach a contact predicate while settling.
        # Freeze that measured pose too, then provide the same bounded hold.
        for _ in range(maximum_settle+minimum_settle):
            if not done_reached and done is not None and done():
                done_reached = True
                stopped_at = settle_ticks
                freeze()
                desired_q = _unit_quaternion(_numpy(controller.targets[side][1])[0])
            if ((done_reached and settle_ticks-stopped_at >= minimum_settle)
                    or (not done_reached and settle_ticks >= maximum_settle)):
                break
            if guard is not None:
                guard()
            controller.tick(render=frame_due(controller.physics_ticks+1, controller.dt, fps))
            settle_ticks += 1
            if guard is not None:
                guard()
            if not done_reached and done is not None and done():
                done_reached = True
                stopped_at = settle_ticks
                freeze()
                desired_q = _unit_quaternion(_numpy(controller.targets[side][1])[0])
            actual_pos, actual_q = controller.pose(side)
            linear_error = float(np.linalg.norm(_numpy(controller.targets[side][0])- _numpy(actual_pos)))
            angular_error = _quaternion_distance(_numpy(controller.targets[side][1])[0], _numpy(actual_q)[0])
            if (not done_reached and settle_ticks >= minimum_settle and linear_error <= position_tolerance
                    and angular_error <= orientation_tolerance):
                break
        actual_pos, actual_q = controller.pose(side)
        position_error = float(np.linalg.norm(_numpy(end_pos)-_numpy(actual_pos)))
        angular_error = _quaternion_distance(desired_q, _numpy(actual_q)[0])
        remaining = _quaternion_distance(end_q, _numpy(actual_q)[0])
        hold_position_error = float(np.linalg.norm(_numpy(controller.targets[side][0])-_numpy(actual_pos)))
        original_target_reached=(remaining <= orientation_tolerance and position_error <= position_tolerance)
        controller.steps += 1
        return dict(step_before=previous_steps, step_after=controller.steps,
                    simulation_seconds=float(controller.sim.current_time)-before,
                    planned_ticks=ticks, motion_ticks=motion_ticks, settle_ticks=settle_ticks,
                    done_reached=done_reached, joint_velocity_feedforward=ff,
                    planned_rotation_rad=angle, task_axis=task_axis.tolist(), base_axis=base_axis.tolist(),
                    pivot_task=None if pivot_task is None else point.tolist(),
                    axial_translation_task=None if axial_translation_task is None else feed_task.tolist(),
                    max_angular_speed_rad_s=speed, max_angular_acceleration_rad_s2=acceleration,
                    tracking_error_m={side:position_error}, tracking_error_rad={side:remaining},
                    hold_tracking_error_m={side:hold_position_error},
                    hold_tracking_error_rad={side:angular_error},
                    original_target_quaternion_base_wxyz=end_q.tolist(),
                    hold_target_quaternion_base_wxyz=desired_q.tolist(),
                    final_quaternion_base_wxyz=_unit_quaternion(_numpy(actual_q)[0]).tolist(),
                    remaining_rotation_rad=remaining,
                    target_reached=original_target_reached,
                    original_target_reached=original_target_reached,
                    hold_target_reached=(angular_error <= orientation_tolerance and
                                         hold_position_error <= position_tolerance))
    finally:
        # Freeze the achieved pose even after a mid-trajectory guard failure.
        # A later action must never inherit an unachieved orientation backlog.
        try:
            if started:
                freeze()
        finally:
            if ff:
                controller.clear_author_velocity_feedforward((side,))
