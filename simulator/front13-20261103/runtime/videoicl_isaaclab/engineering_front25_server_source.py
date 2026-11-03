"""Same-server hydration of archived engineering scene/command provenance.

Only the hydrated in-memory record contains the original scene. Evidence is
hash/count metadata; this module never prints or exports source files/commands.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import math
import re
from . import engineering_checkpoint as core

ENGINEERING_BASE = Path('/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering')
ROOT_RE = re.compile(r'execution-design-v3-20261102-[a-z0-9][a-z0-9-]*')
ROOM_RE = re.compile(r'room-[0-9]{2,3}-(E[0-9]{2})-([ABC])-s([1-9][0-9]*)')
TOKENS = {'STILL','GRASP','RELEASE','FWD','BACK','LEFT','RIGHT','UP','DOWN',
          'ROLL_LEFT','ROLL_RIGHT','PITCH_UP','PITCH_DOWN','ROTATE_CCW','ROTATE_CW'}


def _path(root, relative):
    """No source-controlled path overrides or symlink escape are accepted."""
    path = root
    for part in Path(relative).parts:
        if part in ('..', '.') or Path(part).is_absolute():
            raise ValueError('Invalid server-local source path')
        path = path / part
        if path.is_symlink():
            raise ValueError('Symlink in server-local engineering source')
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        raise ValueError('Server-local source escaped archived engineering root')
    return resolved


def _read(root, relative):
    raw = _path(root, relative).read_bytes()
    return raw, dict(sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))


def _initial_profile(root, spec):
    embodiment = spec.get('embodiment')
    if not isinstance(embodiment, str) or not re.fullmatch(r'[a-z0-9_-]+', embodiment):
        return None, {}, 'original profile name unavailable'
    try:
        raw, evidence = _read(root, 'runtime/configs/embodiments/' + embodiment + '.json')
    except FileNotFoundError:
        return None, {}, 'original profile file unavailable'
    profile = json.loads(raw)
    if evidence['sha256'] != spec.get('embodiment_config_sha256'):
        # RGB cadence derives a per-scene profile without rewriting the frozen
        # original file. Verify that archived derivation exactly; the caller
        # has already required current and archived profile identities equal.
        # This never maps a checkpoint between different camera cadences.
        cadence=spec.get('engineering_render_cadence',{})
        original=profile.get('physics',{}).get('render_hz')
        if (cadence.get('enabled')is not True or cadence.get('engineering_only')is not True
                or cadence.get('changed_config_fields')!=['physics.render_hz']
                or cadence.get('original_profile_sha256')!=evidence['sha256']
                or cadence.get('original_render_hz')!=original
                or type(cadence.get('render_hz'))is not int or cadence['render_hz']not in(1,5)
                or cadence.get('source_sha256')!=spec.get('execution_design',{}).get('source_sha256')
                or cadence.get('derived_profile_sha256')!=spec.get('embodiment_config_sha256')):
            raise ValueError('Original server-local embodiment profile SHA mismatch')
        profile['physics']['render_hz']=cadence['render_hz']
        derived=json.dumps(profile,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if hashlib.sha256(derived).hexdigest()!=spec['embodiment_config_sha256']:
            raise ValueError('Archived camera cadence profile SHA mismatch')
    initial = dict(left=.04, right=.04)
    overrides = profile.get('author_recording', {}).get('initial_gripper_commands_m', {})
    if (not isinstance(overrides, dict) or set(overrides) - set(initial)
            or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= .04 for x in overrides.values())):
        return None, evidence, 'original profile initial grip commands unavailable or invalid'
    initial.update(overrides)
    return initial, evidence, None


def _prefix(raw, source, initial):
    count = 0; previous_tick = None; last_stage = None
    grips = dict(initial); digest = hashlib.sha256(); byte_count = 0
    target = source['actions']
    for line in raw.splitlines(keepends=True):
        if count == target:
            break
        if not line.endswith(b'\n'):
            raise ValueError('Incomplete accepted action line')
        row = json.loads(line)
        if (type(row.get('step_before')) is not int or row['step_before'] != count
                or type(row.get('step_after')) is not int or row['step_after'] != count + 1):
            raise ValueError('Accepted action prefix is not contiguous from zero')
        before = row.get('shared_tick_before'); after = row.get('shared_tick_after')
        if (type(before) is not int or type(after) is not int or after <= before
                or previous_tick is not None and before != previous_tick
                or row.get('left') not in TOKENS or row.get('right') not in TOKENS):
            raise ValueError('Accepted action timing/command schema is incomplete')
        for side in ('left', 'right'):
            if row[side] == 'GRASP':grips[side] = 0.
            elif row[side] == 'RELEASE':grips[side] = .04
        count += 1; previous_tick = after; last_stage = row.get('stage')
        digest.update(line); byte_count += len(line)
    if (count != target or previous_tick != source['shared_tick']
            or previous_tick != source['native_physics_tick'] or last_stage != source['stage']):
        raise ValueError('Accepted prefix does not reach the declared measured boundary')
    return grips, dict(sha256=digest.hexdigest(), byte_count=byte_count, action_count=count)


def _terminal_measurements(controller, result, root, room_dir, evidence):
    """One timed final artifact supplies every pose/q/qd/TCP measurement."""
    raw, proof = _read(root, room_dir + '/reference-final-state.private.json')
    final = core._plain(json.loads(raw)); counters = result['source_counters']
    if (final.get('actions') != counters['actions']
            or final.get('native_physics_tick') != counters['native_physics_tick']
            or final.get('native_physics_tick') != counters['shared_tick']):
        raise ValueError('Terminal measurement actions/native tick do not match requested boundary')
    state = final.get('state'); feedback = final.get('robot_feedback')
    if not isinstance(state, dict) or set(state) != set(controller.scene.objects):
        raise ValueError('Terminal measurement object inventory incomplete')
    if not isinstance(feedback, dict) or set(feedback.get('arms', {})) != {'left','right'}:
        raise ValueError('Terminal same-tick dual-arm feedback incomplete')
    fingers = list(controller.scene.embodiment.config['gripper']['joints'])
    if len(fingers) != 2 or len(set(fingers)) != 2:
        raise ValueError('Matching native two-finger profile required')
    diagnostic = {}
    old_diagnostic = result.get('robot_diagnostics') or {}
    for side in ('left','right'):
        arm = feedback['arms'][side]; names = arm['joint_names']
        if not isinstance(names,list) or len(names) != 7 or len(set(names)) != 7:
            raise ValueError('Terminal native seven-joint names incomplete')
        q = core._array(arm['joint_positions_rad'],(7,),side+' terminal q')
        sensors = arm['measured_sensors']
        measured = {}
        for key,shape in (('joint_velocities_rad_s',(7,)),('joint_soft_limits_rad',(7,2)),('finger_joint_velocities_m_s',(2,))):
            if sensors[key].get('available') is not True:
                raise ValueError('Required terminal measured sensor unavailable: '+key)
            measured[key] = core._array(sensors[key]['value'],shape,side+' '+key).tolist()
        finger_q = core._array(arm['finger_joint_positions'],(2,),side+' terminal finger q').tolist()
        core._array(arm['tcp_position'],(3,),side+' terminal measured TCP')
        core._quat(arm['tcp_quaternion_wxyz'],side+' terminal measured TCP')
        if side in old_diagnostic:
            old = old_diagnostic[side]['arm_joints']
            old_q = dict(zip(old['names'],old['positions_rad']))
            if set(old_q) != set(names) or any(abs(float(old_q[n])-float(q[i]))>1e-5 for i,n in enumerate(names)):
                raise ValueError('Local q and same-boundary terminal q disagree')
        diagnostic[side] = dict(arm_joints=dict(names=list(names),positions_rad=q.tolist(),limits_rad=measured['joint_soft_limits_rad']),
            finger_joints=dict(names=fingers.copy(),positions_m=finger_q,velocities_m_s=measured['finger_joint_velocities_m_s']))
    mechanisms = final.get('mechanisms', {})
    if getattr(controller.scene,'mechanisms',{}) and not mechanisms:
        snapshot_raw, snapshot_proof = _read(root,room_dir+'/native-capture/final-snapshot.private.json')
        snapshot = core._plain(json.loads(snapshot_raw))
        if snapshot.get('actions')!=counters['actions'] or snapshot.get('native_physics_tick')!=counters['native_physics_tick']:
            raise ValueError('Mechanism final snapshot does not match the same terminal boundary')
        mechanisms = snapshot.get('mechanisms')
        evidence['same_tick_mechanism_snapshot'] = snapshot_proof
    if not isinstance(mechanisms,dict) or set(mechanisms) != set(getattr(controller.scene,'mechanisms',{})):
        raise ValueError('Terminal mechanisms unavailable; do not invent q/qd')
    measured_mechanisms = {}
    for name,row in mechanisms.items():
        names = row['joint_names']
        if not isinstance(names,list) or not names or len(set(names))!=len(names) or set(names)!=set(controller.scene.mechanisms[name].joint_names):
            raise ValueError('Terminal mechanism native joint inventory incomplete')
        measured_mechanisms[name] = dict(joint_names=list(names),
            joint_pos=core._array(row['joint_pos'],(len(names),),name+' terminal mechanism q').tolist(),
            joint_vel=core._array(row['joint_vel'],(len(names),),name+' terminal mechanism qd').tolist())
    result['state_task'] = state; result['robot_feedback_same_tick'] = feedback
    result['robot_diagnostics'] = diagnostic; result['mechanisms'] = measured_mechanisms
    result['observed_arm_velocity_source'] = 'same timed reference-final-state.robot_feedback.arms.SIDE.measured_sensors.joint_velocities_rad_s'
    proof.update(object_count=len(state),robot_count=2,action_count=final['actions'],physics_tick_count=final['native_physics_tick'])
    evidence['terminal_boundary'] = proof



def _sealed_room_source(root, room, source):
    """A stopped sibling-independent room can replace a missing pool exit.

    Read these artifacts only on the source server. Return hashes and numeric
    room proof; never retain terminal_geometry, evaluator state or source spec.
    """
    folder = 'result/' + room
    raw, terminal_proof = _read(root, folder + '/native-terminal.private.json')
    terminal = json.loads(raw)
    steps = terminal.get('steps'); tick = terminal.get('terminal_controller_tick')
    if (terminal.get('room') != room or terminal.get('recorder_stopped') is not True
            or type(steps) is not int or steps < source['actions']
            or type(tick) is not int or tick < max(source['shared_tick'], source['native_physics_tick'])):
        raise ValueError('Original source room is not independently sealed at the requested boundary')
    raw, capture_proof = _read(root, folder + '/native-capture/capture.private.json')
    capture = json.loads(raw)
    if (capture.get('engineering_reference_only') is not True
            or type(capture.get('native_action_count')) is not int
            or capture['native_action_count'] != steps):
        raise ValueError('Original source room capture does not match its sealed actions')
    raw, final_proof = _read(root, folder + '/reference-final-state.private.json')
    final = json.loads(raw)
    if (type(final.get('actions')) is not int or final['actions'] != steps
            or type(final.get('native_physics_tick')) is not int or final['native_physics_tick'] != tick):
        raise ValueError('Original source room final measurement does not match its sealed boundary')
    return dict(room_id=room, recorder_stopped=True, action_count=steps,
        physics_tick_count=tick, source_action_count=source['actions'],
        source_physics_tick_count=source['native_physics_tick'],
        terminal=terminal_proof, capture=capture_proof, final_measurement=final_proof)


def _hydrate(controller, record):
    if (not isinstance(record, dict) or record.get('schema') != 'videoicl-historical-approximate-engineering-segment-v1'
            or record.get('debug_only') is not True or record.get('engineering_only') is not True
            or record.get('history_reconstructed') is not False):
        raise ValueError('Historical independent engineering debug source required')
    selector = record.get('server_source')
    if (not isinstance(selector, dict) or not {'engineering_root','room_id'}<=set(selector)
            or set(selector)-{'engineering_root','room_id','measurement'}
            or selector.get('measurement') not in (None,'terminal_boundary')):
        raise ValueError('Exact server-local engineering_root and room_id required')
    text = selector['engineering_root']; room = selector['room_id']
    if not isinstance(text, str) or not isinstance(room, str):
        raise ValueError('Server-local source selector must contain strings')
    root = Path(text)
    if (not root.is_absolute() or str(root) != text or root.parent != ENGINEERING_BASE
            or not ROOT_RE.fullmatch(root.name) or root.is_symlink() or not root.is_dir()):
        raise ValueError('Server-local engineering root outside explicit archive allowlist')
    match = ROOM_RE.fullmatch(room)
    if match is None:
        raise ValueError('Invalid archived engineering room id')
    try:
        exit_raw, exit_evidence = _read(root, 'exit.private.json')
    except FileNotFoundError:
        exit_evidence = None
    else:
        if type(json.loads(exit_raw).get('code')) is not int:
            raise ValueError('Original archived engineering exit receipt required')
    room_dir = 'result/' + room
    raw, scene_evidence = _read(root, room_dir + '/scene-input.private.json')
    spec = core._plain(json.loads(raw))
    actual = core.identity(SimpleNamespace(scene=SimpleNamespace(spec=spec)))
    if actual != core.identity(controller):
        raise ValueError('Original server-local assignment/source/profile/physical identity mismatch')
    if 'scene_input' in record and actual != core.identity(SimpleNamespace(scene=SimpleNamespace(spec=record['scene_input']))):
        raise ValueError('Reconstructed and original server-local scene identity mismatch')
    expected = f"{spec['id']}-{spec['variant']}-{spec['execution_design'].get('condition')}-s{spec['seed']}"
    if (spec['id'] not in {f'E{i:02}' for i in range(14, 26)} or record.get('identity') != expected
            or match.groups() != (spec['id'], spec['variant'], str(spec['seed']))):
        raise ValueError('Original server-local task/variant/seed mismatch')
    provenance = record.get('scene_input_provenance', {})
    catalog = spec.get('provenance', {}).get('catalog_sha256')
    if (not isinstance(catalog, str) or not re.fullmatch('[0-9a-f]{64}', catalog)
            or provenance.get('catalog_sha256') != catalog
            or controller.scene.spec.get('provenance', {}).get('catalog_sha256') != catalog):
        raise ValueError('Original server-local source catalog SHA mismatch')
    source = record.get('source_counters', {})
    if (type(source.get('actions')) is not int or source['actions'] <= 0
            or type(source.get('shared_tick')) is not int or type(source.get('native_physics_tick')) is not int
            or not isinstance(source.get('stage'), str) or not source['stage']):
        raise ValueError('Historical accepted-prefix boundary required')
    evidence = dict(scene_input=scene_evidence)
    if exit_evidence is not None:
        evidence['old_exit'] = exit_evidence
    else:
        evidence['sealed_room'] = _sealed_room_source(root, room, source)
    initial, profile_evidence, problem = _initial_profile(root, spec)
    if profile_evidence:evidence['profile'] = profile_evidence
    grips = deepcopy(record.get('grips', {'left':None,'right':None}))
    if set(grips) != {'left','right'} or any(x is not None and (type(x) not in (int,float) or not math.isfinite(x) or not 0 <= x <= .04) for x in grips.values()):
        raise ValueError('Invalid explicitly known historical grip command')
    prefix_verified = False
    try:
        commands, command_evidence = _read(root, room_dir + '/engineering-reference/demo-actions.private.jsonl')
    except FileNotFoundError:
        problem = 'accepted action file unavailable'
    else:
        evidence['accepted_action_file'] = command_evidence
        if initial is not None:
            try:
                inferred, prefix_evidence = _prefix(commands, source, initial)
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                problem = 'accepted action prefix did not verify complete counters/schema'
            else:
                if any(grips[s] is not None and grips[s] != inferred[s] for s in grips):
                    raise ValueError('Known historical grip conflicts with accepted prefix')
                grips = inferred; evidence['accepted_prefix'] = prefix_evidence; prefix_verified = True
    result = deepcopy(record); result['scene_input'] = spec; result['grips'] = grips
    if selector.get('measurement') == 'terminal_boundary':
        _terminal_measurements(controller,result,root,room_dir,evidence)
    result['scene_input_provenance'] = dict(kind='literal original scene read on the same server only',
        literal_remote_scene_input_readback=True, server_local_source_verified=True,
        catalog_sha256=catalog, catalog_matches_native_provenance=True,
        accepted_prefix_verified=prefix_verified, server_local_evidence=evidence,
        terminal_measurement_hydrated=selector.get('measurement')=='terminal_boundary')
    result['grip_provenance'] = {s:dict(status='server-local verified complete accepted prefix' if prefix_verified else 'existing explicit value retained; unknown remains unknown',
        source_action_count=source['actions'], inference_reliable=prefix_verified)for s in ('left','right')}
    if not prefix_verified:
        result['grip_provenance']['unavailable_reason'] = problem or 'original profile unavailable; no command inference attempted'
    result.setdefault('source_evidence', {})['server_local_hydration'] = evidence
    return result


def hydrate(controller, record):
    """Hydrate an in-memory fixture; no native writes, printing or source export."""
    try:
        return _hydrate(controller, record)
    except (KeyError, TypeError, AttributeError, OSError) as exc:
        raise ValueError('Server-local engineering source validation failed: ' + type(exc).__name__) from exc
