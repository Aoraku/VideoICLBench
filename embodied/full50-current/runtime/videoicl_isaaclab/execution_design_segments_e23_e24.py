"""Explicit local engineering segments; no reset, score, or history writes."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def _point(value, name):
    result=np.asarray(value,float)
    if result.shape!=(3,) or not np.isfinite(result).all():
        raise ToolExecutionError('Finite three-coordinate '+name+' required')
    return result


def _scope(author, task):
    spec=author.scene.spec
    if (spec.get('id')!=task or
            spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102' or
            not getattr(author,'control_report',{}).get('engineering_reference_only')):
        raise ToolExecutionError('Explicit v3 independent engineering segment required')


def _air_optimizer_seed(q,limits,recovery=False,reserve=.05):
    if not .02<=reserve<=.05:raise ToolExecutionError('Reviewed20-to50mrad E23 reserve required')
    lower=limits[:,0]+reserve;upper=limits[:,1]-reserve
    margin=float(np.min(np.minimum(q-limits[:,0],limits[:,1]-q)))
    if recovery:
        if margin<.02:raise ToolExecutionError('E23 recovery starts inside actual20mrad joint reserve')
        # Only the numerical search seed is projected. The actual measured q
        # stays intact and remains the start of the full swept mesh screen.
        seed=np.clip(q,lower+1e-8,upper-1e-8)
    else:
        if np.any(q<=lower)or np.any(q>=upper):raise ToolExecutionError('E23 air handoff lacks original joint margin')
        seed=q.copy()
    return lower,upper,seed,margin


def _air_check(policy,side,*,position=None,rotation=None,payload=None,target=None,
               allow_target_finger_contact=False,recovery_start=False):
    """Read current meshes and reject an unsafe next public increment."""
    from scipy.optimize import least_squares
    from .execution_design_e24_transit import capture_model,screen_joint_segment
    from .execution_design_e24_collision import actual_object_parts
    from .execution_design_e24_lid import table_bounds
    from .execution_design_drawer_ik_probe import forward_at_delta
    from .author_orientation import _axis_angle
    model,_=capture_model(policy,side);other='left'if side=='right'else'right'
    idle,_=capture_model(policy,other);parts=actual_object_parts(policy)
    prefix=lambda name:'object:'+name+':'
    environment=[r for r in parts if not any(r['name'].startswith(prefix(n))for n in (payload,target)if n)]
    low,high=table_bounds(policy);environment.append(dict(name='table',lo=low,hi=high))
    environment.extend(dict(name=other+':'+c['name'],points=c['points'],
                            lo=c['points'].min(0),hi=c['points'].max(0))for c in idle['clouds'])
    if payload:
        policy.require_held(dict(actor=payload),side)
        model['clouds']=model['clouds']+[dict(name='held:'+r['name'],influence=7,points=r['points'])
            for r in parts if r['name'].startswith(prefix(payload))]
    q=model['q'];candidate=q
    def screen(m,start,end,obstacles,margin):
        if getattr(policy,'_engineering_coarse_free_space',False):
            try:return screen_joint_segment(m,start,end,obstacles,margin=margin,maximum_motion_bound=.005)
            except ToolExecutionError:pass
        return screen_joint_segment(m,start,end,obstacles,margin=margin)
    if position is not None or rotation is not None:
        desired_position=model['position']if position is None else np.asarray(position,float)
        desired_rotation=model['rotation']if rotation is None else np.asarray(rotation,float)
        reserve=getattr(policy,'_engineering_air_joint_reserve',.05)
        lower,upper,seed,start_margin=_air_optimizer_seed(q,model['limits'],recovery_start,reserve)
        def residual(value):
            p,r=forward_at_delta(model['position'],model['rotation'],model['jacobian'],value-q)
            axis,angle=_axis_angle(desired_rotation@r.T)
            return np.r_[10*(p-desired_position),axis*angle,.005*(value-q)]
        fit=least_squares(residual,seed,bounds=(lower,upper),max_nfev=180,
                          ftol=1e-9,xtol=1e-9,gtol=1e-9)
        error=residual(fit.x);distance=float(np.linalg.norm(fit.x-q))
        increment_limit=.35 if rotation is not None else getattr(policy,'_engineering_translation_joint_increment',.15)
        if (np.linalg.norm(error[:3])/10>=.001 or np.linalg.norm(error[3:6])>=math.radians(1.5)
                or distance>=increment_limit):
            raise ToolExecutionError('E23 air handoff next public increment lacks nearby IK')
        candidate=fit.x
        endpoint_margin=float(np.min(np.minimum(candidate-model['limits'][:,0],model['limits'][:,1]-candidate)))
        if recovery_start and endpoint_margin<=.05:
            raise ToolExecutionError('E23 recovery endpoint lacks original50mrad joint reserve')
    if getattr(policy,'_engineering_air_joint_reserve',None)is not None and not recovery_start:
        _air_optimizer_seed(q,model['limits'],reserve=policy._engineering_air_joint_reserve)
    environment_check=screen(model,q,candidate,environment,margin=.005)
    checks=dict(environment=environment_check,measured_joint_positions_rad=q.tolist())
    if position is not None or rotation is not None:
        checks['kinematic']=dict(actual_start_margin_rad=start_margin,candidate_endpoint_margin_rad=endpoint_margin,
                                 recovery_start_allowed=bool(recovery_start),measured_q_unchanged=True)
    if target:
        near=[r for r in parts if r['name'].startswith(prefix(target))]
        # Finger/object contact is intentional during grasp/release. The palm
        # and arm stay separated from the unchanged source cup throughout.
        palm=dict(model,clouds=[c for c in model['clouds']if 'finger'not in c['name']and not c['name'].startswith('held:')])
        checks['target_palm']=screen(palm,q,candidate,near,margin=.002)
        if not allow_target_finger_contact:
            fingers=dict(model,clouds=[c for c in model['clouds']if 'finger'in c['name']])
            checks['target_open_fingers']=screen(fingers,q,candidate,near,margin=.001)
    return checks


def _air_feedback(policy,side):
    feedback=policy.c.action_feedback().get('control_feedback',{}).get(side,{})
    if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names') or
            feedback.get('consecutive_ik_refusals',0)>0):
        raise ToolExecutionError('E23 air handoff public controller rejected the increment')


def _air_move(policy,side,point,*,held_guards=(),guards=(),material=None,tolerance=.001,maximum_step=.002,**geometry):
    point=_point(point,'air handoff waypoint')
    for _ in range(700):
        for ref,hand in held_guards:policy.require_held(ref,hand)
        for guard in guards:guard()
        current=policy.tip(side)if material is None else policy.point(material)
        error=point-current
        if np.max(np.abs(error))<=tolerance:return
        axis=int(np.argmax(np.abs(error)));distance=min(maximum_step,abs(float(error[axis])))
        movement=np.zeros(3);movement[axis]=math.copysign(distance,error[axis])
        before_check=_air_check(policy,side,position=policy.tip(side)+movement,**geometry)
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        before=policy.tip(side).copy();policy.act(side,token,mm=distance*1000)
        _air_feedback(policy,side)
        for ref,hand in held_guards:policy.require_held(ref,hand)
        for guard in guards:guard()
        after_check=_air_check(policy,side,**geometry)
        if getattr(policy,'_engineering_translation_joint_increment',None)is not None:
            before_q=np.asarray(before_check['measured_joint_positions_rad']);after_q=np.asarray(after_check['measured_joint_positions_rad'])
            if np.linalg.norm(after_q-before_q)>=.35:raise ToolExecutionError('Actual public translation left original0.35rad joint branch')
        achieved=float((policy.tip(side)-before)[axis])*math.copysign(1.,error[axis])
        if achieved<.0001:raise ToolExecutionError('E23 air handoff public translation failed to advance')
    raise ToolExecutionError('E23 air handoff waypoint exhausted')


def _air_rotate_empty(policy,side,target_rotation,*,held_guards=(),tolerance_degrees=2.,maximum_degrees=5.,**geometry):
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import _axis_rotation
    station=policy.tip(side).copy();target=np.asarray(target_rotation,float)
    tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(220):
        for ref,hand in held_guards:policy.require_held(ref,hand)
        state,_=policy.snapshot()
        if any(body['grasp'][0 if side=='left'else 1]for body in state.values()):
            raise ToolExecutionError('E23 air handoff empty wrist unexpectedly holds an object')
        current=np.asarray(policy.a.tcp_rotation_task(side));axis,error=_axis_angle(target@current.T)
        if error<math.radians(tolerance_degrees):return
        component=int(np.argmax(np.abs(axis)));sign=float(np.sign(axis[component]));chosen=None
        for degrees in ((10.,5.,2.5,1.25,.625,.5)if maximum_degrees>=10 else(5.,2.5,1.25,.625,.5)):
            if degrees<policy.min_deg:continue
            rotation=_axis_rotation(np.eye(3)[component],sign*math.radians(degrees))@current
            try:_air_check(policy,side,rotation=rotation,**geometry)
            except ToolExecutionError:continue
            chosen=degrees;break
        if chosen is None:raise ToolExecutionError('E23 air handoff has no safe nearby empty wrist increment')
        policy.act(side,tokens[component][int(sign<0)],degrees=chosen);_air_feedback(policy,side)
        for ref,hand in held_guards:policy.require_held(ref,hand)
        _air_check(policy,side,**geometry)
        after=np.asarray(policy.a.tcp_rotation_task(side));advanced=_axis_angle(after@current.T)[1]
        if advanced<math.radians(.01):raise ToolExecutionError('E23 air handoff public rotation failed to advance')
        if np.max(np.abs(policy.tip(side)-station))>.001:
            _air_move(policy,side,station,held_guards=held_guards,**geometry)
    raise ToolExecutionError('E23 air handoff empty wrist exhausted')


def _air_finger_speed(policy,side):
    robot=policy.a.scene.robots[side];indices,names=robot.find_joints('panda_finger_joint[1-2]')
    if list(names)!=['panda_finger_joint1','panda_finger_joint2']:
        raise ToolExecutionError('Actual E23 receiver finger joints required')
    value=robot.data.joint_vel[0,indices]
    speed=np.asarray(value.detach().cpu().numpy(),float)
    if speed.shape!=(2,)or not np.isfinite(speed).all():raise ToolExecutionError('Actual E23 finger velocity unavailable')
    return float(np.max(np.abs(speed)))


def _air_handoff_red(policy,parameters):
    from .realworld_tool_expert import _axis_rotation
    name=policy.identity['red'];ref=dict(actor=name)
    expected=_point(parameters.get('expected_right_tip_task_m',[-.236606746912,-.351350069046,1.122655448914]),'right checkpoint TCP')
    center=_point(parameters.get('cup_station_task_m',[-.20,0,1.05]),'cup handoff station')
    staging=_point(parameters.get('left_pre_rotation_station_task_m',[-.25,.30,1.10]),'left rotation station')
    grasp_local=np.array([0.,0.,-.0305])
    policy.require_held(ref,'right');state,_=policy.snapshot()
    if any(body['grasp'][0]for body in state.values()):raise ToolExecutionError('E23 receiver must start empty')
    if np.max(np.abs(policy.tip('right')-expected))>.003:raise ToolExecutionError('E23 source differs from selected 199-step checkpoint')
    if policy.objects[name].get('source_asset',{}).get('sha256')!='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b':
        raise ToolExecutionError('Original E23 hollow cup mesh required')
    right=((ref,'right'),)
    policy.stage('local-E23-right-carry-to-air-handoff')
    _air_move(policy,'right',center,held_guards=right,material=dict(actor=name,local=[0,0,0]),payload=name)
    policy.stage('local-E23-left-open-air-staging')
    policy.act('left','RELEASE');policy.require_held(ref,'right')
    _air_move(policy,'left',staging,held_guards=right,target=name)
    return _air_complete_handoff(policy)


def _air_complete_handoff(policy):
    """Continue from the current empty receiver; no source-arm prefix replay."""
    from .realworld_tool_expert import _axis_rotation
    name=policy.identity['red'];ref=dict(actor=name);right=((ref,'right'),)
    policy.require_held(ref,'right');state,_=policy.snapshot()
    if any(body['grasp'][0]for body in state.values()):
        raise ToolExecutionError('E23 handoff continuation needs the actual empty receiver')
    if policy.objects[name].get('source_asset',{}).get('sha256')!='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b':
        raise ToolExecutionError('Original E23 hollow cup mesh required for continuation')
    grasp_local=np.array([0.,0.,-.0305])
    policy.stage('local-E23-left-empty-orientation')
    cup_rotation=np.asarray(policy.snapshot()[0][name]['mat'])
    base=np.array([[0.,-1,0],[-1,0,0],[0,0,-1.]])
    target_rotation=cup_rotation@_axis_rotation([1,0,0],-math.pi/2)@base
    _air_rotate_empty(policy,'left',target_rotation,held_guards=right,target=name)
    policy.stage('local-E23-left-open-air-approach')
    _air_move(policy,'left',policy.point(dict(actor=name,local=(grasp_local+[0,.16,0]).tolist())),held_guards=right,target=name)
    policy.stage('local-E23-left-whole-cup-low-grasp')
    _air_move(policy,'left',policy.point(dict(actor=name,local=grasp_local.tolist())),held_guards=right,target=name)
    policy.act('left','GRASP');policy.require_held(ref,'right');policy.require_held(ref,'left')
    return _air_release_after_receiver_grip(policy)


def _air_release_after_receiver_grip(policy,*,single_real_observation=False,retreat_up=.08,retreat_y=.10):
    """Old-hand release follows an actual bilateral receiver observation."""
    name=policy.identity['red'];ref=dict(actor=name)
    settled=0
    for _ in range(6):
        policy.require_held(ref,'right');policy.require_held(ref,'left')
        _air_check(policy,'left',target=name,allow_target_finger_contact=True)
        settled=settled+1 if single_real_observation or _air_finger_speed(policy,'left')<.002 else 0
        if settled>=(1 if single_real_observation else 3):break
        policy.act()
    else:raise ToolExecutionError('E23 receiver bilateral grip did not settle before old-hand release')
    policy.stage('local-E23-real-two-hand-grip-before-release')
    policy.require_held(ref,'right');policy.require_held(ref,'left')
    policy.act('right','RELEASE')
    for _ in range(2):policy.require_held(ref,'left');policy.act()
    policy.require_held(ref,'left')
    if policy.held(ref,'right'):raise ToolExecutionError('E23 original hand did not release physically')
    left=((ref,'left'),)
    policy.stage('local-E23-right-release-retreat')
    speed=dict(tolerance=.006,maximum_step=.006)if single_real_observation else{}
    _air_move(policy,'right',policy.tip('right')+[0,0,retreat_up],held_guards=left,target=name,allow_target_finger_contact=True,**speed)
    _air_move(policy,'right',policy.tip('right')+[0,-retreat_y,0],held_guards=left,target=name,allow_target_finger_contact=True,**speed)
    policy.require_held(ref,'left');_air_check(policy,'left',payload=name)
    body=policy.snapshot()[0][name];tip=policy.tip('left');tcp_rotation=np.asarray(policy.a.tcp_rotation_task('left'))
    return dict(segment='e23_air_handoff_red',local_completed=True,actions=policy.c.steps-policy.start,
        operations=policy.operations,held_actor=name,side='left',
        actual_cup_origin_in_tcp_frame_m=(tcp_rotation.T@(np.asarray(body['pos'])-tip)).tolist(),
        actual_cup_rotation_in_tcp_frame=(tcp_rotation.T@np.asarray(body['mat'])).tolist())


def _air_resume_handoff(policy,parameters):
    from .realworld_tool_expert import _axis_rotation
    name=policy.identity['red'];ref=dict(actor=name)
    policy.require_held(ref,'right');state,_=policy.snapshot()
    if any(body['grasp'][0]for body in state.values()):raise ToolExecutionError('E23 recovery receiver must remain empty')
    if policy.objects[name].get('source_asset',{}).get('sha256')!='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b':
        raise ToolExecutionError('Original E23 hollow cup mesh required for recovery')
    current=np.asarray(policy.a.tcp_rotation_task('right'))
    # One full public ten-degree step leaves room for the following carry.
    # A two-degree recovery cleared50mrad only briefly before the next
    # measured translations returned joint7 to the same boundary.
    degrees=10.
    target=_axis_rotation([0,0,1],math.radians(degrees))@current
    policy.stage('local-E23-one-CCW-recovery-inside-joint-limit')
    before=_air_check(policy,'right',rotation=target,payload=name,recovery_start=True)
    policy.act('right','ROTATE_CCW',degrees=degrees)
    _air_feedback(policy,'right');policy.require_held(ref,'right')
    # Re-enter the original50mrad gate immediately. No alternative physical
    # action or retry is attempted if this single recovery was refused.
    after=_air_check(policy,'right',position=policy.tip('right'),
                     rotation=policy.a.tcp_rotation_task('right'),payload=name)
    policy.operations.append(dict(stage='local-E23-single-recovery-readback',
        public_token='ROTATE_CCW',degrees=degrees,before=before,after=after))
    resumed=dict(parameters,expected_right_tip_task_m=policy.tip('right').tolist())
    if parameters.get('handoff_at_current_cup_center')is True:
        # The restored cup is already in the handoff workspace. Use its real
        # post-recovery centre instead of winding the wrist to remove a small
        # station error. The remaining empty-hand/grasp checks are unchanged.
        resumed['cup_station_task_m']=policy.point(dict(actor=name,local=[0,0,0])).tolist()
        policy.operations.append(dict(stage='local-E23-use-current-real-cup-station',
            cup_station_task_m=resumed['cup_station_task_m'],remaining_right_carry_skipped=True))
    result=_air_handoff_red(policy,resumed)
    result['segment']='e23_resume_air_handoff';result['single_public_recovery_performed']=True
    return result


def _rotate_held_at_station(policy, name, side, target):
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import _axis_rotation
    from .execution_design_drawer_ik_probe import inspect
    from .execution_design_e23_clearance import verify_rotation_clearance,restore_rotation_station
    tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    ref=dict(actor=name);stalled=0
    for _ in range(160):
        restore_rotation_station(policy,name,side)
        verify_rotation_clearance(policy,name,side,'local-segment-before-rotation')
        policy.require_held(ref,side)
        current=np.asarray(policy.snapshot()[0][name]['mat'])
        axis,error=_axis_angle(target@current.T)
        if error<math.radians(6 if getattr(policy,'_engineering_air_joint_reserve',None)is not None else 4):return
        component=int(np.argmax(np.abs(axis)));direction=float(np.sign(axis[component]))
        degrees=min(10. if getattr(policy,'_engineering_air_joint_reserve',None)is not None else 5.,max(policy.min_deg,abs(math.degrees(error*axis[component]))))
        delta=_axis_rotation(np.eye(3)[component],direction*math.radians(degrees))
        tcp=np.asarray(policy.a.tcp_rotation_task(side))
        rows=inspect(policy.a,policy.c,side,[dict(position=policy.tip(side).tolist(),rotation=(delta@tcp).tolist())])
        if len(rows)!=1:raise ToolExecutionError('Missing local E23 rotation IK diagnostic')
        row=rows[0]
        if not (row.get('kinematically_reachable') and row.get('position_error_m',1)<.001 and
                row.get('orientation_error_rad',1)<math.radians(1.5) and
                row.get('minimum_joint_margin_rad',0)>getattr(policy,'_engineering_air_joint_reserve',.05) and row.get('joint_distance_rad',9)<.35):
            raise ToolExecutionError('Local E23 rotation lacks original nearby IK margin')
        policy.act(side,tokens[component][int(direction<0)],degrees=degrees)
        policy.require_held(ref,side)
        verify_rotation_clearance(policy,name,side,'local-segment-after-rotation')
        if getattr(policy,'_engineering_air_joint_reserve',None)is not None:
            after=np.asarray(policy.snapshot()[0][name]['mat'])
            progress=error-_axis_angle(target@after.T)[1]
            stalled=stalled+1 if progress<math.radians(.1)else 0
            if stalled>=3:raise ToolExecutionError('Actual E23 held rotation failed to advance three times')
    raise ToolExecutionError('Local E23 held rotation exhausted')


def run_segment(author, segment, parameters):
    if segment in('e24_side_pinch_and_cover_from310','e24_down_pitch_and_cover_from3','e24_down_two_mm_and_cover_from6'):
        from .execution_design_e24_side_pinch import run_segment as side_pinch
        return side_pinch(author,segment,parameters)
    if segment in('e23_high_handoff_from256','e23_finish_high_handoff_from132','e23_grasp_current_lowwall_from12'):
        from .execution_design_e23_high_handoff import run_segment as high_handoff
        return high_handoff(author,segment,parameters)
    if segment=='e24_verify_clear_layout_restore':
        _scope(author,'E24')
        if parameters!={}:raise ValueError('No E24 layout verification overrides permitted')
        from .execution_design_e24_layout import verify_native_restore
        return dict(verify_native_restore(author),segment=segment)
    """Run one caller-selected segment against an already restored native state.

    Restoring actors, velocities, controller buffers and debug-only histories
    belongs to the caller. This entrypoint reads actual state and public acts.
    """
    if not isinstance(parameters,dict):raise ToolExecutionError('Explicit segment parameters required')
    if segment=='e23_complete_handoff_from149':
        _scope(author,'E23');spec=author.scene.spec
        checkpoint=getattr(author,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
        if (parameters!={}or spec.get('variant')!='A'or spec.get('seed')!=4201
                or spec.get('execution_design',{}).get('condition')!='I'
                or checkpoint.get('diagnostic_only')is not True
                or source.get('steps')!=149 or source.get('physics_ticks')!=14902
                or not getattr(author.c,'_engineering_diagnostic_only',False)
                or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
            raise ToolExecutionError('Registered E23 A149 admitted native checkpoint required')
        from .realworld_structural_expert import StructuralAuthor
        policy=StructuralAuthor(author);name=policy.identity['red'];state,contacts=policy.snapshot()
        policy.require_held(dict(actor=name),'right')
        if (any(body['grasp'][0]or(other!=name and body['grasp'][1])for other,body in state.items())
                or not all(frozenset((name,'right_finger'+str(i)))in contacts for i in(1,2))):
            raise ToolExecutionError('E23 A149 requires actual right bilateral red grip and empty left hand')
        _air_check(policy,'right',payload=name)
        result=_air_complete_handoff(policy);result['segment']=segment
        return result
    if segment=='e23_air_handoff_red':
        _scope(author,'E23')
        from .realworld_structural_expert import StructuralAuthor
        return _air_handoff_red(StructuralAuthor(author),parameters)
    if segment in ('e23_resume_air_handoff','e23_handoff_at_current_station'):
        _scope(author,'E23')
        from .realworld_structural_expert import StructuralAuthor
        options=dict(parameters,handoff_at_current_cup_center=True)if segment=='e23_handoff_at_current_station'else parameters
        result=_air_resume_handoff(StructuralAuthor(author),options)
        result['segment']=segment
        return result
    if segment in('e24_approach_settled_lid1_and_push','e24_continue_settled_contact1_and_push'):
        _scope(author,'E24')
        from .execution_design_e24_reference import MeasuredE24Author
        from .execution_design_e24_lid import approach_settled_lid1_and_push
        options=dict(source_boundary=(1,101))if segment=='e24_continue_settled_contact1_and_push'else{}
        result=approach_settled_lid1_and_push(MeasuredE24Author(author),parameters,**options)
        result['segment']=segment
        return result
    if segment=='e24_push_contact_short':
        _scope(author,'E24')
        from .execution_design_e24_reference import MeasuredE24Author
        from .execution_design_e24_lid import push_contact_short
        result=push_contact_short(MeasuredE24Author(author))
        result['segment']=segment
        return result
    if segment in ('e24_continue_lid_from_transit','e24_push_from_contact_band'):
        _scope(author,'E24')
        migration=getattr(author,'_engineering_resume_checkpoint',{}).get('context',{}).get('e24_layout_migration')
        if migration is not None:
            from .execution_design_e24_layout import verify_native_restore
            verify_native_restore(author)
        from .execution_design_e24_reference import MeasuredE24Author
        from .execution_design_e24_lid import continue_lid_from_transit,push_from_contact_band
        policy=MeasuredE24Author(author)
        expected=parameters.get('expected_left_tip_task_m')
        if expected is not None and np.max(np.abs(policy.tip('left')-_point(expected,'expected TCP')))>.003:
            raise ToolExecutionError('E24 continuation TCP differs from selected native checkpoint')
        function=push_from_contact_band if segment=='e24_push_from_contact_band'else continue_lid_from_transit
        ref,side=function(policy)
        policy.require_held(ref,side)
        return dict(segment=segment,local_completed=True,actions=policy.c.steps-policy.start,
                    operations=policy.operations,held_actor=ref['actor'],side=side)
    if segment=='e24_pickup_lid_overhang':
        _scope(author,'E24')
        from .execution_design_e24_reference import MeasuredE24Author
        from .execution_design_e24_lid import pickup_lid_overhang
        policy=MeasuredE24Author(author)
        state,_=policy.snapshot()
        if any(any(body['grasp'])for body in state.values()):
            raise ToolExecutionError('E24 lid segment requires both actual hands empty')
        expected=parameters.get('expected_left_tip_task_m')
        if expected is not None and np.max(np.abs(policy.tip('left')-_point(expected,'expected TCP')))>.003:
            raise ToolExecutionError('E24 restored actual TCP differs from selected checkpoint')
        ref,side=pickup_lid_overhang(policy)
        policy.require_held(ref,side)
        return dict(segment=segment,local_completed=True,actions=policy.c.steps-policy.start,
                    operations=policy.operations,held_actor=ref['actor'],side=side)
    if segment=='e23_hang_held_red':
        _scope(author,'E23')
        from .realworld_structural_expert import StructuralAuthor
        from .realworld_mechanism_evidence import _rotation
        policy=StructuralAuthor(author);name=policy.identity['red']
        side=parameters.get('side')
        if side not in ('left','right'):raise ToolExecutionError('Explicit actual held-cup side required')
        branch_id=parameters.get('branch_id')
        if branch_id not in policy.s['branches']:raise ToolExecutionError('Explicit source branch identity required')
        rotation=_rotation(parameters.get('cup_rotation_task'))
        station=_point(parameters.get('expected_station_tip_task_m'),'actual rotation station')
        waypoints=parameters.get('mouth_waypoints_task')
        if not isinstance(waypoints,list) or not waypoints:
            raise ToolExecutionError('Explicit reviewed E23 mouth waypoints required')
        checked=[]
        for row in waypoints:
            if not isinstance(row,dict) or not isinstance(row.get('stage'),str):
                raise ToolExecutionError('Named E23 waypoint required')
            checked.append(dict(stage=row['stage'],point=_point(row.get('point'),'mouth waypoint'),
                                allow_support_contact=row.get('allow_support_contact') is True))
        ref=dict(actor=name)
        policy.require_held(ref,side)
        if np.max(np.abs(policy.tip(side)-station))>.003:
            raise ToolExecutionError('E23 restored actual TCP differs from selected rotation station')
        policy._e23_rotation_station=(name,side,np.asarray(policy.tip(side)).copy())
        policy.stage('local-E23-held-red-rotation')
        _rotate_held_at_station(policy,name,side,rotation)
        branch=policy.s['branches'][branch_id];support=branch['ref'].get('actor',branch['ref'].get('contact_body'))
        control=dict(actor=name,local=policy.s['cups'][name]['rim_local'])
        for row in checked:
            def guard():
                policy.require_held(ref,side)
                if not row['allow_support_contact'] and policy.contact(name,support):
                    raise ToolExecutionError('Premature E23 cup/tree contact in local segment')
            policy.stage('local-E23-'+row['stage'])
            policy.move_point(side,control,row['point'],guard)
        policy.stage('local-E23-release-red')
        policy.release(ref,side)
        retreat=_point(parameters.get('post_release_tcp_offset_task',[0,0,.04]),'post-release retreat')
        policy.move(side,policy.tip(side)+retreat);policy.wait(3)
        if not policy.contact(name,support):raise ToolExecutionError('Local released cup lacks actual branch support')
        return dict(segment=segment,local_completed=True,actions=policy.c.steps-policy.start,
                    operations=policy.operations,released_actor=name,branch_id=branch_id)
    raise ToolExecutionError('Unknown independent E23/E24 segment '+str(segment))
