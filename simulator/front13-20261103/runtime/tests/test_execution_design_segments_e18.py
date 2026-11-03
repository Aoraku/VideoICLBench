"""Local E18 admission and actual grip/progress protocol tests."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_support import VERSION,SOURCE_SHA
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError
from videoicl_isaaclab.execution_design_segments_e18 import run_segment


def author(**changes):
    spec=dict(id='E18',execution_design=dict(revision='embodied50-execution-v3-20261102'),
        e18_support_layout=dict(version=VERSION,source_cabinet_sha256=SOURCE_SHA,lift_m=.035))
    spec.update(changes)
    return SimpleNamespace(scene=SimpleNamespace(spec=spec),control_report=dict(engineering_reference_only=True))


def fake_worker(monkeypatch,*,increase=.001,force=2.,speed=0.,contact=True):
    import videoicl_isaaclab.execution_design_e18_reference as module
    a=author();c=SimpleNamespace(steps=1,contact_forces={frozenset(('cabinet/left',f'left_finger{i}')):force for i in (1,2)},action_feedback=lambda:{'control_feedback':{'left':{}}})
    data=SimpleNamespace(joint_pos=np.array([[.0014,.0014]]),joint_vel=np.array([[speed,speed]]))
    robot=SimpleNamespace(data=data,find_joints=lambda _:([0,1],['panda_finger_joint1','panda_finger_joint2']))
    a.scene.robots={'left':robot};calls=[];travel=0.
    w=SimpleNamespace(a=a,c=c,start_steps=1,roles={'drawer':{'contact_body':'cabinet/left'}},operations=[])
    def acquire(role):calls.append(('acquire',role));c.steps+=10;return 'left'
    def act(side=None,token='STILL',mm=1.):
        nonlocal travel
        calls.append((side,token,mm));c.steps+=1
        if token=='BACK':travel+=increase
    w.acquire=acquire;w.act=act;w.stage=lambda name:w.operations.append(dict(stage=name));w.displacement=lambda _:travel
    w.axis=lambda _:np.array([-1.,0,0]);w.touching=lambda *a,**k:contact
    w.motion={'drawer':{'open_distance':.095}}
    def hold(role,side):w.act(side,'GRASP');return dict(actual_public_grasp=True)
    w.prepare_drawer_public_pull=hold;w.record_drawer_public_pull=lambda *args:dict(actual_native_readback=True)
    w._public_pull_observation=lambda *args:dict(actual_native_readback=True)
    w._require_public_pull_grip=lambda *args:None
    def z_follow(role,side):w.act(side,'DOWN',mm=.5);return dict(performed=True,requested_mm=.5)
    w.follow_drawer_pad_z_once=z_follow
    monkeypatch.setattr(module,'E18MeasuredAuthor',lambda _,**kwargs:w)
    return a,w,calls


def test_segment_uses_original_acquire_then_only_one_short_public_pull(monkeypatch):
    a,w,calls=fake_worker(monkeypatch)
    r=run_segment(a,'e18_acquire_and_short_pull',{})
    assert calls==[('acquire','drawer'),('left','BACK',3.)]
    assert len(r['grip_observations'])==1 and w._engineering_single_handle_observation
    assert r['measured_displacement_increase_m']==pytest.approx(.001)
    assert r['local_completed'] and not({'success','task_score_100','native_history'}&r.keys())


def test_held_checkpoint_short_pull_uses_current_real_grip_without_reacquire(monkeypatch):
    import videoicl_isaaclab.execution_design_e18_reference as module
    a,w,calls=fake_worker(monkeypatch);constructor=[]
    monkeypatch.setattr(module,'E18MeasuredAuthor',lambda _,**kwargs:constructor.append(kwargs)or w)
    result=run_segment(a,'e18_continue_held_short_pull',{'side':'left'})
    assert constructor==[dict(allow_existing_e18_drawer=True)]
    assert calls==[('left','BACK',3.)]
    assert result['segment']=='e18_continue_held_short_pull' and result['actions']==1


def test_existing_travel_constructor_gate_requires_the_explicit_debug_entry():
    from videoicl_isaaclab.realworld_mechanism_expert import _Author
    a=author(variant='A',semantic={});a.c=SimpleNamespace()
    a.scene.spec['engineering_checkpoint_resume']=dict(diagnostic_only=True,entry='different_entry')
    with pytest.raises(MechanismExecutionError,match='explicit E18 held short-pull checkpoint'):
        _Author(a,allow_existing_e18_drawer=True)


def test_native166_segment_runs_only_three_real_grasp_pull_pairs(monkeypatch):
    a,w,calls=fake_worker(monkeypatch);a._engineering_resume_checkpoint={'source':{'steps':166}}
    result=run_segment(a,'e18_hold166_then_three_short_pulls',{})
    assert calls==[('left','GRASP',1.),('left','BACK',3.)]*3
    assert result['actions']==result['maximum_public_actions']==6
    assert len(result['pulls'])==3 and not result['full_drawer_open_completed']
    assert result['original_full_open_target_m']==.095


def test_repeated_native166_pulls_stop_first_lost_grip_and_never_run_third_pair(monkeypatch):
    a,w,calls=fake_worker(monkeypatch);a._engineering_resume_checkpoint={'source':{'steps':166}}
    act=w.act;count=[]
    def lose_on_second(*args,**kwargs):
        act(*args,**kwargs)
        if args[1]=='BACK':
            count.append(True)
            if len(count)==2:w.touching=lambda *a,**k:False
    w.act=lose_on_second
    with pytest.raises(MechanismExecutionError,match='bilateral'):
        run_segment(a,'e18_hold166_then_three_short_pulls',{})
    assert len(calls)==4


def test_follow166_entry_uses_measured162_calibration_and_at_most_two_three_action_groups(monkeypatch):
    a,w,calls=fake_worker(monkeypatch);a._engineering_resume_checkpoint={'source':{'steps':166}}
    def follow(role,side):
        assert w._e18_pull_reference[('drawer','left')]['source_action']==162
        w.act(side,'FWD',mm=1.);w.act(side,'GRASP');return dict(public_follow_mm=1.)
    w.prepare_drawer_public_pull=follow
    result=run_segment(a,'e18_follow166_then_two_short_pulls',{})
    assert calls==[('left','FWD',1.),('left','GRASP',1.),('left','BACK',3.)]*2
    assert result['actions']==result['maximum_public_actions']==6 and len(result['pulls'])==2
    assert not result['full_drawer_open_completed']


def test_native2_vertical_follow_then_two_two_mm_pulls_has_no_axial_replay_or_full_claim(monkeypatch):
    a,w,calls=fake_worker(monkeypatch)
    a.scene.spec.update(variant='A',seed=4201);a.scene.spec['execution_design']['condition']='I'
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':2,'physics_ticks':202}}
    w.c._engineering_diagnostic_only=True;w.c._engineering_checkpoint_readback_passed=True
    result=run_segment(a,'e18_zfollow2_then_two_2mm_pulls',{})
    assert calls==[('left','DOWN',.5),('left','GRASP',1.),('left','BACK',2.),('left','GRASP',1.),('left','BACK',2.)]
    assert result['actions']==5 and result['maximum_public_actions']==6
    assert len(result['pulls'])==2 and not result['full_drawer_open_completed']
    assert result['original_full_open_target_m']==.095


def test_native4_repeats_one_measured_z_follow_before_each_two_mm_pull(monkeypatch):
    a,w,calls=fake_worker(monkeypatch)
    a.scene.spec.update(variant='A',seed=4201);a.scene.spec['execution_design']['condition']='I'
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':4,'physics_ticks':402}}
    w.c._engineering_diagnostic_only=True;w.c._engineering_checkpoint_readback_passed=True
    result=run_segment(a,'e18_zfollow4_before_two_2mm_pulls',{})
    assert calls==[('left','DOWN',.5),('left','GRASP',1.),('left','BACK',2.)]*2
    assert result['actions']==6 and len(result['pulls'])==2
    assert all(row['z_follow']['performed']for row in result['pulls'])
    assert not result['full_drawer_open_completed']


def test_native4_follow_stops_on_first_real_grip_rejection(monkeypatch):
    a,w,calls=fake_worker(monkeypatch)
    a.scene.spec.update(variant='A',seed=4201);a.scene.spec['execution_design']['condition']='I'
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':4,'physics_ticks':402}}
    w.c._engineering_diagnostic_only=True;w.c._engineering_checkpoint_readback_passed=True
    def reject(*args):raise MechanismExecutionError('actual grip rejected')
    w._require_public_pull_grip=reject
    with pytest.raises(MechanismExecutionError,match='actual grip rejected'):
        run_segment(a,'e18_zfollow4_before_two_2mm_pulls',{})
    assert calls==[('left','DOWN',.5),('left','GRASP',1.)]


@pytest.mark.parametrize('kwargs,match',[({'force':.001},'force'),({'contact':False},'bilateral')])
def test_unverified_grip_aborts_before_any_pull(monkeypatch,kwargs,match):
    a,w,calls=fake_worker(monkeypatch,**kwargs)
    with pytest.raises(MechanismExecutionError,match=match):run_segment(a,'e18_acquire_and_short_pull',{})
    assert calls==[('acquire','drawer')]


def test_failed_single_short_pull_is_not_retried(monkeypatch):
    a,w,calls=fake_worker(monkeypatch,increase=.00049)
    with pytest.raises(MechanismExecutionError,match='below0.5mm'):run_segment(a,'e18_acquire_and_short_pull',{})
    assert sum(token=='BACK'for _,token,*_ in calls)==1


def test_fast_finger_motion_is_recorded_without_extra_stability_wait(monkeypatch):
    a,w,calls=fake_worker(monkeypatch,speed=.03)
    result=run_segment(a,'e18_acquire_and_short_pull',{})
    assert result['grip_observations'][0]['finger_velocity_m_s']==[.03,.03]
    assert calls==[('acquire','drawer'),('left','BACK',3.)]


def test_actual_joint_progress_is_retained_with_honest_post_pull_grip_loss(monkeypatch):
    a,w,calls=fake_worker(monkeypatch);act=w.act
    def lost_after_pull(*args,**kwargs):
        act(*args,**kwargs)
        w.touching=lambda *a,**k:False
        w.c.contact_forces={key:0. for key in w.c.contact_forces}
    w.act=lost_after_pull
    result=run_segment(a,'e18_acquire_and_short_pull',{})
    assert result['local_completed'] and result['measured_displacement_increase_m']>=.0005
    assert result['post_pull_grip']['grip_present'] is False
    assert result['post_pull_grip']['contact_forces_n']==[0.,0.]


def test_native_controller_refusal_is_never_hidden_by_joint_progress(monkeypatch):
    a,w,calls=fake_worker(monkeypatch)
    w.c.action_feedback=lambda:{'control_feedback':{'left':{'status':'blocked'}}}
    with pytest.raises(MechanismExecutionError,match='controller rejected'):run_segment(a,'e18_acquire_and_short_pull',{})
    assert calls==[('acquire','drawer'),('left','BACK',3.)]


def test_original_35mm_support_scope_is_required_before_acquire():
    for a in [author(id='E24'),author(e18_support_layout={})]:
        with pytest.raises(ValueError):run_segment(a,'e18_acquire_and_short_pull',{})
    a=author();a.control_report['engineering_reference_only']=False
    with pytest.raises(ValueError):run_segment(a,'e18_acquire_and_short_pull',{})


def test_no_full_workflow_or_unknown_local_entry():
    with pytest.raises(ValueError):run_segment(author(),'full_drawer_and_ball',{})
