from copy import deepcopy
from types import SimpleNamespace as N
import json
import numpy as np
import pytest
from test_execution_design_e07_reference import author
from videoicl_isaaclab.execution_design_e25_a_receiver import settled_receiver_rotation
from videoicl_isaaclab.execution_design_segments_e19_e25 import run_segment
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def fixture(tmp_path):
    a=author(tmp_path,task='E25');state,contacts=a.c.snapshot();contacts.add(frozenset(('knife','table')));a.c.steps=0;a.carried_payload=None
    q=np.array([[0.,0.,0.,-1.,0.,2.,0.]]);limits=np.array([[[-3.,3.]]*7]);a.scene.robots['left'].data.joint_pos=q;a.scene.robots['left'].data.soft_joint_pos_limits=limits
    a.scene.robots['left'].find_joints=lambda pattern:(list(range(7)),[f'panda_joint{i}'for i in range(1,8)])
    tip=np.array([-.28,-.03,.92]);a.tip=lambda side:tip.copy();a.tcp_rotation_task=lambda side:np.diag([1.,-1.,-1.]);a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(tip[2]-.01));a.tip_array=tip
    return a,state,contacts


def feasible(a,c,side,targets):
    return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.5,candidate_joints_rad=a.scene.robots['left'].data.joint_pos[0].tolist(),position_error_m=0.,orientation_error_rad=0.)]


def test_settled_five_degree_knife_uses_actual_axis_without_source_mutation(tmp_path):
    a,state,contacts=fixture(tmp_path);state['knife']['mat']=_axis_rotation([1,0,0],np.deg2rad(5.05855));before=deepcopy(a.scene.spec);old=state['knife']['mat'].copy();desired=a.tcp_rotation_task('left')
    result=settled_receiver_rotation(a,'left','knife',desired,feasible)
    np.testing.assert_allclose(abs(result[:,1]@(state['knife']['mat']@np.array([0,1,0]))),1.,atol=1e-10)
    assert a.scene.spec==before;np.testing.assert_array_equal(state['knife']['mat'],old)
    assert np.linalg.det(result)==pytest.approx(1.)
    log=json.loads((tmp_path/'e25-a-settled-receiver-axis.private.jsonl').read_text())
    assert log['endpoint_screen_passed']and not log['actuation_performed']and not log['native_passed']


@pytest.mark.parametrize('fault',['support','held','source','ik','branch','limit'])
def test_settled_axis_candidate_fails_closed_without_public_actions(tmp_path,fault):
    a,state,contacts=fixture(tmp_path);state['knife']['mat']=_axis_rotation([1,0,0],np.deg2rad(5.05855));probe=feasible
    if fault=='support':contacts.clear()
    elif fault=='held':state['knife']['grasp'][0]=True
    elif fault=='source':next(o for o in a.scene.spec['objects']if o['id']=='knife')['source_asset']['sha256']='bad'
    else:
        def probe(a,c,s,t):
            row=feasible(a,c,s,t)[0]
            if fault=='ik':row['kinematically_reachable']=False
            elif fault=='branch':row['candidate_joints_rad'][0]+=1.
            else:row['minimum_joint_margin_rad']=0.
            return [row]
    with pytest.raises((RuntimeError,ValueError)):settled_receiver_rotation(a,'left','knife',a.tcp_rotation_task('left'),probe)
    assert a.c.steps==0


def test_existing_acceptable_receiver_axis_does_not_request_extra_ik_or_rotation(tmp_path):
    a,state,contacts=fixture(tmp_path);state['knife']['mat']=_axis_rotation([1,0,0],np.deg2rad(4.9));calls=[];desired=a.tcp_rotation_task('left')
    result=settled_receiver_rotation(a,'left','knife',desired,lambda *args:calls.append(args))
    np.testing.assert_array_equal(result,desired);assert calls==[]


def placement(tmp_path,monkeypatch,fault=None):
    from videoicl_isaaclab import execution_design_e25_reference as reference
    a,state,contacts=fixture(tmp_path);calls=[];a.floor_clear_tcp=lambda side:.81
    monkeypatch.setattr(reference,'prepare_receiver',lambda *args:calls.append('receiver'))
    def act(left='STILL',right='STILL',*args,**kwargs):
        calls.append(left);a.c.steps+=1
        if left=='GRASP'and fault!='no_grip':
            state['knife']['grasp'][0]=True;contacts.update(frozenset(('knife','left_finger'+str(i)))for i in (1,2))
        elif left=='RELEASE':
            state['knife']['grasp'][0]=False
            contacts.difference_update(frozenset(('knife','left_finger'+str(i)))for i in (1,2))
            if fault!='no_support':contacts.add(frozenset(('knife','table')))
    a.act=act
    def move(goals,**kwargs):
        delta=np.asarray(goals['left'])-a.tip_array
        if a.carried_payload==('knife','left'):
            state['knife']['pos']+=delta
            if goals['left'][2]>.98:contacts.discard(frozenset(('knife','table')))
            if fault=='slip':state['knife']['grasp'][0]=False
        a.tip_array[:]=goals['left'];a.act()
    a.move_generated=move;a.prepare_generated_gripper=lambda side:None
    a.rotate_held=lambda *args:calls.append('original_goal_rotation')
    a.release_generated=lambda side:a.act('RELEASE','STILL')
    return a,state,contacts,calls


def test_short_terminal_entry_really_grasps_and_places_original_knife_goal(tmp_path,monkeypatch):
    a,state,contacts,calls=placement(tmp_path,monkeypatch);before=deepcopy(a.scene.spec);other={n:deepcopy(b)for n,b in state.items()if n!='knife'}
    result=run_segment(a,'e25_a_place_settled_relay_knife',{})
    assert result['local_completed']and set(result)=={'local_completed','operations','active_actions'}
    goal=next(g for g in a.scene.spec['goals']if g['object']=='knife');zone=next(z for z in a.scene.spec['zones']if z['id']==goal['target'])
    np.testing.assert_allclose(state['knife']['pos'][:2],zone['xy'],atol=1e-10)
    assert calls.count('GRASP')==1 and calls.count('RELEASE')==1 and 'original_goal_rotation'in calls
    assert not any(state['knife']['grasp'])and frozenset(('knife','table'))in contacts and a.carried_payload is None
    assert a.scene.spec==before
    for n,b in other.items():np.testing.assert_array_equal(state[n]['pos'],b['pos'])


@pytest.mark.parametrize('fault',['no_grip','slip','no_support'])
def test_short_entry_cannot_report_completion_without_real_grip_and_support(tmp_path,monkeypatch,fault):
    a,state,contacts,calls=placement(tmp_path,monkeypatch,fault)
    with pytest.raises(RuntimeError):run_segment(a,'e25_a_place_settled_relay_knife',{})
    if fault!='no_support':assert 'RELEASE'not in calls


def test_full_receiver_preparation_executes_small_actual_axis_correction(tmp_path,monkeypatch):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_receiver
    from videoicl_isaaclab import execution_design_drawer_ik_probe as ik
    a,state,contacts=fixture(tmp_path);state['knife']['mat']=_axis_rotation([1,0,0],np.deg2rad(5.05855));r=np.diag([1.,-1.,-1.]);calls=[]
    a.tcp_rotation_task=lambda side:r.copy();a.move_generated=lambda goals:a.tip_array.__setitem__(slice(None),goals['left'])
    a.c.action_feedback=lambda:{'control_feedback':{'left':{'status':'reached','joint_limit_names':[]}}}
    def act(left,right,rotation_deg):
        nonlocal r
        assert right=='STILL';calls.append(left)
        axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}[left]
        r=_axis_rotation(axis,np.deg2rad(rotation_deg))@r
    a.act=act;monkeypatch.setattr(ik,'inspect',feasible)
    prepare_receiver(a,'left','knife',{'_e07_after_relay':{},'_e25_receiver_rotation_task':r.tolist()},.89,[-.28,-.03])
    assert 1<=len(calls)<=3 and a.control_report['e25_receiver_orientation']['actual_error_rad']<np.deg2rad(.75)


def admitted_held73(tmp_path,monkeypatch,fault=None):
    a,state,contacts,calls=placement(tmp_path,monkeypatch,fault)
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':73,'physics_ticks':7311}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    state['knife']['grasp'][0]=True
    contacts.update(frozenset(('knife','left_finger'+str(i)))for i in(1,2))
    return a,state,contacts,calls


def test_a73_clearance_contains_whole_actual_knife_sweep_without_state_changes(tmp_path,monkeypatch):
    from videoicl_isaaclab.execution_design_e25_a_receiver import held_rotation_clearance
    a,state,contacts,calls=admitted_held73(tmp_path,monkeypatch)
    state['knife']['pos']=np.array([-.2052477896,-.0286369324,.8391351676])
    state['knife']['mat']=np.array([[.9335743785,.0515861511,.3546514213],[-.0162169337,.9946532845,-.1019891575],[-.3580164313,.0894631147,.9294194579]])
    a.tip_array[:]=[-.2849229276,-.025752984,.8849112368]
    before=deepcopy(state);original=deepcopy(a.scene.spec)
    height=held_rotation_clearance(a);report=a.control_report['e25_a_knife_rotation_clearance']
    assert report['actual_tcp_to_bounds_radius_m']>.18
    assert height>=report['obstacle_top_z_m']+report['actual_tcp_to_bounds_radius_m']+.025
    assert height>.99 and calls==[]and a.scene.spec==original
    for name,body in state.items():
        np.testing.assert_array_equal(body['pos'],before[name]['pos']);np.testing.assert_array_equal(body['mat'],before[name]['mat'])


def test_native_a73_lifts_real_knife_before_original_rotation_without_regrasp(tmp_path,monkeypatch):
    a,state,contacts,calls=admitted_held73(tmp_path,monkeypatch);old=a.rotate_held
    def rotate(*args):
        assert frozenset(('knife','table'))not in contacts
        assert a.tip('left')[2]>.98
        old(*args)
    a.rotate_held=rotate
    result=run_segment(a,'e25_a_place_held_knife_from73',{})
    assert result['local_completed']and 'GRASP'not in calls and calls.count('RELEASE')==1
    assert 'original_goal_rotation'in calls and not any(state['knife']['grasp'])
    assert frozenset(('knife','table'))in contacts


@pytest.mark.parametrize('fault',['source_step','source_tick','diagnostic','readback','mode','seed','one_finger','no_grip','parameters'])
def test_a73_native_boundary_and_real_hold_are_required(tmp_path,monkeypatch,fault):
    a,state,contacts,calls=admitted_held73(tmp_path,monkeypatch);p={}
    if fault=='source_step':a._engineering_resume_checkpoint['source']['steps']=74
    elif fault=='source_tick':a._engineering_resume_checkpoint['source']['physics_ticks']=7411
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='seed':a.scene.spec['seed']=4202
    elif fault=='one_finger':contacts.discard(frozenset(('knife','left_finger2')))
    elif fault=='no_grip':state['knife']['grasp'][0]=False
    else:p={'assume_held':True}
    with pytest.raises((ValueError,RuntimeError)):run_segment(a,'e25_a_place_held_knife_from73',p)
    assert calls==[]


def test_a73_cannot_rotate_if_knife_still_has_real_table_contact(tmp_path,monkeypatch):
    a,state,contacts,calls=admitted_held73(tmp_path,monkeypatch)
    old=a.move_generated
    def move(*args,**kwargs):
        old(*args,**kwargs);contacts.add(frozenset(('knife','table')))
    a.move_generated=move
    with pytest.raises(RuntimeError,match='still touches table'):run_segment(a,'e25_a_place_held_knife_from73',{})
    assert 'original_goal_rotation'not in calls and 'RELEASE'not in calls


def test_full_A_knife_calls_the_identical_sweep_lift_before_rotation(tmp_path,monkeypatch):
    import ast
    from pathlib import Path
    from videoicl_isaaclab import execution_design_e25_a_receiver as receiver
    # Execute the real method without importing GPU-only torch dependencies.
    path=Path(receiver.__file__).with_name('demonstration.py');tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Demonstration')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='rotate_held')
    namespace={'__package__':'videoicl_isaaclab','np':np}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),namespace)
    a,state,contacts=fixture(tmp_path);a.scene.embodiment.config={};calls=[]
    monkeypatch.setattr(receiver,'lift_knife_for_rotation',lambda actual:calls.append(actual))
    namespace['rotate_held'](a,'knife','left',{'yaw':0.})
    assert calls==[a]


def test_native_a21_uses_earlier_true_grip_without_replaying_acquisition(tmp_path,monkeypatch):
    a,state,contacts,calls=admitted_held73(tmp_path,monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':21,'physics_ticks':2111}
    result=run_segment(a,'e25_a_place_held_knife_from21',{})
    assert result['local_completed']and 'GRASP'not in calls and calls.count('RELEASE')==1


@pytest.mark.parametrize('source',[(73,7311),(21,2112),(22,2211)])
def test_a21_cannot_alias_later_or_different_native_boundary(tmp_path,monkeypatch,source):
    a,state,contacts,calls=admitted_held73(tmp_path,monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':source[0],'physics_ticks':source[1]}
    with pytest.raises(ValueError,match='A21'):run_segment(a,'e25_a_place_held_knife_from21',{})
    assert not calls
