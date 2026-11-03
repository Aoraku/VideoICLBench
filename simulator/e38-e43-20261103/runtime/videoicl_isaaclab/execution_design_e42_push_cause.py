"""E42 v3: accumulate only measured adjacent true-edge driven increments.

Clean contact gaps contribute no displacement. A hand, another held tool, or
wrong source-tool contact invalidates the chain and resets the driven vector.
Opposite increments cancel; traveled arc length and final position are not used.
"""
import numpy as np

POLICY='fragmented_held_edge_net_v1'


def enabled(spec):
    return spec.get('id')=='E42' and spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'


def update(record,sample,invalidated,intervention=False):
    record.setdefault('push_cause_policy',POLICY)
    record['effective_push_forbidden_intervention']=bool(record.get('effective_push_forbidden_intervention') or intervention)
    record.setdefault('effective_push_net_delta_m',[0.,0.,0.])
    record.setdefault('effective_push_valid_increments',0)
    record.setdefault('effective_push_fragment_count',0)
    if invalidated:
        record['effective_push_net_delta_m']=[0.,0.,0.]
        record['effective_push_valid_increments']=0
        record['effective_push_fragment_count']=0
        record.pop('effective_push_previous_sample',None)
    previous=record.pop('effective_push_previous_sample',None)
    if sample is None:return False
    position=np.asarray(sample['pos'],float)
    if position.shape!=(3,)or not np.isfinite(position).all():raise ValueError('Finite actual edge-push position required')
    step=sample['step']
    if type(step)is not int or step<0:raise ValueError('Actual monotonically increasing physics step required')
    if previous is not None and previous['step']==step-1:
        net=np.asarray(record['effective_push_net_delta_m'])+position-np.asarray(previous['pos'])
        record['effective_push_net_delta_m']=net.tolist()
        record['effective_push_valid_increments']+=1
    else:record['effective_push_fragment_count']+=1
    record['effective_push_previous_sample']=dict(step=step,pos=position.tolist())
    return not record['effective_push_forbidden_intervention'] and record['effective_push_valid_increments']>=2 and float(np.linalg.norm(record['effective_push_net_delta_m']))>.02


def export(record):
    return dict(policy=POLICY,direct_hand_intervention=record.get('direct_hand_intervention',False),other_held_tool_intervention=record.get('other_held_tool_intervention',False),no_forbidden_intervention=not record.get('effective_push_forbidden_intervention',False),net_delta_m=list(record.get('effective_push_net_delta_m',[0.,0.,0.])),
        valid_increment_count=record.get('effective_push_valid_increments',0),
        contact_fragment_count=record.get('effective_push_fragment_count',0),
        delivery_chain_valid=record.get('delivery_chain_valid')is True,
        last_valid_transport_end_step=record.get('last_valid_transport_end_step'))
