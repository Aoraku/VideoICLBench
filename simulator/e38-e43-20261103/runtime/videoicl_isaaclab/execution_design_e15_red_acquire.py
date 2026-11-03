"""Real red-T grasp and short lift after the native118 hover continuation."""
from types import SimpleNamespace
import math
import numpy as np
from .execution_design_segments_e15_recover import _capture,_margin,_preflight
from .execution_design_e24_transit import screen_joint_segment
from .realworld_tool_expert import _axis_rotation


def run_segment(a,segment,parameters):
    from .execution_design_e15_wrist import _scope
    _scope(a);spec=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{})
    near_grasp=segment=='e15_b_close_lift_from56'
    boundary=(56,5603)if near_grasp else(118,11802)
    if (segment not in('e15_b_grasp_red_hover118','e15_b_close_lift_from56')or parameters!={}or spec.get('variant')!='B'
            or spec.get('seed')!=4201 or spec['execution_design'].get('condition')!='I'
            or cp.get('diagnostic_only')is not True
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=boundary
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted E15B/I4201 actual hover118/11802 required')
    objects={obj['id']:obj for obj in spec['objects']};red=objects['red_t']
    if red.get('source_asset',{}).get('sha256')!='98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493':
        raise ValueError('Original source red T required')
    state,contacts=a.c.snapshot();blue_position=np.asarray(state['blue_t']['pos']).copy()
    blue_rotation=np.asarray(state['blue_t']['mat']).copy();initial_red_z=float(state['red_t']['pos'][2])
    if any(any(row['grasp'])for row in state.values()):raise RuntimeError('E15 hover acquisition starts actually empty')
    p=SimpleNamespace(a=a,c=a.c,spec=spec,objects=objects,tip=a.tip,snapshot=a.c.snapshot)
    start=a.c.steps;receipts=[];wrist_steps=0;carrying=False
    def guard():
        actual,pairs=a.c.snapshot();blue=actual['blue_t']
        if (any(blue['grasp'])or frozenset(('blue_t','table'))not in pairs
                or np.linalg.norm(np.asarray(blue['pos'])-blue_position)>.002
                or np.linalg.norm(np.asarray(blue['mat'])-blue_rotation)>.02):
            raise RuntimeError('Protected original blue T changed during red acquisition')
        if carrying:
            if not actual['red_t']['grasp'][1]or not all(frozenset(('red_t','right_finger'+str(i)))in pairs for i in(1,2)):
                raise RuntimeError('E15 actual bilateral red grip lost during short lift')
    def model():
        guard();m,obstacles=_capture(p)
        feedback=a.c.action_feedback().get('control_feedback',{}).get('right',{})
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0:
            raise RuntimeError('E15 red acquisition public controller refused')
        if _margin(m['q'],m['limits'])<=.02:raise RuntimeError('E15 red acquisition lacks original20mrad actual reserve')
        table=[o for o in obstacles if o['name']=='table'];assert len(table)==1
        environment=[o for o in obstacles if o['name']!='table'and not(carrying and o['name'].startswith('object:red_t:'))]
        payload=[o for o in obstacles if o['name'].startswith('object:red_t:')]
        if carrying:
            if not payload:raise RuntimeError('Actual held source T collision parts required')
            m=dict(m,clouds=m['clouds']+[dict(name='held:'+o['name'],influence=7,points=o['points'])for o in payload])
        return m,environment,table
    def issue(token,mm=1.,degrees=None):
        if a.c.steps-start>=250:raise RuntimeError('E15 bounded actual red acquisition exhausted250 public actions')
        if degrees is None:a.act('STILL',token,mm)
        else:a.act('STILL',token,rotation_deg=degrees)
        guard()
    def checked(token,delta=None,degrees=None):
        m,environment,table=model();desired=m['rotation']
        if degrees is not None:desired=_axis_rotation([0,0,1],math.radians(degrees))@desired
        position=m['position']if delta is None else m['position']+delta
        receipt=_preflight(m,environment,position,desired)
        # Preserve the original floor-clear TCP allowance for acquisition;
        # the fingers intentionally approach within0.3mm of the tabletop.
        robot=dict(m,clouds=[c for c in m['clouds']if not c['name'].startswith('held:')])
        screen_joint_segment(robot,m['q'],np.asarray(receipt['candidate_joints_rad']),table,margin=1e-6)
        before=m['position'].copy()
        issue(token,mm=float(np.linalg.norm(delta)*1000.) if delta is not None else 1.,degrees=degrees)
        after,env_after,table_after=model()
        screen_joint_segment(after,after['q'],after['q'],env_after,margin=.005)
        robot_after=dict(after,clouds=[c for c in after['clouds']if not c['name'].startswith('held:')])
        screen_joint_segment(robot_after,after['q'],after['q'],table_after,margin=1e-6)
        if carrying and min(float(c['points'][:,2].min())for c in after['clouds']if c['name'].startswith('held:'))<float(table_after[0]['hi'][2])-1e-5:
            raise RuntimeError('E15 actual held source T crossed the tabletop')
        if np.linalg.norm(after['q']-m['q'])>=.35:raise RuntimeError('E15 acquisition left original nearby joint branch')
        if delta is not None and float((after['position']-before)@(delta/np.linalg.norm(delta)))<.0001:
            raise RuntimeError('E15 real red acquisition increment failed to advance')
        receipt.update(public_token=token,requested_mm=None if delta is None else float(np.linalg.norm(delta)*1000.),
            actual_tip_task_m=after['position'].tolist(),actual_margin_rad=_margin(after['q'],after['limits']))
        receipts.append(receipt);return after
    a.stage='local-E15-real-red-descent-from-hover118'
    if near_grasp:
        actual=a.finger_geometry('right');body=a.c.snapshot()[0]['red_t']
        point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(red['grasp_point_local'])
        top=float(body['pos'][2])+(np.abs(np.asarray(body['mat']))@np.asarray(red['size']))[2]
        if (actual.get('source')!='actual_collision_mesh_current_body_pose'
                or actual['lowest_z_task_m']<.800001 or actual['lowest_z_task_m']>top-.002
                or np.linalg.norm(a.tip('right')[:2]-point[:2])>.002):
            raise RuntimeError('E15 near-table actual finger pad does not cover real T above original table')
        receipts.append(dict(operation='actual_near_table_pad_instead_of_nominal_tip',
            actual_finger_lowest_z_m=float(actual['lowest_z_task_m']),actual_red_top_z_m=top,
            remaining_nominal_downward_move_omitted=True))
    for _ in range(0 if near_grasp else 160):
        m,_,_=model();body=a.c.snapshot()[0]['red_t']
        point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(red['grasp_point_local'])
        goal=np.r_[point[:2],max(float(point[2]),float(a.floor_clear_tcp('right')))]
        error=goal-m['position'];tolerance=min(.0035,max(.0008,min(red['size'])*.2))
        if np.max(np.abs(error))<=tolerance:break
        if _margin(m['q'],m['limits'])<.04:
            if wrist_steps>=12:raise RuntimeError('E15 acquisition small wrist reserve exhausted')
            checked('ROTATE_CCW',degrees=2.);wrist_steps+=1;continue
        axis=int(np.argmax(np.abs(error)));delta=np.zeros(3)
        delta[axis]=math.copysign(min(.003,max(.0005,abs(float(error[axis])))),error[axis])
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(delta[axis]<0)]
        checked(token,delta=delta)
    else:
        if not near_grasp:raise RuntimeError('E15 measured red descent did not reach original grasp tolerance')
    a.stage='local-E15-real-red-GRASP'
    for _ in range(3):
        issue('GRASP');model()
        actual,pairs=a.c.snapshot()
        if actual['red_t']['grasp'][1]and all(frozenset(('red_t','right_finger'+str(i)))in pairs for i in(1,2)):
            carrying=True;break
    else:raise RuntimeError('E15 red T lacks actual bilateral grip after original three GRASP bound')
    a.carried_payload=('red_t','right');a.stage='local-E15-real-red-short-lift'
    lift_origin=a.tip('right').copy()
    for _ in range(20):
        remaining=.020-float(a.tip('right')[2]-lift_origin[2])
        if remaining<=.001:break
        checked('UP',delta=np.array([0.,0.,min(.002,max(.0005,remaining))]))
    else:raise RuntimeError('E15 actual short lift failed to rise20mm')
    guard();body=a.c.snapshot()[0]['red_t'];rise=float(body['pos'][2])-initial_red_z
    if rise<.010:raise RuntimeError('E15 real held red T rose less than10mm')
    return dict(segment=segment,local_completed=True,actions=a.c.steps-start,operations=receipts,
        held_actor='red_t',side='right',actual_red_rise_m=rise,full_task_completed=False)
