"""E40 public-action preparation: lay the held clip, then pinch its handles."""
import numpy as np

from .realworld_tool_expert import ToolExecutionError, _axis_rotation
from .execution_design_clip_grasp import actual_handles, convex_meshes_clear
from .execution_design_clip_handover import (
    open_clip_hand, plan_pair, follow_pair, public_rotation_poses, rotation_clear, _log,
)


def horizontal_handle_turn(points):
    """One shortest tilt makes the measured pair horizontal, without pose writes."""
    points = np.asarray(points, float)
    if points.shape != (2, 3) or not np.isfinite(points).all():
        raise ValueError('Two measured finite source handles required')
    delta = points[1] - points[0]
    if np.linalg.norm(delta) < .001:
        raise ValueError('Distinct actual source handles required')
    horizontal = delta.copy(); horizontal[2] = 0.
    if np.linalg.norm(horizontal) < 1e-6:
        horizontal = np.array([np.linalg.norm(delta), 0., 0.])
    horizontal *= np.linalg.norm(delta) / np.linalg.norm(horizontal)
    # Both horizontal directions are equivalent for an ordinary pinch.
    if delta @ horizontal < 0:
        horizontal *= -1
    axis = np.cross(delta, horizontal)
    angle = float(np.arctan2(np.linalg.norm(axis), delta @ horizontal))
    if np.linalg.norm(axis) < 1e-9:
        return np.eye(3)
    return _axis_rotation(axis / np.linalg.norm(axis), angle)


def horizontal_handle_turns(points):
    """Both analytic tilt directions preserve a horizontal handle pair."""
    from .author_orientation import _axis_angle
    short = horizontal_handle_turn(points)
    axis, angle = _axis_angle(short)
    if angle < 1e-9:
        return [short]
    return [short, _axis_rotation(axis, angle - np.pi)]


def squeeze_from_table(policy, clip, handle_ref, body_ref, support, side):
    from .execution_design_native_finger_mesh import measured_mesh
    from .execution_design_mechanism_geometry import collision_parts
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .author_orientation import _axis_angle

    if policy.task != 'E40' or not getattr(policy.c, '_public_gripper_limits', None):
        raise ValueError('Explicit E40 ramped public-action engineering route required')
    policy.require_held(body_ref, support)
    names = ('panda_hand', *policy.a.scene.embodiment.fingers)
    floor = table_bounds_task(policy.a.scene)['top']
    held = lambda: policy.require_held(body_ref, support)
    open_clip_hand(policy, side, held)
    # The empty hand starts below the held clip. Leave sideways before turning
    # the loaded hand, rather than lifting its palm through the payload.
    away = policy.tip(side).copy()
    clip_y = float(policy.frame(body_ref)[0][1])
    sign = 1. if side == 'left' else -1.
    if sign * (away[1] - clip_y) < .14:
        away[1] = clip_y + sign * .16
    empty = [measured_mesh(policy.a, side, n) for n in names]
    obstacles = [measured_mesh(policy.a, support, n) for n in names]
    obstacles += [np.asarray(p['vertices_task']) for p in collision_parts(policy.a, clip['mechanism'])]
    delta = away - policy.tip(side)
    if not all(convex_meshes_clear(np.vstack((m, m + delta)), o, clearance=.0005)
               for m in empty for o in obstacles):
        raise ToolExecutionError('Empty hand has no measured sideways clip retreat')
    policy.stage('clip-table-support-empty-retreat')
    policy.move(side, away, held)

    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    points, _, _ = actual_handles(policy.mechanisms()[clip['mechanism']],
                                  asset['physical_affordances']['body_geometry'])
    current = np.asarray(policy.a.tcp_rotation_task(support))
    alternatives = horizontal_handle_turns(points)
    tcp = policy.tip(support)
    loaded = [measured_mesh(policy.a, support, n) for n in names]
    loaded += [np.asarray(p['vertices_task']) for p in collision_parts(policy.a, clip['mechanism'])]
    local = [(m - tcp) @ current for m in loaded]
    obstacles = [measured_mesh(policy.a, side, n) for n in names]
    measured = capture(policy.a, policy.c, support)
    chosen = None
    # These are CPU waypoints, not separate simulation attempts. The first
    # continuous clear path wins. Yaw leaves both handle heights unchanged.
    # A raised quarter-turn has a measured continuous native-J branch here;
    # the reversed tilt is rejected if its palm would lie below the table.
    turns = [_axis_rotation([0., 0., 1.], np.pi/2) @ alternatives[0], *alternatives]
    choices = [(turn @ current, waypoints) for turn in turns
               for waypoints in ([tcp + [0., 0., .08]], [])]
    for desired, waypoints in choices:
        hand_min = min(float((m @ desired.T)[:, 2].min()) for m in local[:3])
        payload_min = min(float((m @ desired.T)[:, 2].min()) for m in local[3:])
        placement_min_hand_z = floor + .0005 + hand_min - payload_min
        if placement_min_hand_z < floor + .0002:
            _log(policy, 'clip-table-support-plans.private.jsonl', dict(
                target_rotation=desired.tolist(), placement_min_hand_z=placement_min_hand_z,
                collision_clear=False, reason='loaded_hand_below_table_at_payload_placement',
                native_success=False))
            continue
        previous = tcp.copy(); poses = []
        translation_clear = True
        for target in waypoints:
            swept = [np.vstack((m @ current.T + previous, m @ current.T + target)) for m in local]
            translation_clear = translation_clear and all(
                m[:, 2].min() >= floor + .0002
                and all(convex_meshes_clear(m, o, clearance=.0005) for o in obstacles)
                for m in swept)
            start = previous.copy()
            count = max(1, int(np.ceil(np.linalg.norm(target - start) / .008)))
            poses += [dict(position=(start + (target-start)*i/count).tolist(), rotation=current.tolist())
                      for i in range(1, count+1)]
            previous = target
        turns = public_rotation_poses(previous, current, desired)
        poses += turns
        path = solve_local_pose_path(measured['position'], measured['rotation_task'],
            measured['jacobian'], measured['q'], measured['limits'], poses,
            max_rotation_step_rad=np.deg2rad(1.))
        clear = translation_clear and rotation_clear(local, previous, current, turns, obstacles, floor)
        _log(policy, 'clip-table-support-plans.private.jsonl', dict(
            waypoints=[p.tolist() for p in waypoints], target_rotation=desired.tolist(),
            measured=measured, path=path,
            collision_clear=clear, placement_min_hand_z=placement_min_hand_z,
            loaded_local_meshes=[m.tolist() for m in local],
            other_hand_meshes=[m.tolist() for m in obstacles], native_success=False))
        if path['feasible'] and clear:
            chosen = (desired, waypoints)
            break
    if chosen is None:
        raise ToolExecutionError('Loaded clip table-placement turn has no measured clear joint path')
    desired, waypoints = chosen
    for waypoint in waypoints:
        policy.move(support, waypoint, held)
    policy.stage('clip-table-support-lay-horizontal')
    for _ in range(90):
        held()
        axis, angle = _axis_angle(desired @ np.asarray(policy.a.tcp_rotation_task(support)).T)
        if angle < np.deg2rad(1.):
            break
        i = int(np.argmax(abs(axis)))
        token = (('ROLL_LEFT', 'ROLL_RIGHT'), ('PITCH_UP', 'PITCH_DOWN'),
                 ('ROTATE_CCW', 'ROTATE_CW'))[i][int(axis[i] < 0)]
        policy.act(support, token, degrees=min(7., abs(np.rad2deg(angle * axis[i]))))
    else:
        raise ToolExecutionError('Held clip did not reach its horizontal-handle orientation')

    def clip_points():
        return np.vstack([p['vertices_task'] for p in collision_parts(policy.a, clip['mechanism'])])
    contacts = [body_ref['contact_body'], *handle_ref['grasp_contacts']]
    def on_table():
        return any(policy.contact(body, 'table') for body in contacts)
    policy.stage('clip-table-support-place')
    for _ in range(40):
        held()
        if on_table():
            break
        dz = float(clip_points()[:, 2].min()) - floor - .0005
        if dz < policy.min_mm / 1000.:
            # Release at most one millimetre above the real table and let
            # gravity seat it. Do not require a force before unloading it.
            if dz >= -.0005:
                break
            raise ToolExecutionError('Measured clip geometry crossed the table before release')
        step = min(policy.max_mm / 1000., dz)
        meshes = [measured_mesh(policy.a, support, n) for n in names]
        if min(float(m[:, 2].min()) for m in meshes) - step < floor + .0002:
            raise ToolExecutionError('Loaded hand would cross the table while laying the clip')
        policy.act(support, 'DOWN', mm=step * 1000.)
    else:
        raise ToolExecutionError('Clip did not reach actual tabletop support')
    def table_or_gripped():
        if policy.held(handle_ref, side) or on_table():
            return
        # A short gravity settling gap is acceptable during preparation.
        # A real lift still requires both hands on the intended two handles.
        if float(clip_points()[:, 2].min()) > floor + .004:
            raise ToolExecutionError('Clip lost table support before its real handle grasp')
    open_clip_hand(policy, support, table_or_gripped)
    if not on_table():
        policy.wait(1)
        if not on_table():
            raise ToolExecutionError('Released clip has no real tabletop support')
    policy.stage('clip-table-support-release-body')
    policy.move(support, policy.tip(support) + [0., 0., .12], table_or_gripped)
    # Move the released hand outside the measured approach volume.
    policy.move(support, policy.tip(support) + [0., -.16 if support == 'right' else .16, 0.], table_or_gripped)
    return squeeze_table_clip(policy, clip, handle_ref, body_ref, side)


def squeeze_table_clip(policy, clip, handle_ref, body_ref, side):
    """Resume a real supported clip without repeating body pickup/placement."""
    from .execution_design_mechanism_geometry import collision_parts
    from .execution_design_thin_edge import table_bounds_task
    floor = table_bounds_task(policy.a.scene)['top']
    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    contacts = [body_ref['contact_body'], *handle_ref['grasp_contacts']]
    def table_or_gripped():
        if policy.held(handle_ref, side) or any(policy.contact(body, 'table') for body in contacts):
            return
        points = np.vstack([p['vertices_task'] for p in collision_parts(policy.a, clip['mechanism'])])
        if float(points[:, 2].min()) > floor + .004:
            raise ToolExecutionError('Clip lost actual table support before handle grasp')
    table_or_gripped()
    points, _, _ = actual_handles(policy.mechanisms()[clip['mechanism']],
                                  asset['physical_affordances']['body_geometry'])
    plan = plan_pair(policy, side, None, points, 'direct-handle-squeeze', clip)
    follow_pair(policy, clip, handle_ref, side, None, body_ref, points, plan,
                'direct-handle-squeeze', support_guard=table_or_gripped)
    policy.require_held(handle_ref, side)
    before = policy.frame(body_ref)[0].copy()
    policy.stage('clip-table-support-real-lift')
    policy.move(side, policy.tip(side) + [0., 0., .06],
                lambda: policy.require_held(handle_ref, side))
    if policy.frame(body_ref)[0][2] - before[2] < .04:
        raise ToolExecutionError('Table-supported handle grasp did not lift the whole clip')
    from .execution_design_clip_edge_alignment import align_open_clip
    align_open_clip(policy, clip, handle_ref, side)
    return side
