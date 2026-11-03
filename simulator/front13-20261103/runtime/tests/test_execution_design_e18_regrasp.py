from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e18_regrasp as module
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError


def worker(monkeypatch,*,stuck_release=False,lose_pull=False):
    calls=[];state=dict(axial=.00886691800476965,q=[.00125,.00192],travel=.0093297,grip=True)
    c=SimpleNamespace(steps=0,_engineering_diagnostic_only=True,_engineering_checkpoint_readback_passed=True,
        action_feedback=lambda:{'control_feedback':{'left':{}}})
    a=SimpleNamespace(scene=SimpleNamespace(spec=dict(variant='A',seed=4201,execution_design=dict(condition='I'))),
        _engineering_resume_checkpoint=dict(diagnostic_only=True,source=dict(steps=2,physics_ticks=202)))
    w=SimpleNamespace(a=a,c=c,min_mm=.5,operations=[],motion={'drawer':{'open_distance':.095}})
    w.stage=lambda name:None;w.axis=lambda role:np.array([-1.,0,0]);w.displacement=lambda role:state['travel']
    w.tip=lambda side:np.array([-state['axial']-state['travel'],0.,.913])
    def observation(*args):
        return dict(tcp_axial_offset_m=state['axial'],finger_q_m=list(state['q']),bilateral_contact=state['grip'])
    w._public_pull_observation=observation;w.record_drawer_public_pull=observation
    def require(row,side):
        if not row['bilateral_contact']:raise MechanismExecutionError('actual bilateral grip lost')
    w._require_public_pull_grip=require
    def act(side,token,mm=1.):
        c.steps+=1;calls.append((token,mm))
        if token=='RELEASE' and not stuck_release:state.update(q=[.04,.04],grip=False)
        elif token=='FWD':state['axial']-=mm/1000
        elif token=='GRASP':state.update(q=[.0014,.0014],grip=True)
        elif token=='BACK':
            state['travel']+=.001
            if lose_pull:state['grip']=False
    w.act=act
    def follow(*args):act('left','DOWN',mm=.5);return dict(performed=True)
    w.follow_drawer_pad_z_once=follow
    monkeypatch.setattr(module,'_hand_clearance',lambda *args,**kwargs:dict(actual_geometry_checked=True))
    return w,calls


def test_one_real_release_inward_regrasp_and_two_limited_pulls(monkeypatch):
    w,calls=worker(monkeypatch);result=module.run(w,{})
    assert [token for token,_ in calls]==['RELEASE','FWD','GRASP','DOWN','BACK','DOWN','BACK']
    assert calls[1][1]==pytest.approx(1.084949875992324)
    assert calls.count(('GRASP',1.))==1 and result['actions']==7
    assert result['local_completed'] and not result['full_drawer_open_completed']
    assert not({'success','task_score_100'}&result.keys())


def test_unopened_actual_fingers_prevent_inward_move(monkeypatch):
    w,calls=worker(monkeypatch,stuck_release=True)
    with pytest.raises(MechanismExecutionError,match='actual release'):module.run(w,{})
    assert calls==[('RELEASE',1.)]


def test_first_real_lost_grip_prevents_second_pull(monkeypatch):
    w,calls=worker(monkeypatch,lose_pull=True)
    with pytest.raises(MechanismExecutionError,match='actual bilateral'):module.run(w,{})
    assert [token for token,_ in calls]==['RELEASE','FWD','GRASP','DOWN','BACK']


def test_native3_finishes_measured_real_closing_once_without_repeating_regrasp(monkeypatch):
    w,calls=worker(monkeypatch)
    w.a._engineering_resume_checkpoint['source']=dict(steps=3,physics_ticks=302)
    old=w._public_pull_observation
    w._public_pull_observation=lambda role,side,phase:(dict(bilateral_contact=False,
        finger_q_m=[.0053196,.0053213],finger_qd_m_s=[-.0266035,-.0266116])if phase==0 else old(role,side,phase))
    result=module.finish_closing(w,{})
    assert [token for token,_ in calls]==['GRASP','DOWN','BACK','DOWN','BACK']
    assert result['local_completed']and result['maximum_public_actions']==6


def test_zero_force_without_real_closing_does_not_create_a_grip(monkeypatch):
    w,calls=worker(monkeypatch)
    w.a._engineering_resume_checkpoint['source']=dict(steps=3,physics_ticks=302)
    w._public_pull_observation=lambda *args:dict(bilateral_contact=False,finger_q_m=[.005,.005],finger_qd_m_s=[0.,0.])
    with pytest.raises(MechanismExecutionError,match='neither real closing'):module.finish_closing(w,{})
    assert calls==[]
