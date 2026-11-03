import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab import engineering_front25_suffix as dispatch
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def current(monkeypatch):
    a,state,contacts=context('E20','A',('red_supply_1','right'));calls=[]
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':543,'physics_ticks':55140}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    a.scene.robots['right'].data.joint_vel[:]=[[.02636,-.00669]]
    a.tip=lambda side:state['red_supply_1']['pos'].copy();z=float(state['red_supply_1']['pos'][2])
    def act(p,side,token,mm=None,**kwargs):
        assert side=='right'and token=='UP'and mm==10.;calls.append(token);p.c.steps+=1
        state['red_supply_1']['pos'][2]+=mm/1000.
        if state['red_supply_1']['pos'][2]>z+.004:contacts.discard(frozenset(('red_supply_1','fixture7')))
    monkeypatch.setattr(P,'act',act)
    return a,state,contacts,calls


def test_A543_observes_fast_finger_once_then_tests_real_grip_and_liftoff(monkeypatch):
    a,state,contacts,calls=current(monkeypatch)
    r=dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_a_lift_red_from543','parameters':{}})
    assert r['segment_passed']and len(calls)==1 and not r['full_task_acceptance']
    assert not a.control_report['e20_a_red_single_finger_speed_observation']['velocity_quiet_wait_required']
    assert frozenset(('red_supply_1','fixture7'))not in contacts


def test_functional_lift_allows_small_lateral_motion_but_rejects_actual_drop(monkeypatch):
    from videoicl_isaaclab.execution_design_e20_reference import verify_grip_during_small_liftoff
    a,state,contacts,calls=current(monkeypatch);p=P(a)
    original=P.act
    def lift(p,side,token,**kwargs):
        original(p,side,token,**kwargs);state['red_supply_1']['pos'][0]+=.009
    monkeypatch.setattr(P,'act',lift)
    verify_grip_during_small_liftoff(p,p.ref('red_supply_1'),'right',initial_measured_grips=2)
    assert calls==['UP']and p.a.control_report['e20_small_liftoffs'][0]['lateral_envelope_m']==.020
    a,state,contacts,calls=current(monkeypatch);p=P(a);original=P.act
    def drop(p,side,token,**kwargs):
        original(p,side,token,**kwargs);state['red_supply_1']['grasp'][1]=False
    monkeypatch.setattr(P,'act',drop)
    with pytest.raises(ToolExecutionError,match='Actual grip lost'):
        verify_grip_during_small_liftoff(p,p.ref('red_supply_1'),'right',initial_measured_grips=2)


def test_A7_exact_successful_lift_boundary_continues_original_placement_without_regrasp(monkeypatch):
    from videoicl_isaaclab import execution_design_e20_slots as slots
    a,state,contacts,calls=current(monkeypatch);a._engineering_resume_checkpoint={
        'diagnostic_only':True,'source':{'steps':7,'physics_ticks':702},'stage':'checkpoint-suffix-completed',
        'context':{'entry':'e20_a_lift_red_from543'}}
    contacts.discard(frozenset(('red_supply_1','fixture7')))
    phases=[]
    def place(p,name,actor,local,*,actual_held_side):
        assert name=='red_supply_1'and actual_held_side=='right';phases.append('place_actual_held')
        state[name]['grasp'][1]=False;contacts.add(frozenset((name,actor)))
    monkeypatch.setattr(P,'place',place);monkeypatch.setattr(P,'free_chip_slot',lambda *a:[0,0,0])
    monkeypatch.setattr(P,'local_stage',lambda p:phases.append('remaining'))
    monkeypatch.setattr(P,'package_stage',lambda p:phases.append('package'))
    monkeypatch.setattr(P,'deliver',lambda p:phases.append('deliver'))
    p=P(a)
    for r in p.d['local_regions']:
        for n in r['candidates'][:r['count']]:contacts.add(frozenset((n,r['actor'])))
    monkeypatch.setattr(slots,'_inside',lambda p,r,n:n in r['candidates'][:r['count']])
    result=dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_a_finish_after_red_lift7','parameters':{}})
    assert result['segment_passed']and phases==['place_actual_held','remaining','package','deliver']
    assert calls==[]and not result['full_task_acceptance']


@pytest.mark.parametrize('fault',['step','readback','contact','nonfinite'])
def test_A543_keeps_real_scope_joint_and_bilateral_checks(monkeypatch,fault):
    a,state,contacts,calls=current(monkeypatch)
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=542
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='contact':contacts.discard(frozenset(('red_supply_1','right_finger2')))
    else:a.scene.robots['right'].data.joint_vel[0,0]=np.nan
    with pytest.raises((ValueError,ToolExecutionError)):dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_a_lift_red_from543','parameters':{}})
    assert not calls
