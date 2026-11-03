"""Measured public red-T turn/release after the real fourteen-action lift."""
import math
from types import SimpleNamespace
import numpy as np
from .execution_design_segments_e15_recover import _capture,_margin,_preflight
from .execution_design_e24_transit import screen_joint_segment
from .realworld_tool_expert import _axis_rotation
from .realworld_semantic_checks import POSITION_TOLERANCE_M,ANGLE_TOLERANCE_DEG


def positive_remaining(goal,yaw):
    delta=math.atan2(math.sin(goal-yaw),math.cos(goal-yaw))
    return delta if delta>=-math.radians(3)else delta+2*math.pi


def run_segment(a,segment,parameters):
    from .execution_design_e15_wrist import _scope
    from .execution_design_segments_e15 import _goal
    _scope(a);spec=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{})
    if (segment!='e15_b_rotate_place_red_from14'or parameters!={}or spec.get('variant')!='B'
            or spec.get('seed')!=4201 or spec['execution_design'].get('condition')!='I'
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=(14,1403)
            or cp.get('diagnostic_only')is not True
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted E15B native real-held14/1403 boundary required')
    objects={o['id']:o for o in spec['objects']};obj=objects['red_t']
    if obj.get('source_asset',{}).get('sha256')!='98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493':
        raise ValueError('Original source T geometry required')
    goal=_goal(spec,'red_t','red_t_target');zone=next(z for z in spec['zones']if z['id']==goal['target'])
    p=SimpleNamespace(a=a,c=a.c,spec=spec,objects=objects,tip=a.tip,snapshot=a.c.snapshot)
    initial=a.c.snapshot()[0];blue_pos=np.asarray(initial['blue_t']['pos']).copy();blue_mat=np.asarray(initial['blue_t']['mat']).copy()
    start=a.c.steps;operations=[];carrying=True
    def guard():
        state,contacts=a.c.snapshot();blue=state['blue_t'];red=state['red_t']
        if(any(blue['grasp'])or frozenset(('blue_t','table'))not in contacts
                or np.linalg.norm(np.asarray(blue['pos'])-blue_pos)>.002
                or np.linalg.norm(np.asarray(blue['mat'])-blue_mat)>.02):
            raise RuntimeError('Original blue T changed during held red suffix')
        if carrying and(not red['grasp'][1]or red['grasp'][0]
                or not all(frozenset(('red_t','right_finger'+str(i)))in contacts for i in(1,2))):
            raise RuntimeError('Actual bilateral red T grip required throughout public turn')
        return state,contacts
    def capture():
        guard();m,obstacles=_capture(p)
        if _margin(m['q'],m['limits'])<=.02:raise RuntimeError('E15 held red lacks original20mrad measured reserve')
        feedback=a.c.action_feedback().get('control_feedback',{}).get('right',{})
        if(feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0):
            raise RuntimeError('E15 held red public controller refused')
        payload=[o for o in obstacles if o['name'].startswith('object:red_t:')]
        if not payload:raise RuntimeError('Actual enabled red T collision parts required')
        environment=[o for o in obstacles if o['name']!='table'and not o['name'].startswith('object:red_t:')]
        table=[o for o in obstacles if o['name']=='table'];assert len(table)==1
        if carrying:m=dict(m,clouds=m['clouds']+[dict(name='held:'+o['name'],influence=7,points=o['points'])for o in payload])
        return m,environment,table,payload
    def issue(token,delta=None,degrees=None):
        if a.c.steps-start>=220:raise RuntimeError('Bounded E15 held-red suffix exhausted')
        m,environment,table,_=capture();position=m['position']if delta is None else m['position']+delta
        rotation=m['rotation']if degrees is None else _axis_rotation([0,0,1],math.radians(degrees))@m['rotation']
        receipt=_preflight(m,environment,position,rotation)
        robot=dict(m,clouds=[c for c in m['clouds']if not c['name'].startswith('held:')])
        screen_joint_segment(robot,m['q'],np.asarray(receipt['candidate_joints_rad']),table,margin=1e-6)
        if degrees is None:a.act('STILL',token,float(np.linalg.norm(delta)*1000))
        else:a.act('STILL',token,rotation_deg=degrees)
        after,environment,table,payload=capture()
        screen_joint_segment(after,after['q'],after['q'],environment,margin=.005)
        robot=dict(after,clouds=[c for c in after['clouds']if not c['name'].startswith('held:')])
        screen_joint_segment(robot,after['q'],after['q'],table,margin=1e-6)
        if min(float(o['points'][:,2].min())for o in payload)<float(table[0]['hi'][2])-1e-5:
            raise RuntimeError('Actual held red T crossed original tabletop')
        if np.linalg.norm(after['q']-m['q'])>=.35:raise RuntimeError('E15 held turn left original nearby joint branch')
        receipt.update(public_token=token,degrees=degrees,actual_margin_rad=_margin(after['q'],after['limits']))
        operations.append(receipt)
    guard();a.carried_payload=('red_t','right');a.stage='local-E15-actual-held-red-CCW-turn'
    for _ in range(110):
        state,_=guard();r=np.asarray(state['red_t']['mat']);yaw=math.atan2(r[1,0],r[0,0]);remaining=positive_remaining(goal['yaw'],yaw)
        if abs(remaining)<=math.radians(3):break
        if remaining>math.radians(200):raise RuntimeError('E15 selected positive held turn exceeds reviewed half-turn')
        issue('ROTATE_CCW',degrees=min(4.,max(.5,math.degrees(remaining))))
        after=guard()[0]['red_t']['mat'];advanced=math.atan2(math.sin(math.atan2(after[1][0],after[0][0])-yaw),math.cos(math.atan2(after[1][0],after[0][0])-yaw))
        if advanced<math.radians(.01):raise RuntimeError('Actual held red CCW rotation failed to advance')
    else:raise RuntimeError('Actual held red turn exhausted')
    a.stage='local-E15-held-red-original-position-return'
    for _ in range(40):
        state,_=guard();error=np.asarray(zone['xy'])-np.asarray(state['red_t']['pos'])[:2]
        if np.max(np.abs(error))<=.002:break
        axis=int(np.argmax(np.abs(error)));delta=np.zeros(3);delta[axis]=math.copysign(min(.003,abs(float(error[axis]))),error[axis])
        issue((('FWD','BACK'),('LEFT','RIGHT'))[axis][int(delta[axis]<0)],delta=delta)
    else:raise RuntimeError('E15 held red original XY return exhausted')
    a.stage='local-E15-held-red-supported-release'
    floor=float(zone.get('surface_z',.8));before=a.c.snapshot()[0]['red_t']['pos'][2]
    for _ in range(30):
        _,_,_,payload=capture();gap=min(float(o['points'][:,2].min())for o in payload)-floor
        if gap<=.005:break
        issue('DOWN',delta=np.array([0.,0.,-min(.002,gap-.004)]))
    else:raise RuntimeError('E15 red supported release height unreachable')
    guard();a.carried_payload=None;carrying=False;a.release_generated('right')
    for _ in range(10):issue('UP',delta=np.array([0.,0.,.002]))
    state,contacts=guard();body=state['red_t'];yaw=math.atan2(body['mat'][1][0],body['mat'][0][0]);angle=math.atan2(math.sin(yaw-goal['yaw']),math.cos(yaw-goal['yaw']))
    if(any(body['grasp'])or frozenset(('red_t','table'))not in contacts
            or np.linalg.norm(np.asarray(body['pos'])[:2]-zone['xy'])>POSITION_TOLERANCE_M
            or abs(angle)>math.radians(ANGLE_TOLERANCE_DEG)):
        raise RuntimeError('Released red T failed unchanged original position/yaw/table goal')
    return dict(local_completed=True,segment=segment,actions=a.c.steps-start,operations=operations,
        actual_red_position_task_m=body['pos'],actual_original_goal_yaw_error_rad=angle,
        real_released_table_support=True,blue_remaining=True,full_task_completed=False)
