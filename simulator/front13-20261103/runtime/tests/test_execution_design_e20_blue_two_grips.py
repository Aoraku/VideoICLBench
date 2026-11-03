import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab import execution_design_e20_reference as reference
from videoicl_isaaclab import execution_design_e20_b_held98 as suffix
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_B_left_two_actual_grips_start_real_lift_before_overturning_third(monkeypatch):
    a,state,contacts=context('E20','B');p=P(a);calls=[]
    def act(p,side,token,**kwargs):
        calls.append(token);state['blue_supply_1']['grasp'][0]=True
        contacts.update(frozenset(('blue_supply_1','left_finger'+str(i)))for i in(1,2))
    monkeypatch.setattr(P,'act',act)
    monkeypatch.setattr(reference,'verify_grip_during_small_liftoff',lambda p,r,s,**kw:calls.append(('lift',s,kw)))
    reference.finish_chip_grip(p,p.ref('blue_supply_1'),'left')
    assert calls==['GRASP','GRASP',('lift','left',{'initial_measured_grips':1})]


def test_B98_other_boundary_rejects_before_any_manipulation():
    a,state,contacts=context('E20','B',('blue_supply_1','left'))
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':99,'physics_ticks':9902}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    with pytest.raises(ToolExecutionError,match='B98'):suffix.run_segment(a,'e20_b_lift_and_finish_from_left98',{})


@pytest.mark.parametrize('fault',[None,'finger','geometry'])
def test_B98_true_held_chip_can_already_clear_rail_but_keeps_bilateral_geometry(monkeypatch,fault):
    a,state,contacts=context('E20','B',('blue_supply_1','left'))
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':98,'physics_ticks':9802}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    contacts.discard(frozenset(('blue_supply_1','fixture3')))
    if fault=='finger':contacts.discard(frozenset(('blue_supply_1','left_finger2')))
    elif fault=='geometry':a.scene.spec['fixtures'][3]['size'][0]+=.01
    class ReachedActualLift(Exception):pass
    monkeypatch.setattr(reference,'verify_grip_during_small_liftoff',lambda *args,**kw:(_ for _ in()).throw(ReachedActualLift()))
    with pytest.raises(ReachedActualLift if fault is None else ToolExecutionError):
        suffix.run_segment(a,'e20_b_lift_and_finish_from_left98',{})
