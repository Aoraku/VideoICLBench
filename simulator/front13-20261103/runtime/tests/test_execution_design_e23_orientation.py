"""CPU geometry and reject-only IK tests; no physical acceptance assertion."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e23_orientation import axial_rotations,align_cup_axis
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError,_axis_rotation

@pytest.mark.parametrize('axis',[[0,0,1],[0,0,-1],[.3,.8,-.2],[-.5,.1,.2]])
def test_each_candidate_has_same_cup_axis_with_only_free_twist(axis):
    current=_axis_rotation([1,0,0],.2);desired=np.asarray(axis,float);desired/=np.linalg.norm(desired)
    choices=axial_rotations(current,[0,0,1],desired)
    assert len(choices)==6
    for degrees,rotation in choices:
        np.testing.assert_allclose(rotation@np.array([0,0,1.]),desired,atol=1e-10)
        np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-10)
        assert np.linalg.det(rotation)==pytest.approx(1.)

def policy():
    state={'red':{'mat':np.eye(3)}};calls=[]
    p=SimpleNamespace(task='E23',a=SimpleNamespace(tcp_rotation_task=lambda side:np.eye(3)),
        c=object(),snapshot=lambda:(state,set()),tip=lambda side:np.array([.1,.2,.94]),operations=[],
        require_held=lambda ref,side:calls.append(('guard',ref['actor'])),stage=lambda name:calls.append(('stage',name)))
    def rotate(name,side,target):calls.append(('public_rotate',side,target.copy()));state[name]['mat']=target.copy()
    p.rotate_actor=rotate
    return p,state,calls

def candidate(margin=.12,reachable=True,distance=2):
    return dict(kinematically_reachable=reachable,position_error_m=.0001,orientation_error_rad=.005,
                minimum_joint_margin_rad=margin,joint_distance_rad=distance)

def test_readonly_ik_margin_then_public_motion_and_actual_axis_check():
    p,state,calls=policy();observed=[]
    def probe(a,c,side,targets):
        observed.extend(targets)
        return [candidate(.0001),candidate(.20),candidate(.30,distance=1),candidate(reachable=False),candidate(.15),candidate(.06)]
    align_cup_axis(p,'red','right',[0,0,1],[.5,.8,-.1],probe)
    assert len(observed)==6 and all(x['position']==[.1,.2,.94]for x in observed)
    assert p.operations[-1]['chosen_index']==2 and p.operations[-1]['chosen_twist_deg']==-60
    assert not p.operations[-1]['collision_verified'] and not p.operations[-1]['native_success_asserted']
    assert [x[0]for x in calls].count('public_rotate')==1

def test_no_margin_or_incomplete_candidates_do_not_actuate():
    for probe in (lambda *args:[candidate(.01)]*6,lambda *args:[candidate()]*3):
        p,state,calls=policy()
        with pytest.raises(ToolExecutionError):align_cup_axis(p,'red','right',[0,0,1],[1,0,0],probe)
        np.testing.assert_array_equal(state['red']['mat'],np.eye(3))
        assert not any(x[0]=='public_rotate'for x in calls)

def test_target_claim_without_actual_rotation_rejected():
    p,state,calls=policy();p.rotate_actor=lambda *args:None
    with pytest.raises(ToolExecutionError,match='does not match real branch'):
        align_cup_axis(p,'red','right',[0,0,1],[1,0,0],lambda *args:[candidate()]*6)

def test_unreachable_and_nonfinite_candidates_cannot_be_selected():
    p,state,calls=policy();rows=[candidate(reachable=False)]*6;rows[2]=candidate(margin=float('nan'))
    with pytest.raises(ToolExecutionError,match='No measured'):
        align_cup_axis(p,'red','right',[0,0,1],[1,0,0],lambda *args:rows)


def incremental_policy(tmp_path):
    p,state,calls=policy();p.max_deg=10.;p.min_deg=.5;p.a.out=tmp_path
    p.a.tcp_rotation_task=lambda side:state['red']['mat'].copy()
    axes={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
    def act(side,token,degrees):
        calls.append(('public_act',token,degrees));i,sign=axes[token]
        state['red']['mat']=_axis_rotation(np.eye(3)[i],np.radians(sign*degrees))@state['red']['mat']
    p.act=act
    return p,state,calls


def test_incremental_axis_alignment_does_not_demand_irrelevant_twist(tmp_path):
    import json
    from videoicl_isaaclab.execution_design_e23_orientation import align_cup_axis_incremental
    p,state,calls=incremental_policy(tmp_path);state['red']['mat']=_axis_rotation([0,0,1],1.3)
    target=np.array([.4,.6,.5]);target/=np.linalg.norm(target)
    align_cup_axis_incremental(p,'red','right',[0,0,1],target,lambda a,c,s,targets:[candidate(.15,distance=.1)for _ in targets])
    assert np.dot(state['red']['mat'][:,2],target)>np.cos(np.radians(4))
    assert not any(x[0]=='public_rotate'for x in calls)
    actions=[x for x in calls if x[0]=='public_act'];assert actions and all(x[2]<=5 for x in actions)
    rows=[json.loads(x)for x in(tmp_path/'e23-axis-steps.private.jsonl').read_text().splitlines()]
    assert len(rows)==2*len(actions) and rows[0]['chosen_index']is not None
    assert rows[-1]['actual_native_state']is True


@pytest.mark.parametrize('margin,distance',[(.001,.1),(.2,2.)])
def test_incremental_rejects_unsafe_margin_or_disconnected_endpoint_before_motion(tmp_path,margin,distance):
    import json
    from videoicl_isaaclab.execution_design_e23_orientation import align_cup_axis_incremental
    p,state,calls=incremental_policy(tmp_path)
    with pytest.raises(ToolExecutionError,match='near-neighbor'):
        align_cup_axis_incremental(p,'red','right',[0,0,1],[.4,.6,.5],lambda a,c,s,targets:[candidate(margin,distance=distance)for _ in targets])
    assert not any(x[0]=='public_act'for x in calls)
    assert json.loads((tmp_path/'e23-axis-steps.private.jsonl').read_text())['chosen_index']is None


def test_incremental_requires_actual_motion_and_persists_failed_tracking(tmp_path):
    from videoicl_isaaclab.execution_design_e23_orientation import align_cup_axis_incremental
    p,state,calls=incremental_policy(tmp_path);p.act=lambda *args,**kwargs:None
    with pytest.raises(ToolExecutionError,match='stopped improving'):
        align_cup_axis_incremental(p,'red','right',[0,0,1],[1,0,0],lambda a,c,s,targets:[candidate(.15,distance=.1)for _ in targets])
    assert len((tmp_path/'e23-axis-steps.private.jsonl').read_text().splitlines())==10


def test_incremental_tcp_rotation_preserves_measured_nonidentity_grip_transform(tmp_path):
    from videoicl_isaaclab.execution_design_e23_orientation import align_cup_axis_incremental
    p,state,calls=incremental_policy(tmp_path)
    grip=_axis_rotation([1,0,0],.8)@_axis_rotation([0,0,1],-.6)
    p.a.tcp_rotation_task=lambda side:state['red']['mat']@grip
    observed=[]
    def inspect(a,c,side,targets):
        actual_cup=state['red']['mat'];actual_tcp=actual_cup@grip
        for target in targets:
            delta=np.asarray(target['rotation'])@actual_tcp.T
            # A real wrist delta must act identically on the held cup, while
            # preserving the measured cup-to-hand rotation.
            np.testing.assert_allclose((delta@actual_cup)@grip,target['rotation'],atol=1e-10)
            angle=np.arccos(np.clip((np.trace(delta)-1)/2,-1,1))
            assert angle==pytest.approx(np.radians(5))
            observed.append(delta)
        return [candidate(.15,distance=.1)for _ in targets]
    align_cup_axis_incremental(p,'red','right',[0,0,1],[.4,.5,.7],inspect)
    assert observed


def test_incremental_actual_grip_loss_stops_after_first_public_action(tmp_path):
    from videoicl_isaaclab.execution_design_e23_orientation import align_cup_axis_incremental
    p,state,calls=incremental_policy(tmp_path);acted=[];original=p.act
    def act(*args,**kwargs):original(*args,**kwargs);acted.append(True)
    p.act=act
    def guard(*args):
        if acted:raise ToolExecutionError('Actual bilateral grip lost')
    p.require_held=guard
    with pytest.raises(ToolExecutionError,match='grip lost'):
        align_cup_axis_incremental(p,'red','right',[0,0,1],[1,0,0],lambda a,c,s,targets:[candidate(.15,distance=.1)for _ in targets])
    assert len(acted)==1


@pytest.mark.parametrize('failure_phase',['before-axis-increment','after-axis-increment'])
def test_measured_clearance_callback_stops_before_next_public_action(tmp_path,failure_phase):
    from videoicl_isaaclab.execution_design_e23_orientation import align_cup_axis_incremental
    p,state,calls=incremental_policy(tmp_path);phases=[]
    def clearance(phase):
        phases.append(phase)
        if phase==failure_phase:raise ToolExecutionError('Uncertain actual full-arm clearance')
    with pytest.raises(ToolExecutionError,match='full-arm clearance'):
        align_cup_axis_incremental(p,'red','right',[0,0,1],[1,0,0],
            lambda a,c,s,targets:[candidate(.15,distance=.1)for _ in targets],clearance_guard=clearance)
    actual=[x for x in calls if x[0]=='public_act']
    assert len(actual)==(0 if failure_phase.startswith('before') else 1)
    assert phases[-1]==failure_phase
