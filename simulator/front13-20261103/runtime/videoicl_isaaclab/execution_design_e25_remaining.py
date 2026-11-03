"""Admitted E25 checkpoint suffixes reuse the original remaining-goal loop."""
import hashlib,json
from pathlib import Path
import numpy as np
from .execution_design_segments_e19_e25 import _scope,_empty


def validate_initial_identity(a,initial_identity):
    from .engineering_checkpoint import identity
    current=identity(a.c)
    if initial_identity==current:return
    receipt=a.scene.spec.get('engineering_render_checkpoint_migration')
    cp=getattr(a,'_engineering_resume_checkpoint',{})
    if (not isinstance(receipt,dict)or cp.get('render_cadence_migration_receipt')!=receipt
            or receipt.get('from_render_hz')!=5 or receipt.get('to_render_hz')!=1
            or receipt.get('changed_config_fields')!=['physics.render_hz']
            or receipt.get('physics_parameters_unchanged')is not True
            or receipt.get('all_native_state_fields_preserved')is not True
            or receipt.get('history_reconstructed')is not False
            or initial_identity!=receipt.get('source_identity')
            or initial_identity.get('embodiment_config_sha256')!=receipt.get('source_profile_sha256')
            or current['embodiment_config_sha256']!=receipt.get('target_profile_sha256')):
        raise ValueError('Original initial policy lacks verified render-only identity chain')
    digest=receipt.get('source_native_checkpoint_integrity_sha256')
    if not isinstance(digest,str)or len(digest)!=64 or any(x not in'0123456789abcdef'for x in digest):
        raise ValueError('Verified native render migration integrity required')
    expected=dict(initial_identity);expected['embodiment_config_sha256']=receipt['target_profile_sha256']
    if expected!=current:raise ValueError('Initial policy assignment/source/geometry changed beyond render cadence')


def validate_resume(a,context):
    _scope(a,'E25',a.scene.spec['variant'])
    if (not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)
            or a.scene.spec.get('seed')!=4201
            or set(context)!={'home_xy','active_hand','completed_objects'}
            or context['active_hand']!='left'
            or context['completed_objects']not in(['spoon'],['spoon','knife'])
            or(context['completed_objects']==['spoon','knife']and a.scene.spec['variant']!='A')):
        raise ValueError('Admitted E25 actual remaining-goal policy context required')
    for side in('left','right'):
        xy=np.asarray(context['home_xy'][side],float)
        if xy.shape!=(2,)or not np.isfinite(xy).all():raise ValueError('Finite original workspace references required')
    _empty(a)


def in_original_goal(a,name):
    state,contacts=a.c.snapshot();body=state[name]
    goal=next(g for g in a.scene.spec['goals']if g['object']==name)
    zone=next(z for z in a.scene.spec['zones']if z['id']==goal['target'])
    center=np.asarray(goal.get('placement_xy',zone['xy']),float)
    support=goal.get('required_support',zone.get('support','table'))
    if zone.get('anchor_object'):
        anchor=state[zone['anchor_object']]
        center=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(zone.get('anchor_local_center',[0,0,0])))[:2]
        support=goal.get('required_support',zone.get('support',zone['anchor_object']))
    return bool(not any(body['grasp'])and np.all(abs(np.asarray(body['pos'])[:2]-center)<=np.asarray(zone['half_size']))
        and frozenset((name,support))in contacts)


def run_segment(a,segment,parameters):
    variant=a.scene.spec['variant'];_scope(a,'E25',variant)
    cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    entry={'e25_a_finish_remaining_from586':('A',586,59440),
           'e25_a_finish_after_knife_relay186':('A',186,18602),
           'e25_b_finish_remaining_from636':('B',636,64440)}.get(segment)
    completed_return=(segment=='e25_b_finish_after_return'and variant=='B'
        and cp.get('stage')=='checkpoint-suffix-completed'
        and cp.get('context',{}).get('entry')=='e25_b_empty_return_from636'
        and cp.get('context',{}).get('local_debug_only')is True)
    if (not(entry is not None and(variant,source.get('steps'),source.get('physics_ticks'))==entry or completed_return)
            or set(parameters)!={'initial_checkpoint'}or cp.get('diagnostic_only')is not True
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Explicit A586/B636 or completed B-return native suffix required')
    reference=parameters['initial_checkpoint'];root=(
        'execution-design-v3-20261102-e25a-full-positive-slot10-v8-s4201'if variant=='A'else
        'execution-design-v3-20261102-e25b-full-positive-slot10-v7-s4201')
    expected='/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering/'+root+'/result/room-00-E25-'+variant+'-s4201/engineering-reference/checkpoints/stage-0001-initial.private.json'
    if reference['path']!=expected:raise ValueError('Pinned original E25 workspace policy source required')
    raw=Path(expected).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('E25 initial policy SHA mismatch')
    initial=json.loads(raw)
    from .layout import rotation_matrix
    validate_initial_identity(a,initial['identity'])
    if initial['source']['steps']!=0:
        raise ValueError('Original source/assignment/profile/geometry identity required')
    home={};rotations={}
    for side in('left','right'):
        r=initial['robots'][side]['root_state_task'];R=rotation_matrix(np.asarray(r[3:7]));target=initial['controller']['tcp_targets_base'][side]
        home[side]=(np.asarray(r[:3])+R@np.asarray(target['position']))[:2].tolist()
        rotations[side]=R@rotation_matrix(np.asarray(target['quaternion']))
    context=dict(home_xy=home,active_hand='left',completed_objects=['spoon'])
    validate_resume(a,context)
    if not in_original_goal(a,'spoon'):raise RuntimeError('Actual completed spoon original support/goal must be preserved')
    a._e25_home_rotations=rotations;a._engineering_e25_remaining=context
    before=a.c.steps
    try:
        if segment=='e25_a_finish_after_knife_relay186':
            from .execution_design_e25_functional import prepare_next_pickup
            from .execution_design_e25_a_receiver import place_settled_knife
            prepare_next_pickup(a,'left','knife')
            place_settled_knife(a,dict(side='left',action_limit=500))
            if not in_original_goal(a,'knife'):raise RuntimeError('Actual relayed knife original goal/support missing')
            context['completed_objects'].append('knife')
        a.solve_generated()
        if not all(in_original_goal(a,g['object'])for g in a.scene.spec['goals']):
            raise RuntimeError('Actual remaining E25 objects lack original goal support/regions')
        return dict(local_completed=True,actions=a.c.steps-before,operations=[dict(
            operation='original_remaining_E25_goals',completed_prefix_not_replayed=['spoon'])])
    finally:del a._engineering_e25_remaining
