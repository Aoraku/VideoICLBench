from copy import deepcopy
from types import SimpleNamespace as N
import numpy as np
import pytest
from test_execution_design_e07_reference import author,feasible
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_segments_e19_e25 import run_segment,approach_e25_piece


def acquisition(tmp_path,monkeypatch,variant,source_fork=False):
    from videoicl_isaaclab.execution_design_e07_reference import plan_transfers
    from videoicl_isaaclab import execution_design_e25_reference as palm
    a=author(tmp_path,variant=variant,task='E25');plan=plan_transfers(a,a.scene.spec['goals'],feasible)
    name='fork'if source_fork else'spoon'if variant=='B'else'knife';side='right'if variant=='B'or source_fork else'left'
    goal=next(g for g in plan if g['object']==name and (('_e07_after_relay'in g)==(variant=='C'and not source_fork)))
    state,contacts=a.c.snapshot();contacts.update(frozenset((n,'table'))for n in state)
    if variant=='C'and not source_fork:state[name]['pos'][:2]=goal['_e07_after_relay']['xy']
    position=np.array([-.2,-.03,.96]);calls=[];a.c.steps=10;a.carried_payload=None
    a.tip=lambda s:position.copy();a.floor_clear_tcp=lambda s:.81
    a.align_gripper_axis=lambda s,axis:calls.append('align')
    monkeypatch.setattr(palm,'prepare_source_palm',lambda *args:calls.append('palm'))
    def move(goals,**kwargs):
        delta=np.asarray(goals[side])-position
        if a.carried_payload==(name,side):state[name]['pos']+=delta
        position[:]=goals[side];calls.append(('move',goals,kwargs));a.c.steps+=1
    a.move_generated=move;a.prepare_generated_gripper=lambda s:calls.append('prepare_gripper')
    def act(left,right,*args):
        calls.append((left,right));a.c.steps+=1
        if (left if side=='left'else right)=='GRASP':
            state[name]['grasp'][('left','right').index(side)]=True
            contacts.update(frozenset((name,side+'_finger'+str(i)))for i in (1,2))
    a.act=act
    p=dict(side=side,goal=goal,approach_z=.92,expected_source_pose=deepcopy(state[name]))
    return a,p,state,contacts,calls,name


@pytest.mark.parametrize('variant,segment',[('B','e25_source_spoon_b'),('C','e25_relay_knife_c')])
def test_true_acquisition_tails_use_original_approach_and_no_score(tmp_path,monkeypatch,variant,segment):
    a,p,state,contacts,calls,name=acquisition(tmp_path,monkeypatch,variant);before=deepcopy(a.scene.spec)
    result=run_segment(a,segment,p)
    assert result['local_completed']and set(result)=={'local_completed','operations','active_actions'}
    assert calls[:2]==['align','palm']and len([c for c in calls if isinstance(c,tuple)and c[0]=='move'])==4
    assert a.carried_payload==(name,p['side'])and a.scene.spec==before


@pytest.mark.parametrize('fault',['held','pose','support','scope','hand','missing_context'])
def test_bad_checkpoint_context_rejects_before_any_public_operation(tmp_path,monkeypatch,fault):
    a,p,state,contacts,calls,name=acquisition(tmp_path,monkeypatch,'B')
    if fault=='held':state[name]['grasp'][0]=True
    if fault=='pose':state[name]['pos'][0]+=.003
    if fault=='support':contacts.clear()
    if fault=='scope':a.scene.spec['variant']='A'
    if fault=='hand':p['side']='left'
    if fault=='missing_context':p.pop('expected_source_pose')
    with pytest.raises((RuntimeError,ValueError,KeyError)):run_segment(a,'e25_source_spoon_b',p)
    assert not calls


def test_partial_contact_cannot_complete_segment(tmp_path,monkeypatch):
    a,p,state,contacts,calls,name=acquisition(tmp_path,monkeypatch,'B');real=a.act
    def one_finger(*args):real(*args);contacts.discard(frozenset((name,'right_finger2')))
    a.act=one_finger
    with pytest.raises(RuntimeError,match='bilateral'):run_segment(a,'e25_source_spoon_b',p)
    assert a.carried_payload is None


def test_a_return_restores_policy_context_without_world_or_score_write(tmp_path,monkeypatch):
    from videoicl_isaaclab import execution_design_generated_route as route
    a=author(tmp_path,task='E25');a.c.steps=50;a.carried_payload=None;position=np.array([.16,.18,.89]);a.tip=lambda s:position.copy()
    p=dict(home_xy={'left':[-.19,.3],'right':[-.19,-.3]},home_rotations={s:np.eye(3)for s in ('left','right')},clearance=.89)
    calls=[]
    def park(a,previous,chosen,home,clearance):calls.append((previous,chosen));position[:]=[*home['left'],clearance];a.c.steps+=1
    monkeypatch.setattr(route,'park_before_hand_switch',park)
    result=run_segment(a,'e25_empty_return_a',p)
    assert result['local_completed']and calls==[('left','right')]
    p['home_rotations']['left']=np.diag([-1.,-1.,1.])
    with pytest.raises(ValueError,match='Home context'):run_segment(a,'e25_empty_return_a',p)


def test_e19_uses_actual_held_source_and_original_policy_budget(monkeypatch):
    from videoicl_isaaclab import realworld_structural_expert as structural,execution_design_e19_reference as cap
    state={'water_bottle':dict(pos=np.array([.06,.15,.9]),mat=np.eye(3)),
           'cap_red':dict(pos=np.array([.06,.15,1.03]),mat=np.eye(3),grasp=[True,False])};held=[True]
    contacts={frozenset(('cap_red','left_finger'+str(i)))for i in (1,2)}
    a=N(scene=N(spec={'id':'E19','variant':'C','execution_design':{'revision':REVISION_V3,'source_sha256':source_sha256(REVISION_V3)}},embodiment=N(name='franka')),
        c=N(steps=430),smooth=False,_execution_design_reference_authorized=True,control_report={'engineering_reference_only':True})
    t=N(s={'caps':{'cap_red':{'center_local':[0,0,-.007]}},'mouths':{'water_bottle':{'center_local':[0,0,.095]}}},
        snapshot=lambda:(state,contacts),point=lambda ref:np.array([.06,.15,1.03]),body_point=lambda *args:np.array([.06,.15,.995]),operations=[])
    def require(*args):
        if not held[0]:raise RuntimeError('actual hold lost')
    t.require_held=require;monkeypatch.setattr(structural,'StructuralAuthor',lambda a:t)
    def gravity(*args,**kwargs):
        assert args==(t,'cap_red',p['ref'],'left',p['control'],'water_bottle')
        assert kwargs=={'entry_phase':'rim_release'}
        assert t.start==0 and t.limit==3000;t.operations.append({'operation':'real_release'});a.c.steps+=1
    monkeypatch.setattr(cap,'gravity_seat_red_water',gravity)
    p=dict(side='left',ref={'actor':'cap_red','local':[0,0,.003],'jaw_axis_local':[0,1,0]},control={'actor':'cap_red','local':[0,0,-.007]},policy_start=0,policy_limit=3000,expected_source_pose=deepcopy(state['water_bottle']))
    assert run_segment(a,'e19_release_red_water',p)==dict(local_completed=True,operations=[{'operation':'real_release'}],active_actions=1)
    held[0]=False
    with pytest.raises(RuntimeError,match='hold lost'):run_segment(a,'e19_release_red_water',p)
    p['policy_start']=1000
    with pytest.raises(ValueError,match='budget'):run_segment(a,'e19_release_red_water',p)


def test_unknown_segment_and_non_e25_approach_are_rejected():
    a=N(c=N(steps=0),scene=N(spec={'id':'E19'}))
    with pytest.raises(ValueError,match='Unknown'):run_segment(a,'unknown',{})
    with pytest.raises(ValueError,match='E25'):approach_e25_piece(a,'left',[0,0],.81,.92,.001)


@pytest.mark.parametrize('fault',[None,'grip','contact','policy','hand'])
def test_b_winding_segment_requires_actual_checkpoint_hold(tmp_path,monkeypatch,fault):
    from test_execution_design_e25_b_transport import author as held_author,goal
    from videoicl_isaaclab import execution_design_e25_b_transport as transport
    a,_=held_author(tmp_path);a.carried_payload=None;calls=[]
    p=dict(side='left',object='spoon',expected_source_pose=deepcopy(a.state['spoon']),goal=goal())
    if fault=='grip':a.state['spoon']['grasp'][0]=False
    elif fault=='contact':a.contacts.discard(frozenset(('spoon','left_finger2')))
    elif fault=='policy':a.carried_payload=('knife','right')
    elif fault=='hand':p['side']='right'
    def execute(*args):calls.append(args);a.c.steps+=1
    monkeypatch.setattr(transport,'rotate_transport_payload',execute)
    if fault:
        with pytest.raises((RuntimeError,ValueError)):run_segment(a,'e25_b_winding_transport',p)
        assert calls==[]
    else:
        result=run_segment(a,'e25_b_winding_transport',p)
        assert result==dict(local_completed=True,operations=[dict(operation='actual_held_winding_transport',actor='spoon',side='left')],active_actions=1)
        assert a.carried_payload==('spoon','left')and len(calls)==1


@pytest.mark.parametrize('empty_parameters',[False,True])
def test_b_winding_replans_admitted_current_hold_with_empty_or_stale_context(tmp_path,monkeypatch,empty_parameters):
    from test_execution_design_e25_b_transport import author as held_author,goal
    from videoicl_isaaclab import execution_design_e25_b_transport as transport
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    a,_=held_author(tmp_path);a.carried_payload=None;before=deepcopy(a.scene.spec);calls=[]
    old=deepcopy(a.state['spoon']);a.state['spoon']['pos'][0]+=.002376
    a.state['spoon']['mat']=_axis_rotation([0,0,1],np.deg2rad(2.54))@a.state['spoon']['mat']
    p={}if empty_parameters else dict(side='left',object='spoon',goal=goal(),expected_source_pose=old)
    def execute(a,name,side,selected):
        calls.append((name,side,selected,deepcopy(a.state[name])));a.c.steps+=1
    monkeypatch.setattr(transport,'rotate_transport_payload',execute)
    result=run_segment(a,'e25_b_winding_transport',p)
    assert result['local_completed']and len(calls)==1 and calls[0][:2]==('spoon','left')
    assert {k:v for k,v in calls[0][2].items()if k!='_e07_after_relay'}==a.scene.spec['goals'][0]
    np.testing.assert_array_equal(calls[0][3]['pos'],a.state['spoon']['pos'])
    assert a.scene.spec==before and a.carried_payload==('spoon','left')


@pytest.mark.parametrize('fault',[None,'lift_slip','lift_not_raised'])
def test_c_source_fork_segment_proves_actual_lift_without_task_score(tmp_path,monkeypatch,fault):
    a,p,state,contacts,calls,name=acquisition(tmp_path,monkeypatch,'C',source_fork=True);p['clearance']=.92
    original=a.move_generated
    def move(goals,**kwargs):
        before=state['fork']['pos'].copy();original(goals,**kwargs)
        if a.carried_payload==('fork','right'):
            if fault=='lift_slip':state['fork']['grasp'][1]=False
            elif fault=='lift_not_raised':state['fork']['pos'][:]=before
    a.move_generated=move
    if fault:
        with pytest.raises(RuntimeError,match='fork lift'):run_segment(a,'e25_source_fork_c',p)
    else:
        result=run_segment(a,'e25_source_fork_c',p)
        assert result['local_completed']and set(result)=={'local_completed','operations','active_actions'}
        assert [r['operation']for r in result['operations']]==['actual_source_acquisition','actual_held_source_lift']
        assert a.carried_payload==('fork','right')and state['fork']['grasp'][1]
