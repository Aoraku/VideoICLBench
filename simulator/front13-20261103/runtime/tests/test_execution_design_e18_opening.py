from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e18_opening as module
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError


def worker(monkeypatch,*,increment=.00133,lose=False):
    state=dict(q=.012);calls=[];c=SimpleNamespace(steps=0,
        _engineering_diagnostic_only=True,_engineering_checkpoint_readback_passed=True)
    a=SimpleNamespace(scene=SimpleNamespace(spec=dict(variant='A',seed=4201,execution_design=dict(condition='I'))),
        _engineering_resume_checkpoint=dict(diagnostic_only=True,source=dict(steps=4,physics_ticks=402)))
    w=SimpleNamespace(a=a,c=c,motion={'drawer':{'open_distance':.095}},roles={'drawer':{'open_threshold':.015}},operations=[])
    w.stage=lambda name:None;w.displacement=lambda _:state['q'];w.axis=lambda _:np.array([-1.,0,0])
    def act(side,token,mm):
        calls.append((side,token,mm));c.steps+=1;state['q']+=increment
    w.act=act;w.record_drawer_public_pull=lambda *args:dict(bilateral_contact=not lose,force=[1.6,1.5])
    def require(row,side):
        if not row['bilateral_contact']:raise MechanismExecutionError('actual contact lost')
    w._require_public_pull_grip=require
    monkeypatch.setattr(module,'prepare',lambda *args:dict(actual_measured_preparation=True))
    return w,calls


def test_continue_to_original95mm_not_merely_native15mm_threshold(monkeypatch):
    w,calls=worker(monkeypatch);result=module.run(w,{})
    assert .094<=result['measured_final_drawer_m']<=.096
    assert result['original_full_open_target_m']==.095 and result['original_open_tolerance_m']==.001
    assert len(calls)>50 and all(token=='BACK'and mm<=2. for _,token,mm in calls)
    assert result['full_drawer_open_completed']and not result['balls_or_full_task_completed']
    assert not({'success','task_score_100'}&result.keys())


def test_first_lost_real_grip_stops_continuous_opening(monkeypatch):
    w,calls=worker(monkeypatch,lose=True)
    with pytest.raises(MechanismExecutionError,match='actual contact lost'):module.run(w,{})
    assert len(calls)==1


def test_original_eighty_waypoint_bound_is_not_extended(monkeypatch):
    w,calls=worker(monkeypatch,increment=.0002)
    with pytest.raises(MechanismExecutionError,match='did not reach measured target'):module.run(w,{})
    assert len(calls)==80
