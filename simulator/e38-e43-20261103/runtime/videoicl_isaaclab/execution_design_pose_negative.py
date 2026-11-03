"""E15/E22 independent physical counterexamples; no native world/score writes."""
from copy import deepcopy
import itertools,math
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_back25_negative import Back25NegativeAuthor
from .realworld_semantic_checks import POSITION_TOLERANCE_M,ANGLE_TOLERANCE_DEG

CAPABILITIES={t:frozenset(('wrong_rule','wrong_destination','not_released'))for t in ('E15','E22')}
_TERMINAL_TOKEN=object()


def _valid_spec(spec):
    d=spec.get('execution_design',{})
    return (spec.get('id')in CAPABILITIES and d.get('revision')==REVISION_V3
            and d.get('source_sha256')==source_sha256(REVISION_V3)
            and spec.get('task_revision',REVISION_V3)==REVISION_V3)


def allow_original_terminal_failure(author):
    """Only the private runner may return the unchanged native failed result."""
    return bool(getattr(author,'_pose_negative_terminal_token',None)is _TERMINAL_TOKEN
        and getattr(author,'_execution_design_reference_authorized',False)
        and getattr(author,'control_report',{}).get('engineering_reference_only')
        and _valid_spec(author.scene.spec) and _valid_spec(author.c.scene.spec))


def _yaw(body):
    m=np.asarray(body['mat'],float);return math.atan2(m[1,0],m[0,0])


def _angle(a,b):return abs((a-b+math.pi)%(2*math.pi)-math.pi)


def _outside_site(spec,state,table_bounds):
    lo,hi=(np.asarray(x,float)for x in table_bounds)
    payloads={g['object']for g in spec['goals']};radius=max(np.linalg.norm(o['size'][:2])for o in spec['objects']if o['id']in payloads)+.025
    for xy in ([ -.19,-.15],[-.22,.18],[-.32,0],[.0,-.32]):
        xy=np.asarray(xy,float)
        if np.any(xy-radius<lo[:2])or np.any(xy+radius>hi[:2]):continue
        clear=True
        for obj in spec['objects']:
            body=state[obj['id']];extent=np.abs(body['mat'])@np.asarray(obj['size'])
            if np.all(np.abs(xy-np.asarray(body['pos'])[:2])<extent[:2]+radius):clear=False
        if clear:return dict(id='negative-private-table-site',xy=xy.tolist(),half_size=[radius,radius],surface_z=float(hi[2]),support='table',hidden=True)
    raise RuntimeError('No measured empty physical table site for counterexample')


def _side(vector):
    x,y=vector[:2]
    return 'front'if x>abs(y)else'left'if y>abs(x)else'right'if -y>abs(x)else'other'


def negative_plan(spec,control,initial,table_bounds):
    if not _valid_spec(spec):raise ValueError('E15/E22 counterexample requires checksum-pinned v3')
    if control=='wrong_members':raise NotImplementedError('No independent wrong-identity source member; omission/duplication is not a substitute')
    if control not in CAPABILITIES[spec['id']]:raise ValueError('Unreviewed E15/E22 control')
    active=spec['semantic']['groups']['active']
    for name in active:
        if name not in initial or not np.isfinite(np.r_[initial[name]['pos'],np.asarray(initial[name]['mat']).ravel()]).all():
            raise ValueError('Sealed actual initial poses required')
    plan=deepcopy(spec);plan['expert_preserve_goal_order']=True
    perturb=dict(task=spec['id'],control=control,original_goals=deepcopy(spec['goals']),negative_condition_observed=None,native_review_required=True)
    if spec['id']=='E15' and control=='wrong_rule':
        names=list(spec['semantic']['objects']);a,b=names
        # A->C violates only orientation; B->C violates only position;
        # C->A violates only orientation. All two original members remain.
        alternate={'A':'C','B':'C','C':'A'}[spec['variant']]
        swap_xy=alternate in ('A','C');swap_yaw=alternate in ('B','C')
        site=_outside_site(spec,initial,table_bounds);plan['zones'].append(site);goals=[]
        if swap_xy:goals.append(dict(type='place',object=a,target=site['id'],yaw=_yaw(initial[a])))
        for name,other in ((b,a),(a,b)) if swap_xy else ((a,b),(b,a)):
            point=initial[other if swap_xy else name]['pos']
            zone=dict(id='negative-transform-'+name,xy=list(point[:2]),half_size=[.035,.035],surface_z=site['surface_z'],support='table',hidden=True)
            plan['zones'].append(zone);goals.append(dict(type='place',object=name,target=zone['id'],yaw=_yaw(initial[other if swap_yaw else name])))
        plan['goals']=goals;perturb.update(alternate_transform=alternate,exchange_position=swap_xy,exchange_orientation=swap_yaw)
    elif spec['id']=='E22' and control=='wrong_rule':
        targets=[g['target']for g in plan['goals']]
        if set(targets)!=set(('front','left','right')):raise ValueError('Original car-relative three-side goals required')
        for g,target in zip(plan['goals'],targets[1:]+targets[:1]):g['target']=target
        perturb['attempted_mapping']={g['object']:g['target']for g in plan['goals']}
    elif control=='wrong_destination':
        goal=plan['goals'][-1];name=goal['object']
        if spec['id']=='E15':site=_outside_site(spec,initial,table_bounds);strategy='measured_empty_table_outside_real_target'
        else:
            car=initial[spec['semantic']['car']];frame=np.asarray(car['mat'])@np.asarray(spec['semantic'].get('car_frame',np.eye(3)))
            role=goal['target'];delta={'front':[.105,0,0],'left':[0,.11,0],'right':[0,-.11,0]}[role]
            local=frame.T@np.asarray(delta)
            # World-fixed directions only witness an invalid destination when
            # they actually fall outside all three legal car-relative sides.
            if _side(local)=='other':strategy='world_fixed_direction_outside_actual_car_sides'
            else:delta=(-frame[:,0]*.15).tolist();strategy='actual_car_rear_outside_all_three_destinations'
            xy=(np.asarray(car['pos'])+delta)[:2]
            lo,hi=(np.asarray(x)for x in table_bounds)
            if np.any(xy-.035<lo[:2])or np.any(xy+.035>hi[:2]):raise RuntimeError('Actual outside-car table destination is off table')
            site=dict(id='negative-outside-car',xy=xy.tolist(),half_size=[.035,.035],surface_z=float(hi[2]),support='table',hidden=True)
        plan['zones'].append(site);goal['target']=site['id'];goal.pop('placement_xy',None);goal['required_support']='table'
        perturb.update(outside_member=name,destination_strategy=strategy)
    else:perturb['held_member']=plan['goals'][-1]['object']
    perturb['attempted_goals']=deepcopy(plan['goals'])
    perturb['required_native_review']='All intended physical interventions must occur with actual support/release or retained bilateral hold; original native history/score must reject. Route errors are not passed negative controls.'
    return plan,perturb


def intervention_observations(spec,plan,control,initial,state,contacts,score,side_held=None):
    """Reject incomplete routes using actual poses/contact/native stability."""
    final={g['object']:g for g in plan['goals']};zones={z['id']:z for z in plan['zones']}
    evidence=score.get('progress_evidence',{});physical=evidence.get('object_status',{});objects={o['id']:o for o in spec['objects']}
    held_name=plan['goals'][-1]['object']if control=='not_released'else None;rows={}
    for name,g in final.items():
        body=state[name];zone=zones[g['target']];xy=np.asarray(g.get('placement_xy',zone['xy']))
        if zone.get('anchor_object'):
            anchor=state[zone['anchor_object']];xy=(anchor['pos']+anchor['mat']@np.asarray(zone['anchor_local_center']))[:2]
        error=float(np.linalg.norm(np.asarray(body['pos'])[:2]-xy));yawerr=_angle(_yaw(body),float(g.get('yaw',_yaw(body))))
        if error>POSITION_TOLERANCE_M or math.degrees(yawerr)>ANGLE_TOLERANCE_DEG:
            raise RuntimeError('Physical counterexample did not attain intended pose: '+name)
        if name==held_name:
            if side_held not in ('left','right')or not body['grasp'][0 if side_held=='left'else 1]:raise RuntimeError('Counterexample final body is not actually held')
            if not all(frozenset((name,f'{side_held}_finger{i}'))in contacts for i in (1,2)):raise RuntimeError('Counterexample requires actual bilateral final contact')
        else:
            obj=objects[name];label=obj.get('semantic_identity',obj.get('identity',name))
            status=evidence.get('actor_status',{}).get(name,physical.get(label,physical.get(name,{})))
            if any(body.get('grasp',[]))or frozenset((name,'table'))not in contacts or not status.get('stable'):
                raise RuntimeError('Counterexample body lacks actual released stable table support: '+name)
        rows[name]=dict(position_error_m=error,yaw_error_deg=math.degrees(yawerr),actually_held=any(body.get('grasp',[])))
    if spec['id']=='E22':
        car=spec['semantic']['car'];delta=float(np.linalg.norm(np.asarray(state[car]['pos'])-initial[car]['pos']));turned=float(np.linalg.norm(np.asarray(state[car]['mat'])-initial[car]['mat']))
        if delta>.002 or turned>.02:raise RuntimeError('Counterexample moved actual car reference')
        rows['reference_car']=dict(displacement_m=delta,rotation_matrix_delta=turned)
        if control=='wrong_destination':
            name=plan['goals'][-1]['object'];frame=np.asarray(state[car]['mat'])@np.asarray(spec['semantic'].get('car_frame',np.eye(3)))
            side=_side(frame.T@(np.asarray(state[name]['pos'])-state[car]['pos']))
            if side!='other':raise RuntimeError('Counterexample final body did not leave legal car-relative destinations')
            rows[name]['actual_car_side']=side
    if score.get('success') or score.get('strict_success'):raise RuntimeError('Original native evaluator unexpectedly accepted counterexample')
    return rows


class PoseNegativeAuthor(Back25NegativeAuthor):
    def __init__(self,author,control):
        if not getattr(author,'control_report',{}).get('engineering_reference_only')or getattr(author,'smooth',False)or author.scene.spec.get('author_smooth_recording'):
            raise ValueError('Explicit independently recorded engineering authorization required')
        initial=getattr(author.c.evaluator,'initial',None)
        if not initial:raise ValueError('Original evaluator must have sealed actual initial state')
        scene=author.scene;table=scene.layout.config['table'];origin=np.asarray(getattr(scene,'origin',(0,0,0)))
        center=np.asarray(table['position'])+origin;half=np.asarray(table['size'])/2
        corners=np.array([scene.world_to_task(center+half*np.asarray(s))for s in itertools.product((-1,1),repeat=3)])
        self.author=author;self.control=control;self.initial=deepcopy(initial);self.held_side=None
        self.plan,self.perturbation=negative_plan(scene.spec,control,self.initial,(corners.min(0),corners.max(0)))

    def solve_negative(self):
        a=self.author;old=getattr(a,'_pose_negative_terminal_token',None);old_act=a.act;had_act='act'in a.__dict__;old_instance=a.__dict__.get('act')
        # The superclass's final hold invokes only real public STILL actions.
        # Capture actual held side from the native snapshot, never a fake flag.
        def act(*args,**kwargs):
            result=old_act(*args,**kwargs)
            if self.control=='not_released':
                values,_=a.c.snapshot();name=self.perturbation['held_member'];flags=values[name]['grasp']
                if sum(bool(x)for x in flags)==1:self.held_side='left'if flags[0]else'right'
            return result
        try:
            a._pose_negative_terminal_token=_TERMINAL_TOKEN;a.act=act
            report=super().solve_negative()
        finally:
            if old is None:a.__dict__.pop('_pose_negative_terminal_token',None)
            else:a._pose_negative_terminal_token=old
            if had_act:a.act=old_instance
            else:a.__dict__.pop('act',None)
        state,contacts=a.c.snapshot();score=a.c.evaluator.result()
        observations=intervention_observations(a.scene.spec,self.plan,self.control,self.initial,state,contacts,score,self.held_side)
        report.update(intervention_observations=observations,original_native_result=score,negative_condition_observed=None,native_validation_required=True)
        return report
