"""Offline safety contracts only; fixtures are never native acceptance."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_owned_hold_negative import negative_plan,verify_final_hold,OwnedHoldNegativeAuthor
from videoicl_isaaclab.execution_design_reference import reference_capability
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator


def spec(task,variant='A',condition='I',seed=4201):
    source=load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    return apply_execution_inputs(source,condition=condition,seed=seed,revision=REVISION_V3)


def fixture(s):
    zones={z['id']:z for z in s['zones']};objects={o['id']:o for o in s['objects']}
    state={o['id']:dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),mat=np.eye(3),grasp=[False,False])for o in s['objects']}
    for o in s['objects']:
        yaw=o.get('yaw',0);state[o['id']]['mat']=np.array([[math.cos(yaw),-math.sin(yaw),0],[math.sin(yaw),math.cos(yaw),0],[0,0,1]])
    initial=deepcopy(state)
    for g in s['goals']:
        zone=zones[g['target']];yaw=g.get('yaw',0);xy=g.get('placement_xy',zone['xy'])
        if zone.get('anchor_object'):xy=(state[zone['anchor_object']]['pos']+state[zone['anchor_object']]['mat']@np.array(zone['anchor_local_center']))[:2]
        state[g['object']]=dict(pos=np.array([*xy,zone.get('surface_z',.8)+objects[g['object']]['size'][2]]),mat=np.array([[math.cos(yaw),-math.sin(yaw),0],[math.sin(yaw),math.cos(yaw),0],[0,0,1]]),grasp=[False,False])
    name=s['goals'][-1]['object'];state[name]['grasp']=[True,False]
    contacts={frozenset((name,'left_finger1')),frozenset((name,'left_finger2'))}
    # CPU-only observation derivation from fixture poses and explicit contacts.
    # This is never written to a native result or accepted as a physics test.
    e=NativeTaskEvaluator(s);e.initial=initial;e.state=state;e.contacts=contacts
    e.initial_contacts=set();e.grounded=set(state)-{name}
    for actor,g in {g['object']:g for g in s['goals']}.items():
        if actor!=name:contacts.add(frozenset((actor,g.get('required_support','table'))))
    if s['id']=='E21':
        e.event_history['placements']=[dict(object=e.label(n),target=slot,step=i+1,released=True,support_contact=True)
            for i,(n,slot) in enumerate(zip(s['semantic']['release_order'][:-1],['top_left','top_right','bottom_left']))]
    observation=e.derive(False)
    status={n:dict(released=n!=name,stable=n!=name,supported=n!=name) for n in state}
    score=dict(success=False,history_valid=True,errors=[],progress_evidence=dict(
        source='trusted_native_per_physics_tick',history_valid=True,initial={'sealed':True},
        observation=observation,object_status={e.label(n):v for n,v in status.items()},actor_status=status))
    return state,contacts,score


@pytest.mark.parametrize('task',['E14','E16','E21','E25'])
@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('condition','RIE')
@pytest.mark.parametrize('seed',[4201,4202,4203])
def test_all_owned_hold_plans_preserve_original_objects_rules_and_goals(task,variant,condition,seed):
    s=spec(task,variant,condition,seed);before=deepcopy(s);plan,evidence=negative_plan(s,'not_released')
    assert s==before and plan['objects']==s['objects']and plan['semantic']==s['semantic']and plan['goals']==s['goals']
    assert evidence['negative_condition_observed']is None and evidence['held_member']==s['goals'][-1]['object']
    assert reference_capability(task,'not_released')['implemented'] and not reference_capability(task,'not_released')['native_validated']
    state,contacts,score=fixture(s);assert verify_final_hold(s,state,contacts,score)['held_member']==evidence['held_member']


@pytest.mark.parametrize('change',['distant','too_high','wrong_yaw','no_grasp','unilateral','other_held','other_unstable','accepted','nan'])
def test_incomplete_or_wrong_physical_interventions_are_not_successful_controls(change):
    s=spec('E16');state,contacts,score=fixture(s);name=s['goals'][-1]['object'];other=next(n for n in {g['object']for g in s['goals']}if n!=name)
    if change=='distant':state[name]['pos'][0]+=.1
    elif change=='too_high':state[name]['pos'][2]+=.1
    elif change=='wrong_yaw':state[name]['mat']=-state[name]['mat']
    elif change=='no_grasp':state[name]['grasp']=[False,False]
    elif change=='unilateral':contacts.remove(frozenset((name,'left_finger1')))
    elif change=='other_held':state[other]['grasp']=[False,True]
    elif change=='other_unstable':score['progress_evidence']['actor_status'][other]['stable']=False
    elif change=='accepted':score['success']=True
    elif change=='nan':state[name]['pos'][0]=float('nan')
    with pytest.raises(RuntimeError):verify_final_hold(s,state,contacts,score)


def test_reference_uses_public_hold_and_restores_scene_and_permission_after_exit():
    s=spec('E16');state,contacts,score=fixture(s);scene=SimpleNamespace(spec=s)
    c=SimpleNamespace(scene=scene,steps=0,snapshot=lambda:(state,contacts),evaluator=SimpleNamespace(result=lambda:score))
    calls=[]
    a=SimpleNamespace(scene=scene,c=c,smooth=False,control_report={'engineering_reference_only':True})
    def act():calls.append('STILL');c.steps+=1
    a.act=act;a.release_generated=lambda side:calls.append('RELEASE')
    original_release=a.release_generated
    def solve():
        a._engineering_release_is_relay=True;a.release_generated('left');a._engineering_release_is_relay=False
        for _ in s['goals']:a.release_generated('left')
        raise AssertionError('Must exit at final real hold before releasing')
    a.solve_generated=solve
    report=OwnedHoldNegativeAuthor(a,'not_released').solve_negative()
    assert calls==['RELEASE']*len(s['goals'])+['STILL']*3
    assert a.scene is scene and c.scene is scene and a.release_generated is original_release
    assert not a._execution_design_reference_authorized and report['negative_condition_observed']is None


def test_wrong_control_source_or_unapproved_author_cannot_enter():
    s=spec('E14')
    with pytest.raises(ValueError):negative_plan(s,'wrong_members')
    s['execution_design']['source_sha256']='untrusted'
    with pytest.raises(ValueError):negative_plan(s,'not_released')
    with pytest.raises(ValueError):OwnedHoldNegativeAuthor(SimpleNamespace(scene=SimpleNamespace(spec=spec('E14'))),'not_released')


@pytest.mark.parametrize('change',['wrong_cell','wrong_order','same_tick','missing_support','above_rim','old_actor_lookup'])
def test_e21_preserves_actual_cell_sequence_and_does_not_accept_drop_height(change):
    s=spec('E21');state,contacts,score=fixture(s);e=score['progress_evidence'];name=s['goals'][-1]['object']
    if change=='old_actor_lookup':
        # Actual native envelopes use color identities here, not actor names.
        e.pop('actor_status');assert 'red' in e['object_status'] and 'red_block' not in e['object_status']
        assert verify_final_hold(s,state,contacts,score)['held_member']==name
        return
    if change=='wrong_cell':e['observation']['cells']['red']='bottom_right'
    elif change=='wrong_order':e['observation']['placement_events'][0]['object']='yellow'
    elif change=='same_tick':e['observation']['placement_events'][1]['step']=1
    elif change=='missing_support':e['observation']['placement_events'][0]['support_contact']=False
    else:
        # The positive route may drop from above the rim. Withholding that
        # release is an incomplete placement, not an isolated release defect.
        state[name]['pos'][2]+=.04
    with pytest.raises(RuntimeError):verify_final_hold(s,state,contacts,score)


@pytest.mark.parametrize('task,field,value',[
    ('E14','support_edges',[]),
    ('E14','final_top_to_bottom',['red','yellow','blue','green']),
    ('E16','supported_in_tray',[]),
    ('E16','in_tray',[]),
    ('E25','handle_toward',{}),
    ('E25','regions',{}),
    ('E25','far_left_to_right',['fork','knife','spoon']),
])
def test_generic_supported_status_does_not_replace_original_native_relations(task,field,value):
    s=spec(task);state,contacts,score=fixture(s);score['progress_evidence']['observation'][field]=value
    with pytest.raises(RuntimeError):verify_final_hold(s,state,contacts,score)


@pytest.mark.parametrize('change',['history','source','seal','errors','relative_pose','yaw'])
def test_untrusted_history_and_old_loose_pose_thresholds_are_rejected(change):
    s=spec('E16');state,contacts,score=fixture(s);name=s['goals'][-1]['object']
    if change=='history':score['history_valid']=False
    elif change=='source':score['progress_evidence']['source']='cpu_fixture'
    elif change=='seal':score['progress_evidence']['initial']['sealed']=False
    elif change=='errors':score['errors']=['snapshot rejected']
    elif change=='relative_pose':state[name]['pos'][0]+=.022
    else:
        a=math.radians(12);state[name]['mat']=np.array([[math.cos(a),-math.sin(a),0],[math.sin(a),math.cos(a),0],[0,0,1]])@state[name]['mat']
    with pytest.raises(RuntimeError):verify_final_hold(s,state,contacts,score)


@pytest.mark.parametrize('task',['E14','E16','E25'])
def test_final_count_includes_original_unstack_goals_and_excludes_each_real_relay(task):
    s=spec(task);state,contacts,score=fixture(s);scene=SimpleNamespace(spec=s)
    c=SimpleNamespace(scene=scene,steps=0,snapshot=lambda:(state,contacts),evaluator=SimpleNamespace(result=lambda:score))
    calls=[];a=SimpleNamespace(scene=scene,c=c,smooth=False,control_report={'engineering_reference_only':True})
    def act():c.steps+=1;calls.append('STILL')
    a.act=act;a.release_generated=lambda side:calls.append('RELEASE')
    def solve():
        for index,_ in enumerate(s['goals']):
            if task!='E14':
                a._engineering_release_is_relay=True;a.release_generated('left');a._engineering_release_is_relay=False
            a.release_generated('left')
            assert index<len(s['goals'])-1
    a.solve_generated=solve
    report=OwnedHoldNegativeAuthor(a,'not_released').solve_negative()
    expected=len(s['goals'])-1+(len(s['goals']) if task!='E14' else 0)
    assert calls==['RELEASE']*expected+['STILL']*3 and report['execution_finished']
    assert report['negative_condition_observed']is None
