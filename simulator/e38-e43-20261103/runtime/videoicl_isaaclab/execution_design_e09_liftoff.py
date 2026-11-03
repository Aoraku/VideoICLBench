"""E09-only public small-step lift with actual payload retention checks."""
import json
from contextlib import contextmanager
import numpy as np
from .realworld_tool_expert import ToolExecutionError


@contextmanager
def piece_transport_steps(policy,name):
    """Keep demonstrated retention step size during this one piece placement."""
    reviewed=(policy.task=='E09'
        and policy.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
        and policy.a.control_report.get('engineering_reference_only')
        and name in set(policy.d['target_members'])|set(policy.d.get('batch_members',{}).get('distractor',[])))
    if not reviewed:
        yield
        return
    previous=policy.max_mm;old_step=getattr(policy,'_e09_piece_transport_mm',None)
    try:
        policy.max_mm=min(25.,float(policy.a.scene.embodiment.config['control']['step_mm'][1]));policy._e09_piece_transport_mm=25.
        yield
    finally:
        policy.max_mm=previous
        if old_step is None:
            if hasattr(policy,'_e09_piece_transport_mm'):del policy._e09_piece_transport_mm
        else:policy._e09_piece_transport_mm=old_step


def lift_piece(policy, ref, side):
    if (policy.task!='E09' or policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or not policy.a.control_report.get('engineering_reference_only')):
        raise ValueError('E09 v3 independent engineering reference required')
    name=ref['actor'];origin=np.asarray(policy.frame({'actor':name})[0],float).copy()
    supports=[n for n in ['table',*(f'fixture{i}'for i,_ in enumerate(policy.spec.get('fixtures',[])))]if policy.contact(name,n)]
    tip0=np.asarray(policy.tip(side)).copy()
    for _ in range(60):
        policy.require_held(ref,side)
        policy.act(side,'UP',mm=2. if policy.frame({'actor':name})[0][2]-origin[2]<.010 else 25.)
        held=policy.held(ref,side);point=np.asarray(policy.frame({'actor':name})[0],float)
        delta=point-origin;remaining_support=[n for n in supports if policy.contact(name,n)]
        with (policy.a.out/'e09-piece-liftoff.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(actor=name,step=policy.c.steps,held=held,
                payload_delta_m=delta.tolist(),original_supports=supports,remaining_supports=remaining_support))+'\n')
        if not held:raise ToolExecutionError('Actual E09 piece grip lost during small-step liftoff')
        if delta[2]>=.070:
            if remaining_support:raise ToolExecutionError('E09 piece remains on initial support after lift')
            return
        if float(policy.tip(side)[2]-tip0[2])>.020 and delta[2]<.004:
            raise ToolExecutionError('E09 hand rises without actual payload lift')
    raise ToolExecutionError('E09 bounded small-step lift exhausted')
