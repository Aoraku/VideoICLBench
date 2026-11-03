"""Explicit engineering-only checkpoint restoration and suffix dispatch."""
from pathlib import Path
import hashlib
import importlib
import json
import math
import os
import numpy as np

HANDLERS = {
    **{task: 'engineering_local_suffix' for task in ('E28', 'E31', 'E34', 'E37')},
    'E39': 'engineering_e39_suffix', 'E40': 'engineering_e40_suffix',
    'E42': 'engineering_tool_suffix', 'E43': 'engineering_tool_suffix',
    'E45': 'engineering_tool_suffix', 'E46': 'engineering_tool_suffix',
    **{task: 'engineering_thin_suffix' for task in ('E44', 'E50')},
    **{task: 'execution_design_cards_reference' for task in ('E47', 'E48', 'E49')},
}
HANDLERS.update({task:'engineering_front25_suffix'for task in ('E15','E17','E18','E19','E20','E23','E24','E25')})


def restore_requested(controllers, cases, control, *, _request_override=None, _request_path=None):
    path = os.environ.get('VIC_ENGINEERING_CHECKPOINT_REQUEST')
    if not path and _request_override is None:
        return {}
    request_path = Path(_request_path if _request_override is not None else path)
    request = _request_override if _request_override is not None else json.loads(request_path.read_text())
    from .engineering_checkpoint_cohort import SCHEMA,selected_requests
    if request.get('schema')==SCHEMA:
        if _request_override is not None:raise ValueError('Nested cohort restore forbidden')
        selected=selected_requests(request,cases,controllers,request_path,control)
        result={}
        for room,case,single in selected:
            result.update(restore_requested({room:controllers[room]},[case],control,
                _request_override=single,_request_path=request_path))
        return result
    if control != 'positive' or len(cases) != 1 or len(controllers) != 1:
        raise ValueError('Checkpoint diagnostics require one room or an explicit validated cohort')
    case = cases[0]; room = case['episode_id']; controller = controllers[room]
    for key in ('task', 'variant', 'seed'):
        if request.get(key) != case[key]:
            raise ValueError('Checkpoint request case identity mismatch: ' + key)
    if case['task'] not in HANDLERS or not isinstance(request.get('entry'), str):
        raise ValueError('Explicit supported engineering suffix entry required')
    checkpoint_path = Path(request['checkpoint'])
    if not checkpoint_path.is_absolute():
        checkpoint_path = request_path.parent / checkpoint_path
    raw = checkpoint_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != request.get('sha256'):
        raise ValueError('Frozen checkpoint file SHA mismatch')
    checkpoint = json.loads(raw)
    if checkpoint.get('schema') == 'engineering-e44-rule-branch-v1':
        from .engineering_e44_rule_branch_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema') == 'engineering-e44-guide-material-migration-v1':
        from .engineering_e44_guide_material_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema') == 'engineering-render-cadence-migration-v1':
        from .engineering_render_checkpoint_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema') == 'engineering-e24-lid-layout-migration-v1':
        from .engineering_e24_layout_fixture import materialize
        checkpoint = materialize(controller, checkpoint, request)
    if checkpoint.get('schema') in ('engineering-e50-contact-hold-migration-v1','engineering-practical-card-contact-hold-migration-v1'):
        from .engineering_e50_contact_hold_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema') == 'engineering-e50-slow-reference-migration-v1':
        from .engineering_e50_slow_reference_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema') == 'engineering-thin-skin50-migration-v1':
        from .engineering_thin_contact_skin_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema') == 'engineering-e40-gripper-reference-migration-v1':
        from .engineering_e40_gripper_reference_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema')=='engineering-gripper-reference-profile-migration-v1':
        from .engineering_gripper_reference_fixture import materialize
        checkpoint=materialize(controller,checkpoint)
    if checkpoint.get('schema') == 'engineering-e40-coordinate-migration-v1':
        from .engineering_e40_coordinate_fixture import materialize
        checkpoint = materialize(controller, checkpoint, request)
    if checkpoint.get('schema') == 'engineering-thin-cooking-migration-v1':
        from .engineering_thin_cooking_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    if checkpoint.get('schema')=='engineering-e46-height-input-migration-v1':
        from .execution_design_e46_input_v2 import materialize
        checkpoint=materialize(controller,checkpoint)
    if checkpoint.get('schema')=='engineering-e46-partition-migration-v1':
        from .execution_design_e46_partition import materialize
        checkpoint=materialize(controller,checkpoint)
    if checkpoint.get('schema')=='engineering-e46-cooking-migration-v1':
        from .engineering_e46_cooking_fixture import materialize
        checkpoint=materialize(controller,checkpoint,request)
    if checkpoint.get('schema')=='engineering-e37-cooking-migration-v1':
        from .engineering_e37_cooking_fixture import materialize
        checkpoint=materialize(controller,checkpoint,request)
    if checkpoint.get('schema')=='engineering-e28-cooking-migration-v1':
        from .engineering_e28_cooking_fixture import materialize
        checkpoint=materialize(controller,checkpoint,request)
    if checkpoint.get('schema')=='engineering-e43-ball-migration-v1':
        from .engineering_e43_ball_fixture import materialize
        checkpoint=materialize(controller,checkpoint)
    if checkpoint.get('schema')=='engineering-e45-public-prefix-variant-v1':
        from .engineering_e45_public_prefix import materialize
        checkpoint=materialize(controller,checkpoint)
    if checkpoint.get('schema')=='engineering-e45-balls-migration-v1':
        from .engineering_e45_balls_fixture import materialize
        checkpoint=materialize(controller,checkpoint)
    if checkpoint.get('schema')=='videoicl-historical-approximate-engineering-segment-v1':
        if checkpoint.get('server_source'):
            from .engineering_front25_server_source import hydrate
            checkpoint = hydrate(controller, checkpoint)
        if checkpoint.get('restore_policy') is not None:
            from .engineering_front25_quasistatic_fixture import convert
        else:
            from .engineering_front25_fixture import convert
        checkpoint=convert(controller,checkpoint)
    if checkpoint.get('schema') == 'engineering-measured-pose-fixture-v1':
        from .engineering_pose_fixture import materialize
        checkpoint = materialize(controller, checkpoint)
    from .engineering_checkpoint import restore_startup
    receipt = restore_startup(controller, checkpoint)
    if checkpoint.get('render_cadence_migration_receipt') is not None:
        controller.scene.spec['engineering_render_checkpoint_migration']=checkpoint['render_cadence_migration_receipt']
    from .realworld_evaluator_selector import create_evaluator
    controller.scene.spec['engineering_checkpoint_resume'] = dict(
        diagnostic_only=True, entry=request['entry'], source_file_sha256=request['sha256'],
        source_actions=checkpoint['source']['steps'], source_stage=checkpoint['stage'],
        source_initial_episode=False)
    # Preserve physical state while discarding completion/history labels. This
    # suffix can never provide a complete source-initial positive witness.
    controller.evaluator = create_evaluator(controller.scene.spec)
    controller.evaluator.reset_episode()
    return {room: dict(request=request, checkpoint=checkpoint, restore_receipt=receipt)}


def retarget_fixture_hold(pool, controllers, resumed):
    """Refresh forward kinematics under measured joint holds, then set TCP hold."""
    selected = {room: row for room, row in resumed.items()
                if row['checkpoint']['state_quality'] == 'measured_pose_fixture' or
                row['request'].get('retarget_measured_hold') is True}
    if not selected:
        return
    for room, row in selected.items():
        controller = controllers[room]
        if controller._author_joint_override:
            raise ValueError('Checkpoint fixture cannot overwrite a live joint override')
        for side, asset in controller.scene.robots.items():
            arm = controller.ids[side][0]
            q = asset.data.joint_pos[:, arm].clone()
            controller._author_joint_override[side] = (q, q * 0.)
    try:
        pool.tick()
        for room, row in selected.items():
            controller = controllers[room]
            controller.targets = {side: tuple(x.clone() for x in controller.pose(side))
                                  for side in controller.scene.robots}
            controller._public_reference = {}
            controller._public_reference_velocity = {}
            row['restore_receipt']['quasi_static_retarget_physics_ticks'] = 1
            row['restore_receipt']['native_fk_retarget_completed'] = True
            row['restore_receipt']['stage_entry_controller_policy'] = 'hold_measured_joints_then_measured_tcp'
    finally:
        for room in selected:
            controllers[room]._author_joint_override = {}


def validate_after_settle(controller, resumed):
    from .engineering_checkpoint import capture
    checkpoint = resumed['checkpoint']; request = resumed['request']
    if (checkpoint.get('context', {}).get('requires_native_fk_retarget') is True
            and (resumed['restore_receipt'].get('native_fk_retarget_completed') is not True
                 or resumed['restore_receipt'].get('quasi_static_retarget_physics_ticks') != 1)):
        raise ValueError('Historical joint-only fixture requires completed native FK retarget before admission')
    actual = capture(controller, 'checkpoint-restoration-readback')
    if resumed.get('artifact_folder'):
        path = Path(resumed['artifact_folder']) / 'checkpoint-readback-actual.private.json'
        path.write_text(json.dumps(actual, indent=2) + '\n'); path.chmod(0o600)
    focus=request.get('focus_objects')
    names=set(checkpoint['objects'])
    if focus is not None:
        if (not isinstance(focus,list)or not focus or any(not isinstance(n,str)for n in focus)
                or len(focus)!=len(set(focus))or not set(focus)<=names):
            raise ValueError('Explicit nonempty native object names required for segment readback focus')
        protected={n for pair in request.get('required_contacts',[])for n in pair if n in names}
        protected.update(n for n,_ in request.get('required_grasps',[]))
        if not protected<=set(focus):raise ValueError('Segment readback focus cannot omit required contact/grasp objects')
    positions = []; angles = [];all_positions=[];all_angles=[];object_drift={}
    for family in ('objects', 'mechanisms'):
        for name, saved in checkpoint[family].items():
            before = np.asarray(saved['root_state_task'], float)
            after = np.asarray(actual[family][name]['root_state_task'], float)
            position=float(np.linalg.norm(before[:3] - after[:3]))
            dot = abs(float(before[3:7] @ after[3:7]) /
                      (np.linalg.norm(before[3:7]) * np.linalg.norm(after[3:7])))
            angle=2. * math.acos(float(np.clip(dot, 0., 1.)))
            all_positions.append(position);all_angles.append(angle)
            object_drift[name]=dict(translation_m=position,rotation_rad=angle,
                required_for_segment=family=='mechanisms'or focus is None or name in focus)
            if family=='mechanisms'or focus is None or name in focus:
                positions.append(position);angles.append(angle)
    state, contacts = controller.snapshot()
    missing = [pair for pair in request.get('required_contacts', []) if frozenset(pair) not in contacts]
    expected_grasps = list(request.get('required_grasps', []))
    for name, flags in checkpoint.get('readback', {}).get('object_grasps', {}).items():
        for side, held in zip(('left', 'right'), flags):
            if held and [name, side] not in expected_grasps:
                expected_grasps.append([name, side])
    missing_grasps = [dict(object=name, side=side) for name, side in expected_grasps
                      if not state[name]['grasp'][('left', 'right').index(side)]]
    max_position = max(positions, default=0.); max_angle = max(angles, default=0.)
    limits = request.get('restoration_tolerances', {})
    valid = (max_position <= float(limits.get('translation_m', .005)) and
             max_angle <= float(limits.get('rotation_rad', math.radians(5.))) and
             not missing and not missing_grasps)
    report = dict(diagnostic_only=True, passed=bool(valid),
        maximum_root_translation_drift_m=max_position, maximum_root_rotation_drift_rad=max_angle,
        validation_scope='all_objects'if focus is None else'named_segment_objects_and_all_mechanisms',
        focus_objects=focus,per_object_drift=object_drift,
        all_objects_maximum_translation_drift_m=max(all_positions,default=0.),
        all_objects_maximum_rotation_drift_rad=max(all_angles,default=0.),
        all_objects_within_tolerances=bool(max(all_positions,default=0.)<=float(limits.get('translation_m',.005))and max(all_angles,default=0.)<=float(limits.get('rotation_rad',math.radians(5.)))),
        missing_contacts=missing, missing_grasps=missing_grasps,
        actual_contacts=[sorted(pair) for pair in contacts],
        actual_object_grasps={name: list(v['grasp']) for name, v in state.items()},
        exact_physx_contact_cache_restored=False)
    if not valid:
        raise ValueError('Checkpoint physical readback rejected: ' + json.dumps(report))
    return report


def solve_suffix(author):
    if not author.control_report.get('engineering_reference_only'):
        raise ValueError('Checkpoint suffix is private engineering only')
    task = author.scene.spec['id']
    if task not in HANDLERS:
        raise ValueError('Checkpoint suffix task outside explicit scope')
    module = importlib.import_module('.' + HANDLERS[task], __package__)
    result = module.solve(author, author._engineering_resume_checkpoint,
                          author._engineering_resume_context)
    if task in ('E15','E17','E18','E19','E20','E23','E24','E25','E28','E31','E34','E37') and result.get('segment_passed') is True:
        # Preserve the exact successful boundary too: before-action.latest is
        # necessarily one action earlier and final snapshots omit drive state.
        # This is read-only capture, with no settling tick/history restoration.
        from .engineering_checkpoint import capture
        checkpoint = capture(author.c, 'checkpoint-suffix-completed', context=dict(
            entry=author._engineering_resume_context.get('entry'),
            carried_payload=getattr(author,'carried_payload',None), local_debug_only=True))
        path = Path(author.out) / 'checkpoints' / 'complete-after-last-action.private.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(checkpoint, indent=2) + '\n').encode()
        path.write_bytes(raw);path.chmod(0o600)
        result = dict(result, complete_checkpoint=dict(path=str(path),
            sha256=hashlib.sha256(raw).hexdigest(),
            source=checkpoint['source'], no_physics_advance=True))
    return dict(result, diagnostic_only=True, source_initial_episode=False,
                native_task_acceptance=False, checkpoint_suffix=True)
