"""A600: release the real spoon already inside its unchanged table goal."""
import math
import numpy as np
from .execution_design_segments_e19_e25 import _scope
from .execution_design_e25_b_reference import SECTIONS,_joints
from .realworld_tool_expert import _axis_rotation


def ready(a):
    _scope(a,'E25','A');spec=a.scene.spec
    obj=next(o for o in spec['objects']if o['id']=='spoon')
    if obj.get('source_asset',{}).get('sha256')!=SECTIONS['spoon']['sha256']:
        raise ValueError('Original A spoon source mesh required')
    goal=next(g for g in spec['goals']if g['object']=='spoon')
    zone=next(z for z in spec['zones']if z['id']==goal['target'])
    if zone.get('anchor_object')or goal.get('required_support',zone.get('support','table'))!='table':
        raise ValueError('Original A spoon table goal required')
    state,contacts=a.c.snapshot();body=state['spoon'];xy=np.asarray(goal.get('placement_xy',zone['xy']))
    angle=math.acos(float(np.clip((np.trace(_axis_rotation([0,0,1],float(goal.get('yaw',0)))@np.asarray(body['mat']).T)-1)/2,-1,1)))
    return bool(not np.any(abs(np.asarray(body['pos'])[:2]-xy)>np.asarray(zone['half_size']))
        and float(zone.get('surface_z',.8))<float(body['pos'][2])<float(zone.get('surface_z',.8))+.06
        and angle<math.radians(6))


def lower_until_original_goal(a,goal,target):
    """Stop public lowering at the real unchanged goal, without centering."""
    _scope(a,'E25','A')
    if goal.get('object')!='spoon'or '_e07_after_relay'not in goal:
        raise ValueError('Original final A relay-spoon placement required')
    target=np.asarray(target,float)
    if target.shape!=(3,)or not np.isfinite(target).all():raise ValueError('Finite original spoon waypoint required')
    for _ in range(120):
        state,contacts=a.c.snapshot()
        if (not state['spoon']['grasp'][0]or not all(frozenset(('spoon','left_finger'+str(i)))in contacts for i in(1,2))
                or any(v['grasp'][1]or(n!='spoon'and v['grasp'][0])for n,v in state.items())):
            raise RuntimeError('A spoon actual bilateral grip lost before release')
        if ready(a)and a.finger_geometry('left')['lowest_z_task_m']>=.815:
            a.control_report['e25_a_spoon_actual_goal_stop']=dict(original_goal_unchanged=True,
                actual_position_task_m=np.asarray(state['spoon']['pos']).tolist(),native_task_acceptance=False)
            return
        error=target-np.asarray(a.tip('left'))
        if np.max(abs(error))<=.001:raise RuntimeError('A spoon original waypoint reached without physical release geometry')
        axis=int(np.argmax(abs(error)));desired=1 if error[axis]>0 else -1
        positive=getattr(a,'generated_axis_signs',{}).get('left',{}).get(axis,1)
        labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis]
        token=labels[0]if desired==positive else labels[1]
        a.act(token,'STILL',mm=min(5.,float(abs(error[axis])*1000)))
    raise RuntimeError('A spoon bounded public approach did not reach original release region')


def run_segment(a,segment,parameters):
    _scope(a,'E25','A');cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (segment!='e25_a_release_spoon_from600'or parameters!={}or a.scene.spec.get('seed')!=4201
            or cp.get('diagnostic_only')is not True or source.get('steps')!=600
            or source.get('physics_ticks')!=60840 or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered A600 native held-spoon boundary required')
    state,contacts=a.c.snapshot()
    if (not state['spoon']['grasp'][0]or not all(frozenset(('spoon','left_finger'+str(i)))in contacts for i in(1,2))
            or any(v['grasp'][1]or(n!='spoon'and v['grasp'][0])for n,v in state.items())):
        raise RuntimeError('A600 actual bilateral spoon hold and empty peer required')
    q,limits,_=_joints(a,'left')
    if np.any(q<=limits[:,0]+.015)or np.any(q>=limits[:,1]-.015):
        raise RuntimeError('A600 actual native joint limit approached')
    if (not ready(a)or a.finger_geometry('left')['lowest_z_task_m']<.815
            or any(any('left_finger'+str(i)in pair for i in(1,2))and 'spoon'not in pair for pair in contacts)):
        raise RuntimeError('A600 actual spoon/finger geometry is outside original short table release')
    before=a.c.steps;a.stage='local-A600-actual-table-spoon-release';a.release_generated('left');a.carried_payload=None
    def supported():
        state,contacts=a.c.snapshot()
        if any(any(v['grasp'])for v in state.values())or frozenset(('spoon','table'))not in contacts or not ready(a):
            raise RuntimeError('A600 real released spoon lacks original table support/goal')
    supported();tip=np.asarray(a.tip('left'));a.stage='released-spoon'
    a.move_generated({'left':[*tip[:2],tip[2]+.05]});supported()
    return dict(local_completed=True,actions=a.c.steps-before,operations=[dict(
        operation='actual_spoon_release_inside_original_A_goal',original_goal_unchanged=True)])
