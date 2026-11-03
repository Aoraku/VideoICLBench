"""E25A settled relay knife: measured empty-jaw correction and local placement."""
from copy import deepcopy
import json
import math
import itertools
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .author_orientation import _axis_angle,_rotation
from .realworld_tool_expert import _axis_rotation


def _scope(a):
    s=a.scene.spec;d=s.get('execution_design',{})
    if (s.get('id')!='E25'or s.get('variant')!='A'or d.get('revision')!=REVISION_V3
            or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not getattr(a,'_execution_design_reference_authorized',False)
            or not a.control_report.get('engineering_reference_only')or a.smooth
            or a.scene.embodiment.name!='franka'):
        raise ValueError('Pinned E25A Panda engineering receiver required')


def settled_receiver_rotation(a,side,name,desired,ik_probe=None):
    """Reject-only native IK check of the minimal actual settled-jaw correction."""
    _scope(a)
    if side!='left'or name!='knife':raise ValueError('Reviewed E25A left relay knife required')
    from .execution_design_e25_reference import grasp_spec
    obj=next(o for o in a.scene.spec['objects']if o['id']==name);grasp_spec(a,obj)
    state,contacts=a.c.snapshot()
    if any(any(b.get('grasp',[]))for b in state.values())or frozenset((name,'table'))not in contacts:
        raise RuntimeError('Actual empty hands and supported settled knife required')
    desired=_rotation(desired,'receiver candidate');jaw=np.asarray(state[name]['mat'])@np.asarray(obj['grasp_axis_local'],float);jaw/=np.linalg.norm(jaw)
    actual=desired[:,1];target=jaw if actual@jaw>=0 else-jaw;angle=math.acos(float(np.clip(actual@target,-1,1)))
    if angle<=math.radians(5):return desired
    axis=np.cross(actual,target);axis/=np.linalg.norm(axis);corrected=_axis_rotation(axis,angle)@desired
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    from .execution_design_e25_b_reference import _joints
    q,_,_=_joints(a,side);rows=ik_probe(a,a.c,side,[dict(position=np.asarray(a.tip(side)).tolist(),rotation=corrected.tolist())])
    passed=len(rows)==1 and rows[0].get('kinematically_reachable')and rows[0].get('minimum_joint_margin_rad',0)>.02
    if passed:
        candidate=np.asarray(rows[0].get('candidate_joints_rad'),float)
        passed=(candidate.shape==(7,)and np.isfinite(candidate).all()and np.max(abs(candidate-q))<.4
            and rows[0].get('position_error_m',float('inf'))<.001 and rows[0].get('orientation_error_rad',float('inf'))<math.radians(1.5))
    with(a.out/'e25-a-settled-receiver-axis.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(object=name,side=side,settled_jaw_axis_task=jaw.tolist(),original_candidate=desired.tolist(),
            corrected_candidate=corrected.tolist(),correction_rad=float(angle),native_ik_candidates=rows,
            endpoint_screen_passed=bool(passed),actuation_performed=False,native_passed=False))+'\n')
    if not passed:raise RuntimeError('E25A settled receiver axis lacks a connected native endpoint')
    return corrected



def held_rotation_clearance(a):
    """Bound the real knife's rotational sweep about the measured left TCP."""
    _scope(a)
    from .execution_design_generated_route import measured_generated_clearance
    from .execution_design_e25_reference import grasp_spec
    state,contacts=a.c.snapshot();body=state['knife']
    if (not body['grasp'][0]or not all(frozenset(('knife','left_finger'+str(i)))in contacts for i in(1,2))
            or any(b['grasp'][1]or(n!='knife'and b['grasp'][0])for n,b in state.items())):
        raise RuntimeError('E25A rotation sweep requires actual bilateral knife grip')
    obj=next(o for o in a.scene.spec['objects']if o['id']=='knife');grasp_spec(a,obj)
    half=np.asarray(obj.get('bounds_half_extent',obj['size']),float);center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    tip=np.asarray(a.tip('left'),float);r=np.asarray(body['mat'],float);p=np.asarray(body['pos'],float)
    if (half.shape!=(3,)or center.shape!=(3,)or r.shape!=(3,3)or tip.shape!=(3,)or p.shape!=(3,)
            or not np.isfinite(np.r_[half,center,r.ravel(),tip,p]).all()or np.any(half<=0)):
        raise ValueError('Actual knife transform and original physical bounds required')
    corners=np.asarray([p+r@(center+half*np.asarray(sign))for sign in itertools.product((-1,1),repeat=3)])
    radius=float(np.linalg.norm(corners-tip,axis=1).max())
    measured=measured_generated_clearance(a)
    obstacle=max([.8]+[float(z.get('surface_z',.8))for z in a.scene.spec['zones']]
        +[float(top)for name,top in measured['object_tops_task_m'].items()if name!='knife'])
    height=max(float(tip[2]),float(measured['clearance_z_m']),obstacle+radius+.025)
    a.control_report['e25_a_knife_rotation_clearance']=dict(actual_tcp_to_bounds_radius_m=radius,
        obstacle_top_z_m=obstacle,clearance_z_m=height,margin_m=.025,native_grasp_validated=True)
    return height


def lift_knife_for_rotation(a):
    """Public lift above the real knife sweep; shared by full and local A."""
    height=held_rotation_clearance(a)
    if float(a.tip('left')[2])<height-.0035:
        a.move_generated({'left':[*a.tip('left')[:2],height]})
    state,contacts=a.c.snapshot()
    if (not state['knife']['grasp'][0]or not all(frozenset(('knife','left_finger'+str(i)))in contacts for i in(1,2))):
        raise RuntimeError('E25A actual bilateral knife grip lost during sweep lift')
    if frozenset(('knife','table'))in contacts:
        raise RuntimeError('E25A knife still touches table before free rotation')
    return height


def _place_held_knife(a,original,spec,before,limit):
    """Existing original placement after a true held-state continuation."""
    state,contacts=a.c.snapshot()
    # Validate the real hold before reconstructing only the policy context.
    clearance=held_rotation_clearance(a);holding=True;old_act=a.act
    a.carried_payload=('knife','left');a.stage='grasped-knife'
    def guard():
        state,contacts=a.c.snapshot()
        if a.c.steps-before>=limit:raise RuntimeError('E25A local knife action budget exhausted')
        if any(b['grasp'][1]or(n!='knife'and b['grasp'][0])for n,b in state.items()):
            raise RuntimeError('E25A local knife acquired an unexpected payload')
        if holding and(not state['knife']['grasp'][0]or not all(frozenset(('knife','left_finger'+str(i)))in contacts for i in(1,2))):
            raise RuntimeError('E25A actual bilateral knife grip lost')
    def act(*args,**kwargs):
        guard();result=old_act(*args,**kwargs);guard();return result
    a.act=act
    try:
        clearance=lift_knife_for_rotation(a)
        a.rotate_held('knife','left',original)
        state,_=a.c.snapshot();offset=np.asarray(a.tip('left'))-np.asarray(state['knife']['pos'])
        target=next(z for z in a.scene.spec['zones']if z['id']==original['target']);xy=np.asarray(original.get('placement_xy',target['xy']),float)
        if target.get('anchor_object'):
            anchor=state[target['anchor_object']];xy=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(target.get('anchor_local_center',[0,0,0])))[:2]
        height=float((np.abs(state['knife']['mat'])@np.asarray(spec['size']))[2]);tcp_xy=xy+offset[:2]
        a.move_generated({'left':[*tcp_xy,clearance]})
        goal_z=float(target.get('surface_z',.8))+height+float(offset[2])+.004
        a.move_generated({'left':[*tcp_xy,goal_z]});guard();holding=False
        a.release_generated('left');state,_=a.c.snapshot()
        if any(state['knife']['grasp']):raise RuntimeError('E25A real knife did not release')
        a.carried_payload=None;a.stage='released-knife';a.move_generated({'left':[*a.tip('left')[:2],clearance]})
        state,contacts=a.c.snapshot();support=original.get('required_support',target.get('support','table'))
        if (any(state['knife']['grasp'])or frozenset(('knife',support))not in contacts
                or np.any(abs(np.asarray(state['knife']['pos'])[:2]-xy)>np.asarray(target['half_size']))):
            raise RuntimeError('E25A original knife goal lacks actual released support/region')
        return [dict(operation='actual_held_knife_sweep_clearance',side='left',clearance_z_m=clearance),
                dict(operation='original_knife_goal_supported_release',side='left')]
    finally:a.act=old_act


def continue_held_knife(a,parameters,*,source_boundary=(73,7311)):
    """Resume a pinned true hold, lift clear, and place its original goal."""
    _scope(a);checkpoint=getattr(a,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
    if source_boundary not in((73,7311),(21,2111)):
        raise ValueError('Reviewed native A21 or A73 held boundary required')
    steps,tick=source_boundary
    if (parameters!={}or a.scene.spec.get('seed')!=4201 or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered A'+str(steps)+' admitted native checkpoint required')
    from .execution_design_e25_reference import grasp_spec
    spec=grasp_spec(a,next(o for o in a.scene.spec['objects']if o['id']=='knife'))
    original=next(g for g in a.scene.spec['goals']if g['object']=='knife')
    return _place_held_knife(a,original,spec,a.c.steps,300)

def place_settled_knife(a,parameters):
    """Resume at the real supported terminal knife; no earlier utensil replay."""
    _scope(a);p=parameters
    if p.get('side','left')!='left':raise ValueError('Reviewed left E25A receiver required')
    state,contacts=a.c.snapshot()
    if getattr(a,'carried_payload',None)is not None or any(any(b.get('grasp',[]))for b in state.values())or frozenset(('knife','table'))not in contacts:
        raise RuntimeError('Actual empty terminal hands and table-supported knife required')
    from .execution_design_e25_reference import grasp_spec,prepare_receiver
    from .execution_design_segments_e19_e25 import approach_e25_piece
    from .execution_design_generated_route import measured_generated_clearance
    obj=next(o for o in a.scene.spec['objects']if o['id']=='knife');spec=grasp_spec(a,obj)
    original=next(g for g in a.scene.spec['goals']if g['object']=='knife');goal=deepcopy(original)
    goal.update(_e07_after_relay={},_e25_receiver_rotation_task=np.asarray(a.tcp_rotation_task('left')).tolist())
    target=next(z for z in a.scene.spec['zones']if z['id']==original['target']);before=a.c.steps;limit=int(p.get('action_limit',400))
    if not 1<=limit<=3000:raise ValueError('Bounded public local action limit required')
    holding=False
    def held():
        state,contacts=a.c.snapshot()
        return bool(state['knife']['grasp'][0]and all(frozenset(('knife','left_finger'+str(i)))in contacts for i in (1,2)))
    def guard():
        state,_=a.c.snapshot()
        if a.c.steps-before>=limit:raise RuntimeError('E25A local knife action budget exhausted')
        if any(b.get('grasp',[False,False])[1]or(n!='knife'and b.get('grasp',[False,False])[0])for n,b in state.items()):raise RuntimeError('E25A local knife acquired an unexpected payload')
        if holding and not held():raise RuntimeError('E25A actual bilateral knife grip lost')
    original_act=a.act
    def act(*args,**kwargs):
        guard();result=original_act(*args,**kwargs);guard();return result
    a.act=act
    try:
        point=np.asarray(state['knife']['pos'])+np.asarray(state['knife']['mat'])@np.asarray(spec['grasp_point_local'])
        approach=float(measured_generated_clearance(a)['clearance_z_m'])
        prepare_receiver(a,'left','knife',goal,approach,point[:2])
        state,_=a.c.snapshot();point=np.asarray(state['knife']['pos'])+np.asarray(state['knife']['mat'])@np.asarray(spec['grasp_point_local'])
        z=max(float(point[2]),float(a.floor_clear_tcp('left')));approach=max(float(measured_generated_clearance(a)['clearance_z_m']),z+.045)
        a.stage='e25-a-settled-knife-acquire'
        approach_e25_piece(a,'left',point[:2],z,approach,min(.0035,max(.0008,min(spec['size'])*.2)))
        for _ in range(3):
            a.act('GRASP','STILL')
            if held():break
        else:raise RuntimeError('E25A settled knife lacks actual bilateral grasp')
        a.act=original_act
        return [dict(operation='actual_settled_relay_knife_acquisition',side='left')]+_place_held_knife(a,original,spec,before,limit)
    finally:a.act=original_act
