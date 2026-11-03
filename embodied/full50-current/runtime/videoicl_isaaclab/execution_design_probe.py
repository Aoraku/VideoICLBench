"""Opt-in engineering controls for an already initialized native RoomPool.

Importing or validating this module starts no simulator, worker, or model.
Only run_controls executes physical actions, in worlds created by the caller.
"""
from pathlib import Path
import hashlib
import json
import time

from .execution_design_native_capture import NativeCapture, _json, _write, _artifact

from .execution_design_back25_negative import EXTRA_CONTROLS
CONTROLS=('positive','wrong_members','wrong_destination','wrong_rule','not_released')+EXTRA_CONTROLS
TASKS=('E01','E09','E17','E20','E39')
ALL_TASKS=tuple(f'E{i:02}' for i in range(1,51))


def validate_execution_cases(cases,control):
    if control not in CONTROLS:raise ValueError('Unknown execution engineering control')
    from .realworld_scenes import load
    rows=[];identities=set()
    for case in cases:
        if case['task'] not in ALL_TASKS:raise ValueError('Execution controls require an E01-E50 task')
        spec=load(case['task'],case['variant'],case['seed'],Path(case['bindings']),verify_files=False)
        design=spec.get('execution_design',{})
        identity=design.get('assignment_identity_sha256')
        from .execution_design import SUPPORTED_REVISIONS,metadata
        if design.get('revision') not in SUPPORTED_REVISIONS or not identity:
            raise ValueError('Explicit revision bindings and fresh assignment identity required')
        if design.get('condition') not in metadata(case['task'],revision=design['revision'])['support_mask']:
            raise ValueError('Condition is not supported by this source revision')
        if control in EXTRA_CONTROLS:
            from .execution_design_back25_negative import CAPABILITIES
            from .execution_design import REVISION_V3
            if design['revision']!=REVISION_V3 or control not in CAPABILITIES.get(case['task'],()):
                raise ValueError('Extra control requires an explicitly implemented back25 v3 case')
        if case['task'] not in TASKS:
            from .execution_design_reference import reference_capability
            cap=reference_capability(case['task'],control)
            if not cap['implemented']:raise NotImplementedError(cap['reason'])
            if cap.get('required_revision') and design['revision']!=cap['required_revision']:
                raise ValueError('Counterexample requires explicit v3 engineering revision')
        if identity in identities:raise ValueError('Duplicate engineering case identity')
        identities.add(identity)
        rows.append(dict(episode_id=case['episode_id'],task=case['task'],variant=case['variant'],seed=case['seed'],
            condition=design['condition'],control=control,assignment_identity_sha256=identity,
            engineering_control_identity_sha256=hashlib.sha256((identity+':'+control).encode()).hexdigest(),
            binding_sha256=hashlib.sha256(Path(case['bindings']).read_bytes()).hexdigest(),
            native_assets_verified=False,native_acceptance='not_run'))
    return rows


def matrix_case_batches(bindings_by_condition,*,tasks=TASKS,seeds=(4201,4202,4203),robot='franka',rooms_per_batch=15):
    """Return explicit JSON case batches; never dispatch or launch them."""
    if set(bindings_by_condition)!=set(('I','E')):raise ValueError('Both I and E binding files required')
    if len(set(seeds))<3 or any(type(s) is not int or s<0 for s in seeds):raise ValueError('At least three distinct nonnegative seeds required')
    if not tasks or any(t not in TASKS for t in tasks):raise ValueError('Only revised workflow tasks supported')
    if not 1<=rooms_per_batch<=15:raise ValueError('Use 1..15 rooms per native process')
    cases=[dict(episode_id=f'{task}-{variant}-{condition}-s{seed}',task=task,variant=variant,seed=seed,
        bindings=str(Path(bindings_by_condition[condition]).resolve(strict=True)),robot=robot)
        for condition in ('I','E') for task in tasks for variant in 'ABC' for seed in seeds]
    return [cases[i:i+rooms_per_batch] for i in range(0,len(cases),rooms_per_batch)]


def full50_matrix_case_batches(bindings_by_condition, *, seeds=(4201,4202,4203),robot='franka',rooms_per_batch=5):
    """Plan the final source's legal cells, including R/E; never launch them."""
    from .execution_design import metadata,REVISION_V3
    if set(bindings_by_condition)!=set('RIE'):raise ValueError('Explicit R/I/E binding files required')
    if len(set(seeds))<3 or any(type(s)is not int or s<0 for s in seeds):raise ValueError('At least three distinct seeds required')
    if not 1<=rooms_per_batch<=15:raise ValueError('Use 1..15 rooms per native process')
    for condition,path in bindings_by_condition.items():
        binding=json.loads(Path(path).read_bytes())
        if binding.get('execution_design')!={'revision':REVISION_V3,'condition':condition}:
            raise ValueError('Full50 plan requires matching explicit v3 condition bindings')
    cases=[dict(episode_id=f'{task}-{variant}-{condition}-s{seed}',task=task,variant=variant,seed=seed,
                bindings=str(Path(bindings_by_condition[condition]).resolve(strict=True)),robot=robot)
           for task in ALL_TASKS for condition in metadata(task,revision=REVISION_V3)['support_mask']
           for variant in 'ABC' for seed in seeds]
    return [cases[i:i+rooms_per_batch]for i in range(0,len(cases),rooms_per_batch)]


def normalized_native_result(result):
    """Present the existing native rubric without turning missing scores into 0."""
    if 'task_score_100' in result and 'native_evidence_valid' in result:return result
    from copy import deepcopy
    row=deepcopy(result);progress=result.get('progress_result',{});evidence=result.get('progress_evidence',{})
    valid=(result.get('history_valid') is True and not result.get('errors') and
           evidence.get('source')=='trusted_native_per_physics_tick' and
           evidence.get('initial',{}).get('sealed') is True and
           progress.get('progress_available') is True)
    row.update(task_score_100=progress.get('task_score_100')if valid else None,
               strict_success=result.get('success')is True and valid,
               native_evidence_valid=bool(valid),original_native_result=result)
    return row


def engineering_robot_diagnostics(author):
    """Read-only post-action diagnostics; unavailable fields never undo an action."""
    import numpy as np
    result={}
    def measured(value):
        if hasattr(value,'detach'):value=value.detach()
        if hasattr(value,'cpu'):value=value.cpu()
        array=np.asarray(value,float)
        if not np.isfinite(array).all():raise ValueError('Nonfinite actual robot state')
        return array.tolist()
    for side in ('left','right'):
        row={};errors={}
        try:row['finger_geometry']=author.finger_geometry(side)
        except Exception as exc:errors['finger_geometry']=type(exc).__name__+': '+str(exc)
        try:
            robot=author.scene.robots[side];ids=author.c.ids[side][0]
            row['arm_joints']=dict(names=[robot.joint_names[i] for i in ids],
                positions_rad=measured(robot.data.joint_pos[0,ids]),
                limits_rad=measured(robot.data.joint_pos_limits[0,ids]))
        except Exception as exc:errors['arm_joints']=type(exc).__name__+': '+str(exc)
        try:
            ids=author.c.ids[side][1]
            row['finger_joints']=dict(names=[robot.joint_names[i] for i in ids],
                positions_m=measured(robot.data.joint_pos[0,ids]),
                velocities_m_s=measured(robot.data.joint_vel[0,ids]))
        except Exception as exc:errors['finger_joints']=type(exc).__name__+': '+str(exc)
        if errors:row['diagnostic_error']=errors
        result[side]=row
    try:
        # Refresh real sensor measurements after the accepted action. This is
        # read-only and cannot change a receipt, controller target or evaluator.
        state,_=author.c.snapshot()
        result['object_grasps']={name:list(body['grasp']) for name,body in state.items()}
        result['contact_forces_n']=[dict(bodies=sorted(pair),force_n=float(force))
            for pair,force in author.c.contact_forces.items()]
        if any(not np.isfinite(row['force_n']) or row['force_n']<0
               for row in result['contact_forces_n']):
            raise ValueError('Invalid measured contact force')
    except Exception as exc:
        result.pop('contact_forces_n',None)
        result['contact_diagnostic_error']=type(exc).__name__+': '+str(exc)
    return result


def engineering_action_plan(left,right,mm,rotation_deg,control,max_subactions):
    """Convert real scalar types exactly; split oversized positive motion only."""
    import math
    import numbers
    values={};requested={}
    for name,value in [('step_mm',mm),('rotation_deg',rotation_deg)]:
        if isinstance(value,bool) or not isinstance(value,numbers.Real):
            raise ValueError('Engineering action requires a real non-boolean scalar: '+name)
        number=float(value)
        if not math.isfinite(number) or number<=0:
            raise ValueError('Engineering action requires a finite positive value: '+name)
        lo,hi=map(float,control[name])
        if not(0<lo<=hi and math.isfinite(hi)):raise ValueError('Invalid public bounds: '+name)
        requested[name]=number;requested[name+'_type']=type(value).__name__
        # Only representation-level roundoff, never a substantive undershoot.
        if number<lo and lo-number<=1e-9:number=lo
        if number>hi and number-hi<=1e-9:number=hi
        if number<lo:raise ValueError('Engineering action below public minimum: '+name)
        values[name]=(number,lo,hi)
    translations={'FWD','BACK','LEFT','RIGHT','UP','DOWN'}
    rotations={'ROTATE_CCW','ROTATE_CW','PITCH_UP','PITCH_DOWN','ROLL_LEFT','ROLL_RIGHT'}
    tokens=[left.removeprefix('MV_'),right.removeprefix('MV_')]
    active={'step_mm':any(t in translations for t in tokens),
            'rotation_deg':any(t in rotations for t in tokens)}
    count=1
    for name,(number,lo,hi) in values.items():
        if number>hi:
            if not active[name]:raise ValueError('Unused parameter exceeds public maximum: '+name)
            count=max(count,math.ceil(number/hi))
    if count>max_subactions:raise RuntimeError('Engineering action budget exhausted before split')
    applied={}
    for name,(number,lo,hi) in values.items():
        value=number/count if active[name]else number
        if not lo<=value<=hi:
            raise ValueError('Simultaneous motion cannot be split within public bounds: '+name)
        applied[name]=float(value)
    plan=[]
    for index in range(count):
        pair=[token if index==0 or t in translations|rotations else 'STILL'
              for token,t in zip((left,right),tokens)]
        plan.append(dict(left=pair[0],right=pair[1],**applied))
    return dict(left=left,right=right,**requested),plan


def persist_engineering_failure_checkpoint(author, room):
    """Read the actual boundary after the last accepted action; never tick."""
    if not getattr(author, '_engineering_stage_checkpoints', False):
        return None
    from .engineering_checkpoint import capture
    before = (author.c.steps, author.c.physics_ticks)
    state = capture(author.c, str(author.stage), context=dict(room=room, after_last_accepted_action=True))
    raw = (json.dumps(state, default=_json, allow_nan=False, separators=(',', ':')) + '\n').encode()
    folder = author.out / 'checkpoints'; folder.mkdir(exist_ok=True)
    path = folder / 'failure-after-last-action.private.json'
    path.write_bytes(raw); path.chmod(0o600)
    if before != (author.c.steps, author.c.physics_ticks):
        raise RuntimeError('Failure checkpoint capture advanced physical state')
    return dict(checkpoint=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                actions=before[0], native_physics_tick=before[1], no_physics_advance=True)


def persist_engineering_checkpoint(author, room):
    """Keep the latest pre-action state and one state per stage transition."""
    if not getattr(author, '_engineering_stage_checkpoints', False):
        return
    from .engineering_checkpoint import capture
    import re
    state = capture(author.c, str(author.stage), context=dict(room=room))
    folder = author.out / 'checkpoints'; folder.mkdir(exist_ok=True)
    raw = (json.dumps(state, default=_json, allow_nan=False, separators=(',', ':')) + '\n').encode()
    latest = folder / 'before-action.latest.private.json'
    temporary = folder / 'before-action.tmp'; temporary.write_bytes(raw)
    temporary.chmod(0o600); temporary.replace(latest)
    # A failed contact can damage the grasp a few actions before the exception.
    # Keep a bounded native-state ring so debug can choose an earlier intact
    # hold without reconstructing qd/drive targets or repeating the prefix.
    recent = folder / 'recent'; recent.mkdir(exist_ok=True)
    ring = recent / ('slot-%02d.private.json' % (author.c.steps % 16))
    ring_tmp = recent / 'slot.tmp'; ring_tmp.write_bytes(raw)
    ring_tmp.chmod(0o600); ring_tmp.replace(ring)
    stage = str(author.stage)
    if stage != getattr(author, '_engineering_last_checkpoint_stage', None):
        index = getattr(author, '_engineering_checkpoint_index', 0) + 1
        slug = re.sub(r'[^a-zA-Z0-9_.-]+', '-', stage)[:70]
        path = folder / ('stage-%04d-%s.private.json' % (index, slug))
        path.write_bytes(raw); path.chmod(0o600)
        author._engineering_checkpoint_index = index
        author._engineering_last_checkpoint_stage = stage
    _write(folder / 'latest.private.json', dict(checkpoint=str(latest),
        sha256=hashlib.sha256(raw).hexdigest(), stage=stage, source_actions=author.c.steps,
        diagnostic_only=True, exact_physx_contact_cache_restored=False,
        recent_checkpoint=str(ring),recent_native_checkpoint_slots=16))


def pooled_author_class(base,pool,room,coordinator=None):
    class PooledEngineeringAuthor(base):
        def engineering_passive_ticks(self,count,guard=None):
            """Bounded gravity/contact diagnostic after a verified single-room restore."""
            if (type(count)is not int or not 1<=count<=250 or coordinator is not None
                    or set(getattr(pool,'controllers',{}))!={room}
                    or room in getattr(pool,'terminal',{})
                    or not getattr(self.c,'_engineering_diagnostic_only',False)
                    or not getattr(self.c,'_engineering_checkpoint_readback_passed',False)
                    or not self.control_report.get('engineering_reference_only')
                    or getattr(self,'_engineering_failure_latched',False)
                    or getattr(self.c,'_engineering_action_in_flight',False)
                    or getattr(self.c,'_public_action_in_flight',False)):
                raise RuntimeError('Passive diagnostic requires an idle verified single-room checkpoint')
            steps=self.c.steps;before=self.c.physics_ticks;shared=pool.physics_ticks
            for _ in range(count):
                if guard:guard()
                pool.tick()
                if self.c.steps!=steps:raise RuntimeError('Passive diagnostic unexpectedly changed public action count')
                if guard:guard()
            receipt=dict(diagnostic_only=True,public_actions_issued=0,requested_physics_ticks=count,
                actual_physics_ticks=self.c.physics_ticks-before,shared_ticks=pool.physics_ticks-shared,
                actions_before=steps,actions_after=self.c.steps,evaluator_labels_written=False)
            with(self.out/'passive-ticks.private.jsonl').open('a')as stream:
                stream.write(json.dumps(receipt)+'\n')
            return receipt

        def note(self,stage):
            # The legacy note method renders twice on the global context.
            # Keep those renders/readbacks inside this room's visibility scope
            # too; action-only isolation cannot protect checkpoint images.
            return pool.render_room(room,passes=1,
                capture=lambda:super(PooledEngineeringAuthor,self).note(stage))

        def act(self,left='STILL',right='STILL',mm=20,rotation_deg=10.):
            if getattr(self,'_engineering_failure_latched',False):
                raise RuntimeError('Engineering failure already latched; further public actions prohibited')
            remaining=self.scene.spec.get('expert_action_budget',1500)-self.c.steps
            requested,plan=engineering_action_plan(left,right,mm,rotation_deg,
                self.scene.embodiment.config['control'],remaining)
            receipts=[]
            for index,command in enumerate(plan):
                persist_engineering_checkpoint(self, room)
                if coordinator is not None:
                    receipt=coordinator.submit(room,command);receipts.append(receipt)
                else:
                    # Engineering routes are serialized, but the native shared
                    # clock still requires an explicit command for every live
                    # room. Record actual idle receipts too; never relax the
                    # production barrier or hide their elapsed physics/actions.
                    controllers=getattr(pool,'controllers',{room:self.c})
                    terminal=getattr(pool,'terminal',{})
                    if room in terminal:raise RuntimeError('Engineering target room is already sealed')
                    commands={other:dict(left='STILL',right='STILL',
                        step_mm=command['step_mm'],rotation_deg=command['rotation_deg'])
                        for other in controllers if other not in terminal}
                    commands[room]=command
                    # Serial engineering references have no consumer for idle
                    # room RGB frames. Preserve all native ticks and idle receipts.
                    from contextlib import nullcontext
                    render_scope=getattr(pool,'engineering_reference_rendering',None)
                    if hasattr(self,'control_report'):
                        self.control_report['engineering_idle_rgb_suppressed']=bool(render_scope is not None and getattr(pool,'render_isolation',False))
                    with render_scope(room) if render_scope is not None else nullcontext():
                        batch=pool.action_batch(commands)
                        receipt=batch[room];receipts.append(receipt)
                        if len(commands)>1:
                            shared=self.out.parents[1]/'shared-barrier-actions.private.jsonl'
                            shared_row=dict(engineering_only=True,active_reference_room=room,
                                commands=commands,receipts=batch)
                            with shared.open('a') as stream:stream.write(json.dumps(shared_row,default=_json)+'\n')
                            shared.chmod(0o600)
                row=dict(stage=self.stage,left=command['left'],right=command['right'],
                         step_mm=command['step_mm'],rotation_deg=command['rotation_deg'],
                         requested_action=requested,subaction_index=index,subaction_count=len(plan),**receipt)
                try:row['tips']={side:self.tip(side).tolist() for side in ('left','right')}
                except Exception as exc:row['diagnostic_error']={'tips':type(exc).__name__+': '+str(exc)}
                row['robot_diagnostics']=engineering_robot_diagnostics(self)
                path=self.out/'demo-actions.private.jsonl'
                with path.open('a') as stream:stream.write(json.dumps(row,default=_json)+'\n')
                path.chmod(0o600)
            if len(receipts)==1:return receipts[0]
            return dict(step_before=receipts[0]['step_before'],step_after=receipts[-1]['step_after'],
                        physics_ticks=sum(r.get('physics_ticks',0)for r in receipts),
                        subaction_receipts=receipts,requested_action=requested)
    return PooledEngineeringAuthor


def classify_result(control,final,errors,capture_complete):
    """Only positive strict native success is automatically classified here."""
    score=final.get('task_score_100')
    valid=final.get('native_evidence_valid') is True and final.get('history_valid') is True
    completed=not errors and capture_complete and valid
    positive=(completed and final.get('strict_success') is True and score==100) if control=='positive' else None
    return dict(control_execution_completed=bool(completed),native_positive_passed=positive,
                negative_condition_observed=None,independent_review_required=True,
                acceptance='positive_native_passed_pending_matrix' if positive else 'pending_independent_review')


def classify_debug_segment(route,errors,capture_complete):
    """A successful local stage remains ineligible as a whole-task positive."""
    passed=bool(not errors and capture_complete and isinstance(route,dict)
                and route.get('segment_passed') is True)
    return dict(native_positive_passed=False,
        acceptance='checkpoint_suffix_diagnostic_only',
        checkpoint_resume_diagnostic_only=True,debug_segment_passed=passed)


def run_controls(pool,controllers,cases,out,*,control,settle_ticks=600,capture_passes=3):
    """Seal every initial world before the first engineering robot action."""
    if control not in CONTROLS:raise ValueError('Explicit engineering control required')
    if control!='positive':
        from .execution_design_reference import reference_capability
        if any(not reference_capability(case['task'],control)['implemented'] for case in cases):
            raise NotImplementedError('Requested task-specific negative public-action route is not implemented')
    if not 1<=settle_ticks<=1000:raise ValueError('Use 1..1000 initial history ticks')
    from .demonstration import Demonstration
    from .execution_design_reference import solve_execution_reference
    from .execution_design_negative_expert import ExecutionDesignNegativeAuthor
    from .execution_design_back25_negative import CAPABILITIES as BACK25_NEGATIVES
    from .execution_design_front13_negative import CAPABILITIES as FRONT13_NEGATIVES
    from .execution_design_front13_grasp_negative import CAPABILITIES as GRASP_NEGATIVES
    from .execution_design_e03_negative import CAPABILITIES as E03_NEGATIVES
    from .execution_design_pose_negative import CAPABILITIES as POSE_NEGATIVES
    from .execution_design_owned_hold_negative import CAPABILITIES as OWNED_HOLD_NEGATIVES
    from .realworld_progress_evidence import initial_diagnostics,seal_initial
    from PIL import Image
    import numpy as np
    out=Path(out);folders={};captures={};initial={};initial_errors={};rows=[]
    started=time.monotonic()
    import os
    coordinator=None
    if os.environ.get('VIC_ENGINEERING_COOPERATIVE_REFERENCES','0')!='0':
        from .execution_design_cooperative import CooperativeReferences,enabled_for
        if enabled_for(controllers,os.environ):coordinator=CooperativeReferences(pool,out)
    try:
        from .engineering_checkpoint_reference import restore_requested, validate_after_settle, retarget_fixture_hold
        resumed = restore_requested(controllers, cases, control)
        # Install capture for all rooms before shared settling/sealing. A later
        # room must not acquire its initial baseline after earlier robot moves.
        for room,c in controllers.items():
            folder=out/room;folder.mkdir(exist_ok=False);folders[room]=folder
            if room in resumed:
                resumed[room]['artifact_folder'] = str(folder)
            _write(folder/'scene-input.private.json',c.scene.spec)
            if c.scene.spec.get('execution_environment_readback'):
                _write(folder/'environment-readback.private.json',c.scene.spec['execution_environment_readback'])
            captures[room]=NativeCapture(c,folder/'native-capture')
        retarget_fixture_hold(pool, controllers, resumed)
        restored_settle = int(next(iter(resumed.values()))['request'].get('settle_ticks', 30)) if resumed else settle_ticks
        if resumed and not 1 <= restored_settle <= 120:
            raise ValueError('Checkpoint readback settling must use 1..120 physics ticks')
        from .engineering_contact_warmup import settle_checkpoint
        contact_warmup=settle_checkpoint(pool,controllers,resumed,restored_settle)
        if contact_warmup is not None:
            for room in resumed:
                _write(folders[room]/'checkpoint-contact-warmup.private.json',contact_warmup)
        for room,c in controllers.items():
            try:
                if room in resumed:
                    initial[room] = dict(room_id=room, can_seal=False,
                        native_evidence_valid=False, source_initial_episode=False,
                        checkpoint_restore_readback=validate_after_settle(c, resumed[room]))
                    c._engineering_checkpoint_readback_passed=True
                    _write(folders[room]/'checkpoint-restoration.private.json', resumed[room]['restore_receipt'])
                    _write(folders[room]/'initial-diagnostics.private.json', initial[room])
                    continue
                initial[room]=initial_diagnostics(c.evaluator,room_id=room)
                _write(folders[room]/'initial-diagnostics.private.json',initial[room])
                seal_initial(c.evaluator)
                _write(folders[room]/'initial-native-score.private.json',c.evaluator.result())
            except Exception as exc:
                initial_errors[room]=type(exc).__name__+': '+str(exc)
        _write(out/'initial-seal-barrier.private.json',dict(
            before_any_action=True,shared_tick=pool.physics_ticks,
            rooms={room:dict(sealed=bool(getattr(c.evaluator,'initial_sealed',getattr(c.evaluator,'progress_initial_sealed',False))),error=initial_errors.get(room)) for room,c in controllers.items()}))
        # Save every room before any reference starts. Capturing later rooms
        # inside run_case would mislabel images taken after another room's
        # physical actions as initial evidence. render_room is render-only;
        # additionally verify the physics/action counters here.
        for room,c in controllers.items():
            folder=folders[room];before=(pool.physics_ticks,c.physics_ticks,c.steps)
            try:
                def capture_initial_rgb():
                    result={};images={}
                    for name in ('head','left_wrist','right_wrist'):
                        camera=c.scene.cameras[name];camera.update(0.,force_recompute=True)
                        rgb=camera.data.output['rgb'][0,:,:,:3].cpu().numpy()
                        if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8:raise ValueError('Invalid initial native RGB: '+name)
                        path=folder/('reference-initial-'+name+'.png');Image.fromarray(rgb).save(path);path.chmod(0o600)
                        result[name]=_artifact(path)
                        images[name]=rgb.copy()
                    from .execution_design_camera_audit import camera_audit
                    audit=camera_audit(c.scene,images)
                    _write(folder/'reference-initial-camera-audit.private.json',audit)
                    if not audit['admission_passed']:raise RuntimeError('Initial camera evidence rejected: '+'; '.join(audit['errors']))
                    return result
                from .execution_design_render_retry import capture as capture_engineering_rgb
                initial_rgb=capture_engineering_rgb(pool,room,c,passes=capture_passes,callback=capture_initial_rgb,
                    log_path=folder/'reference-initial-render-attempts.private.json')
                if before!=(pool.physics_ticks,c.physics_ticks,c.steps):
                    raise RuntimeError('Initial render-only evidence advanced physics/actions')
                _write(folder/'reference-initial-media.private.json',dict(before_any_action=True,
                    initial_sealed=room not in initial_errors and room not in resumed,shared_tick=before[0],
                    native_physics_tick=before[1],actions=before[2],artifacts=initial_rgb))
            except Exception as exc:
                initial_errors[room]='Initial media capture: '+type(exc).__name__+': '+str(exc)
        def run_case(case):
            room=case['episode_id'];c=controllers[room];folder=folders[room]
            author=None;policy=None;errors=[];route=None;artifacts={};final={};capture_complete=False;failure_boundary=None
            try:
                if room in initial_errors:raise RuntimeError(initial_errors[room])
                reference_dir=folder/'engineering-reference';reference_dir.mkdir()
                author=pooled_author_class(Demonstration,pool,room,coordinator)(c,reference_dir,video_prefix='engineering')
                media=dict(engineering_reference_only=True,eligible_as_model_demo=False,
                    local_rule_demo=False,execution_control=control)
                if hasattr(author,'control_report'):author.control_report.update(media)
                author._engineering_stage_checkpoints = (
                    os.environ.get('VIC_ENGINEERING_STAGE_CHECKPOINTS') == '1' and
                    1 <= int(case['task'][1:]) <= 50)
                if room in resumed:
                    author._engineering_resume_checkpoint = resumed[room]['checkpoint']
                    author._engineering_resume_context = resumed[room]['request']
                _write(reference_dir/'engineering-reference-only.private.json',media)
                if control=='positive':route=solve_execution_reference(author)
                elif control in E03_NEGATIVES.get(case['task'],()):
                    from .execution_design_e03_negative import E03NegativeAuthor
                    policy=E03NegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif control in GRASP_NEGATIVES.get(case['task'],()):
                    from .execution_design_front13_grasp_negative import GraspNegativeAuthor
                    policy=GraspNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif control in FRONT13_NEGATIVES.get(case['task'],()):
                    from .execution_design_front13_negative import Front13NegativeAuthor
                    policy=Front13NegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif control in POSE_NEGATIVES.get(case['task'],()):
                    from .execution_design_pose_negative import PoseNegativeAuthor
                    policy=PoseNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif control in OWNED_HOLD_NEGATIVES.get(case['task'],()):
                    from .execution_design_owned_hold_negative import OwnedHoldNegativeAuthor
                    policy=OwnedHoldNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif case['task'] in ('E23','E24'):
                    if case['task']=='E23':
                        from .execution_design_e23_reference import solve_e23_negative_reference as solve_negative
                    else:
                        from .execution_design_e24_reference import solve_e24_negative_reference as solve_negative
                    route=solve_negative(author,control)
                    _write(folder/'perturbation-plan.private.json',route['perturbation'])
                elif control in BACK25_NEGATIVES.get(case['task'],()):
                    from .execution_design_back25_negative import Back25NegativeAuthor
                    policy=Back25NegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif case['task'] in ('E28','E29','E40','E42','E43','E44','E45','E46','E50'):
                    from .execution_design_event_negative import EventNegativeAuthor
                    policy=EventNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif case['task']=='E26':
                    from .execution_design_bell_negative import BellNegativeAuthor
                    policy=BellNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                elif case['task']=='E30':
                    from .execution_design_drawer_negative import DrawerNegativeAuthor
                    policy=DrawerNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    route=policy.solve_negative()
                else:
                    policy=ExecutionDesignNegativeAuthor(author,control)
                    _write(folder/'perturbation-plan.private.json',policy.perturbation)
                    policy.local_stage();policy.package_stage();policy.deliver()
                    route=dict(task=policy.task,variant=policy.variant,control=control,
                        actions=policy.c.steps-policy.start,operations=policy.operations,
                        perturbation=policy.perturbation,execution_finished=True,
                        negative_condition_observed=None,native_validation_required=True)
                _write(folder/'reference-result.private.json',route)
            except Exception as exc:
                errors.append(dict(phase='control',error=type(exc).__name__+': '+str(exc)))
                # Fail this room at the first propagated control error. Final
                # evidence is read-only; sibling rooms retain their own barrier.
                if author is not None:author._engineering_failure_latched=True
                failure_boundary=dict(room=room,stage=getattr(author,'stage',None),
                    actions=int(c.steps),controller_tick=int(c.physics_ticks),
                    shared_tick=int(pool.physics_ticks),error=errors[-1],observed_unix=time.time())
                if author is not None:
                    try:failure_boundary['actual_boundary_checkpoint']=persist_engineering_failure_checkpoint(author,room)
                    except Exception as checkpoint_error:
                        failure_boundary['actual_boundary_checkpoint_error']=type(checkpoint_error).__name__+': '+str(checkpoint_error)
                try:_write(folder/'failure-boundary.private.json',failure_boundary)
                except Exception as log_error:errors.append(dict(phase='failure_boundary_log',error=str(log_error)))
            finally:
                # Preserve final observations even after a failed route. A
                # not_released case is captured before any cleanup operation.
                try:
                    state,contacts=c.snapshot();final=normalized_native_result(c.evaluator.result())
                    _write(folder/'reference-final-state.private.json',dict(state=state,contacts=contacts,
                        contact_forces=[dict(bodies=sorted(pair),force=value) for pair,value in c.contact_forces.items()],robot_feedback=c.public_feedback(),
                        native_physics_tick=c.physics_ticks,actions=c.steps))
                    _write(folder/'reference-final-score.private.json',final)
                    _write(folder/'reference-contact-diagnostics.private.json',c.scene.contact_diagnostics())
                    def capture_rgb():
                        result={};images={}
                        for name in ('head','left_wrist','right_wrist'):
                            camera=c.scene.cameras[name];camera.update(0.,force_recompute=True)
                            rgb=camera.data.output['rgb'][0,:,:,:3].cpu().numpy()
                            if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8:raise ValueError('Invalid native RGB: '+name)
                            path=folder/('reference-final-'+name+'.png');Image.fromarray(rgb).save(path);path.chmod(0o600)
                            result[name]=_artifact(path)
                            images[name]=rgb.copy()
                        from .execution_design_camera_audit import camera_audit
                        audit=camera_audit(c.scene,images)
                        _write(folder/'reference-final-camera-audit.private.json',audit)
                        if not audit['admission_passed']:raise RuntimeError('Final camera evidence rejected: '+'; '.join(audit['errors']))
                        return result
                    from .execution_design_render_retry import capture as capture_engineering_rgb
                    artifacts=capture_engineering_rgb(pool,room,c,passes=capture_passes,callback=capture_rgb,
                        log_path=folder/'reference-final-render-attempts.private.json')
                    capture_complete=len(artifacts)==3
                except Exception as exc:
                    errors.append(dict(phase='final_observation',error=type(exc).__name__+': '+str(exc)))
                try:
                    captures[room].close(error=errors or None,
                        final_rgb_path=folder/'reference-final-head.png',
                        actions_path=author.out/'demo-actions.private.jsonl' if author else None)
                except Exception as exc:
                    capture_complete=False;errors.append(dict(phase='capture_close',error=type(exc).__name__+': '+str(exc)))
                if author is not None:
                    try:author.close()
                    except Exception as exc:errors.append(dict(phase='video_close',error=type(exc).__name__+': '+str(exc)))
                if failure_boundary is not None:
                    after=dict(actions=int(c.steps),controller_tick=int(c.physics_ticks),shared_tick=int(pool.physics_ticks))
                    unchanged=all(after[key]==failure_boundary[key] for key in after)
                    failure_boundary.update(final_observation_boundary=after,
                        no_post_failure_physics_or_actions=unchanged,
                        post_failure_public_actions=after['actions']-failure_boundary['actions'],
                        physics_world_frozen=False,sibling_rooms_not_interrupted=True)
                    if not unchanged:errors.append(dict(phase='failure_boundary',error='Final observation advanced failed room physics/actions'))
                    try:_write(folder/'failure-boundary.private.json',failure_boundary)
                    except Exception as log_error:errors.append(dict(phase='failure_boundary_log',error=str(log_error)))
                try:
                    terminal=pool.seal(room)
                    _write(folder/'native-terminal.private.json',terminal)
                except Exception as exc:errors.append(dict(phase='native_seal',error=type(exc).__name__+': '+str(exc)))
                perturbation=policy.perturbation if policy is not None else (route.get('perturbation') if case['task'] in ('E23','E24') and isinstance(route,dict) else None)
                if perturbation is not None:_write(folder/'perturbation-plan.private.json',perturbation)
                classification=classify_result(control,final,errors,capture_complete)
                if room in resumed:
                    classification.update(classify_debug_segment(route,errors,capture_complete))
                row=dict(**case,control=control,execution_design=c.scene.spec['execution_design'],
                    actual_observations=dict(native_score=final,final_rgb=artifacts,
                        snapshot=str(folder/'reference-final-state.private.json'),
                        raw_contacts=str(folder/'native-capture'/'contacts.private.jsonl.gz')),
                    perturbation=perturbation,
                    error=errors or None,steps=c.steps,**classification)
                _write(folder/'execution-control.private.json',row);rows.append(row)
        if coordinator is None:
            for case in cases:run_case(case)
            scheduling=dict(mode='serial_reference_shared_barrier')
        else:
            # Native two-room render-only diagnostics show one/two passes read
            # stale visibility; twelve passes clear head and both wrist views.
            # Physics and recorder cadence remain one per shared physical tick.
            with pool.engineering_recording_render_passes(12):
                scheduling=coordinator.run({case['episode_id']:lambda case=case:run_case(case) for case in cases})
            scheduling['isolated_recording_render_passes']=12
        ordered={case['episode_id']:index for index,case in enumerate(cases)}
        rows.sort(key=lambda row:ordered[row['episode_id']])
        _write(out/'engineering-scheduling.private.json',scheduling)
        report=dict(schema='videoicl-execution-native-controls-v1',scheduling=scheduling,control=control,rooms=rows,
            room_count=len(rows),all_initial_sealed_before_actions=not initial_errors,
            all_controls_completed=all(r['control_execution_completed'] for r in rows),
            positive_native_passed=all(r['native_positive_passed'] is True for r in rows) if control=='positive' else None,
            negative_condition_observed=None,release_ready=False,model_launch_enabled=False,
            engineering_reference_only=True,eligible_as_model_demo=False,
            acceptance='pending_independent_review',wall_seconds=time.monotonic()-started,
            runner_source_sha256=hashlib.sha256((Path(__file__).parent.parent/'scripts/probe_realworld_room_pool.py').read_bytes()).hexdigest(),
            runtime_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))})
        if resumed:
            report.update(checkpoint_resume_diagnostic_only=True,
                all_debug_segments_passed=all(r.get('debug_segment_passed') is True for r in rows))
        _write(out/'execution-controls.private.json',report)
        return report
    finally:
        for room,cap in captures.items():
            if not cap.closed:
                try:cap.close(error='Engineering runner interrupted before final room capture')
                except Exception as exc:_write(folders[room]/'capture-close-error.private.json',dict(error=type(exc).__name__+': '+str(exc)))
