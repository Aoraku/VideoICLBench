"""B187 native boundary: lower the real transported spoon to its original goal."""
import math
import numpy as np
from .execution_design_e25_b_reference import require_scope,SECTIONS,_joints
from .realworld_tool_expert import _axis_rotation


def run(a,parameters):
    require_scope(a);checkpoint=getattr(a,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
    if (parameters!={}or a.scene.spec.get('seed')!=4201 or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=187 or source.get('physics_ticks')!=18711
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered B187 admitted native spoon boundary required')
    obj=next(o for o in a.scene.spec['objects']if o['id']=='spoon')
    if obj.get('source_asset',{}).get('sha256')!=SECTIONS['spoon']['sha256']:
        raise ValueError('Pinned original spoon source mesh required')
    goal=next(g for g in a.scene.spec['goals']if g['object']=='spoon');zone=next(z for z in a.scene.spec['zones']if z['id']==goal['target'])
    if zone.get('anchor_object')or goal.get('required_support',zone.get('support','table'))!='table':
        raise ValueError('Original B spoon table target required')
    xy=np.asarray(goal.get('placement_xy',zone['xy']));half=np.asarray(zone['half_size']);floor=float(zone.get('surface_z',.8))
    desired=_axis_rotation([0,0,1],float(goal.get('yaw',0)))
    def held():
        state,contacts=a.c.snapshot();body=state['spoon']
        if (not body['grasp'][0]or not all(frozenset(('spoon','left_finger'+str(i)))in contacts for i in(1,2))
                or any(b['grasp'][1]or(n!='spoon'and b['grasp'][0])for n,b in state.items())):
            raise RuntimeError('B187 actual bilateral spoon hold lost')
        q,limits,_=_joints(a,'left')
        if not np.isfinite(q).all()or np.any(q<=limits[:,0]+.015)or np.any(q>=limits[:,1]-.015):
            raise RuntimeError('B187 actual joint limit approached')
        if any(any('left_finger'+str(i)in pair for i in(1,2))and 'spoon'not in pair for pair in contacts):
            raise RuntimeError('B187 actual finger contacts unrelated scene geometry')
        return body
    def in_region(body):
        return not np.any(abs(np.asarray(body['pos'])[:2]-xy)>half)
    body=held()
    angle=math.acos(float(np.clip((np.trace(desired@np.asarray(body['mat']).T)-1)/2,-1,1)))
    if not in_region(body)or angle>math.radians(6):raise RuntimeError('B187 actual spoon has not reached original transport target')
    before=a.c.steps;holding=True;old_act=a.act;a.carried_payload=('spoon','left');a.stage='grasped-spoon'
    def act(*args,**kwargs):
        if a.c.steps-before>=150:raise RuntimeError('B187 original release tail action bound exhausted')
        if holding:held()
        result=old_act(*args,**kwargs)
        if holding:held()
        return result
    a.act=act
    try:
        body=held();tip=np.asarray(a.tip('left'));offset=tip-np.asarray(body['pos'])
        height=float((np.abs(body['mat'])@np.asarray(obj['size']))[2])
        z=max(floor+height+float(offset[2])+.004,float(a.floor_clear_tcp('left',floor=floor)))
        # Existing region tolerance already accepts the achieved4mm endpoint.
        # Preserve its real XY rather than refine a harmless sub-cell offset.
        a.move_generated({'left':[*tip[:2],z]});body=held()
        if not in_region(body):raise RuntimeError('B187 actual spoon left original release region')
        holding=False;a.release_generated('left');a.carried_payload=None
        state,contacts=a.c.snapshot()
        if any(state['spoon']['grasp'])or frozenset(('spoon','table'))not in contacts or not in_region(state['spoon']):
            raise RuntimeError('B187 actual spoon release lacks original table support/region')
        a.stage='released-spoon';tip=np.asarray(a.tip('left'));a.move_generated({'left':[*tip[:2],tip[2]+.05]})
        state,contacts=a.c.snapshot()
        if any(state['spoon']['grasp'])or frozenset(('spoon','table'))not in contacts or not in_region(state['spoon']):
            raise RuntimeError('B187 final original spoon support lost')
        return [dict(operation='actual_transported_spoon_original_goal_release',side='left')]
    finally:a.act=old_act
