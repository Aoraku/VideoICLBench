"""Native near-limit fixture and actual-q public-step recovery protocol."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_segments_e15_recover as module


def test_native215_start_is_allowed_only_for_the_explicit_recovery_without_clipping_q():
    fixture=json.loads((Path(__file__).parent/'data/e15b-native-empty-approach-215.json').read_text())
    q=np.array(fixture['q']);limits=np.array(fixture['limits']);original=q.copy()
    assert module._margin(q,limits)==pytest.approx(.00018072128295898438)
    with pytest.raises(RuntimeError,match='original20mrad'):module._seed(q,limits,False)
    lo,hi,seed=module._seed(q,limits,True)
    np.testing.assert_array_equal(q,original)
    assert np.all(seed>lo)and np.all(seed<hi)
    assert np.min(np.minimum(seed-limits[:,0],limits[:,1]-seed))>=.0201
    q[-1]=limits[-1,1]
    with pytest.raises(RuntimeError,match='strictly inside hard'):module._seed(q,limits,True)


def test_dense_xy_certificate_keeps_every_segment_within_three_mm():
    start=np.array([-.0967488,-.1920322,.9585442]);goal=np.array([.065,-.03025,.9585442])
    rows=module._xy_targets(start,goal,np.eye(3));points=np.array([start]+[row['position']for row in rows])
    assert len(rows)==77 and np.max(np.linalg.norm(np.diff(points,axis=0),axis=1))<=.003
    np.testing.assert_allclose(points[-1],goal)


def public_policy(monkeypatch,*,advance=True):
    position=np.zeros(3);q=np.zeros(7);calls=[];prechecks=[]
    limits=np.tile([-3.,3.],(7,1))
    def capture(_):return dict(position=position.copy(),q=q.copy(),limits=limits),[]
    def act(left,token,mm):
        calls.append((left,token,mm))
        if advance:
            axis=('FWD','LEFT','UP').index(token);position[axis]+=mm/1000;q[0]+=.001
    p=SimpleNamespace(a=SimpleNamespace(act=act))
    monkeypatch.setattr(module,'_capture',capture)
    monkeypatch.setattr(module,'_readback',capture)
    def preflight(model,obstacles,point,rotation,**kwargs):
        prechecks.append((model['q'].copy(),np.asarray(point)-model['position']));return {}
    monkeypatch.setattr(module,'_preflight',preflight)
    return p,calls,prechecks


def test_every_three_mm_public_action_rechecks_current_actual_q(monkeypatch):
    p,calls,prechecks=public_policy(monkeypatch)
    rows=module._follow_xy(p,np.array([.006,0,0]),np.eye(3),lambda:None)
    assert len(rows)==2 and calls==[('STILL','FWD',3.),('STILL','FWD',3.)]
    assert prechecks[0][0][0]==0. and prechecks[1][0][0]==pytest.approx(.001)
    assert max(np.linalg.norm(step)for _,step in prechecks)<=.003


def test_first_nonadvancing_increment_is_never_retried(monkeypatch):
    p,calls,_=public_policy(monkeypatch,advance=False)
    with pytest.raises(RuntimeError,match='failed to advance'):
        module._follow_xy(p,np.array([.006,0,0]),np.eye(3),lambda:None)
    assert len(calls)==1


def test_native_refusal_stops_before_a_second_public_action(monkeypatch):
    p,calls,_=public_policy(monkeypatch)
    def rejected(_):raise RuntimeError('actual public controller refused')
    monkeypatch.setattr(module,'_readback',rejected)
    with pytest.raises(RuntimeError,match='controller refused'):
        module._follow_xy(p,np.array([.006,0,0]),np.eye(3),lambda:None)
    assert len(calls)==1


def test_old_e15_dispatcher_delegates_only_the_new_explicit_entry(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e15 as original
    seen=[];monkeypatch.setattr(module,'run_segment',lambda *args:seen.append(args)or dict(local_completed=True))
    a=SimpleNamespace();result=original.run_segment(a,'e15_b_recover214_and_approach_red',{})
    assert result==dict(local_completed=True)and seen==[(a,'e15_b_recover214_and_approach_red',{})]


def test_native1_continuation_delegates_without_replaying214_recovery(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e15 as original
    seen=[];monkeypatch.setattr(module,'run_segment',lambda *args:seen.append(args)or dict(local_completed=True))
    a=SimpleNamespace();original.run_segment(a,'e15_b_continue_recovered1_to_red',{})
    assert seen==[(a,'e15_b_continue_recovered1_to_red',{})]


def test_real_native1_wrist_has_original_reserve_and_needs_no_seed_projection():
    fixture=json.loads((Path(__file__).parent/'data/e15b-native-empty-approach-215.json').read_text())
    q=np.array([-.19343607127666473,.3478929400444031,.4171135723590851,-2.1320347785949707,
                -.3848789930343628,2.3838346004486084,2.857571840286255])
    limits=np.array(fixture['limits']);original=q.copy()
    assert module._margin(q,limits)==pytest.approx(.03972792625427246)
    _,_,seed=module._seed(q,limits,False)
    np.testing.assert_array_equal(q,original);np.testing.assert_array_equal(seed,q)


def test_small_wrist_uses_one_public_two_degree_action_and_measured_original_gates(monkeypatch):
    limits=np.tile([-3.,3.],(7,1));q=np.zeros(7);q[-1]=2.97
    before=dict(q=q.copy(),limits=limits,position=np.array([0.,0.,.958]),rotation=np.eye(3))
    after=dict(before,q=q.copy(),rotation=module._axis_rotation([0,0,1],np.deg2rad(2.)))
    after['q'][-1]=2.94;reads=[before,after];calls=[];guards=[]
    monkeypatch.setattr(module,'_readback',lambda _:(reads.pop(0),[]))
    monkeypatch.setattr(module,'_preflight',lambda *args,**kwargs:{})
    p=SimpleNamespace(a=SimpleNamespace(act=lambda *args,**kwargs:calls.append((args,kwargs))))
    actual,_,receipt=module._small_wrist_step(p,lambda:guards.append(True))
    assert calls==[(('STILL','ROTATE_CCW'),dict(rotation_deg=2.))]
    assert len(guards)==2 and receipt['actual_post_margin_rad']==pytest.approx(.06)
    assert actual is after and before['q'][-1]==2.97


def test_small_wrist_native_refusal_is_never_retried(monkeypatch):
    limits=np.tile([-3.,3.],(7,1));q=np.zeros(7);q[-1]=2.97
    model=dict(q=q,limits=limits,position=np.zeros(3),rotation=np.eye(3));reads=[];calls=[]
    def read(_):
        if reads:raise RuntimeError('actual native refusal')
        reads.append(True);return model,[]
    monkeypatch.setattr(module,'_readback',read);monkeypatch.setattr(module,'_preflight',lambda *a,**k:{})
    p=SimpleNamespace(a=SimpleNamespace(act=lambda *args,**kwargs:calls.append(args)))
    with pytest.raises(RuntimeError,match='actual native refusal'):module._small_wrist_step(p,lambda:None)
    assert calls==[('STILL','ROTATE_CCW')]


def test_segment_never_accepts_goal_or_scene_overrides():
    with pytest.raises(ValueError,match='no overrides'):
        module.run_segment(SimpleNamespace(),'e15_b_recover214_and_approach_red',{'goal':[0,0,0]})
