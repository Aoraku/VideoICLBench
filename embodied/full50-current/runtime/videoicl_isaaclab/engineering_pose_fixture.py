"""Reconstruct an explicitly labelled quasi-static fixture from old native logs.

Old trajectories omit velocities and drive targets. They cannot be exact
dynamic checkpoints; this adapter uses the actual measured poses/joints with
declared zero-velocity/holding assumptions and requires physical readback.
"""
import copy
import math
import numpy as np
from .engineering_checkpoint import capture, identity, reseal, _hash, PHYSICAL_KEYS
from .layout import rotation_matrix
from .author_orientation import _axis_angle

SCHEMA = 'engineering-measured-pose-fixture-v1'
REVIEWED_SMOOTH_FIELDS = {
    ('physics', 'public_action_max_seconds'): 1.2,
    ('physics', 'public_action_check_seconds'): .1,
    ('control', 'rolling_joint_reference'): True,
    ('control', 'public_reference_acceleration_rad_s2'): 20,
    ('control', 'public_ik_retry_ticks'): 6,
}


def _quat(matrix):
    matrix = np.asarray(matrix, float)
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all() or
            not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-4) or np.linalg.det(matrix) < .999):
        raise ValueError('Measured proper body rotation required')
    axis, angle = _axis_angle(matrix)
    return np.r_[math.cos(angle / 2.), axis * math.sin(angle / 2.)]


def materialize(controller, recipe):
    if recipe.get('schema') != SCHEMA or recipe.get('diagnostic_only') is not True:
        raise ValueError('Explicit measured-pose engineering fixture required')
    spec = recipe['source_scene']; target = identity(controller)
    design = spec['execution_design']
    expected = dict(task=spec['id'], variant=spec['variant'], seed=spec['seed'],
        assignment_identity_sha256=design['assignment_identity_sha256'],
        source_sha256=design['source_sha256'], embodiment_config_sha256=spec['embodiment_config_sha256'],
        physical_geometry_sha256=_hash({key: spec.get(key) for key in PHYSICAL_KEYS}))
    profile_adaptation = False
    if (expected['embodiment_config_sha256'] != target['embodiment_config_sha256'] and
            recipe.get('allow_reviewed_smooth_control_profile') is True):
        old = recipe['source_profile_config']; new = controller.scene.embodiment.config
        if _hash(old) != expected['embodiment_config_sha256'] or _hash(new) != target['embodiment_config_sha256']:
            raise ValueError('Reviewed controller adaptation profile SHA mismatch')
        patched = copy.deepcopy(old)
        for (section, key), value in REVIEWED_SMOOTH_FIELDS.items():
            if new.get(section, {}).get(key) != value:
                raise ValueError('Only the five reviewed smooth-control fields may change')
            patched.setdefault(section, {})[key] = value
        if patched != new:
            raise ValueError('Physical robot/camera/layout changes cannot use a control-only fixture adaptation')
        expected['embodiment_config_sha256'] = target['embodiment_config_sha256']
        profile_adaptation = True
    if expected != target:
        raise ValueError('Measured fixture source/profile/physical scene mismatch')
    result = capture(controller, recipe['stage'], context=recipe.get('context', {}))
    frame = recipe['frame']; diagnostics = recipe['robot_diagnostics']
    if set(frame['state']) != set(result['objects']):
        raise ValueError('Every measured rigid object is required')
    for name, row in result['objects'].items():
        measured = frame['state'][name]
        row['root_state_task'] = [*measured['pos'], *_quat(np.asarray(measured['mat'])).tolist(), *([0.] * 6)]
    for side, row in result['robots'].items():
        native = diagnostics[side]
        joints = {name: value for group, field in (('arm_joints', 'positions_rad'), ('finger_joints', 'positions_m'))
                  for name, value in zip(native[group]['names'], native[group][field])}
        if set(joints) != set(row['joint_names']):
            raise ValueError('Every measured robot joint is required')
        row['joint_pos'] = [float(joints[name]) for name in row['joint_names']]
        row['joint_vel'] = [0.] * len(joints)
        row['drive_targets'] = dict(position=list(row['joint_pos']), velocity=[0.] * len(joints), effort=[0.] * len(joints))
        command = float(recipe['grips'][side])
        finger_ids = controller.ids[side][1]
        values = controller.scene.embodiment.gripper_values(command / .04)
        for index, value in zip(finger_ids, values):
            row['drive_targets']['position'][index] = float(value)
    current = controller.snapshot_mechanisms()
    if set(frame.get('mechanisms', {})) != set(result['mechanisms']):
        raise ValueError('Every measured articulated mechanism is required')
    for name, row in result['mechanisms'].items():
        old = frame['mechanisms'][name]; now = current[name]; body = now['body_names'][0]
        def transform(position, matrix):
            value = np.eye(4); value[:3, :3] = matrix; value[:3, 3] = position
            return value
        root = np.asarray(row['root_state_task'])
        root_to_body = np.linalg.inv(transform(root[:3], rotation_matrix(root[3:7]))) @ transform(now['body_pos_task'][body], now['body_mat_task'][body])
        restored_root = transform(old['body_pos_task'][body], old['body_mat_task'][body]) @ np.linalg.inv(root_to_body)
        row['root_state_task'] = [*restored_root[:3, 3], *_quat(restored_root[:3, :3]), *([0.] * 6)]
        if old['joint_names'] != row['joint_names']:
            raise ValueError('Measured articulated joint order mismatch')
        row['joint_pos'] = list(old['joint_pos']); row['joint_vel'] = [0.] * len(row['joint_names'])
        # Source passive springs/material laws remain authoritative; no added
        # actuator or fabricated holding effort is introduced to mechanisms.
        row['drive_targets'] = dict(position=list(row['joint_pos']), velocity=[0.] * len(row['joint_pos']), effort=[0.] * len(row['joint_pos']))
    if result['passive_material']:
        supplied = recipe.get('passive_material')
        if not isinstance(supplied, dict) or set(supplied) != set(result['passive_material']):
            raise ValueError('Measured or explicitly justified passive material state required')
        result['passive_material'] = copy.deepcopy(supplied)
    result['controller']['grips'] = dict(recipe['grips'])
    result['controller']['rolling_reference'] = {}
    result['controller']['rolling_reference_velocity'] = {}
    result['readback'] = dict(available='contacts' in recipe,
        object_grasps={name: list(body['grasp']) for name, body in frame['state'].items()},
        contacts=copy.deepcopy(recipe.get('contacts', [])),
        limitations=[] if 'contacts' in recipe else ['Source contact list was not supplied; do not substitute template contacts.'])
    result.update(state_quality='measured_pose_fixture', source=dict(
        steps=int(recipe['source_actions']), physics_ticks=int(frame['native_physics_tick']), dt=float(frame['dt'])))
    result['assumptions'] += [
        'Old native logs lack complete root/robot velocity and drive history; all reconstructed velocities are explicitly zero.',
        'Robot bases use the matching fresh profile; arms hold measured q, and saved gripper commands reestablish real contact.',
        'One held-joint readback tick retargets TCP before settling; native contacts and support must be verified.',
        'No evaluator history, completion label, PhysX contact cache or Python call stack is restored.',
        *recipe.get('assumptions', [])]
    if profile_adaptation:
        result['assumptions'].append('Only the already reviewed five smooth-control fields changed; all physical robot, actuator, camera, layout and timestep configuration is identical.')
    return reseal(result)
