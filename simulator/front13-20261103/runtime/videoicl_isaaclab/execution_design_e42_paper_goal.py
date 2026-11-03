"""Engineering stop on the real rectangular marked paper, not its centre.

TabletopScene spawns every E42 zone as an 84mm rectangular paper Pad; shape is
an ink identity marker on that paper. The native paper-region predicate stays
unchanged. This reference uses the full source sphere bounds plus 2mm inset.
"""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def reached(policy,name,inset_m=.002):
    if (policy.task!='E42' or not policy.a.control_report.get('engineering_reference_only')
            or policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'):
        raise ToolExecutionError('E42 v3 engineering paper target only')
    zone=next(z for z in policy.spec['zones']if z['id']==('circle','triangle','square')[policy.index])
    if zone.get('anchor_object')or zone.get('marker')is None or zone.get('hidden'):
        raise ToolExecutionError('Actual source marked rectangular paper required')
    obj=next(o for o in policy.spec['objects']if o['id']==name)
    if obj.get('kind')!='sphere':raise ToolExecutionError('Actual source sphere paper bounds required')
    state,contacts=policy.snapshot();ball=state[name]
    if any(ball['grasp'])or frozenset((name,'table'))not in contacts:
        return False
    if any(frozenset((name,f'{side}_finger{i}'))in contacts for side in('left','right')for i in(1,2)):
        return False
    radius=float(max(obj['size']));center=np.asarray(ball['pos'])+np.asarray(ball['mat'])@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    return bool(np.all(np.abs(center[:2]-np.asarray(zone['xy']))+radius<=np.asarray(zone['half_size'])-float(inset_m)))
