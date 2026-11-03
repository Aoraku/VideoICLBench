"""E20 B/C engineering candidate for the two far blue cells.

The public right-hand retreat and negative task-Y wrist pitch were screened
from native action284 with both actual arm joint vectors. A new grasp can have
different offsets; every height below is therefore measured again. This is a
candidate controller, never an acceptance certificate.
"""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .author_orientation import _axis_angle


def applies(author, name, actor, local):
    return bool(author.task == 'E20' and actor == 'compartment_tray'
                and name.startswith('blue_') and float(local[0]) > .13
                and author.variant in ('B', 'C')
                and author.a.control_report.get('engineering_reference_only')
                and author.d.get('revision') == 'embodied50-execution-v3-20261102'
                and author.d.get('condition') == 'I')


def _empty_right(author):
    state, contacts = author.snapshot()
    if any(v['grasp'][1] for v in state.values()) or any(
            frozenset((n, 'right_finger' + str(i))) in contacts
            for n in state for i in (1, 2)):
        raise ToolExecutionError('E20 far-cell retreat requires actually empty right hand')


def _q4(author):
    robot = author.a.scene.robots['left']
    ids = robot.find_joints('panda_joint4')[0]
    if len(ids) != 1:
        raise ToolExecutionError('E20 actual left panda_joint4 required')
    value = robot.data.joint_pos[0, ids[0]]
    if hasattr(value, 'item'):
        value = value.item()
    value = float(value)
    if not np.isfinite(value) or value >= -.55:
        raise ToolExecutionError('E20 far-cell left q4 reached conservative stall warning')
    return value


def _lowest(author, name):
    fingers = author.a.finger_geometry('left')['fingers']
    if len(fingers) != 2:
        raise ToolExecutionError('E20 far-cell requires both actual finger meshes')
    toes = [float(f['aabb_min_task_m'][2]) for f in fingers]
    payload = float(author.measured_lowest_z(name))
    if not np.isfinite([*toes, payload]).all():
        raise ToolExecutionError('E20 nonfinite actual carried geometry')
    return min(*toes, payload), min(toes)


def _obstacle_top(author, name):
    state = author.snapshot()[0]
    top = .8
    for actor, value in state.items():
        if actor == name:
            continue
        obj = author.objects[actor]
        rotation = np.asarray(value['mat'])
        center = np.asarray(value['pos']) + rotation @ np.asarray(obj.get('local_bounds_center', [0, 0, 0]))
        top = max(top, float(center[2] + np.abs(rotation[2]) @ np.asarray(obj['size'])))
    for f in author.spec.get('fixtures', []):
        if f.get('type') != 'box':
            raise ToolExecutionError('Unreviewed E20 far-cell fixture')
        top = max(top, float(f['z'] + f['size'][2]))
    return top


def place(author, name, ref, side, actor, local):
    if not applies(author, name, actor, local) or side != 'left':
        raise ToolExecutionError('Reviewed E20 B/C left-hand far-blue route required')
    base, rotation = author.frame({'actor': actor})
    base = np.asarray(base, float).copy()
    rotation = np.asarray(rotation, float).copy()
    if rotation[2, 2] < .99:
        raise ToolExecutionError('E20 far-cell requires upright actual tray')
    goal = base + rotation @ np.asarray(local, float)
    tray = author.objects[actor]
    center = base + rotation @ np.asarray(tray.get('local_bounds_center', [0, 0, 0]))
    rim = float(center[2] + np.abs(rotation[2]) @ np.asarray(tray['size']))

    def guard():
        author.require_held(ref, 'left')
        _empty_right(author)
        _q4(author)
        now, rot = author.frame({'actor': actor})
        if np.linalg.norm(np.asarray(now) - base) > .002 or np.linalg.norm(np.asarray(rot) - rotation) > .02:
            raise ToolExecutionError('E20 actual tray moved during far-cell carry')

    guard()
    author.stage('workflow-far-blue-empty-right-' + name)
    author.move('right', [-.192, -.400, .902], guard)
    author.stage('workflow-far-blue-source-pitch-' + name)
    top = _obstacle_top(author, name)
    lowest, _ = _lowest(author, name)
    lift = max(0., top + .090 - lowest)
    tip = np.asarray(author.tip('left'), float)
    author.move('left', [*tip[:2], max(.99, float(tip[2] + lift))], guard)
    c, s = math.cos(math.radians(-15)), math.sin(math.radians(-15))
    desired = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]) @ author.frame({'actor': name})[1]
    pitch_progress=[]
    for _ in range(80):
        guard()
        axis, angle = _axis_angle(desired @ np.asarray(author.frame({'actor': name})[1]).T)
        if angle < math.radians(3):
            break
        pitch_progress.append(angle)
        if len(pitch_progress)>=4 and pitch_progress[-4]-min(pitch_progress[-3:])<math.radians(.1):
            raise ToolExecutionError('E20 held pitch stopped progressing after three actions')
        i = int(np.argmax(np.abs(axis)))
        token = (('ROLL_LEFT', 'ROLL_RIGHT'), ('PITCH_UP', 'PITCH_DOWN'),
                 ('ROTATE_CCW', 'ROTATE_CW'))[i][int(axis[i] < 0)]
        author.act('left', token, degrees=min(2., abs(math.degrees(angle * axis[i]))))
    else:
        raise ToolExecutionError('E20 far-cell actual held pitch did not converge')

    control = {'actor': name, 'local': author.bottom_local(name)}
    point = np.asarray(author.point(control), float)
    lowest, toes = _lowest(author, name)
    # The 4 mm and 3 mm extras absorb motion tolerance; the actual guards
    # retain the original full 50 mm transit and 10 mm finger/rim clearance.
    height = top + .060 + float(point[2] - lowest)
    release_z = max(float(goal[2]), rim + .013 + float(point[2] - toes))
    height = max(height, release_z)
    author.stage('workflow-far-blue-measured-carry-' + name)
    author.move_point('left', control, [*point[:2], height], guard, tolerance=.005)

    def transit_guard():
        guard()
        if _lowest(author, name)[0] < _obstacle_top(author, name) + .050:
            raise ToolExecutionError('E20 far-cell lost measured 50mm body clearance')

    author.move_point('left', control, [*goal[:2], height], transit_guard, tolerance=.005)
    author.stage('workflow-far-blue-release-' + name)
    author.move_point('left', control, [*goal[:2], release_z], guard, tolerance=.002)
    guard()
    if _lowest(author, name)[1] < rim + .010:
        raise ToolExecutionError('E20 far-cell lacks actual 10mm opening clearance')
    release_tip = np.asarray(author.tip('left'), float).copy()
    author.release(ref, 'left')
    author.move('left', release_tip + [0, 0, max(.04, height - release_z)])
    author.wait(3)
    state, contacts = author.snapshot()
    if any(state[name]['grasp']) or frozenset((name, actor)) not in contacts:
        raise ToolExecutionError('E20 far blue lacks released real tray support')
    author.a.control_report.setdefault('e20_far_blue_candidate', []).append(dict(
        actor=name, task_variant=author.variant, measured_obstacle_top_m=top,
        carried_point_z_m=height, release_point_z_m=release_z,
        public_source_pitch_task_y_deg=-15, minimum_transit_clearance_m=.050,
        minimum_opening_clearance_m=.010, real_support_verified=True,
        native_task_acceptance=False))
