"""E40 engineering-only public-action handover, with measured collision guards.

The first top-down grip hides one handle under its palm. A second hand may
take the jaw ends from the side before the first hand accesses both handles.
All geometry is a candidate filter; actual distinct-body contacts are required.
"""
import json
import numpy as np

from .execution_design_clip_grasp import actual_handles, convex_meshes_clear, solve_finger_placement, lift_supported_clip
from .realworld_tool_expert import ToolExecutionError

# Engineering progress guards allow small in-grip settling. Final physical
# clamping remains measured by the native task evaluator.
HANDOVER_TRANSLATION_ALLOWANCE_M = .01
HANDOVER_ROTATION_ALLOWANCE_RAD = np.deg2rad(15.)


def jaw_end_points(mechanism, geometry, half_width):
    if not .005 < half_width < .03:
        raise ValueError('Reviewed clip instance half-width required')
    points = []
    for name, sign in (('JawPositive', 1), ('JawNegative', -1)):
        local = np.array(geometry[name]['jaw_point_body_local'], float)
        # Interior of the source extrusion, not an invented external handle.
        local[0] = sign * half_width * .7
        points.append(np.asarray(mechanism['body_pos_task'][name]) +
                      np.asarray(mechanism['body_mat_task'][name]) @ local)
    return np.asarray(points)


def single_wall_end_points(mechanism, geometry, half_width, body='JawPositive'):
    """Pinch the two extrusion ends of one rigid wall during preparation."""
    if body not in ('JawPositive', 'JawNegative') or not .005 < half_width < .03:
        raise ValueError('Actual source clip wall and half-width required')
    local = np.asarray(geometry[body]['jaw_point_body_local'], float)
    points = np.asarray([local + [sign * half_width * .7, 0., 0.] for sign in (-1., 1.)])
    return points @ np.asarray(mechanism['body_mat_task'][body]).T + mechanism['body_pos_task'][body]


def upper_handle_end_points(mechanism, geometry, half_width):
    """Support the clip from the higher actual source wire crossbar.

    Native restored geometry put the old mouth-lip grip below the assembly
    centre of mass. Choose the upper wire instead, so gravity hangs the clip
    below the pinch. This only selects an approach; real grip/lift still decide.
    """
    if not .005 < half_width < .03:
        raise ValueError('Reviewed clip instance half-width required')
    handles, _, _ = actual_handles(mechanism, geometry)
    body = ('JawPositive', 'JawNegative')[int(np.argmax(handles[:, 2]))]
    local = np.asarray(geometry[body]['handle_point_body_local'], float)
    offset = min(.7 * half_width, .010)
    points_local = np.asarray([local + [sign * offset, 0., 0.] for sign in (-1., 1.)])
    points = (points_local @ np.asarray(mechanism['body_mat_task'][body]).T
              + mechanism['body_pos_task'][body])
    return body, local, points


def route_clear(meshes, jaw, target, closure, pregrasp, height, obstacles, floor, start=None,
                contact_obstacles=()):
    """Whole swept convex volumes, including descent, side entry and closing."""
    target, pregrasp = np.asarray(target), np.asarray(pregrasp)
    above = np.array([*pregrasp[:2], height])
    swept = [np.vstack((mesh + above, mesh + pregrasp)) for mesh in meshes]
    swept += [np.vstack((mesh + pregrasp, mesh + target)) for mesh in meshes]
    if start is not None:
        start = np.asarray(start)
        high = np.array([*start[:2], height])
        swept += [np.vstack((mesh + start, mesh + high)) for mesh in meshes]
        corners = [np.array([x, y, height]) for x in (start[0], pregrasp[0])
                   for y in (start[1], pregrasp[1])]
        swept += [np.vstack([mesh + c for c in corners]) for mesh in meshes]
    # A clip must enter the already open gap. It cannot pass through an open
    # finger merely because closing contact is intended at the final pose.
    if not all(convex_meshes_clear(mesh, obstacle, clearance=.0005)
               for mesh in swept for obstacle in contact_obstacles):
        return False
    swept += [np.vstack((mesh + target, mesh + target + sign * closure * jaw))
              for mesh, sign in zip(meshes[1:], (-1., 1.))]
    return (all(mesh[:, 2].min() >= floor + .0002 - 1e-9 for mesh in swept)
            and all(convex_meshes_clear(mesh, obstacle) for mesh in swept for obstacle in obstacles))


def _log(policy, name, row):
    with (policy.a.out / name).open('a') as stream:
        stream.write(json.dumps(row) + '\n')


def require_supported_clip(policy, support_ref, handle_ref, side):
    """Accept actual bilateral wall contact or one finger on each real jaw."""
    if not policy.held(support_ref, side):
        policy.require_held(handle_ref, side)


def ramped_gripper(policy):
    return bool(getattr(policy.c, '_public_gripper_limits', None))


def open_clip_hand(policy, side, guard=None):
    """Keep the same public RELEASE goal until its measured opening is usable."""
    policy.act(side, 'RELEASE')
    if not ramped_gripper(policy):
        return
    for _ in range(13):
        if guard:
            guard()
        q = policy.a.scene.robots[side].data.joint_pos[:, policy.c.ids[side][1]]
        if float(q.min().item()) >= .039:
            return
        policy.wait(1)
    raise ToolExecutionError('Public clip RELEASE did not reach its measured open stop')


def inspect_unique_poses(policy, side, positions, rotation, cache):
    """Reuse identical-pose solutions while this planning call takes no actions.

    Separate fixed-seed solves prevent the same pose being accepted and then
    rejected merely because its position in a multi-target RNG stream changed.
    Joint limits and all reach/margin checks remain exactly the same.
    """
    from .execution_design_drawer_ik_probe import inspect
    results = []
    for position in positions:
        key = tuple(np.r_[np.asarray(position).ravel(), np.asarray(rotation).ravel()].tolist())
        if key not in cache:
            cache[key] = inspect(policy.a, policy.a.c, side,
                                 [dict(position=position, rotation=rotation)])[0]
        results.append(cache[key])
    return results


def public_rotation_poses(position, start, target):
    """The same dominant-axis rotations used by follow_pair, before actuation."""
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import _axis_rotation
    current = np.asarray(start, float).copy(); poses = []
    for _ in range(180):
        axis, angle = _axis_angle(np.asarray(target) @ current.T)
        if angle < np.deg2rad(1.):
            return poses
        i = int(np.argmax(abs(axis)))
        step = np.sign(axis[i]) * min(np.deg2rad(7.), abs(angle * axis[i]))
        current = _axis_rotation(np.eye(3)[i], step) @ current
        poses.append(dict(position=np.asarray(position).tolist(), rotation=current.tolist()))
    raise ValueError('Public clip rotation candidate did not converge')


def public_route_poses(tcp, start_rotation, plan, maximum_step_m=.012):
    current = np.asarray(tcp, float).copy(); poses = []
    def move(goal, rotation):
        nonlocal current
        goal = np.asarray(goal, float)
        for _ in range(180):
            delta = goal - current
            if max(abs(delta)) <= .002:
                return
            i = int(np.argmax(abs(delta)))
            current[i] += np.sign(delta[i]) * min(maximum_step_m, abs(delta[i]))
            poses.append(dict(position=current.tolist(), rotation=np.asarray(rotation).tolist()))
        raise ValueError('Public clip translation candidate did not converge')
    move([*current[:2], plan.get('orientation_height', current[2])], start_rotation)
    poses += public_rotation_poses(current, start_rotation, plan['rotation'])
    pre = np.asarray(plan['pregrasp']); h = plan['height']
    for goal in ([*current[:2], h], [*pre[:2], h], pre, plan['position']):
        move(goal, plan['rotation'])
    return poses


def rotation_clear(local, position, start, poses, obstacles, floor):
    """Bound the arcs between small public turns, including their sagitta."""
    from .author_orientation import _axis_angle
    previous = np.asarray(start)
    position = np.asarray(position)
    for pose in poses:
        rotation = np.asarray(pose['rotation'])
        angle = _axis_angle(rotation @ previous.T)[1]
        for mesh in local:
            sagitta = np.linalg.norm(mesh, axis=1).max() * (1. - np.cos(angle / 2.))
            sweep = np.vstack((mesh @ previous.T, mesh @ rotation.T)) + position
            if sweep[:, 2].min() - sagitta < floor + .0002:
                return False
            if not all(convex_meshes_clear(sweep, obstacle, clearance=.002 + 2. * sagitta)
                       for obstacle in obstacles):
                return False
        previous = rotation
    return True


def geometry_choices(local, tcp, rotation, obstacles, points, floor, contact_obstacles=(),
                     pad_depth_m=None):
    """Enumerate both real finger assignments without actuation or IK claims."""
    # Panda's prismatic fingers move along TCP Y. Vertex centroids are not
    # symmetric after native convex cooking and do not define the joint axis.
    local_jaw = np.array([0., 1., 0.])
    forward = (local[1].mean(0) + local[2].mean(0)) / 2 - local[0].mean(0)
    forward -= local_jaw * (forward @ local_jaw)
    forward /= np.linalg.norm(forward)
    source = np.column_stack((local_jaw, forward, np.cross(local_jaw, forward)))
    jaw = points[1] - points[0]
    jaw /= np.linalg.norm(jaw)
    up = np.array([0., 0., 1.]); v = up - jaw * (up @ jaw)
    if np.linalg.norm(v) < .01:
        v = np.array([1., 0., 0.]) - jaw * jaw[0]
    v /= np.linalg.norm(v); u = np.cross(jaw, v)
    support_top = max((float(m[:, 2].max()) for m in obstacles), default=floor)
    # Include the exactly measured wrist pose. Public angular quantization
    # should not force an ideal orientation when the actual pads already fit.
    orientations = [(np.asarray(rotation), local_jaw @ np.asarray(rotation).T)]
    for assignment in (1., -1.):
        candidate_jaw = assignment * jaw
        for angle in range(0, 360, 30):
            direction = np.cos(np.deg2rad(angle)) * v + np.sin(np.deg2rad(angle)) * u
            desired = np.column_stack((candidate_jaw, direction, np.cross(candidate_jaw, direction))) @ source.T
            orientations.append((desired, candidate_jaw))
    for desired, candidate_jaw in orientations:
        meshes = [m @ desired.T for m in local]
        for objective in ([0., 0., 1., .01], [0., 0., -1., .01]):
            for row in solve_finger_placement(points, meshes[0], meshes[1:], candidate_jaw, floor,
                                             objective=objective, pad_depth_m=pad_depth_m):
                target = np.asarray(row['tcp_translation'])
                above = max(float(tcp[2]), float(target[2]) + .06,
                            support_top + .004 - min(float(m[:, 2].min()) for m in meshes))
                entrances = [target + sign * .065 * np.eye(3)[axis]
                             for axis in (0, 1, 2) for sign in (-1., 1.)]
                if np.linalg.norm(tcp - target) < .10:
                    entrances.insert(0, np.asarray(tcp).copy())
                for pregrasp in entrances:
                    for height in sorted(set((above, float(tcp[2]), float(target[2])))):
                        if route_clear(meshes, candidate_jaw, target, row['closure_m'], pregrasp, height, obstacles, floor, tcp,
                                       contact_obstacles=contact_obstacles):
                            yield dict(row, position=target.tolist(), rotation=desired.tolist(),
                                       pregrasp=pregrasp.tolist(), height=height)


def orientation_candidates(local, tcp, rotation, obstacles, points, floor, contact_obstacles=(),
                           pad_depth_m=None):
    """Raise the empty hand only as far as the real turn sweep requires."""
    for height in sorted(set((float(tcp[2]), max(float(tcp[2]), .95),
                              max(float(tcp[2]), 1.), max(float(tcp[2]), 1.05)))):
        turn_position = np.array([*tcp[:2], height])
        initial_sweep = [np.vstack((m @ rotation.T + tcp, m @ rotation.T + turn_position))
                         for m in local]
        if (min(m[:, 2].min() for m in initial_sweep) < floor + .0002 or
                not all(convex_meshes_clear(m, o) for m in initial_sweep for o in [*obstacles, *contact_obstacles])):
            continue
        for plan in geometry_choices(local, turn_position, rotation, obstacles, points, floor,
                                     contact_obstacles, pad_depth_m=pad_depth_m):
            turn = public_rotation_poses(turn_position, rotation, plan['rotation'])
            if rotation_clear(local, turn_position, rotation, turn, [*obstacles, *contact_obstacles], floor):
                yield dict(plan, orientation_height=height)


def plan_pair(policy, side, support, points, purpose, clip):
    from .execution_design_native_finger_mesh import measured_mesh as actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    a = policy.a
    tcp, rotation = np.asarray(a.tip(side)), np.asarray(a.tcp_rotation_task(side))
    names = ('panda_hand', *a.scene.embodiment.fingers)
    local = [(actual_mesh(a, side, n) - tcp) @ rotation for n in names]
    obstacles = [actual_mesh(a, support, n) for n in names] if support is not None else []
    from .execution_design_mechanism_geometry import collision_parts
    clip_parts = collision_parts(a, clip['mechanism'])
    contact_obstacles = [np.asarray(p['vertices_task']) for p in clip_parts]
    floor = table_bounds_task(a.scene)['top']
    handle_squeeze = purpose in ('handle-squeeze', 'direct-handle-squeeze')
    choices = orientation_candidates(local, tcp, rotation, obstacles, points, floor, contact_obstacles,
                                      pad_depth_m=.0015 if handle_squeeze else None)
    # Check the actual empty-wrist turn, high translation, descent, entry, final.
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    measured = capture(a, a.c, side)
    valid = []; count = 0
    for row in choices:
        count += 1
        poses = public_route_poses(tcp, rotation, row, maximum_step_m=policy.max_mm / 1000.)
        path = solve_local_pose_path(measured['position'], measured['rotation_task'],
            measured['jacobian'], measured['q'], measured['limits'], poses)
        _log(policy, 'clip-handover-local-path.private.jsonl', dict(purpose=purpose,
            side=side, plan=row, screen=path, native_success=False))
        if path['feasible']:
            valid.append(dict(row, local_path=path))
            break
    _log(policy, 'clip-handover-geometry.private.jsonl', dict(purpose=purpose, side=side,
        support=support, actual_points=points.tolist(), candidate_count=count,
        candidate_count_is_evaluated_prefix=True,
        selection='first_complete_mesh_and_continuous_joint_path_candidate',
        local_meshes=[m.tolist() for m in local], support_meshes=[m.tolist() for m in obstacles],
        target_clip_collision_parts=clip_parts, native_success=False))
    if count == 0:
        raise ToolExecutionError('No measured table/support-clear clip '+purpose+' route')
    if not valid:
        raise ToolExecutionError('No joint-safe clip '+purpose+' route')
    chosen = min(valid, key=lambda r: sum(p['maximum_joint_step_rad'] for p in r['local_path']['rows']))
    _log(policy, 'clip-handover-plans.private.jsonl', dict(purpose=purpose, side=side,
        support=support, plan=chosen, native_success=False))
    return chosen


def checked_approach_move(policy, side, target, guard, tolerance=.002):
    """Stop the local experiment on measured wrong-direction tracking/stall."""
    target = np.asarray(target, float); distances = []
    for _ in range(180):
        guard(); before = np.asarray(policy.tip(side)).copy(); error = target - before
        if max(abs(error)) <= tolerance:
            return
        axis = int(np.argmax(abs(error)))
        token = (('FWD', 'BACK'), ('LEFT', 'RIGHT'), ('UP', 'DOWN'))[axis][int(error[axis] < 0)]
        requested = min(policy.max_mm / 1000., abs(error[axis]))
        policy.act(side, token, mm=requested * 1000.)
        finish_partial_translation(policy, side, guard)
        guard(); after = np.asarray(policy.tip(side)); actual = after - before
        forward = actual[axis] * np.sign(error[axis])
        lateral = np.linalg.norm(np.delete(actual, axis))
        if requested >= .004 and forward < requested * .02 and lateral > .002:
            raise ToolExecutionError('Measured clip approach moved sideways instead of requested axis')
        distances.append(float(np.linalg.norm(target - after)))
        if len(distances) >= 24 and min(distances[-12:]) >= min(distances[-24:-12]) - .0003:
            raise ToolExecutionError('Measured clip approach made no net progress')
    raise ToolExecutionError('Unreachable measured clip approach')


def finish_partial_translation(policy, side, guard):
    """Continue an unfinished public goal before asking for a new direction."""
    if not getattr(policy, '_e40_table_supported_reference', False):
        return
    feedback = getattr(getattr(policy, 'c', None), 'action_feedback', None)
    if not callable(feedback):
        return
    for _ in range(2):
        row = feedback()['control_feedback'][side]
        if row['status'] != 'partial' or row['position_error_m'] <= .002:
            return
        guard()
        policy.wait(1)  # Same Cartesian target; no new motion or private state.
        guard()


def refine_current_handle_grasp(policy, clip, side, support, support_ref, support_guard=None):
    """Correct the last millimetres against current, rather than old, handles."""
    from .execution_design_native_finger_mesh import measured_mesh as actual_mesh
    from .execution_design_mechanism_geometry import collision_parts
    from .execution_design_thin_edge import table_bounds_task
    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    names = ('panda_hand', *policy.a.scene.embodiment.fingers)
    floor = table_bounds_task(policy.a.scene)['top']
    handle_ref = policy.clip_ref(clip, 'handle_grasp')
    def check_support():
        if support_guard is not None:
            support_guard()
        else:
            require_supported_clip(policy, support_ref, handle_ref, support)
    policy.stage('clip-live-handle-pair-refinement')
    for _ in range(12):
        check_support()
        tcp = policy.tip(side).copy()
        meshes = [actual_mesh(policy.a, side, n) for n in names]
        offsets = [m-tcp for m in meshes]
        axis = np.asarray(policy.a.tcp_rotation_task(side))[:, 1]
        points, _, _ = actual_handles(policy.mechanisms()[clip['mechanism']],
                                      asset['physical_affordances']['body_geometry'])
        current = solve_finger_placement(points, offsets[0], offsets[1:], axis, floor,
            margin=.0001, fixed_translation=tcp, pad_depth_m=.0015)
        if current:
            _log(policy, 'clip-live-handle-refinement.private.jsonl', dict(
                actual_points=points.tolist(), tcp=tcp.tolist(),
                current_pose_both_inward_pads_feasible=True,
                planned_closure_m=current[0]['closure_m'], native_grasp_verified=False))
            return current[0]
        rows = solve_finger_placement(points, offsets[0], offsets[1:], axis, floor,
                                     margin=.0005, preferred_translation=tcp, pad_depth_m=.0015)
        if not rows:
            raise ToolExecutionError('Current actual handle pair does not fit measured fingers')
        row = min(rows, key=lambda r: np.linalg.norm(np.asarray(r['tcp_translation'])-tcp))
        delta = np.asarray(row['tcp_translation'])-tcp
        _log(policy, 'clip-live-handle-refinement.private.jsonl', dict(
            actual_points=points.tolist(), tcp=tcp.tolist(), correction_m=delta.tolist(),
            planned_closure_m=row['closure_m'], native_grasp_verified=False))
        i = int(np.argmax(abs(delta))); step = np.zeros(3)
        step[i] = np.sign(delta[i]) * max(policy.min_mm / 1000., min(.004, abs(delta[i])))
        obstacles = [actual_mesh(policy.a, support, n) for n in names] if support is not None else []
        targets = [np.asarray(p['vertices_task']) for p in collision_parts(policy.a, clip['mechanism'])]
        for mesh in meshes:
            sweep = np.vstack((mesh, mesh+step))
            if (sweep[:, 2].min() < floor+.0002
                    or not all(convex_meshes_clear(sweep, o, clearance=.0005) for o in [*obstacles, *targets])):
                raise ToolExecutionError('Live handle correction has no measured open-hand clearance')
        token = (('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[i][int(step[i]<0)]
        policy.act(side, token, mm=abs(step[i])*1000.)
        check_support()
        moved = policy.tip(side)-tcp
        if abs(step[i]) >= .002 and moved[i]*np.sign(step[i]) < .0001 and np.linalg.norm(np.delete(moved,i)) > .002:
            raise ToolExecutionError('Live handle correction moved sideways without net progress')
    raise ToolExecutionError('Live handle pair could not be reached before closing')


def follow_pair(policy, clip, ref, side, support, support_ref, points, plan, purpose,
                support_guard=None):
    from .author_orientation import _axis_angle
    a = policy.a
    opening_handles = purpose in ('handle-squeeze', 'direct-handle-squeeze')
    spine0, rotation0 = policy.frame(support_ref)
    spine0, rotation0 = spine0.copy(), rotation0.copy()
    def held():
        if support_guard is not None:
            support_guard()
            return
        if opening_handles:
            # A handle approach is refined against the current measured
            # articulated handles before closing. Their ordinary in-grip
            # motion is not a failed rigid-wall handover.
            require_supported_clip(policy, support_ref, ref, support)
            return
        policy.require_held(support_ref, support)
        now, rotation = policy.frame(support_ref)
        angle = np.arccos(np.clip((np.trace(rotation @ rotation0.T) - 1.) / 2., -1., 1.))
        if (np.linalg.norm(now - spine0) > HANDOVER_TRANSLATION_ALLOWANCE_M
                or angle > HANDOVER_ROTATION_ALLOWANCE_RAD):
            raise ToolExecutionError('Supporting clip moved after measured '+purpose+' plan')
    policy.stage('clip-'+purpose+'-turn-clearance')
    checked_approach_move(policy, side, [*policy.tip(side)[:2], plan['orientation_height']], held)
    policy.stage('clip-'+purpose+'-orient')
    desired = np.asarray(plan['rotation'])
    for _ in range(180):
        held()
        axis, angle = _axis_angle(desired @ np.asarray(a.tcp_rotation_task(side)).T)
        if angle < np.deg2rad(1.):
            break
        i = int(np.argmax(abs(axis)))
        token = (('ROLL_LEFT', 'ROLL_RIGHT'), ('PITCH_UP', 'PITCH_DOWN'),
                 ('ROTATE_CCW', 'ROTATE_CW'))[i][int(axis[i] < 0)]
        policy.act(side, token, degrees=min(7., abs(np.rad2deg(angle * axis[i]))))
    else:
        raise ToolExecutionError('Clip '+purpose+' wrist orientation did not converge')
    policy.stage('clip-'+purpose+'-approach')
    pre, h = plan['pregrasp'], plan['height']
    for position in ([*policy.tip(side)[:2], h], [*pre[:2], h], pre, plan['position']):
        checked_approach_move(policy, side, position, held)
    closing_plan = plan
    if purpose in ('handle-squeeze', 'direct-handle-squeeze'):
        if support_guard is None:
            closing_plan = refine_current_handle_grasp(policy, clip, side, support, support_ref)
        else:
            closing_plan = refine_current_handle_grasp(policy, clip, side, support, support_ref, support_guard)
    policy.stage('clip-'+purpose+'-grasp')
    stable = 0
    expected_finger_q = None
    if opening_handles:
        q = a.scene.robots[side].data.joint_pos[:, policy.c.ids[side][1]]
        expected_finger_q = float(q.mean().item()) - closing_plan['closure_m']
    def require_support():
        # The old fingers can slide from one rigid wall onto the two jaws
        # while the new hand closes. Both actual contact pairs support the
        # same clip; a missing second finger still fails immediately.
        if support_guard is not None:
            support_guard()
        else:
            require_supported_clip(policy, support_ref, ref, support)
    for _ in range(8):
        if opening_handles:
            if not policy.held(ref, side):
                require_support()
        else:
            held()
        policy.act(side, 'GRASP')
        if opening_handles:
            # Closing the handles is supposed to rotate the articulated jaws.
            # Judge the new actual grip/opening, not the old jaw pose.
            if policy.held(ref, side) and policy.clip_gap(clip)[0] >= clip['expert']['open_gap_m']:
                return
            if not policy.held(ref, side):
                require_support()
                q = a.scene.robots[side].data.joint_pos[:, policy.c.ids[side][1]]
                if float(q.mean().item()) < expected_finger_q - .003:
                    raise ToolExecutionError('Clip handles missed the real inward pads during closing')
        else:
            held()
        stable = stable + 1 if policy.held(ref, side) else 0
        if stable >= (1 if ramped_gripper(policy) else 3):
            return
    raise ToolExecutionError('No native distinct-jaw contacts for clip '+purpose)


def squeeze_with_handover(policy, clip, handle_ref, originally_requested_side):
    # Caller verifies task, revision, source and engineering authorization.
    first = 'left' if originally_requested_side == 'right' else 'right'
    holder = originally_requested_side
    body_ref = lift_supported_clip(policy, clip, handle_ref, first)
    policy.stage('raise-clip-for-under-jaw-handover')
    policy.move(first, policy.tip(first) + [0., 0., .08], lambda: policy.require_held(body_ref, first))
    open_clip_hand(policy, holder, lambda: policy.require_held(body_ref, first))
    direct = plan_direct_handles(policy, clip, first, holder)
    if direct is not None:
        return squeeze_direct_handles(policy, clip, handle_ref, body_ref, first, holder, direct)
    handover_plan = handover_supported_clip(policy, clip, handle_ref, first, holder, body_ref)
    return squeeze_after_handover(policy, clip, handle_ref, first, holder, body_ref, handover_plan)


def plan_direct_handles(policy, clip, support, side):
    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    points, _, _ = actual_handles(policy.mechanisms()[clip['mechanism']],
                                  asset['physical_affordances']['body_geometry'])
    try:
        return plan_pair(policy, side, support, points, 'direct-handle-squeeze', clip)
    except ToolExecutionError as exc:
        # This call performs geometry/IK only. A rejected candidate is not an
        # accepted physical failure; the checked handover remains available.
        if str(exc).startswith(('No measured table/support-clear', 'No joint-safe clip')):
            return None
        raise


def squeeze_direct_handles(policy, clip, handle_ref, body_ref, support, side, plan):
    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    points, _, _ = actual_handles(policy.mechanisms()[clip['mechanism']],
                                  asset['physical_affordances']['body_geometry'])
    follow_pair(policy, clip, handle_ref, side, support, body_ref, points, plan, 'direct-handle-squeeze')
    for _ in range(6):
        if policy.clip_gap(clip)[0] >= clip['expert']['open_gap_m']:
            break
        if not policy.held(handle_ref, side):
            require_supported_clip(policy, body_ref, handle_ref, support)
        policy.act(side, 'GRASP')
    else:
        raise ToolExecutionError('Direct real handle grip did not open the mouth')
    if ramped_gripper(policy):
        open_clip_hand(policy, support, lambda: policy.require_held(handle_ref, side))
    else:
        policy.release(body_ref, support)
    policy.move(support, policy.tip(support) + [0., 0., .08],
                lambda: policy.require_held(handle_ref, side))
    policy.require_held(handle_ref, side)
    return side


def handover_supported_clip(policy, clip, handle_ref, first, holder, body_ref):
    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    geometry = asset['physical_affordances']['body_geometry']
    mechanism = policy.mechanisms()[clip['mechanism']]
    half_width = min(abs(float(asset['bounds'][0][0])), abs(float(asset['bounds'][1][0])))
    # Support a single source rigid body. The ramped branch uses its upper
    # wire crossbar so the load hangs below the grip, while the older branch
    # preserves its mouth-wall route. Final squeeze still needs both jaws.
    receiving_body = 'JawPositive'
    local = None
    if ramped_gripper(policy):
        receiving_body, local, points = upper_handle_end_points(mechanism, geometry, half_width)
    else:
        points = single_wall_end_points(mechanism, geometry, half_width)
    receiving_ref = {k: v for k, v in body_ref.items() if k != 'grasp_contacts'}
    receiving_ref['body'] = receiving_body
    if local is not None:
        receiving_ref['local'] = local.tolist()
    receiving_ref['contact_body'] = next(clip[k]['contact_body'] for k in ('left', 'right')
                                         if clip[k]['body'] == receiving_body)
    handover_plan = plan_pair(policy, holder, first, points, 'jaw-end-handover', clip)
    handover_plan['holder_ref'] = receiving_ref
    follow_pair(policy, clip, receiving_ref, holder, first, body_ref, points, handover_plan, 'jaw-end-handover')
    _, stable_rotation = policy.frame(receiving_ref)
    stable_rotation = stable_rotation.copy()
    def stable_hold():
        require_supported_clip(policy, receiving_ref, handle_ref, holder)
        if ramped_gripper(policy):
            # The two jaws can share the load as RELEASE progresses. Actual
            # bilateral contact and the subsequent whole-spine lift establish
            # support; keeping one articulated wall at its old pose does not.
            return
        _, rotation = policy.frame(receiving_ref)
        angle = np.arccos(np.clip((np.trace(rotation @ stable_rotation.T) - 1.) / 2., -1., 1.))
        if angle > HANDOVER_ROTATION_ALLOWANCE_RAD:
            raise ToolExecutionError('Clip rotated inside the new hand after physical handover')
    if ramped_gripper(policy):
        open_clip_hand(policy, first, stable_hold)
    else:
        policy.act(first, 'RELEASE')
        stable_hold()
        for _ in range(2):
            policy.wait(1); stable_hold()
    if policy.held(body_ref, first):
        raise ToolExecutionError('Original clip support did not release')
    policy.move(first, policy.tip(first) + [0., 0., .10], stable_hold)
    stable_hold()
    before = policy.frame(body_ref)[0].copy()
    policy.move(holder, policy.tip(holder) + [0., 0., .008], stable_hold)
    stable_hold()
    if policy.frame(body_ref)[0][2] - before[2] < .003:
        raise ToolExecutionError('Actually gripped rigid clip wall did not follow handover lift')
    return handover_plan


def squeeze_after_handover(policy, clip, handle_ref, first, holder, body_ref, handover_plan):
    asset = next(m for m in policy.spec['mechanisms'] if m['id'] == clip['mechanism'])['mechanical_asset']
    geometry = asset['physical_affordances']['body_geometry']
    body_ref = dict(handover_plan.get('holder_ref', body_ref))
    # Older stage checkpoints named Spine as their reference frame while
    # physically gripping one articulated jaw. Track the gripped rigid wall;
    # the spring joint is allowed to move the rest of the clip naturally.
    for role in ('left', 'right'):
        if body_ref.get('contact_body') == clip[role]['contact_body']:
            body_ref['body'] = clip[role]['body']
    open_clip_hand(policy, first, lambda: require_supported_clip(policy, body_ref, handle_ref, holder))
    points, _, _ = actual_handles(policy.mechanisms()[clip['mechanism']], geometry)
    plan = plan_pair(policy, first, holder, points, 'handle-squeeze', clip)
    follow_pair(policy, clip, handle_ref, first, holder, body_ref, points, plan, 'handle-squeeze')
    for _ in range(6):
        if policy.clip_gap(clip)[0] >= clip['expert']['open_gap_m']:
            break
        if not policy.held(handle_ref, first):
            require_supported_clip(policy, body_ref, handle_ref, holder)
        policy.act(first, 'GRASP')
    else:
        raise ToolExecutionError('Real clip jaw opening insufficient after handover')
    if ramped_gripper(policy):
        open_clip_hand(policy, holder, lambda: policy.require_held(handle_ref, first))
    else:
        policy.release(body_ref, holder)
    # Retrace the collision-checked side-entry route while the handles are held.
    retreat = np.asarray(handover_plan['pregrasp']) - np.asarray(handover_plan['position'])
    policy.move(holder, policy.tip(holder) + retreat,
                lambda: policy.require_held(handle_ref, first))
    return first
