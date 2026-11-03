from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab import execution_design_e20_b_reseat as candidate
from videoicl_isaaclab import engineering_front25_suffix as dispatcher
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def fixture(monkeypatch,fault=None):
    a,state,contacts=context('E20','B',('blue_supply_1','right'));calls=[]
    state['blue_supply_1']['pos']=np.array([-.20519231,-.11488144,.83756989])
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':2,'physics_ticks':202}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    def act(p,side,token,mm=None,**kwargs):
        calls.append((side,token,mm));p.c.steps+=1
        if token=='DOWN':
            if fault=='support':contacts.discard(frozenset(('blue_supply_1','fixture3')))
        else:
            state['blue_supply_1']['pos'][2]+=.003 if fault=='rise'else .010
            if fault=='slip':state['blue_supply_1']['grasp'][1]=False
            if fault=='xy':state['blue_supply_1']['pos'][0]+=.007
    monkeypatch.setattr(ExecutionDesignAuthor,'act',act)
    return a,state,contacts,calls


def test_B2_uses_one_real_pad_reseat_then_original_short_lift(monkeypatch):
    a,state,contacts,calls=fixture(monkeypatch);before=deepcopy(a.scene.spec)
    result=dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_b_reseat_lift_blue_from2','parameters':{}})
    assert result['segment_passed']and not result['full_task_acceptance']
    assert calls==[('right','DOWN',3.)]+[('right','UP',10.)]*3
    assert a.scene.spec==before and result['operations'][-1]['actual_payload_rise_m']==pytest.approx(.030)


@pytest.mark.parametrize('fault',['step','tick','readback','mode','diagnostic','no_grip'])
def test_B2_requires_the_exact_admitted_actual_hold(monkeypatch,fault):
    a,state,contacts,calls=fixture(monkeypatch)
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=3
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=302
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    else:state['blue_supply_1']['grasp'][1]=False
    with pytest.raises((ToolExecutionError,ValueError)):dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_b_reseat_lift_blue_from2','parameters':{}})
    assert not calls


@pytest.mark.parametrize('fault,count',[('support',1),('slip',2),('xy',2),('rise',4)])
def test_B2_stops_at_first_real_support_grip_or_lift_failure(monkeypatch,fault,count):
    a,state,contacts,calls=fixture(monkeypatch,fault)
    with pytest.raises(ToolExecutionError):candidate.run_segment(a,'e20_b_reseat_lift_blue_from2',{})
    assert len(calls)==count


@pytest.mark.parametrize('actor,side,expects_reseat',[('blue_supply_1','right',True),('blue_supply_3','left',False)])
def test_full_B_reuses_the_single_validated_pad_reseat_only_for_right_blue1(monkeypatch,actor,side,expects_reseat):
    from videoicl_isaaclab.execution_design_e20_reference import finish_chip_grip
    a,state,contacts,calls=fixture(monkeypatch);p=ExecutionDesignAuthor(a);calls.clear()
    def act(policy,hand,token,mm=None,**kwargs):
        calls.append((hand,token,mm));policy.c.steps+=1
        state[actor]['grasp'][0 if hand=='left'else 1]=True
        contacts.update(frozenset((actor,hand+'_finger'+str(i)))for i in(1,2))
    if side=='left':state['blue_supply_1']['grasp'][1]=False
    monkeypatch.setattr(ExecutionDesignAuthor,'act',act)
    finish_chip_grip(p,{'actor':actor},side)
    assert calls==[(side,'GRASP',None)]*3+([(side,'DOWN',3.)]if expects_reseat else[])
