"""E09 reference hand selection from both physical endpoints, before grasping.

This ranks candidate hands only; native reachability, clearance and contact
checks still govern every public action. It is not an IK feasibility claim.
"""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def rank_hands(source, destination, bases, preferred):
    source=np.asarray(source,float);destination=np.asarray(destination,float)
    if source.shape!=(3,) or destination.shape!=(3,) or not np.isfinite([source,destination]).all():
        raise ToolExecutionError('E09 requires finite measured transport endpoints')
    if preferred not in ('left','right') or set(bases)!=set(('left','right')):
        raise ToolExecutionError('E09 requires both actual robot bases')
    costs={}
    for side,base in bases.items():
        base=np.asarray(base,float)
        if base.shape!=(3,) or not np.isfinite(base).all():
            raise ToolExecutionError('E09 requires finite measured robot bases')
        costs[side]=max(float(np.linalg.norm(source[:2]-base[:2])),
                        float(np.linalg.norm(destination[:2]-base[:2])))
    other='right' if preferred=='left' else 'left'
    # Retain the source-side choice unless the complete route improves by
    # at least 20mm. No artificial reach radius or joint-limit relaxation.
    selected=other if costs[preferred]-costs[other]>.020 else preferred
    return selected,costs


def piece_hand(policy,name):
    if (policy.task!='E09' or
        policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102' or
        not policy.a.control_report.get('engineering_reference_only')):
        raise ToolExecutionError('E09 independent engineering reference required')
    preferred=policy.hand_for(name)
    groups=policy.d['unordered_expected_groups']
    indices=[i for i,group in enumerate(groups) if name in group]
    if not indices:return preferred
    if len(indices)!=1:raise ToolExecutionError('E09 piece requires one physical destination group')
    region=policy.d['local_regions'][indices[0]]
    source=np.asarray(policy.frame({'actor':name})[0],float)
    base,rotation=policy.frame({'actor':region['actor']})
    destination=np.asarray(base)+np.asarray(rotation)@((np.asarray(region['lower'])+region['upper'])/2)
    bases={side:policy.a.scene.world_to_task(robot.data.root_pos_w[0].detach().cpu().numpy())
           for side,robot in policy.a.scene.robots.items()}
    side,costs=rank_hands(source,destination,bases,preferred)
    policy.operations.append(dict(operation='e09_endpoint_hand_ranking',actor=name,
                                  selected=side,source_preferred=preferred,
                                  maximum_horizontal_distance_m=costs,
                                  reachability_asserted=False))
    return side
