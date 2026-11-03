"""Bounded real public STILL to verify a near-plane E28 contact-buffer gap.

No contact, support flag, body state, or evaluator history is assigned. A source
or diagnostic author may wait up to three times per food at a native-supported
near-plane pose. Motion resumes only after native contact really returns.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def support_geometry(policy,tool,food):
    state=policy.snapshot()[0];body=state[food];blade=state[tool['actor']]
    obj=next(o for o in policy.spec['objects']if o['id']==food)
    local=np.asarray(blade['mat']).T@(np.asarray(body['pos'])-blade['pos'])
    relative=np.asarray(blade['mat']).T@np.asarray(body['mat'])
    sphere=obj.get('kind')=='sphere'
    radius=np.full(3,float(max(obj['size'])))if sphere else np.abs(relative)@np.asarray(obj['size'])
    lo=np.asarray(tool['support_bounds']['lower']);hi=np.asarray(tool['support_bounds']['upper'])
    normal=np.asarray(tool['support_normal_local'],float);normal/=np.linalg.norm(normal)
    extent=float(max(obj['size']))if sphere else float(np.abs(np.asarray(body['mat']).T@(np.asarray(blade['mat'])@normal))@np.asarray(obj['size']))
    gap=float(normal@local)-extent-float(tool['support_plane_offset'])
    return bool(np.all(local>=lo-radius-.003)and np.all(local<=hi+radius+.003)
        and (np.asarray(blade['mat'])@normal)[2]>.8 and abs(gap)<.012),local,gap


def _pose(policy,tool,food):
    state=policy.snapshot()[0];body=state[food];blade=state[tool['actor']]
    supported,local,gap=support_geometry(policy,tool,food)
    hand=any(body['grasp'])or any(policy.contact(food,f'{side}_finger{i}')for side in('left','right')for i in(1,2))
    return dict(supported=supported,local=local,plane_gap_m=gap,
        relative_rotation=np.asarray(blade['mat']).T@np.asarray(body['mat']),hand_contact=bool(hand),
        actual_blade_contact=policy.contact(food,tool['actor']),table_contact=policy.contact(food,'table'))


def ensure_contact(policy,food,tool,base_guard):
    from .execution_design_e28_source import _scope
    _scope(policy);base_guard();before=_pose(policy,tool,food)
    if before['hand_contact']:raise ToolExecutionError('E28 loaded food touched a robot hand')
    if before['actual_blade_contact']:
        return dict(actual_contact=True,recovered=False)
    if getattr(policy.a,'_engineering_e28_contact_hold',False)is True:
        if not(before['supported']and abs(before['plane_gap_m'])<=.001 and not before['table_contact']):
            raise ToolExecutionError('E28 missing contact is outside original native near-plane support geometry')
        from .execution_design_e28_native_contact import hold
        return hold(policy,food,tool,base_guard,lambda:_pose(policy,tool,food))
    counts=getattr(policy,'_e28_contact_wait_count',{})
    count=int(counts.get(food,0))
    eligible=(count<3 and before['supported']and abs(before['plane_gap_m'])<=.001
        and not before['hand_contact']and not before['table_contact'])
    if not eligible:raise ToolExecutionError('E28 missing blade contact lacks a native-supported near-plane recovery boundary')
    counts[food]=count+1;policy._e28_contact_wait_count=counts;old_stage=policy.a.stage
    step_before=policy.c.steps;tick_before=policy.c.physics_ticks
    policy.stage('e28-verify-near-plane-gap-with-real-STILL')
    try:policy.act()
    finally:policy.a.stage=old_stage
    base_guard();after=_pose(policy,tool,food)
    recovered=bool(after['actual_blade_contact']and not after['hand_contact']and after['supported']
        and abs(after['plane_gap_m'])<=.001 and not after['table_contact'])
    def serial(p):return {k:v.tolist()if isinstance(v,np.ndarray)else v for k,v in p.items()}
    row=dict(food=food,actual_public_action='STILL/STILL',step_before=step_before,step_after=policy.c.steps,
        physics_tick_before=tick_before,physics_tick_after=policy.c.physics_ticks,
        before=serial(before),after=serial(after),actual_native_contact_recovered=recovered,
        contact_or_evaluator_state_written=False,food_wait_number=count+1,maximum_waits_per_food=3)
    with(policy.a.out/'E28-contact-gap-recovery.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
    if not recovered:raise ToolExecutionError('E28 real STILL did not recover actual near-plane blade contact')
    return dict(actual_contact=True,recovered=True,public_actions=policy.c.steps-step_before)
