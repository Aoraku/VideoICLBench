"""Source-initial engineering E37 with actual turning, catching and release.

The revised collision cooking must be explicit. Native scores and thread
history are read by the original evaluator, never supplied by this author.
"""
from copy import deepcopy
import json
import math
import numpy as np


def place_caught_screw(p, screw, ref, side, destination, driver_ref,
                       main_side='left'):
    """Use the original destination, then ordinary gravity release above it."""
    from .execution_design_e37_regrip import _plan, _execute, _hand
    from .realworld_tool_expert import ToolExecutionError
    current=np.asarray(p.snapshot()[0][screw]['mat'],float)
    desired=np.asarray(destination['rotation'],float)
    if desired.shape!=(3,3):
        from .realworld_structural_expert import _rotation
        desired=_rotation(desired)
    hand=_hand(p,side)
    target=np.asarray(destination['point_task'],float)+[0.,0.,.04]
    delta=desired@current.T
    control=p.point(ref)
    tcp=target+delta@(p.tip(side)-control)
    guard=lambda:(p.require_held(driver_ref,main_side),p.require_held(ref,side))
    p.stage('e37-caught-screw-to-original-destination-'+screw)
    plan=_plan(p,side,tcp,delta@hand)
    if plan.get('status')!='Success'or plan.get('verified')is not True:
        raise ToolExecutionError('No verified caught-screw path to original target')
    _execute(p,side,plan,guard)
    p.stage('e37-original-target-real-screw-release-'+screw)
    p.release(ref,side)
    p.move(side,p.tip(side)+[0.,0.,.07],
           lambda:p.require_held(driver_ref,main_side),tolerance=.006)
    p.wait(2)
    state=p.snapshot()[0][screw]
    if any(state['grasp'])or not p.contact(screw,'table'):
        raise ToolExecutionError('Screw has not actually released onto original table')
    return dict(screw=screw,released=True,actual_table_support=True,
                native_position=np.asarray(state['pos']).tolist(),
                original_target=destination['point_task'])


def solve(author):
    from .realworld_structural_expert import StructuralAuthor
    from .realworld_tool_expert import ToolExecutionError
    from .execution_design_e37_regrip import _scope
    from .execution_design_e37_source_left import acquire_left
    from .execution_design_e37_planned_approach import run as approach
    from .execution_design_e37_planned_slot import run as seat
    from .execution_design_e37_unscrew import finish_role
    from .execution_design_e37_free_screw import catch_and_clear
    from .execution_design_e37_table_guard import guard_actions
    p=StructuralAuthor(author);_scope(p)
    if getattr(p.c,'_engineering_diagnostic_only',False):
        raise ValueError('This entry starts from the original source scene')
    driver=next(o for o in p.spec['objects']if o['id']=='driver')
    cooking=driver.get('reviewed_collision_settings',{})
    if cooking.get('approximation')!='sdf'or cooking.get('sdf_resolution')!=384:
        raise ValueError('Explicit source-faithful E37 SDF384 driver required')
    author._engineering_e37_source_author=True
    prefix=acquire_left(author)
    ref=dict(actor='driver',**deepcopy(p.geometry['driver_grasp']))
    side='left';roles=(['left'],['right'],['left','right'])[p.index]
    results=[]
    with guard_actions(p)as observer:
        p._e37_table_readback=observer['snapshot']
        for role in roles:
            entry=p.s['screw_roles'][role]
            fixture=entry['fixture']
            axis=p.frame(fixture['ref'])[1]@np.asarray(fixture['axis_local'],float)
            axis/=np.linalg.norm(axis)
            head=lambda entry=entry:p.body_point(
                dict(actor=entry['screw']),entry['head_socket_local'])
            approach(p,ref,side,entry,axis,head,slot_sign=-1,engage=False)
            seat(p,ref,side,entry,axis,head,torque_degrees=0.)
            turned=finish_role(p,ref,side,entry,axis,head)
            def free(entry=entry):
                m=p.c.evaluator.screw_measure(entry)
                return m['overlap']<=1e-6 and m['fixture_contact']==0
            screw_ref=p.ref(entry['screw'])
            caught=catch_and_clear(p,screw_ref,ref,free,axis,main_side=side)
            placed=place_caught_screw(p,entry['screw'],screw_ref,caught,
                p.geometry['removed_screw_placements'][role],ref,main_side=side)
            results.append(dict(role=role,actual_turn=turned,actual_placement=placed))
    p.wait(2)
    report=dict(task='E37',variant=p.variant,source_initial_episode=True,
        diagnostic_only=False,prefix=prefix,roles=results,
        actions=p.c.steps-p.start,execution_finished=True,
        physics_success_not_asserted=True,native_score_unchanged=True)
    (author.out/'E37-source-actual-workflow.private.json').write_text(
        json.dumps(report,default=lambda x:x.tolist(),indent=2)+'\n')
    return report
