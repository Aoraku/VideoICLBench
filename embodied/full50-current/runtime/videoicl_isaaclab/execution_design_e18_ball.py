"""E18 engineering ball acquisition with measured fingertip floor clearance."""
import math
import numpy as np
from .realworld_mechanism_expert import MechanismExecutionError


def floor_clear_grasp(position, radius, geometry, rotation, clearance=.001):
    point = np.asarray(position, float)
    rotation = np.asarray(rotation, float)
    if (point.shape != (3,) or rotation.shape != (3, 3)
            or not np.isfinite(point).all() or not np.isfinite(rotation).all()
            or not isinstance(radius, (int, float)) or not math.isfinite(radius)
            or not .005 <= radius <= .04
            or geometry.get('source') != 'actual_native_collision_mesh_current_body_pose'):
        raise ValueError('Measured E18 sphere and complete native hand geometry required')
    clouds = [np.asarray(c, float) @ rotation.T for c in geometry['clouds_tcp']]
    if len(clouds) != 3 or any(c.ndim != 2 or c.shape[1] != 3 or not len(c)
                               or not np.isfinite(c).all() for c in clouds):
        raise ValueError('Both complete fingers and palm required')
    floor = float(point[2] - radius)
    relative_low = min(float(np.min(c[:, 2])) for c in clouds)
    target = point.copy()
    target[2] = max(point[2], floor + clearance - relative_low)
    if target[2] > point[2] + .9 * radius:
        raise MechanismExecutionError('E18 sphere cannot overlap pads while clearing its support floor')
    return target, dict(ball_center_task=point.tolist(), sphere_radius_m=radius,
        supporting_floor_estimate_m=floor, hand_lowest_relative_z_m=relative_low,
        grasp_center_task=target.tolist(), planned_floor_clearance_m=target[2] + relative_low - floor,
        native_grip_verified=False)


def align_downward_jaw_x(worker, side):
    """Rotate an empty wrist above the cabinet before entering its narrow bay."""
    from .author_orientation import panda_downward_grasp_delta, _axis_angle
    from .execution_design_e18_geometry import actual_hand_clouds
    from .execution_design_e18_reference import choose_rotation_increment, orientation_waypoints
    geometry = actual_hand_clouds(worker.a, side)
    current = np.asarray(worker.a.tcp_rotation_task(side), float)
    jaw = current @ np.asarray(geometry['jaw_axis_tcp'], float)
    target = panda_downward_grasp_delta(current, jaw, [1., 0., 0.]) @ current
    center = worker.tip(side).copy()
    if center[2] < 1.03:
        raise MechanismExecutionError('E18 ball wrist must rotate above the original cabinet')
    waypoints = orientation_waypoints(current, target)
    index = 0
    worker.stage('E18-empty-ball-jaw-alignment-above-cabinet')
    for _ in range(80):
        actual, _ = worker.c.snapshot()
        if any(row['grasp'][('left', 'right').index(side)] for row in actual.values()):
            raise MechanismExecutionError('E18 ball alignment requires a truly empty hand')
        current = np.asarray(worker.a.tcp_rotation_task(side), float)
        if _axis_angle(target @ current.T)[1] <= math.radians(5.):
            return
        while index < len(waypoints)-1 and _axis_angle(waypoints[index] @ current.T)[1] < math.radians(5.):
            index += 1
        token, degrees = choose_rotation_increment(worker.a, worker.c, side, waypoints[index], .5, 10.)
        worker.a.act(token if side == 'left' else 'STILL',
                     token if side == 'right' else 'STILL', rotation_deg=degrees)
        if np.max(np.abs(worker.tip(side)-center)) > .006:
            worker.move(side, center, tolerance=.005)
    raise MechanismExecutionError('E18 empty ball jaw alignment exhausted bounded public rotations')


def acquire(worker, *, align_jaw_x=False):
    from .execution_design_e18_ball_roll import move_checked
    color = ('red', 'green', 'blue')['ABC'.index(worker.variant)]
    objects = {o['id']: o for o in worker.spec['objects']}
    selected = [n for n in worker.semantic['groups']['balls']
                if objects[n].get('semantic_identity', objects[n].get('identity', n)) == color]
    if len(selected) != 1:
        raise MechanismExecutionError('Unique original E18 selected ball required')
    name = selected[0]
    state, _ = worker.c.snapshot()
    position = np.asarray(state[name]['pos'], float)
    side = worker.semantic.get('expert_hand', 'left' if position[1] >= 0 else 'right')
    if any(state[name]['grasp']):
        raise MechanismExecutionError('E18 floor-clear pickup starts with a released ball')
    if align_jaw_x:
        align_downward_jaw_x(worker, side)
        state, _ = worker.c.snapshot()
        position = np.asarray(state[name]['pos'], float)
    from .execution_design_e18_geometry import actual_hand_clouds
    geometry = actual_hand_clouds(worker.a, side)
    radius = float(max(objects[name]['size']))
    grasp, proof = floor_clear_grasp(position, radius, geometry, worker.a.tcp_rotation_task(side))
    worker.operations.append(dict(operation='measured_ball_grasp_clearance', object=name, **proof))
    worker.stage('E18-floor-clear-ball-acquire-' + name)
    worker.act(side, 'RELEASE')
    initial_opening = worker.displacement('drawer')
    def drawer_clear():
        if worker.displacement('drawer') < initial_opening - .005:
            raise MechanismExecutionError('E18 pickup hand pushed the actual drawer inward more than five millimetres')
    high = max(float(worker.tip(side)[2]), float(grasp[2]) + .008)
    move_checked(worker, side, [*worker.tip(side)[:2], high], tolerance=.006)
    move_checked(worker, side, [*grasp[:2], high], tolerance=.005)
    near = max(float(grasp[2])+.05, .925)
    if high > near+.003:
        move_checked(worker, side, [*grasp[:2], near], tolerance=.005, guard=drawer_clear)
    drawer_clear()
    move_checked(worker, side, grasp, tolerance=.002, guard=drawer_clear)
    index = ('left', 'right').index(side)
    for _ in range(3):
        worker.act(side, 'GRASP')
        actual, _ = worker.c.snapshot()
        if actual[name]['grasp'][index]:
            break
    else:
        raise MechanismExecutionError('E18 floor-clear pickup has no actual selected-ball grip')
    def guard():
        actual, _ = worker.c.snapshot()
        if not actual[name]['grasp'][index]:
            raise MechanismExecutionError('E18 selected-ball grip lost on actual liftoff')
    before = np.asarray(actual[name]['pos'], float)
    move_checked(worker, side, worker.tip(side) + np.array([0., 0., .01]), tolerance=.002, guard=guard)
    actual, _ = worker.c.snapshot()
    lifted = float(np.asarray(actual[name]['pos'])[2] - before[2])
    if lifted < .005:
        raise MechanismExecutionError('E18 selected ball did not lift five millimetres')
    return name, side, guard, dict(actions=worker.c.steps-worker.start_steps,
        actual_liftoff_m=lifted, geometry=proof, actual_grip=True)


def run_segment(author, segment, parameters):
    checkpoint = getattr(author, '_engineering_resume_checkpoint', {})
    spec = author.scene.spec
    expected = {'e18_grasp_lift_ball_from616': (616, 62440),
                'e18_grasp_lift_ball_from_open483': (483, 49140)}.get(segment)
    if (expected is None or parameters != {}
            or (spec['id'], spec['variant'], spec['seed']) != ('E18', 'A', 4201)
            or spec.get('execution_design', {}).get('condition') != 'I'
            or checkpoint.get('source', {}).get('steps') != expected[0]
            or checkpoint.get('source', {}).get('physics_ticks') != expected[1]
            or not getattr(author.c, '_engineering_checkpoint_readback_passed', False)
            or not getattr(author.c, '_engineering_diagnostic_only', False)
            or not author.control_report.get('engineering_reference_only')):
        raise ValueError('Admitted native E18 A/I4201 exact original ball-stage boundary required')
    from .execution_design_e18_reference import E18MeasuredAuthor
    worker = E18MeasuredAuthor(author, allow_existing_e18_drawer=True)
    worker.max_actions = 160 if segment.endswith('open483') else 50
    name, side, _, result = acquire(worker, align_jaw_x=segment.endswith('open483'))
    return dict(segment=segment, local_completed=True, selected_ball=name, side=side,
                operations=worker.operations, **result)
