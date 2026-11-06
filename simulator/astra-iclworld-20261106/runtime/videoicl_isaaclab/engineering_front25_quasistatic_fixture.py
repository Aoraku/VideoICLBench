"""Explicit front25 historical debug fixtures with disclosed velocity assumptions.

No native state is written here. Startup TCP targets are placeholders until the
caller performs the mandatory joint-hold tick, native FK retarget and readback.
"""
from copy import deepcopy
from types import SimpleNamespace
import math
import numpy as np
from . import engineering_checkpoint as core
from . import engineering_front25_fixture as measured

RESTORE_POLICY = dict(arm_velocity='zero_assumed_quasistatic_debug',
                      tcp_target='retarget_from_restored_native_fk')
RETARGET_POLICY = 'hold_measured_joints_then_measured_tcp'


def _velocity(arm, feedback, side):
    """Missing arm velocity is ASSUMED; an advertised measurement must validate."""
    names=arm['names']; measured_values=[]
    if 'velocities_rad_s'in arm:
        measured_values.append(measured._named(names,arm['velocities_rad_s'],side+' diagnostic measured qd'))
    sensor=feedback.get('measured_sensors',{}).get('joint_velocities_rad_s')
    if sensor is not None:
        if not isinstance(sensor,dict):raise ValueError('Invalid historical arm velocity sensor: '+side)
        if sensor.get('available')is True:
            measured_values.append(measured._named(feedback['joint_names'],sensor['value'],side+' measured arm qd'))
        elif sensor.get('available')is not False or sensor.get('value')is not None:
            raise ValueError('Contradictory/unlabelled historical arm velocity: '+side)
    if measured_values:
        if any(set(x)!=set(names)for x in measured_values):raise ValueError('Measured arm velocity joint identity mismatch: '+side)
        if any(any(abs(x[n]-measured_values[0][n])>1e-6 for n in names)for x in measured_values[1:]):
            raise ValueError('Historical measured arm velocity sources disagree: '+side)
        return measured_values[0],'measured'
    return {n:0. for n in names},'ASSUMED_zero_quasistatic_debug'


def _robot(controller,side,destination,diagnostic,feedback,grip,assumptions):
    arm=diagnostic['arm_joints'];fingers=diagnostic['finger_joints']
    arm_q=measured._named(arm['names'],arm['positions_rad'],side+' arm q')
    finger_q=measured._named(fingers['names'],fingers['positions_m'],side+' finger q')
    finger_qd=measured._named(fingers['names'],fingers['velocities_m_s'],side+' MEASURED finger qd')
    names=destination['joint_names']
    if (len(arm_q)!=7 or len(finger_q)!=2 or len(names)!=9 or len(set(names))!=9
            or set(arm_q)&set(finger_q) or set(arm_q)|set(finger_q)!=set(names)):
        raise ValueError('Complete native nine-joint identity required: '+side)
    if ('joint_names'in feedback)!=('joint_positions_rad'in feedback):raise ValueError('Partial historical feedback q: '+side)
    if 'joint_names'in feedback:
        other=measured._named(feedback['joint_names'],feedback['joint_positions_rad'],side+' same-tick feedback q')
        if set(other)!=set(arm_q)or any(abs(other[n]-arm_q[n])>1e-6 for n in arm_q):
            raise ValueError('Historical diagnostics and same-tick feedback q disagree: '+side)
    # Existing TCP measurements are checked and kept as provenance, never filled
    # from fingers, FK or a default pose. They are not used as startup targets.
    if feedback.get('tcp_position')is not None:core._array(feedback['tcp_position'],(3,),side+' historical TCP position')
    if feedback.get('tcp_quaternion_wxyz')is not None:core._quat(feedback['tcp_quaternion_wxyz'],side+' historical TCP quaternion')
    arm_qd,velocity_source=_velocity(arm,feedback,side)
    q={**arm_q,**finger_q};qd={**arm_qd,**finger_qd}
    destination['joint_pos']=[float(q[n])for n in names]
    destination['joint_vel']=[float(qd[n])for n in names]
    destination['root_state_task'][7:]=[0.]*6
    config=controller.scene.embodiment.config['gripper'];finger_names=config.get('joints',fingers['names'])
    if len(finger_names)!=2 or set(finger_names)!=set(finger_q):raise ValueError('Native gripper profile joint identity mismatch: '+side)
    opened=core._array(config['open'],(2,),side+' profile open');closed=core._array(config['closed'],(2,),side+' profile closed')
    if float(np.mean(opened)-np.mean(closed))<=1e-9:raise ValueError('Increasing native gripper opening required')
    if grip is None:
        mean=float(np.mean(list(finger_q.values())));fraction=(mean-float(np.mean(closed)))/float(np.mean(opened-closed))
        if not -1e-4<=fraction<=1.0001:raise ValueError('Measured opening outside native gripper profile: '+side)
        command=.04*float(np.clip(fraction,0.,1.))
        assumptions.append(side+': historical grip command UNKNOWN; NEW debug hold uses measured finger-opening mean/profile, not a claimed historical command.')
    else:
        if type(grip)not in(float,int)or not math.isfinite(grip)or not 0.<=grip<=.04:raise ValueError('Invalid known historical grip: '+side)
        command=float(grip);assumptions.append(side+': explicitly known historical public grip retained.')
    drive=destination['joint_pos'].copy();requested=closed+(opened-closed)*(command/.04)
    for name,value in zip(finger_names,requested):drive[names.index(name)]=float(value)
    destination['drive_targets']=dict(position=drive,velocity=[0.]*9,effort=[0.]*9)
    if velocity_source=='measured':assumptions.append(side+': historical arm qd MEASURED and retained by native joint name.')
    else:assumptions.append(side+': historical arm qd MISSING; ASSUMED zero for quasistatic debug initialization, NOT measured and NOT reconstructed history.')
    assumptions.append(side+': arm/finger q and finger qd MEASURED and retained; NEW measured-q/profile-finger drive, zero velocity/effort targets; fresh fixed-base pose retained with ASSUMED zero base velocities.')
    return command,velocity_source


def _convert(controller,record):
    if (not isinstance(record,dict)or record.get('schema')!=measured.SCHEMA
            or record.get('engineering_only')is not True or record.get('debug_only')is not True
            or record.get('history_reconstructed')is not False or set(record)&measured.FORBIDDEN
            or record.get('restore_policy')!=RESTORE_POLICY):
        raise ValueError('Explicit historical quasistatic debug restore_policy required')
    record=core._plain(record);spec=record.get('scene_input')
    if not isinstance(spec,dict):raise ValueError('Verified historical scene input required')
    fresh=core.capture(controller,'historical-quasistatic-fixture-validation')
    if fresh['identity']!=core.identity(SimpleNamespace(scene=SimpleNamespace(spec=spec))):
        raise ValueError('Historical assignment/source/profile/physical geometry identity mismatch')
    identity=fresh['identity'];design=spec.get('execution_design',{})
    if identity['task']not in('E17','E20','E23','E25')or record.get('identity')!=f"{identity['task']}-{identity['variant']}-{design.get('condition')}-s{identity['seed']}":
        raise ValueError('Quasistatic historical fixtures require registered front25 segment scope')
    provenance=record.get('scene_input_provenance',{});catalog=provenance.get('catalog_sha256')
    literal=provenance.get('literal_remote_scene_input_readback')
    server_verified=literal is True and provenance.get('server_local_source_verified')is True
    reconstructed=literal is False and provenance.get('server_local_source_verified')in(None,False)
    if (not(server_verified or reconstructed)or provenance.get('catalog_matches_native_provenance')is not True
            or not isinstance(catalog,str)or len(catalog)!=64 or any(ch not in'0123456789abcdef'for ch in catalog)
            or catalog!=spec.get('provenance',{}).get('catalog_sha256')
            or catalog!=controller.scene.spec.get('provenance',{}).get('catalog_sha256')):
        raise ValueError('Historical catalog/source provenance mismatch')
    if fresh.get('passive_material'):raise ValueError('Missing historical passive material state')
    source=measured._time(record,controller.dt);states=record.get('state_task')
    if not isinstance(states,dict)or set(states)!=set(fresh['objects']):raise ValueError('Historical object inventory mismatch')
    for name,state in states.items():fresh['objects'][name]['root_state_task']=measured._pose(state,'object/'+name)
    assumptions=fresh['assumptions']
    assumptions.extend([
        'Historical object root velocities MISSING: ASSUMED zero, not measured. Historical poses retained with matrix-to-unit-quaternion conversion.',
        'Original source/assignment/profile/geometry/catalog identities verified; '+('literal source scene SERVER-LOCAL.'if server_verified else'scene is a declared deterministic LOCAL reconstruction.'),
        'Fresh capture TCP targets are STARTUP PLACEHOLDERS ONLY, not historical TCP measurements and not safe segment targets.',
        'MANDATORY: one restored-joint-position-hold physical tick, then replace BOTH TCP targets from actual restored native FK, clear rolling reference, warm up and verify actual pose/support/grasp before public actions.',
        'PhysX contact caches and evaluator/history/success/grasp labels are NOT restored; local segment cannot grant full-task acceptance.',
    ])
    diagnostics=record.get('robot_diagnostics',{});feedback=record.get('robot_feedback_same_tick');grips=record.get('grips',{})
    if feedback is not None and not isinstance(feedback,dict):raise ValueError('Invalid historical same-tick feedback')
    arms=feedback.get('arms',{})if feedback is not None else{}
    if (set(fresh['robots'])!={'left','right'}or not set(fresh['robots'])<=set(diagnostics)
            or not isinstance(arms,dict)or set(arms)-set(fresh['robots'])or set(grips)!=set(fresh['robots'])):
        raise ValueError('Complete historical dual-arm diagnostics and grip fields required')
    placeholders=deepcopy(fresh['controller']['tcp_targets_base']);commands={};velocity_sources={}
    if set(placeholders)!=set(fresh['robots']):raise ValueError('Complete fresh startup TCP placeholders required')
    for side,destination in fresh['robots'].items():
        core._array(placeholders[side]['position'],(3,),side+' fresh startup TCP');core._quat(placeholders[side]['quaternion'],side+' fresh startup TCP')
        commands[side],velocity_sources[side]=_robot(controller,side,destination,diagnostics[side],arms.get(side,{}),grips[side],assumptions)
    mechanisms=record.get('mechanisms',{})
    if not isinstance(mechanisms,dict)or set(mechanisms)!=set(fresh['mechanisms']):raise ValueError('Historical mechanism inventory mismatch')
    for name,destination in fresh['mechanisms'].items():
        row=mechanisms[name];q=measured._named(row['joint_names'],row['joint_pos'],name+' mechanism q');qd=measured._named(row['joint_names'],row['joint_vel'],name+' mechanism qd')
        if set(q)!=set(destination['joint_names']):raise ValueError('Historical mechanism joint identity mismatch')
        destination['joint_pos']=[float(q[n])for n in destination['joint_names']];destination['joint_vel']=[float(qd[n])for n in destination['joint_names']]
        destination['root_state_task'][7:]=[0.]*6
        destination['drive_targets']=dict(position=destination['joint_pos'].copy(),velocity=[0.]*len(q),effort=[0.]*len(q))
        assumptions.append(name+': MEASURED mechanism q/qd retained; fresh fixed base, ASSUMED zero base velocities and NEW measured-q drive hold.')
    fresh.update(state_quality='measured_pose_fixture',diagnostic_only=True,stage=record['source_counters']['stage'],source=source,
        context=dict(historical_fixture_schema=measured.SCHEMA,historical_identity=record['identity'],
            source_evidence=deepcopy(record.get('source_evidence',{})),missing_restore_fields=deepcopy(record.get('missing_restore_fields',[])),
            scene_input_provenance=deepcopy(provenance),grip_provenance=deepcopy(record.get('grip_provenance',{})),
            diagnostic_only=True,historical_grasp_flags_restored=False,restore_policy=deepcopy(RESTORE_POLICY),
            arm_velocity_provenance=velocity_sources,mandatory_native_fk_retarget=True,requires_native_fk_retarget=True,native_fk_retarget_completed=False,
            tcp_targets_are_startup_placeholders=True,mandatory_physical_readback=['pose','support_contacts','actual_grasps'],
            public_actions_forbidden_until_retarget_and_readback=True))
    fresh['controller']=dict(grips=commands,tcp_targets_base=placeholders,rolling_reference={},rolling_reference_velocity={})
    return core.reseal(fresh)


def convert(controller,record):
    try:return _convert(controller,record)
    except(KeyError,TypeError,IndexError,AttributeError)as exc:
        raise ValueError('Incomplete historical quasistatic fixture: '+str(exc))from exc


def require_retarget_and_readback(checkpoint,restore_receipt,physical_readback):
    """Caller gate before segment dispatch; this does not step or mutate state."""
    context=checkpoint.get('context',{})
    if (checkpoint.get('state_quality')!='measured_pose_fixture'or checkpoint.get('diagnostic_only')is not True
            or context.get('mandatory_native_fk_retarget')is not True
            or context.get('requires_native_fk_retarget')is not True
            or context.get('restore_policy')!=RESTORE_POLICY
            or type(restore_receipt.get('quasi_static_retarget_physics_ticks'))is not int
            or restore_receipt['quasi_static_retarget_physics_ticks']!=1
            or restore_receipt.get('native_fk_retarget_completed')is not True
            or restore_receipt.get('stage_entry_controller_policy')!=RETARGET_POLICY):
        raise ValueError('Mandatory restored native FK retarget has not completed')
    if (physical_readback.get('diagnostic_only')is not True or physical_readback.get('passed')is not True
            or physical_readback.get('missing_contacts')!=[]or physical_readback.get('missing_grasps')!=[]):
        raise ValueError('Mandatory actual pose/support/grasp readback has not passed')
    return dict(ready_for_local_segment=True,diagnostic_only=True,full_task_acceptance=False)
