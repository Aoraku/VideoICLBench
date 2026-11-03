"""Private E18 acquire/three-millimetre pull segment; no full-task scoring."""
import math
import numpy as np
from .realworld_mechanism_expert import MechanismExecutionError


def _grip_observation(worker,side,*,require_grip=True):
    role='drawer';robot=worker.a.scene.robots[side]
    indices,names=robot.find_joints('panda_finger_joint[1-2]')
    if list(names)!=['panda_finger_joint1','panda_finger_joint2']:
        raise MechanismExecutionError('Actual E18 finger joint identity required')
    def measured(value):
        if hasattr(value,'detach'):value=value.detach()
        if hasattr(value,'cpu'):value=value.cpu()
        result=np.asarray(value,float)[0,indices]
        if result.shape!=(2,)or not np.isfinite(result).all():
            raise MechanismExecutionError('Invalid actual E18 finger measurement')
        return result
    opening=measured(robot.data.joint_pos);speed=measured(robot.data.joint_vel)
    bilateral=worker.touching(role,side,both=True)
    body=worker.roles[role]['contact_body'];forces=[]
    for i in (1,2):
        force=worker.c.contact_forces.get(frozenset((body,f'{side}_finger{i}')))
        if not isinstance(force,(int,float))or not math.isfinite(force)or force<0:
            raise MechanismExecutionError('E18 short pull lacks valid measured finger contact force')
        forces.append(float(force))
    minimum=.0003 if worker.a.scene.spec.get('e18_support_layout')else .002
    valid=bool(bilateral and not np.any(opening<minimum)and min(forces)>.001)
    if require_grip and min(forces)<=.001:
        raise MechanismExecutionError('E18 short pull lacks original measured two-finger contact force')
    if require_grip and not valid:
        raise MechanismExecutionError('E18 short pull lost actual bilateral handle grip')
    return dict(step=worker.c.steps,side=side,bilateral_contact=bool(bilateral),grip_present=valid,
        opening_m=opening.tolist(),finger_velocity_m_s=speed.tolist(),contact_forces_n=forces)


def run_segment(author,segment,parameters):
    if segment not in ('e18_acquire_and_short_pull','e18_continue_held_short_pull','e18_hold166_then_three_short_pulls','e18_follow166_then_two_short_pulls','e18_zfollow2_then_two_2mm_pulls','e18_zfollow4_before_two_2mm_pulls','e18_regrasp2_deeper_then_two_pulls','e18_finish_closing3_then_two_pulls','e18_continue_original_open4'):
        raise ValueError('Unknown E18 local segment')
    if not isinstance(parameters,dict):raise ValueError('Explicit E18 local parameters required')
    from .execution_design import REVISION_V3
    from .execution_design_e18_support import VERSION,LIFT_M,SOURCE_SHA
    spec=author.scene.spec;layout=spec.get('e18_support_layout',{})
    if (spec.get('id')!='E18' or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or not getattr(author,'control_report',{}).get('engineering_reference_only')):
        raise ValueError('Explicit v3 E18 engineering segment required')
    if (layout.get('version')!=VERSION or layout.get('source_cabinet_sha256')!=SOURCE_SHA
            or not isinstance(layout.get('lift_m'),(int,float))
            or not math.isclose(layout['lift_m'],LIFT_M,rel_tol=0,abs_tol=1e-12)):
        raise ValueError('Original E18 source cabinet and explicit35mm support layout required')
    from .execution_design_e18_reference import E18MeasuredAuthor
    continuing=segment!='e18_acquire_and_short_pull'
    worker=E18MeasuredAuthor(author,allow_existing_e18_drawer=True)if continuing else E18MeasuredAuthor(author)
    worker._engineering_single_handle_observation=True
    initial=worker.displacement('drawer')
    if continuing:
        side=parameters.get('side','left')
        if side not in ('left','right'):raise ValueError('Actual selected E18 handle hand required')
    else:side=worker.acquire('drawer')
    if segment=='e18_regrasp2_deeper_then_two_pulls':
        from .execution_design_e18_regrasp import run
        return dict(run(worker,parameters),segment=segment)
    if segment=='e18_finish_closing3_then_two_pulls':
        from .execution_design_e18_regrasp import finish_closing
        return dict(finish_closing(worker,parameters),segment=segment)
    if segment=='e18_continue_original_open4':
        from .execution_design_e18_opening import run
        return dict(run(worker,parameters),segment=segment)
    if segment in ('e18_zfollow2_then_two_2mm_pulls','e18_zfollow4_before_two_2mm_pulls'):
        checkpoint=getattr(author,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
        repeat_z=segment=='e18_zfollow4_before_two_2mm_pulls'
        boundary=(4,402)if repeat_z else(2,202)
        if (parameters!={}or spec.get('variant')!='A'or spec.get('seed')!=4201
                or spec.get('execution_design',{}).get('condition')!='I'
                or checkpoint.get('diagnostic_only')is not True
                or(source.get('steps'),source.get('physics_ticks'))!=boundary
                or not getattr(worker.c,'_engineering_diagnostic_only',False)
                or not getattr(worker.c,'_engineering_checkpoint_readback_passed',False)):
            raise ValueError('Admitted E18 A/I4201 exact native pad-follow boundary required')
        worker.stage('local-E18-one-vertical-pad-follow-from-native'+str(boundary[0]))
        z_follow=None if repeat_z else worker.follow_drawer_pad_z_once('drawer',side);pulls=[]
        def issue(token,mm=1.):
            if worker.c.steps-worker.start_steps>=6:
                raise MechanismExecutionError('E18 vertical-follow short segment exhausted six public actions')
            worker.act(side,token,mm=mm)
        for index in range(2):
            if repeat_z:
                if worker.c.steps-worker.start_steps>=6:
                    raise MechanismExecutionError('E18 vertical-follow short segment exhausted six public actions')
                z_follow=worker.follow_drawer_pad_z_once('drawer',side)
            worker.stage('local-E18-one-GRASP-and-two-mm-pull-'+str(index+1))
            issue('GRASP');hold=worker._public_pull_observation('drawer',side,1)
            worker._require_public_pull_grip(hold,side)
            before=worker.displacement('drawer');axis=worker.axis('drawer');component=int(np.argmax(np.abs(axis)))
            if abs(float(axis[component]))<.95:
                raise MechanismExecutionError('E18 reduced short pull is not a public translation axis')
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(axis[component]<0)]
            issue(token,mm=2.);after_readback=worker.record_drawer_public_pull('drawer',side)
            worker._require_public_pull_grip(after_readback,side);grip=_grip_observation(worker,side)
            after=worker.displacement('drawer');increase=float(after-before)
            if increase<.0005:
                raise MechanismExecutionError('E18 actual two-mm drawer pull increase below0.5mm')
            pulls.append(dict(index=index+1,z_follow=z_follow,hold=hold,readback=after_readback,grip=grip,
                displacement_before_m=before,displacement_after_m=after,displacement_increase_m=increase))
        return dict(segment=segment,local_completed=True,actions=worker.c.steps-worker.start_steps,
            operations=worker.operations,z_follow=z_follow,pulls=pulls,maximum_public_actions=6,
            full_drawer_open_completed=False,original_full_open_target_m=worker.motion['drawer']['open_distance'])
    if segment in ('e18_hold166_then_three_short_pulls','e18_follow166_then_two_short_pulls'):
        checkpoint=getattr(author,'_engineering_resume_checkpoint',{})
        if checkpoint.get('source',{}).get('steps')!=166:
            raise ValueError('Original E18 native166 held drawer boundary required')
        following=segment=='e18_follow166_then_two_short_pulls'
        if following:
            # Engineering calibration from the actual full-source162 grip,
            # reconstructed with0.199um agreement to the native TCP. These are
            # reference offsets only; no actual pose, joint or contact is set.
            worker._e18_pull_reference={('drawer',side):dict(axial_m=.007781968128777326,
                lateral_m=.0003404816092280285,source_action=162,engineering_calibration=True)}
        pulls=[]
        for index in range(2 if following else 3):
            worker.stage('local-E18-one-GRASP-before-short-pull-'+str(index+1))
            hold=worker.prepare_drawer_public_pull('drawer',side)
            before=worker.displacement('drawer');axis=worker.axis('drawer')
            component=int(np.argmax(np.abs(axis)))
            if abs(float(axis[component]))<.95:
                raise MechanismExecutionError('E18 short pull axis is not aligned with public translation axes')
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(axis[component]<0)]
            worker.act(side,token,mm=3.)
            feedback=worker.c.action_feedback().get('control_feedback',{}).get(side,{})
            if (feedback.get('status')=='blocked'or feedback.get('joint_limit_names')
                    or feedback.get('consecutive_ik_refusals',0)>0):
                raise MechanismExecutionError('E18 actual public short pull controller rejected the action')
            after_readback=worker.record_drawer_public_pull('drawer',side)
            grip=_grip_observation(worker,side)
            after=worker.displacement('drawer');increase=float(after-before)
            if increase<.0005:
                raise MechanismExecutionError('E18 actual repeated drawer pull increase below0.5mm')
            pulls.append(dict(index=index+1,hold=hold,readback=after_readback,grip=grip,
                displacement_before_m=before,displacement_after_m=after,displacement_increase_m=increase))
        return dict(segment=segment,local_completed=True,actions=worker.c.steps-worker.start_steps,
            operations=worker.operations,pulls=pulls,maximum_public_actions=6,
            full_drawer_open_completed=False,original_full_open_target_m=worker.motion['drawer']['open_distance'])
    worker.stage('local-E18-single-real-handle-observation')
    observations=[_grip_observation(worker,side)]
    before=worker.displacement('drawer');axis=worker.axis('drawer')
    component=int(np.argmax(np.abs(axis)))
    if abs(float(axis[component]))<.95:
        raise MechanismExecutionError('E18 short pull axis is not aligned with public translation axes')
    token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(axis[component]<0)]
    worker.stage('local-E18-three-millimetre-short-pull')
    worker.act(side,token,mm=3.)
    feedback=worker.c.action_feedback().get('control_feedback',{}).get(side,{})
    if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names')
            or feedback.get('consecutive_ik_refusals',0)>0):
        raise MechanismExecutionError('E18 public short pull controller rejected the action')
    post=_grip_observation(worker,side,require_grip=False);after=worker.displacement('drawer')
    increase=float(after-before)
    if increase<.0005:
        raise MechanismExecutionError('E18 actual drawer increase below0.5mm after public3mm short pull')
    return dict(segment=segment,local_completed=True,actions=worker.c.steps-worker.start_steps,
        operations=worker.operations,side=side,source_displacement_before_acquire_m=initial,
        grip_gate='single_bilateral_nonempty_observation',grip_observations=observations,
        requested_public_pull_mm=3.,public_pull_token=token,
        measured_displacement_before_pull_m=before,measured_displacement_after_pull_m=after,
        measured_displacement_increase_m=increase,post_pull_grip=post)
