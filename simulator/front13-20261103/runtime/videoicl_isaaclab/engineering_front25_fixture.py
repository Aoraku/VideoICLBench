"""Convert historical front25 measurements into an honest debug fixture.

This is a pure adapter over the public engineering checkpoint core. Missing
state is declared explicitly; no evaluator, contact or grasp flag is restored.
"""
from copy import deepcopy
from types import SimpleNamespace
import math
import numpy as np
from scipy.spatial.transform import Rotation
from . import engineering_checkpoint as core
from .layout import multiply_quaternions, rotation_matrix

SCHEMA = 'videoicl-historical-approximate-engineering-segment-v1'
FORBIDDEN = {'evaluator', 'history', 'success', 'strict_success', 'task_score_100',
             'engineering_score_100', 'initial_sealed', 'grasp', 'grasp_flags', 'controller'}


def _array(value, shape, label):
    return core._array(value, shape, label)


def _rotation(value, label):
    matrix = _array(value, (3, 3), label)
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=2e-5, rtol=0) or not .99998 <= np.linalg.det(matrix) <= 1.00002:
        raise ValueError('Proper historical rotation required: ' + label)
    q = Rotation.from_matrix(matrix).as_quat()
    return np.r_[q[3], q[:3]]


def _named(names, values, label):
    if not isinstance(names, list) or not names or len(set(names)) != len(names) or any(not isinstance(n, str) for n in names):
        raise ValueError('Unique historical joint names required: ' + label)
    array = _array(values, (len(names),), label)
    return dict(zip(names, array))


def _time(record, dt):
    source = record.get('source_counters', {})
    steps = source.get('actions'); ticks = source.get('native_physics_tick')
    if (type(steps) is not int or steps < 0 or type(ticks) is not int or ticks < 0
            or source.get('shared_tick') != ticks or not isinstance(source.get('stage'), str) or not source['stage']):
        raise ValueError('Historical completed-boundary counters/stage required')
    if not math.isfinite(float(dt)) or float(dt) <= 0:
        raise ValueError('Finite positive native dt required')
    return dict(steps=steps, physics_ticks=ticks, dt=float(dt))


def _pose(row, label):
    if set(row) - {'pos', 'mat', 'grasp'}:
        raise ValueError('Unreviewed historical object fields: ' + label)
    # The historical grasp field is evidence only and intentionally unused.
    return np.r_[_array(row['pos'], (3,), label + ' position'),
                 _rotation(row['mat'], label + ' rotation'), np.zeros(6)].tolist()


def _tcp_hold(scene, root_task, feedback, side):
    root_world = core._root_to_world(scene, root_task)
    base_q = core._quat(root_world[3:7], side + ' fresh base')
    task_q = core._quat(feedback['tcp_quaternion_wxyz'], side + ' measured TCP')
    world_q = multiply_quaternions(scene.layout.task_quat, task_q)
    inverse_base = base_q * np.array([1., -1., -1., -1.])
    target_q = core._quat(multiply_quaternions(inverse_base, world_q), side + ' new TCP hold')
    task_pos = _array(feedback['tcp_position'], (3,), side + ' measured TCP position')
    world_pos = _array(scene.task_to_world(task_pos), (3,), side + ' measured world TCP')
    target_pos = rotation_matrix(base_q).T @ (world_pos - root_world[:3])
    return dict(position=target_pos.tolist(), quaternion=target_q.tolist())


def _robot(controller, side, destination, diagnostic, feedback, grip, assumptions):
    arm = diagnostic['arm_joints']; fingers = diagnostic['finger_joints']
    arm_q = _named(arm['names'], arm['positions_rad'], side + ' arm q')
    finger_q = _named(fingers['names'], fingers['positions_m'], side + ' finger q')
    finger_qd = _named(fingers['names'], fingers['velocities_m_s'], side + ' finger qd')
    sensor = feedback['measured_sensors']['joint_velocities_rad_s']
    if sensor.get('available') is not True:
        raise ValueError('Measured historical arm velocity required: ' + side)
    arm_qd = _named(feedback['joint_names'], sensor['value'], side + ' measured arm qd')
    measured_q = _named(feedback['joint_names'], feedback['joint_positions_rad'], side + ' feedback arm q')
    names = destination['joint_names']
    if (len(arm_q) != 7 or len(finger_q) != 2 or len(names) != 9
            or set(arm_q) & set(finger_q) or set(arm_q) != set(arm_qd) or set(arm_q) != set(measured_q)
            or set(arm_q) | set(finger_q) != set(names)):
        raise ValueError('Complete native nine-joint identity required: ' + side)
    if any(abs(arm_q[n] - measured_q[n]) > 1e-6 for n in arm_q):
        raise ValueError('Historical robot diagnostics and same-tick feedback disagree: ' + side)
    q = {**arm_q, **finger_q}; qd = {**arm_qd, **finger_qd}
    destination['joint_pos'] = [float(q[n]) for n in names]
    destination['joint_vel'] = [float(qd[n]) for n in names]
    destination['root_state_task'][7:] = [0.] * 6
    config = controller.scene.embodiment.config['gripper']
    finger_names = config.get('joints', fingers['names'])
    if len(finger_names) != 2 or set(finger_names) != set(finger_q):
        raise ValueError('Native gripper profile joint identity mismatch: ' + side)
    opened = _array(config['open'], (2,), side + ' profile open')
    closed = _array(config['closed'], (2,), side + ' profile closed')
    if float(np.mean(opened) - np.mean(closed)) <= 1e-9:
        raise ValueError('Historical mean-opening hold requires increasing profile opening')
    if grip is None:
        mean = float(np.mean(list(finger_q.values())))
        fraction = (mean - float(np.mean(closed))) / float(np.mean(opened - closed))
        if not -1e-4 <= fraction <= 1.0001:
            raise ValueError('Measured opening outside native gripper profile: ' + side)
        command = .04 * float(np.clip(fraction, 0., 1.))
        assumptions.append(side + ': historical public grip command UNKNOWN; NEW debug hold command uses the measured finger-opening mean '
                           + repr(mean) + ' m, mapped through profile open/closed. This is not an inferred historical command.')
    else:
        if type(grip) not in (float, int) or not math.isfinite(grip) or not 0. <= grip <= .04:
            raise ValueError('Historical canonical grip command outside [0,.04]: ' + side)
        command = float(grip)
        assumptions.append(side + ': original explicitly known public grip command retained: ' + repr(command) + ' m.')
    drive = destination['joint_pos'].copy()
    requested = closed + (opened - closed) * (command / .04)
    for name, value in zip(finger_names, requested):
        drive[names.index(name)] = float(value)
    destination['drive_targets'] = dict(position=drive, velocity=[0.] * len(names), effort=[0.] * len(names))
    assumptions.append(side + ': measured arm/finger q and qd retained; NEW drive holds measured arm q, profile-mapped finger command, zero velocity/effort targets. Fresh fixed-base root pose retained; base velocities initialized zero.')
    return command


def _convert(controller, record):
    """Read fresh native state; return a resealed, unscored measured-pose fixture."""
    if (not isinstance(record, dict) or record.get('schema') != SCHEMA
            or record.get('debug_only') is not True or record.get('engineering_only') is not True
            or record.get('history_reconstructed') is not False or set(record) & FORBIDDEN):
        raise ValueError('Explicit historical debug fixture without score/history/grasp injection required')
    record = core._plain(record)
    source_spec = record.get('scene_input')
    if not isinstance(source_spec, dict):
        raise ValueError('Historical reconstructed scene input required')
    fresh = core.capture(controller, 'historical-fixture-validation')
    source_identity = core.identity(SimpleNamespace(scene=SimpleNamespace(spec=source_spec)))
    if fresh['identity'] != source_identity:
        raise ValueError('Historical assignment/source/profile/physical geometry identity mismatch')
    identity = fresh['identity']; design = source_spec.get('execution_design', {})
    if (identity['task'] not in {f'E{i:02}' for i in range(14, 26)}
            or record.get('identity') != f"{identity['task']}-{identity['variant']}-{design.get('condition')}-s{identity['seed']}"):
        raise ValueError('Historical front25 case identity mismatch')
    provenance = record.get('scene_input_provenance', {})
    catalog = provenance.get('catalog_sha256')
    literal = provenance.get('literal_remote_scene_input_readback')
    server_verified = literal is True and provenance.get('server_local_source_verified') is True
    reconstructed = literal is False and provenance.get('server_local_source_verified') in (None, False)
    if (not (server_verified or reconstructed)
            or provenance.get('catalog_matches_native_provenance') is not True
            or not isinstance(catalog, str) or len(catalog) != 64 or any(ch not in '0123456789abcdef' for ch in catalog)
            or catalog != source_spec.get('provenance', {}).get('catalog_sha256')
            or catalog != controller.scene.spec.get('provenance', {}).get('catalog_sha256')):
        raise ValueError('Deterministically reconstructed scene catalog hash/provenance mismatch')
    if fresh.get('passive_material'):
        raise ValueError('Historical fixture lacks measured passive-material state')
    source = _time(record, controller.dt)
    states = record.get('state_task')
    if not isinstance(states, dict) or set(states) != set(fresh['objects']):
        raise ValueError('Historical object inventory mismatch')
    for name, state in states.items():
        fresh['objects'][name]['root_state_task'] = _pose(state, 'object/' + name)
    assumptions = fresh['assumptions']
    assumptions += [
        'Historical object linear/angular velocities are MISSING and explicitly initialized to zero; pose matrices are converted to unit quaternion wxyz.',
        ('Original literal scene-input bytes were read and identity-verified SERVER-LOCALLY; original spec/public commands are not exported by this adapter.'
         if server_verified else 'Source scene input is a deterministic LOCAL reconstruction with matching catalog SHA, NOT literal remote scene-input bytes.'),
        'Measured TCP task pose is NOT the original controller goal: it defines a NEW base-frame debug hold at the measured pose; no FK/default wrist target is used.',
        'PhysX contact/solver caches, evaluator/history/success and historical grasp flags are NOT restored; caller must warm up and validate actual poses/contacts.',
    ]
    diagnostics = record.get('robot_diagnostics', {})
    arms = record.get('robot_feedback_same_tick', {}).get('arms', {})
    grips = record.get('grips', {})
    if set(fresh['robots']) != {'left', 'right'} or not set(fresh['robots']) <= set(diagnostics) or set(arms) != set(fresh['robots']) or set(grips) != set(fresh['robots']):
        raise ValueError('Complete historical dual-arm measurements/commands required')
    new_grips = {}; tcp = {}
    for side, destination in fresh['robots'].items():
        new_grips[side] = _robot(controller, side, destination, diagnostics[side], arms[side], grips[side], assumptions)
        tcp[side] = _tcp_hold(controller.scene, destination['root_state_task'], arms[side], side)
    mechanisms = record.get('mechanisms', {})
    if not isinstance(mechanisms, dict) or set(mechanisms) != set(fresh['mechanisms']):
        raise ValueError('Historical mechanism inventory mismatch')
    for name, destination in fresh['mechanisms'].items():
        measured = mechanisms[name]
        q = _named(measured['joint_names'], measured['joint_pos'], name + ' mechanism q')
        qd = _named(measured['joint_names'], measured['joint_vel'], name + ' mechanism qd')
        if set(q) != set(destination['joint_names']):
            raise ValueError('Historical mechanism joint identity mismatch: ' + name)
        destination['joint_pos'] = [float(q[n]) for n in destination['joint_names']]
        destination['joint_vel'] = [float(qd[n]) for n in destination['joint_names']]
        destination['root_state_task'][7:] = [0.] * 6
        destination['drive_targets'] = dict(position=destination['joint_pos'].copy(), velocity=[0.] * len(q), effort=[0.] * len(q))
        assumptions.append(name + ': original measured mechanism q/qd mapped by native joint names; fresh fixed-base root retained, base velocity zero, NEW measured-q/zero velocity-effort drive hold.')
    fresh.update(state_quality='measured_pose_fixture', stage=record['source_counters']['stage'], source=source,
        context=dict(historical_fixture_schema=SCHEMA, historical_identity=record['identity'],
            source_evidence=deepcopy(record.get('source_evidence', {})),
            missing_restore_fields=deepcopy(record.get('missing_restore_fields', [])),
            scene_input_provenance=deepcopy(provenance), grip_provenance=deepcopy(record.get('grip_provenance', {})),
            observed_arm_velocity_source=record.get('observed_arm_velocity_source'),
            diagnostic_only=True, historical_grasp_flags_restored=False))
    fresh['controller'] = dict(grips=new_grips, tcp_targets_base=tcp, rolling_reference={}, rolling_reference_velocity={})
    return core.reseal(fresh)


def convert(controller, record):
    """Return a public-core resealed fixture without changing native state."""
    try:
        return _convert(controller, record)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('Incomplete historical front25 measurement: ' + str(exc)) from exc
