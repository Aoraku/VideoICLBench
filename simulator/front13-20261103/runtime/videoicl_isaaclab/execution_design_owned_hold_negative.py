"""E14/E16/E21/E25 physical final-hold controls; no world/score changes."""
from copy import deepcopy
import math
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_back25_negative import Back25NegativeAuthor
from .realworld_semantic_checks import check_task, POSITION_TOLERANCE_M, ANGLE_TOLERANCE_DEG, _placement_events

CAPABILITIES={task:frozenset(('not_released',))for task in ('E14','E16','E21','E25')}


def negative_plan(spec,control):
    design=spec.get('execution_design',{})
    if (control not in CAPABILITIES.get(spec.get('id'),()) or design.get('revision')!=REVISION_V3
            or design.get('source_sha256')!=source_sha256(REVISION_V3)
            or spec.get('task_revision',REVISION_V3)!=REVISION_V3):
        raise ValueError('Checksum-pinned owned v3 final-hold control required')
    if not spec.get('goals')or any(g.get('type')!='place'for g in spec['goals']):
        raise ValueError('Original public placement route required')
    plan=deepcopy(spec);plan['expert_preserve_goal_order']=True
    return plan,dict(task=spec['id'],control=control,held_member=spec['goals'][-1]['object'],
        original_goals=deepcopy(spec['goals']),attempted_goals=deepcopy(spec['goals']),
        negative_condition_observed=None,native_review_required=True,
        required_native_review='Real final bilateral hold at the original destination; earlier placements released and stable. Incomplete routes are not passed negatives.')


def verify_final_hold(spec,state,contacts,score):
    """Reject a grasp failure, a premature hold, or an incomplete placement."""
    evidence=score.get('progress_evidence',{})
    if (score.get('history_valid') is not True or score.get('errors')
            or evidence.get('source')!='trusted_native_per_physics_tick'
            or evidence.get('history_valid') is not True or not evidence.get('initial',{}).get('sealed')):
        raise RuntimeError('Valid sealed native history required for a final-hold control')
    name=spec['goals'][-1]['object'];body=state[name]
    flags=body.get('grasp',[])
    if len(flags)!=2 or sum(bool(x)for x in flags)!=1:
        raise RuntimeError('Final negative object must be actually held by exactly one hand')
    side='left'if flags[0]else'right'
    if not all(frozenset((name,f'{side}_finger{i}'))in contacts for i in (1,2)):
        raise RuntimeError('Final negative object requires actual bilateral finger contact')
    final={g['object']:g for g in spec['goals']};zones={z['id']:z for z in spec['zones']}
    objects={o['id']:o for o in spec['objects']};physical=evidence.get('object_status',{})
    label=lambda actor:objects[actor].get('semantic_identity',objects[actor].get('identity',actor))
    rows={}
    for actor,goal in final.items():
        actual=state[actor];zone=zones[goal['target']]
        xy=np.asarray(goal.get('placement_xy',zone['xy']),float)
        if zone.get('anchor_object'):
            anchor=state[zone['anchor_object']]
            xy=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(zone['anchor_local_center']))[:2]
        expected_z=float(zone.get('surface_z',.8))+float(objects[actor]['size'][2])
        position=np.asarray(actual['pos'],float);rotation=np.asarray(actual['mat'],float)
        if position.shape!=(3,)or rotation.shape!=(3,3)or not np.isfinite(np.r_[position,rotation.ravel()]).all():
            raise RuntimeError('Finite actual final object pose required')
        distance=float(np.linalg.norm(position[:2]-xy));height=abs(float(position[2])-expected_z)
        yaw=math.atan2(rotation[1,0],rotation[0,0]);yaw_error=abs((yaw-float(goal.get('yaw',yaw))+math.pi)%(2*math.pi)-math.pi)
        if distance>POSITION_TOLERANCE_M or height>.02 or yaw_error>math.radians(ANGLE_TOLERANCE_DEG):
            raise RuntimeError('Final hold route did not achieve original destination: '+actor)
        if actor!=name:
            status=evidence.get('actor_status',{}).get(actor,physical.get(label(actor),{}))
            if any(actual.get('grasp',[]))or not status.get('released')or not status.get('stable')or not status.get('supported'):
                raise RuntimeError('Earlier original member is not released stable and supported: '+actor)
        rows[actor]=dict(xy_error_m=distance,height_error_m=height,yaw_error_rad=yaw_error,held=actor==name)
    original_geometry=_verify_original_relations(spec,state,evidence,final,name,objects,label)
    if score.get('success')or score.get('strict_success'):
        raise RuntimeError('Original native evaluator unexpectedly accepted final hold')
    return dict(held_member=name,side=side,bilateral_contact=True,objects=rows,original_geometry=original_geometry)


def _verify_original_relations(spec,state,evidence,final,held,objects,label):
    """Read original native observations; never fabricate a released observation.

    Only the final member's release/support may be missing. A failed or partial
    earlier placement, wrong ordering, or an above-rim hover is not this control.
    """
    task=spec['id'];obs=evidence.get('observation',{})
    checks=check_task(task,spec['variant'],obs)['checks']
    required={
        'E14':('four_original_layers','top_indexed_reordering'),
        'E16':('three_original_objects','operator_frame_defined','relative_positions','individual_orientations'),
        'E21':(),
        'E25':('plate_relative_regions','handle_directions','utensil_relative_order'),
    }[task]
    if not all(checks.get(k) is True for k in required):
        raise RuntimeError('Original native relation is incomplete: '+task)
    earlier={label(n) for n in final if n!=held}
    if task=='E14':
        # Final held top layer need not be supported. Every earlier layer must
        # retain its original measured directional support edge, not table only.
        edges={tuple(edge) for edge in obs.get('support_edges',[])}
        order=obs['final_top_to_bottom'][::-1]
        if order[-1]!=label(held):raise RuntimeError('Final held member must be the original top layer')
        if any((a,b) not in edges for a,b in zip(['table']+order,order[:-1])):
            raise RuntimeError('Earlier tower support chain is incomplete')
    elif task=='E16':
        if not earlier<=set(obs.get('in_tray',[])) or not earlier<=set(obs.get('supported_in_tray',[])):
            raise RuntimeError('Earlier original members lack actual tray containment/support')
        # Native container_members deliberately excludes held bodies. Apply the
        # SAME measured cavity-box geometry, without claiming support/release.
        entry=spec['semantic']['containers']['tray'];anchor=state[entry['object']]
        obj=objects[held];body=state[held];rotation=np.asarray(body['mat'])
        center=np.asarray(body['pos'])+rotation@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        local=np.asarray(anchor['mat']).T@(center-np.asarray(anchor['pos']))
        radius=np.abs(np.asarray(anchor['mat']).T@rotation)@np.asarray(obj['size'])
        if not (np.all(local-radius>=np.asarray(entry['lower'])-.003) and np.all(local+radius<=np.asarray(entry['upper'])+.003)):
            raise RuntimeError('Held original member is not geometrically inside the tray')
    elif task=='E21':
        names=spec['semantic']['release_order'];slots=['top_left','top_right','bottom_left','bottom_right']
        expected=dict(zip(map(label,names),slots));events=_placement_events(obs.get('placement_events'))
        if (events is None or len(events)!=len(names)-1 or any(e.get('object')!=label(n) or e.get('target')!=slot
                or e.get('released') is not True or e.get('support_contact') is not True
                for e,n,slot in zip(events,names[:-1],slots[:-1]))
                or obs.get('cells')!={n:expected[n] for n in earlier}):
            raise RuntimeError('Earlier actual released placement sequence/cells are incomplete')
        bounds=spec['semantic']['compartment_bounds'][spec['semantic']['mapping'][held]]
        anchor=state[spec['semantic']['container']];body=state[held];obj=objects[held]
        center=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        local=np.asarray(anchor['mat']).T@(center-np.asarray(anchor['pos']))
        if not (np.all(local>=np.asarray(bounds['lower'])-.003) and np.all(local<=np.asarray(bounds['upper'])+.003)):
            raise RuntimeError('Held member is outside the original compartment geometry (including height)')
    return dict(required_native_checks={k:checks[k] for k in required},earlier_members=sorted(earlier),
                final_release_and_support_excluded=True)


class OwnedHoldNegativeAuthor(Back25NegativeAuthor):
    def __init__(self,author,control):
        if (getattr(author,'smooth',False)or author.scene.spec.get('author_smooth_recording')
                or not getattr(author,'control_report',{}).get('engineering_reference_only')):
            raise ValueError('Independently recorded public engineering actions required')
        self.author=author;self.control=control
        self.plan,self.perturbation=negative_plan(author.scene.spec,control)

    def solve_negative(self):
        report=super().solve_negative()
        state,contacts=self.author.c.snapshot();score=self.author.c.evaluator.result()
        report['intervention_observations']=verify_final_hold(self.author.scene.spec,state,contacts,score)
        report['original_native_result']=score
        return report
