from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_card_direct import prove_bilateral_lift
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_contact_without_actual_card_motion_cannot_certify_grasp():
    p=SimpleNamespace(frame=lambda ref:(np.array([0.,0.,.8]),np.eye(3)),require_held=lambda ref,side:None,
                      act=lambda *args,**kwargs:None)
    with pytest.raises(ToolExecutionError,match='physically lift card25mm'):
        prove_bilateral_lift(p,{},'left')


def test_bilateral_contact_lost_after_first_lift_stops_before_further_actions():
    calls=[];held=[True]
    def require(ref,side):
        if not held[0]:raise ToolExecutionError('Actual grip lost')
    def act(side,token,mm):
        calls.append((side,token,mm));held[0]=False
    p=SimpleNamespace(frame=lambda ref:(np.array([0.,0.,.8]),np.eye(3)),require_held=require,act=act)
    with pytest.raises(ToolExecutionError,match='Actual grip lost'):
        prove_bilateral_lift(p,{},'left')
    assert calls==[('left','UP',2.)]


def test_toe_refinement_does_not_accept164um_above_table_without_motion():
    from videoicl_isaaclab.execution_design_card_direct import refine_open_toe_height
    a=SimpleNamespace(finger_geometry=lambda side:dict(lowest_z_task_m=.800164))
    calls=[];p=SimpleNamespace(a=a,act=lambda *args,**kw:calls.append((args,kw)))
    with pytest.raises(ToolExecutionError,match='50um table clearance'):
        refine_open_toe_height(p,'left',.8)
    assert len(calls)==5


def test_small_first_lift_retains_actual_motion_and_every_step_grip_checks():
    position=np.array([0.,0.,.8]);calls=[];checks=[];callbacks=[]
    def act(side,token,mm):calls.append(mm);position[2]+=mm/1000.
    p=SimpleNamespace(frame=lambda ref:(position.copy(),np.eye(3)),require_held=lambda *args:checks.append(True),act=act)
    result=prove_bilateral_lift(p,{},'left',initial_lift_step_mm=.5,after_action=callbacks.append)
    assert calls[:4]==[.5]*4 and all(mm==2. for mm in calls[4:])
    assert result>=.025 and len(checks)==2*len(calls) and callbacks==list(range(1,len(calls)+1))
