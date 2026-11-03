"""E37 engineering: physically catch an already freed screw from the side.

The driving hand remains on the driver until the opposite hand genuinely
holds the screw. No fixture/thread state or score is written here.
"""
import math
import numpy as np


def catch_and_clear(p,screw_ref,driver_ref,free_predicate,axis,*,
                    main_side='left',extra_guard=None):
    from .execution_design_e37_regrip import (
        _scope,_record,_plan,_execute,_opposed_close,_hand,hold_measured_arm)
    from .realworld_tool_expert import ToolExecutionError
    _scope(p)
    if main_side not in('left','right')or not callable(free_predicate):
        raise ValueError('Explicit driving hand and original native free predicate required')
    catch_side='right'if main_side=='left'else'left'
    axis=np.asarray(axis,float)
    if axis.shape!=(3,)or not np.isfinite(axis).all()or np.linalg.norm(axis)<1e-12:
        raise ValueError('Actual source screw axis required')
    axis=axis/np.linalg.norm(axis)
    driver=driver_ref['actor'];screw=screw_ref['actor']

    def original_free():
        if extra_guard is not None:extra_guard()
        if not free_predicate():
            raise ToolExecutionError('Screw is not free under the original source predicate')

    def driver_held():original_free();p.require_held(driver_ref,main_side)
    def both_held():driver_held();p.require_held(screw_ref,catch_side)

    p.stage('e37-real-'+catch_side+'-free-screw-side-catch')
    with hold_measured_arm(p,main_side):
        p.act(catch_side,'RELEASE');driver_held();accepted=None
        for yaw in(0.,math.pi/2,-math.pi/2,math.pi):
            approach=np.array([math.cos(yaw),math.sin(yaw),0.])
            finger=np.array([-approach[1],approach[0],0.])
            for sign in(1.,-1.):
                hand=np.column_stack((np.cross(sign*finger,approach),sign*finger,approach))
                proposal=_plan(p,catch_side,p.point(screw_ref),hand)
                if proposal.get('status')=='Success'and proposal.get('verified')is True:
                    accepted=proposal;break
            if accepted is not None:break
        if accepted is None:
            raise ToolExecutionError('No full-world side approach to the original free screw')
        _execute(p,catch_side,accepted,driver_held)
        _opposed_close(p,screw_ref,catch_side,driver_held,start=.018,minimum=.001)
        both_held()

    p.stage('e37-real-driving-tool-clear-of-caught-screw')
    with hold_measured_arm(p,catch_side):
        hand=_hand(p,main_side)
        # The already accepted physical driver/screw contact is the only
        # optional pair; the job's reviewed profile must also authorize it.
        proposal=_plan(p,main_side,p.tip(main_side)+axis*.05,hand,
                       driver=driver,screw=screw)
        _execute(p,main_side,proposal,both_held)
        base=p.a.scene.world_to_task(
            p.a.scene.robots[main_side].data.root_pos_w[0].detach().cpu().numpy())
        accepted=None
        for dx,dy,z in((.20,-.15,1.25),(.20,.15,1.25),(.05,-.20,1.28),(.05,.20,1.28)):
            target=np.array([base[0]+dx,base[1]+dy,z])
            proposal=_plan(p,main_side,target,hand)
            if proposal.get('status')=='Success'and proposal.get('verified')is True:
                accepted=proposal;break
        if accepted is None:raise ToolExecutionError('No full-world held-driver pickup clearance')
        _execute(p,main_side,accepted,both_held)
    both_held()
    _record(p,'E37-free-screw-real-catch-completed.private.jsonl',dict(
        main_side=main_side,catch_side=catch_side,screw=screw,driver=driver,
        original_free_predicate=True,actual_both_grips=True,state_written=False))
    return catch_side
