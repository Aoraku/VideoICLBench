"""E15B214 empty-hand recovery and measured three-mm approach; debug only."""
import math
from types import SimpleNamespace
import numpy as np
from scipy.optimize import least_squares
from .author_orientation import _axis_angle
from .realworld_tool_expert import _axis_rotation


def _margin(q,limits):
    return float(np.min(np.minimum(q-limits[:,0],limits[:,1]-q)))


def _seed(q,limits,recovery):
    margin=_margin(q,limits)
    if not np.isfinite(np.r_[q,limits.ravel()]).all()or margin<=0:
        raise RuntimeError('E15 recovery requires actual measured joints strictly inside hard limits')
    lo=limits[:,0]+.0201;hi=limits[:,1]-.0201
    if not recovery and (np.any(q<=lo)or np.any(q>=hi)):
        raise RuntimeError('E15 actual approach joints lack original20mrad margin')
    # This projection changes only the numerical optimizer seed. The actual
    # q remains the start of the complete hard-limit and collision sweep.
    return lo,hi,np.clip(q,lo+1e-8,hi-1e-8)if recovery else q.copy()


def _capture(policy):
    from .execution_design_e24_transit import capture_model
    from .execution_design_e24_collision import actual_object_parts
    from .execution_design_e24_lid import table_bounds
    model,_=capture_model(policy,'right');idle,_=capture_model(policy,'left')
    obstacles=actual_object_parts(policy);lo,hi=table_bounds(policy)
    obstacles.append(dict(name='table',lo=lo,hi=hi))
    for cloud in idle['clouds']:
        points=cloud['points'];obstacles.append(dict(name='left:'+cloud['name'],points=points,
            lo=points.min(0),hi=points.max(0)))
    return model,obstacles


def _preflight(model,obstacles,position,rotation,*,recovery=False):
    from .execution_design_drawer_ik_probe import forward_at_delta
    from .execution_design_e24_transit import screen_joint_segment
    q=model['q'];limits=model['limits'];lo,hi,seed=_seed(q,limits,recovery)
    def residual(value):
        point,frame=forward_at_delta(model['position'],model['rotation'],model['jacobian'],value-q)
        axis,angle=_axis_angle(rotation@frame.T)
        return np.r_[10*(point-position),axis*angle,.01*(value-q)]
    fit=least_squares(residual,seed,bounds=(lo,hi),max_nfev=180,ftol=1e-9,xtol=1e-9,gtol=1e-9)
    error=residual(fit.x);distance=float(np.linalg.norm(fit.x-q));margin=_margin(fit.x,limits)
    if (np.linalg.norm(error[:3])/10>=.001 or np.linalg.norm(error[3:6])>=math.radians(1.5)
            or distance>=.35 or margin<=.02):
        raise RuntimeError('E15 next public increment lacks original IK precision/margin/increment')
    # Linear joint interpolation stays in the convex hard-limit box. It must
    # also pass the unchanged full-mesh continuous five-mm clearance screen.
    hard_margin=min(_margin(q,limits),margin)
    if hard_margin<=0:raise RuntimeError('E15 recovery joint path crosses an actual hard limit')
    screen=screen_joint_segment(model,q,fit.x,obstacles,margin=.005)
    return dict(actual_start_margin_rad=_margin(q,limits),candidate_endpoint_margin_rad=margin,
        candidate_joints_rad=fit.x.tolist(),
        joint_increment_rad=distance,minimum_hard_limit_margin_over_path_rad=hard_margin,
        position_error_m=float(np.linalg.norm(error[:3])/10),
        orientation_error_rad=float(np.linalg.norm(error[3:6])),swept_screen=screen,
        recovery_start_exception=bool(recovery),actual_q_unchanged=True)


def _readback(policy,*,require_margin=True):
    from .execution_design_e24_transit import screen_joint_segment
    feedback=policy.c.action_feedback().get('control_feedback',{}).get('right',{})
    if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names')
            or feedback.get('consecutive_ik_refusals',0)>0):
        raise RuntimeError('E15 actual public controller refused the increment')
    model,obstacles=_capture(policy);margin=_margin(model['q'],model['limits'])
    if margin<=(.02 if require_margin else 0):
        raise RuntimeError('E15 actual public action lacks original measured joint margin')
    screen_joint_segment(model,model['q'],model['q'],obstacles,margin=.005)
    return model,obstacles


def _xy_targets(start,goal,rotation):
    count=max(1,math.ceil(float(np.linalg.norm(goal-start))/.003))
    return [dict(position=(start+(goal-start)*i/count).tolist(),rotation=rotation.tolist())
            for i in range(1,count+1)]


def _small_wrist_step(policy,guard):
    guard();model,obstacles=_readback(policy)
    chosen=_axis_rotation([0,0,1],math.radians(2.))@model['rotation']
    receipt=_preflight(model,obstacles,model['position'],chosen)
    policy.a.act('STILL','ROTATE_CCW',rotation_deg=2.)
    guard();after,obstacles=_readback(policy)
    axis,angle=_axis_angle(after['rotation']@model['rotation'].T)
    _,error=_axis_angle(chosen@after['rotation'].T)
    if (float(axis[2]*angle)<.001 or error>math.radians(1.5)
            or np.linalg.norm(after['position']-model['position'])>.001
            or np.linalg.norm(after['q']-model['q'])>=.35
            or _margin(after['q'],after['limits'])<_margin(model['q'],model['limits'])+.003):
        raise RuntimeError('E15 actual two-degree wrist step did not recover original nearby reserve/pose')
    receipt.update(operation='actual_public_two_degree_wrist_reserve',public_ccw_degrees=2.,
        actual_post_margin_rad=_margin(after['q'],after['limits']),
        actual_tip_task_m=after['position'].tolist())
    return after,obstacles,receipt


def _follow_xy(policy,goal,rotation,guard,*,maintain_wrist_reserve=False):
    receipts=[];wrist_steps=0
    for _ in range(200):
        guard();model,obstacles=_capture(policy);error=goal-model['position']
        if np.linalg.norm(error[:2])<=.001 and abs(error[2])<=.004:return receipts
        if maintain_wrist_reserve and _margin(model['q'],model['limits'])<.040:
            if wrist_steps>=12:raise RuntimeError('E15 bounded empty-wrist reserve steps exhausted')
            actual,_,receipt=_small_wrist_step(policy,guard);wrist_steps+=1
            rotation=actual['rotation'].copy()
            from .execution_design_e15_path import solve_path
            remaining=solve_path(dict(actual,rotation_task=rotation),_xy_targets(actual['position'],goal,rotation))
            if not remaining or not all(row['kinematically_reachable']for row in remaining):
                raise RuntimeError('E15 actual two-degree branch lacks original remaining XY endpoint gates')
            receipt['remaining_original_endpoint_gate_count']=len(remaining);receipts.append(receipt)
            continue
        axis=2 if abs(error[2])>.004 else int(np.argmax(np.abs(error[:2])))
        distance=min(.003,abs(float(error[axis])));move=np.zeros(3)
        move[axis]=math.copysign(distance,error[axis])
        receipt=_preflight(model,obstacles,model['position']+move,rotation)
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        before=model['position'].copy();policy.a.act('STILL',token,distance*1000.)
        guard();after,_=_readback(policy)
        if np.linalg.norm(after['q']-model['q'])>=.35:
            raise RuntimeError('E15 actual approach increment left original nearby joint branch')
        if float((after['position']-before)[axis])*math.copysign(1.,error[axis])<.0001:
            raise RuntimeError('E15 first public approach increment failed to advance')
        receipt.update(public_token=token,requested_mm=distance*1000.,
            actual_position_task_m=after['position'].tolist(),actual_joint_margin_rad=_margin(after['q'],after['limits']))
        receipts.append(receipt)
    raise RuntimeError('E15 bounded actual-q approach exhausted')


def run_segment(author,segment,parameters):
    if segment not in('e15_b_recover214_and_approach_red','e15_b_continue_recovered1_to_red','e15_b_continue11_with_small_wrist_steps')or parameters!={}:
        raise ValueError('Explicit E15B214 empty recovery/approach entry with no overrides required')
    from .execution_design_e15_wrist import _scope
    _scope(author);spec=author.scene.spec;design=spec['execution_design']
    checkpoint=getattr(author,'_engineering_resume_checkpoint',{})
    continuing=segment=='e15_b_continue_recovered1_to_red'
    small_steps=segment=='e15_b_continue11_with_small_wrist_steps'
    boundary=(11,1102)if small_steps else(1,102)if continuing else(214,None)
    source=checkpoint.get('source',{})
    if (spec.get('variant')!='B'or spec.get('seed')!=4201 or design.get('condition')!='I'
            or checkpoint.get('diagnostic_only')is not True or source.get('steps')!=boundary[0]
            or((continuing or small_steps)and(source.get('physics_ticks')!=boundary[1]
                or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)))):
        raise ValueError('Pinned E15B/I/4201 native214 diagnostic boundary required')
    objects={obj['id']:obj for obj in spec['objects']};red=objects['red_t']
    if red.get('source_asset',{}).get('sha256')!='98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493':
        raise ValueError('Original E15 red T source geometry required')
    if getattr(author,'carried_payload',None)is not None:
        raise RuntimeError('E15 recovery starts with real empty hands')
    initial,pairs=author.c.snapshot();saved={name:(np.asarray(body['pos']).copy(),np.asarray(body['mat']).copy())for name,body in initial.items()}
    def guard():
        state,contacts=author.c.snapshot()
        for name,(position,frame)in saved.items():
            body=state[name]
            if (any(body['grasp'])or frozenset((name,'table'))not in contacts
                    or np.linalg.norm(np.asarray(body['pos'])-position)>.002
                    or np.linalg.norm(np.asarray(body['mat'])-frame)>.02):
                raise RuntimeError('E15 source T/empty-hand invariant changed during local approach')
    guard();policy=SimpleNamespace(a=author,c=author.c,spec=spec,objects=objects,
        tip=author.tip,snapshot=author.c.snapshot)
    before=author.c.steps;operations=[];model,obstacles=_capture(policy)
    if small_steps:
        author.stage='local-E15-native11-small-public-wrist-reserve'
        actual,obstacles,receipt=_small_wrist_step(policy,guard)
        operations.append(receipt)
    elif continuing:
        actual,obstacles=_readback(policy)
        operations.append(dict(operation='continue_from_measured_native_recovery_boundary',
            source_actions=1,source_physics_ticks=102,measured_joint_margin_rad=_margin(actual['q'],actual['limits']),
            previous_native_refusal_not_reclassified=True))
    else:
        chosen=_axis_rotation([0,0,1],math.radians(10.))@model['rotation']
        receipt=_preflight(model,obstacles,model['position'],chosen,recovery=True)
        author.stage='local-E15B214-one-inward-public-CCW10'
        author.act('STILL','ROTATE_CCW',rotation_deg=10.)
        guard();actual,obstacles=_readback(policy)
        if np.linalg.norm(actual['q']-model['q'])>=.35:
            raise RuntimeError('E15 actual recovery left original nearby joint branch')
        operations.append(dict(operation='single_actual_inward_recovery',public_ccw_degrees=10.,preflight=receipt,
            measured_post_margin_rad=_margin(actual['q'],actual['limits'])))
    body=author.c.snapshot()[0]['red_t'];pickup=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(red.get('grasp_point_local',[0,0,0]))
    goal=np.r_[pickup[:2],actual['position'][2]];rotation=actual['rotation'].copy()
    from .execution_design_e15_path import solve_path
    from .execution_design_e24_transit import screen_joint_segment
    targets=_xy_targets(actual['position'],goal,rotation)
    measured=dict(actual,rotation_task=rotation)
    plan=solve_path(measured,targets)
    if len(plan)!=len(targets)or not all(row['kinematically_reachable']for row in plan):
        raise RuntimeError('E15 actual post-recovery three-mm XY path fails original endpoint gates')
    previous=actual['q']
    for row in plan:
        candidate=np.asarray(row['candidate_joints_rad'])
        screen_joint_segment(actual,previous,candidate,obstacles,margin=.005);previous=candidate
    author.stage='local-E15B214-actual-q-three-mm-XY-approach'
    receipts=_follow_xy(policy,goal,rotation,guard,maintain_wrist_reserve=small_steps)
    guard();final,_=_readback(policy)
    operations.append(dict(operation='actual_q_three_mm_XY_approach',nominal_dense_points=len(plan),
        public_steps=receipts,goal_task_m=goal.tolist(),actual_tip_task_m=final['position'].tolist()))
    return dict(local_completed=True,actions=author.c.steps-before,operations=operations,
        actual_tip_task_m=final['position'].tolist(),actual_joint_margin_rad=_margin(final['q'],final['limits']),
        original_red_grasp_XY_task_m=pickup[:2].tolist(),object_grasped_or_task_completed=False)
