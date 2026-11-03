"""Local segment scope and restored-state rejection tests."""
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_segments_e23_e24 import run_segment,_point
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def author(task='E24',revision='embodied50-execution-v3-20261102',engineering=True):
    return SimpleNamespace(scene=SimpleNamespace(spec=dict(id=task,execution_design=dict(revision=revision))),
                           control_report=dict(engineering_reference_only=engineering))


@pytest.mark.parametrize('segment,task',[('e24_pickup_lid_overhang','E24'),('e24_continue_lid_from_transit','E24'),('e24_push_from_contact_band','E24'),('e24_push_contact_short','E24'),('e23_hang_held_red','E23'),('e23_air_handoff_red','E23'),('e23_resume_air_handoff','E23'),('e23_handoff_at_current_station','E23')])
@pytest.mark.parametrize('revision,engineering',[('old',True),('embodied50-execution-v3-20261102',False)])
def test_rejects_unapproved_scope_before_physical_access(segment,task,revision,engineering):
    with pytest.raises(ToolExecutionError,match='independent engineering'):
        run_segment(author(task,revision,engineering),segment,{})


def test_unknown_segment_and_missing_parameters():
    with pytest.raises(ToolExecutionError,match='Unknown'):run_segment(author(),'other',{})
    with pytest.raises(ToolExecutionError,match='parameters'):run_segment(author(),'e24_pickup_lid_overhang',None)


@pytest.mark.parametrize('point',[None,[0,1],[0,1,float('nan')]])
def test_invalid_checkpoint_coordinate(point):
    with pytest.raises(ToolExecutionError):_point(point,'checkpoint')


def test_e24_rejects_actual_held_object(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_reference as module
    monkeypatch.setattr(module,'MeasuredE24Author',lambda _:SimpleNamespace(snapshot=lambda:({'red':dict(grasp=[False,True])},[])))
    with pytest.raises(ToolExecutionError,match='hands empty'):
        run_segment(author(),'e24_pickup_lid_overhang',{})


def test_e24_result_is_local_and_contains_no_native_score(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_reference as module
    from videoicl_isaaclab import execution_design_e24_lid as lid
    policy=SimpleNamespace(snapshot=lambda:({'red':dict(grasp=[False,False])},[]),
        c=SimpleNamespace(steps=17),start=10,operations=[dict(stage='real-public-action')],require_held=lambda *_:None)
    monkeypatch.setattr(module,'MeasuredE24Author',lambda _:policy)
    monkeypatch.setattr(lid,'pickup_lid_overhang',lambda _:({'actor':'lid'},'left'))
    result=run_segment(author(),'e24_pickup_lid_overhang',{})
    assert result['local_completed'] and result['actions']==7
    assert not ({'task_score','success','native_history','task_score_100'} & result.keys())


def test_e24_settled_entry_dispatches_to_only_the_bounded_settled_helper(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_reference as module
    from videoicl_isaaclab import execution_design_e24_lid as lid
    policy=object();seen=[]
    monkeypatch.setattr(module,'MeasuredE24Author',lambda _:policy)
    monkeypatch.setattr(lid,'approach_settled_lid1_and_push',lambda p,params:seen.append((p,params))or dict(local_completed=True))
    result=run_segment(author(),'e24_approach_settled_lid1_and_push',{})
    assert seen==[(policy,{})]and result['segment']=='e24_approach_settled_lid1_and_push'


def handoff_policy(receiver_grips=True,lose_receiver=False):
    import numpy as np
    holds={'left':False,'right':True};calls=[];positions={'right':np.array([-.236606746912,-.351350069046,1.122655448914]),'left':np.array([-.19,.3,.98])}
    cup={'pos':np.array([-.2,-.35,1.09]),'mat':np.eye(3)};c=SimpleNamespace(steps=199)
    p=SimpleNamespace(identity={'red':'red'},objects={'red':{'source_asset':{'sha256':'c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b'}}},
        start=199,c=c,operations=[],a=SimpleNamespace(tcp_rotation_task=lambda _:np.eye(3)))
    p.tip=lambda side:positions[side].copy()
    p.point=lambda ref:cup['pos']+np.asarray(ref['local'])
    p.snapshot=lambda:({'red':dict(cup,grasp=[holds['left'],holds['right']])},[])
    p.held=lambda ref,side:holds[side]
    def require(ref,side):
        if not holds[side]:raise ToolExecutionError('Actual grip lost on red')
    p.require_held=require
    def act(side=None,token='STILL',**kwargs):
        calls.append((side,token,dict(holds)));c.steps+=1
        if token=='RELEASE':holds[side]=False
        elif token=='GRASP':holds[side]=receiver_grips
        elif lose_receiver and holds['left']:holds['left']=False
    p.act=act;p.stage=lambda name:p.operations.append(dict(stage=name))
    return p,calls,holds,positions,cup


def patch_handoff_geometry(monkeypatch,p,positions,cup):
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    import numpy as np
    def move(policy,side,point,**kwargs):
        if kwargs.get('material'):cup['pos']=np.asarray(point)
        else:positions[side]=np.asarray(point)
    monkeypatch.setattr(module,'_air_move',move)
    monkeypatch.setattr(module,'_air_rotate_empty',lambda *a,**k:None)
    monkeypatch.setattr(module,'_air_check',lambda *a,**k:{})
    monkeypatch.setattr(module,'_air_finger_speed',lambda *a:0.)


@pytest.mark.parametrize('receiver_grips,lose_receiver',[(False,False),(True,True)])
def test_air_handoff_never_releases_old_hand_without_persistent_actual_new_grip(monkeypatch,receiver_grips,lose_receiver):
    from videoicl_isaaclab.execution_design_segments_e23_e24 import _air_handoff_red
    p,calls,holds,positions,cup=handoff_policy(receiver_grips,lose_receiver)
    patch_handoff_geometry(monkeypatch,p,positions,cup)
    with pytest.raises(ToolExecutionError,match='grip lost'):_air_handoff_red(p,{})
    assert not any(side=='right'and token=='RELEASE'for side,token,_ in calls)


def test_air_handoff_requires_real_dual_grip_before_old_release_and_returns_local_result(monkeypatch):
    from videoicl_isaaclab.execution_design_segments_e23_e24 import _air_handoff_red
    p,calls,holds,positions,cup=handoff_policy()
    patch_handoff_geometry(monkeypatch,p,positions,cup)
    result=_air_handoff_red(p,{})
    release=next(before for side,token,before in calls if side=='right'and token=='RELEASE')
    assert release=={'left':True,'right':True}
    assert holds=={'left':True,'right':False}
    assert result['local_completed'] and result['side']=='left'
    assert not ({'success','task_score_100','native_history'} & result.keys())


def test_air_move_aborts_after_first_nonadvancing_public_action(monkeypatch):
    import numpy as np
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    calls=[];p=SimpleNamespace(tip=lambda _:np.zeros(3),act=lambda *a,**k:calls.append((a,k)))
    monkeypatch.setattr(module,'_air_check',lambda *a,**k:{})
    monkeypatch.setattr(module,'_air_feedback',lambda *a:None)
    with pytest.raises(ToolExecutionError,match='failed to advance'):module._air_move(p,'left',[.01,0,0])
    assert len(calls)==1


def test_one_recovery_search_keeps_actual_q_and_original_endpoint_bounds():
    import numpy as np
    from videoicl_isaaclab.execution_design_segments_e23_e24 import _air_optimizer_seed
    q=np.array([2.8482658863]);limits=np.array([[-2.8972997665,2.8972997665]]);original=q.copy()
    with pytest.raises(ToolExecutionError,match='original joint margin'):_air_optimizer_seed(q,limits)
    lo,hi,seed,margin=_air_optimizer_seed(q,limits,True)
    np.testing.assert_array_equal(q,original)
    assert margin==pytest.approx(.0490338802) and lo[0]<seed[0]<hi[0]
    assert hi[0]==pytest.approx(limits[0,1]-.05)
    with pytest.raises(ToolExecutionError,match='actual20mrad'):
        _air_optimizer_seed(np.array([limits[0,1]-.019]),limits,True)


def test_resume_rotates_once_then_restores_standard_gate_and_current_tip(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    import numpy as np
    from videoicl_isaaclab.author_orientation import _axis_angle
    p,calls,holds,positions,cup=handoff_policy();checks=[];resumed=[];commands=[]
    original=p.act
    def act(*args,**kwargs):commands.append(kwargs);original(*args,**kwargs)
    p.act=act
    monkeypatch.setattr(module,'_air_check',lambda *a,**k:checks.append(k)or{})
    monkeypatch.setattr(module,'_air_feedback',lambda *a:None)
    monkeypatch.setattr(module,'_air_handoff_red',lambda policy,parameters:resumed.append(parameters)or dict(local_completed=True))
    result=module._air_resume_handoff(p,{'expected_right_tip_task_m':[999,999,999]})
    assert [(s,t)for s,t,_ in calls]==[('right','ROTATE_CCW')]
    assert checks[0]['recovery_start'] is True and 'recovery_start'not in checks[1]
    assert commands==[dict(degrees=10.)]
    axis,angle=_axis_angle(checks[0]['rotation'])
    assert np.degrees(angle)==pytest.approx(10.) and axis[2]>0
    assert resumed[0]['expected_right_tip_task_m']==positions['right'].tolist()
    assert result['segment']=='e23_resume_air_handoff'


def test_failed_post_recovery_gate_never_retries_or_starts_handoff(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    p,calls,holds,positions,cup=handoff_policy();count=[]
    def check(*args,**kwargs):
        count.append(kwargs)
        if len(count)>1:raise ToolExecutionError('actual margin still below50mrad')
        return {}
    monkeypatch.setattr(module,'_air_check',check);monkeypatch.setattr(module,'_air_feedback',lambda *a:None)
    monkeypatch.setattr(module,'_air_handoff_red',lambda *a:pytest.fail('must not continue after failed recovery'))
    with pytest.raises(ToolExecutionError,match='below50mrad'):module._air_resume_handoff(p,{})
    assert [(s,t)for s,t,_ in calls]==[('right','ROTATE_CCW')]


def test_resume_can_use_current_real_cup_center_and_skip_remaining_right_carry(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    p,calls,holds,positions,cup=handoff_policy();resumed=[]
    monkeypatch.setattr(module,'_air_check',lambda *a,**k:{})
    monkeypatch.setattr(module,'_air_feedback',lambda *a:None)
    monkeypatch.setattr(module,'_air_handoff_red',lambda policy,parameters:resumed.append(parameters)or dict(local_completed=True))
    module._air_resume_handoff(p,dict(handoff_at_current_cup_center=True,cup_station_task_m=[999,999,999]))
    assert resumed[0]['cup_station_task_m']==cup['pos'].tolist()
    assert [(s,t)for s,t,_ in calls]==[('right','ROTATE_CCW')]


def test_reviewed_receiver_twenty_mrad_does_not_modify_hard_limits_or_measured_q():
    import numpy as np
    from videoicl_isaaclab.execution_design_segments_e23_e24 import _air_optimizer_seed
    limits=np.array([[-1.762799859,1.762799859]]);q=np.array([-1.716708779]);original=q.copy()
    lo,hi,seed,margin=_air_optimizer_seed(q,limits,reserve=.02)
    np.testing.assert_array_equal(q,original);np.testing.assert_array_equal(seed,q)
    assert lo[0]==pytest.approx(limits[0,0]+.02)and margin==pytest.approx(.046091080)
    with pytest.raises(ToolExecutionError):_air_optimizer_seed(np.array([limits[0,0]+.019]),limits,reserve=.02)
    with pytest.raises(ToolExecutionError):_air_optimizer_seed(q,limits,reserve=.019)


def test_single_real_receiver_observation_still_requires_actual_dual_grip_before_release(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    p,calls,holds,positions,cup=handoff_policy(receiver_grips=False)
    patch_handoff_geometry(monkeypatch,p,positions,cup)
    with pytest.raises(ToolExecutionError,match='grip lost'):
        module._air_release_after_receiver_grip(p,single_real_observation=True)
    assert not any(side=='right'and token=='RELEASE'for side,token,_ in calls)


def test_larger_empty_translation_screen_keeps_actual_point35_joint_branch(monkeypatch):
    import numpy as np
    from videoicl_isaaclab import execution_design_segments_e23_e24 as module
    actual=np.zeros(3);calls=[];checks=[]
    p=SimpleNamespace(_engineering_translation_joint_increment=.35,tip=lambda _:actual.copy())
    def act(*args,**kwargs):actual[0]+=.002;calls.append(args)
    def check(*args,**kwargs):
        checks.append(kwargs)
        return dict(measured_joint_positions_rad=[0.]if len(checks)==1 else[.4])
    p.act=act;monkeypatch.setattr(module,'_air_check',check);monkeypatch.setattr(module,'_air_feedback',lambda *args:None)
    with pytest.raises(ToolExecutionError,match='0.35rad'):module._air_move(p,'left',[.01,0,0])
    assert len(calls)==1
