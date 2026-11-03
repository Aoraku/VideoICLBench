from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab import engineering_front25_suffix as dispatcher
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def fixture(monkeypatch,fault=None):
    a,state,contacts=context('E20','A');calls=[]
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':268,'physics_ticks':27640}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    a.tip=lambda side:state['blue_supply_3']['pos'].copy()
    def act(p,side,token,mm=None,**kwargs):
        assert side=='left';calls.append((token,mm));p.c.steps+=1
        if token=='GRASP':
            state['blue_supply_3']['grasp'][0]=True
            contacts.update(frozenset(('blue_supply_3','left_finger'+str(i)))for i in(1,2))
        else:
            state['blue_supply_3']['pos'][2]+=.010
            if fault=='slip':state['blue_supply_3']['grasp'][0]=False
    monkeypatch.setattr(ExecutionDesignAuthor,'act',act)
    return a,state,contacts,calls


def test_A268_dispatch_runs_current_three_grasp_then_true_short_lift(monkeypatch):
    a,state,contacts,calls=fixture(monkeypatch);before=deepcopy(a.scene.spec)
    result=dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_a_grasp_lift_blue_from268','parameters':{}})
    assert result['segment_passed']and calls==[('GRASP',None)]*3+[('UP',10.)]*3
    assert a.scene.spec==before and not result['full_task_acceptance']


@pytest.mark.parametrize('fault',['step','tick','readback','mode','held'])
def test_A268_admission_rejects_other_boundaries_or_false_hold_context(monkeypatch,fault):
    a,state,contacts,calls=fixture(monkeypatch)
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=269
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=27740
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    else:state['blue_supply_3']['grasp'][0]=True
    with pytest.raises((ValueError,ToolExecutionError)):dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_a_grasp_lift_blue_from268','parameters':{}})
    assert not calls


def test_A268_first_real_lift_grip_failure_stops(monkeypatch):
    a,state,contacts,calls=fixture(monkeypatch,'slip')
    with pytest.raises(ToolExecutionError):dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_a_grasp_lift_blue_from268','parameters':{}})
    assert len(calls)==4
