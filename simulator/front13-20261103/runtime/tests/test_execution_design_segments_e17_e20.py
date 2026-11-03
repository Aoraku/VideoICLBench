"""Local segment admission, original policy initialization and failure guards."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_segments_e17_e20 as segments
from videoicl_isaaclab import execution_design_e17_insertion as insertion
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_e20_reference as e20
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_scenes import build_execution_scene
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def context(task='E20',variant='A',held=None):
    runtime=Path(__file__).parents[1]
    spec=build_execution_scene(load(task,variant,4201,runtime/'configs/realworld_full50_bindings.json',verify_files=False),seed=4201)
    state={o['id']:dict(pos=np.array([*o.get('xy',[0,0]),o.get('center_z',o.get('bottom',.8)+o['size'][2])]),
                       mat=np.eye(3),grasp=[False,False])for o in spec['objects']}
    contacts=set()
    if held:
        name,side=held;state[name]['grasp'][0 if side=='left'else 1]=True
        contacts.update(frozenset((name,f'{side}_finger{i}'))for i in (1,2))
    contacts.update(frozenset((name,ref))for name,ref in spec['execution_design'].get('initial_storage',{}).items())
    q=np.array([[.0112,.0108]]);qd=np.array([[-.0079,.0086]])
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=q,joint_vel=qd))
    c=SimpleNamespace(steps=0,snapshot=lambda:(state,contacts),ids={'left':([],[0,1]),'right':([],[0,1])})
    a=SimpleNamespace(control_report={'engineering_reference_only':True},c=c,
        scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50],'rotation_deg':[.5,20]}}),robots={'left':robot,'right':robot}))
    blue='blue_supply_3';point=state[blue]['pos'].copy()if blue in state else np.zeros(3)
    a.tip=lambda side:point.copy()
    return a,state,contacts


def native_stand():
    return dict(measured=True,derived_geometry_sha256=stand.GEOMETRY_SHA,
                mass_kg=[[stand.MASS_KG]],kinematic_enabled=False,gravity_disabled=False)


def test_blue_constructs_original_policy_and_only_returns_local_operations(monkeypatch):
    author,state,contacts=context();called=[]
    def finish(policy,ref,side):
        assert isinstance(policy,ExecutionDesignAuthor)
        assert policy.start==0 and policy.task=='E20'and policy.variant=='A'
        assert side=='left'and ref['actor']=='blue_supply_3'
        state['blue_supply_3']['grasp'][0]=True
        contacts.update(frozenset(('blue_supply_3',f'left_finger{i}'))for i in (1,2))
        called.append('three-grasp-tail')
    monkeypatch.setattr(e20,'finish_chip_grip',finish)
    result=segments.run_segment(author,'e20_grasp_blue',{})
    assert called==['three-grasp-tail']
    assert set(result)=={'local_completed','operations'}and result['local_completed']
    assert result['operations'][0]['stage']=='local-e20-blue-three-grasp-tail'


@pytest.mark.parametrize('variant,index',[('A',0),('B',1)])
def test_held_green_continues_without_pickup_or_prefix_replay(monkeypatch,variant,index):
    author,_,_=context('E17',variant,('green_square','right'));calls=[]
    monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    monkeypatch.setattr(ExecutionDesignAuthor,'pickup',lambda *args,**kw:pytest.fail('held segment must never pickup'))
    monkeypatch.setattr(insertion,'place_held_lower',lambda policy,name,actor,target,ref,side:calls.append((name,target,side)))
    result=segments.run_segment(author,'e17_insert_held_green',{})
    assert result['local_completed']and calls==[('green_square',insertion.front_lower_slot(None,index,2),'right')]


def test_red_liftoff_checks_real_source_hold_before_calling_tail(monkeypatch):
    author,_,_=context(held=('red_supply_1','right'));calls=[]
    monkeypatch.setattr(e20,'verify_grip_during_small_liftoff',lambda policy,ref,side,**kw:calls.append(kw))
    result=segments.run_segment(author,'e20_liftoff_red',{'measured_grips_before':2})
    assert result['local_completed']and calls==[{'initial_measured_grips':2}]


@pytest.mark.parametrize('segment,parameters',[('unknown',{}),('e20_grasp_blue',None),('e20_grasp_blue',{'pose':[0,0,0]}),
    ('e17_insert_held_green',{'task_score_100':100}),('e20_liftoff_red',{'assume_held':True})])
def test_unknown_or_state_writing_parameters_rejected_before_policy(monkeypatch,segment,parameters):
    author,_,_=context();monkeypatch.setattr(segments,'ExecutionDesignAuthor',lambda a:pytest.fail('must reject before policy'))
    with pytest.raises(ToolExecutionError):segments.run_segment(author,segment,parameters)


@pytest.mark.parametrize('mode',['formal','revision','condition','task'])
def test_only_explicit_v3_I_owned_engineering_admitted(monkeypatch,mode):
    author,_,_=context()
    if mode=='formal':author.control_report.clear()
    elif mode=='revision':author.scene.spec['execution_design']['revision']='v2'
    elif mode=='condition':author.scene.spec['execution_design']['condition']='E'
    else:author.scene.spec['id']='E21'
    monkeypatch.setattr(segments,'ExecutionDesignAuthor',lambda a:pytest.fail('must reject before policy'))
    with pytest.raises(ToolExecutionError):segments.run_segment(author,'e20_grasp_blue',{})


@pytest.mark.parametrize('mode',['grip_flag_only','no_hold','other_hand','other_contact','source_sha','stand_hash','mass','kinematic','assignment'])
def test_held_green_rejects_unmeasured_or_incompatible_world(monkeypatch,mode):
    author,state,contacts=context('E17','A',('green_square','right'));actual=native_stand()
    if mode=='grip_flag_only':contacts.remove(frozenset(('green_square','right_finger2')))
    elif mode=='no_hold':state['green_square']['grasp'][1]=False
    elif mode=='other_hand':state['stand']['grasp'][0]=True
    elif mode=='other_contact':contacts.add(frozenset(('stand','left_finger1')))
    elif mode=='source_sha':next(o for o in author.scene.spec['objects']if o['id']=='green_square')['source_asset']['sha256']='bad'
    elif mode=='stand_hash':actual['derived_geometry_sha256']='bad'
    elif mode=='mass':actual['mass_kg']=[[np.nan]]
    elif mode=='kinematic':actual['kinematic_enabled']=True
    else:next(r for r in author.scene.spec['execution_design']['local_regions']if r['id']=='lower')['members']=[]
    monkeypatch.setattr(stand,'native_readback',lambda scene:actual)
    monkeypatch.setattr(insertion,'place_held_lower',lambda *args:pytest.fail('must reject before actions'))
    with pytest.raises(ToolExecutionError):segments.run_segment(author,'e17_insert_held_green',{})


@pytest.mark.parametrize('parameters',[{'target_index':1},{'target_index':True},{'target_index':-1}])
def test_green_target_cannot_override_the_actual_assignment(monkeypatch,parameters):
    author,_,_=context('E17','A',('green_square','right'));monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    with pytest.raises(ToolExecutionError):segments.run_segment(author,'e17_insert_held_green',parameters)


@pytest.mark.parametrize('mode',['already_held','no_rail','far_tip','source_size'])
def test_blue_tail_requires_the_true_pregrasp_source_context(monkeypatch,mode):
    author,state,contacts=context()
    if mode=='already_held':state['blue_supply_3']['grasp'][0]=True
    elif mode=='no_rail':contacts.remove(frozenset(('blue_supply_3','fixture2')))
    elif mode=='far_tip':author.tip=lambda side:state['blue_supply_3']['pos']+[.003,0,0]
    else:next(o for o in author.scene.spec['objects']if o['id']=='blue_supply_3')['size']=[]
    monkeypatch.setattr(e20,'finish_chip_grip',lambda *args:pytest.fail('must reject before GRASP'))
    with pytest.raises(ToolExecutionError):segments.run_segment(author,'e20_grasp_blue',{})


@pytest.mark.parametrize('mode',['fast','lost_rail','missing_contact','bad_prefix'])
def test_red_requires_actual_grip_stability_and_verified_prefix_fields(monkeypatch,mode):
    author,_,contacts=context(held=('red_supply_1','right'));parameters={}
    if mode=='fast':author.scene.robots['right'].data.joint_vel[0,0]=.04
    elif mode=='lost_rail':contacts.remove(frozenset(('red_supply_1','fixture7')))
    elif mode=='missing_contact':contacts.remove(frozenset(('red_supply_1','right_finger1')))
    else:parameters={'measured_grips_before':3}
    monkeypatch.setattr(e20,'verify_grip_during_small_liftoff',lambda *args,**kw:pytest.fail('must reject before UP'))
    with pytest.raises(ToolExecutionError):segments.run_segment(author,'e20_liftoff_red',parameters)


def blue_lift_context(monkeypatch,mode='good'):
    author,state,contacts=context('E20','C');author._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':276,'physics_ticks':28440}};calls=[]
    def finish(policy,ref,side):
        calls.append(('original-three-grasp',side));state['blue_supply_3']['grasp'][0]=True
        contacts.update(frozenset(('blue_supply_3',f'left_finger{i}'))for i in(1,2))
        # The lift baseline is measured after the original closing motion.
        state['blue_supply_3']['pos'][:2]+=[.002,.004]
    def act(policy,side,token,mm):
        calls.append((side,token,mm));policy.c.steps+=1
        state['blue_supply_3']['pos'][2]+=.003 if mode=='no_rise'else .010
        if mode=='slide':state['blue_supply_3']['pos'][0]+=.007
        if mode=='lost_contact':contacts.discard(frozenset(('blue_supply_3','left_finger2')))
        if mode=='lost_grip':state['blue_supply_3']['grasp'][0]=False
    monkeypatch.setattr(e20,'finish_chip_grip',finish);monkeypatch.setattr(ExecutionDesignAuthor,'act',act)
    return author,state,contacts,calls


def test_blue_short_lift_uses_original_grasp_then_public_30mm_without_wait(monkeypatch):
    author,state,contacts,calls=blue_lift_context(monkeypatch)
    result=segments.run_segment(author,'e20_grasp_and_lift_blue',{})
    assert result['local_completed']and calls==[('original-three-grasp','left'),('left','UP',10.),('left','UP',10.),('left','UP',10.)]
    proof=result['operations'][-1]
    assert proof['measured_object_rise_m']==pytest.approx(.030)and proof['measured_xy_slide_m']==0.
    assert state['blue_supply_3']['grasp']==[True,False]


@pytest.mark.parametrize('mode,reason,up_count',[('slide','slides sideways',1),('lost_contact','bilateral',1),('lost_grip','Actual grip lost',1),('no_rise','at least 20mm',3)])
def test_short_lift_rejects_actual_slip_grip_or_insufficient_rise_at_first_failure(monkeypatch,mode,reason,up_count):
    author,state,contacts,calls=blue_lift_context(monkeypatch,mode)
    with pytest.raises(ToolExecutionError,match=reason):segments.run_segment(author,'e20_grasp_and_lift_blue',{})
    assert len(calls)-1==up_count


def test_original_blue_grasp_entry_still_finishes_before_any_lift(monkeypatch):
    author,state,contacts,calls=blue_lift_context(monkeypatch)
    assert segments.run_segment(author,'e20_grasp_blue',{})['local_completed']
    assert calls==[('original-three-grasp','left')]


@pytest.mark.parametrize('fault',['variant','seed','steps','tick','diagnostic'])
def test_short_lift_requires_the_actual_C276_debug_boundary(monkeypatch,fault):
    author,state,contacts,calls=blue_lift_context(monkeypatch)
    if fault=='variant':author.scene.spec['variant']='B'
    elif fault=='seed':author.scene.spec['seed']=4202
    elif fault=='steps':author._engineering_resume_checkpoint['source']['steps']=278
    elif fault=='tick':author._engineering_resume_checkpoint['source']['physics_ticks']=28640
    else:author._engineering_resume_checkpoint['diagnostic_only']=False
    with pytest.raises(ToolExecutionError,match='C276'):segments.run_segment(author,'e20_grasp_and_lift_blue',{})
    assert not calls


def blue_b522_context(monkeypatch,mode='good'):
    a,state,contacts=context('E20','B');a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':522,'physics_ticks':53040}};calls=[]
    a.tip=lambda side:state['blue_supply_1']['pos'].copy()
    def act(policy,side,token,mm=None,**kwargs):
        assert side=='right';calls.append((token,mm));policy.c.steps+=1
        if token=='GRASP':
            state['blue_supply_1']['grasp'][1]=mode!='no_grip'
            contacts.update(frozenset(('blue_supply_1','right_finger'+str(i)))for i in(1,2))
            if mode=='one_finger':contacts.discard(frozenset(('blue_supply_1','right_finger2')))
            if mode=='grasp_slide':state['blue_supply_1']['pos'][0]+=.007
        elif token=='UP':
            state['blue_supply_1']['pos'][2]+=.003 if mode=='no_rise'else .010
            if mode=='lift_slide':state['blue_supply_1']['pos'][0]+=.007
            if mode=='lift_slip':state['blue_supply_1']['grasp'][1]=False
        else:pytest.fail('B522 local diagnostic must not add waits/repositioning')
    monkeypatch.setattr(ExecutionDesignAuthor,'act',act)
    return a,state,contacts,calls


def test_b522_executes_at_most_six_actual_actions_and_measures_body_lift(monkeypatch):
    a,state,contacts,calls=blue_b522_context(monkeypatch);before=deepcopy(a.scene.spec)
    result=segments.run_segment(a,'e20_b_grasp_and_lift_blue1',{})
    assert result['local_completed']and calls==[('GRASP',None)]*3+[('UP',10.)]*3
    assert a.c.steps==6 and state['blue_supply_1']['grasp']==[False,True]
    assert result['operations'][-1]['measured_object_rise_m']==pytest.approx(.030)
    assert a.scene.spec==before and not any(k in result for k in('task_score_100','success'))


@pytest.mark.parametrize('mode,expected_actions',[('no_grip',1),('one_finger',1),('grasp_slide',2),('lift_slide',4),('lift_slip',4),('no_rise',6)])
def test_b522_stops_at_first_true_grip_contact_slide_or_lift_failure(monkeypatch,mode,expected_actions):
    a,state,contacts,calls=blue_b522_context(monkeypatch,mode)
    with pytest.raises(ToolExecutionError):segments.run_segment(a,'e20_b_grasp_and_lift_blue1',{})
    assert len(calls)==expected_actions


@pytest.mark.parametrize('fault',['variant','seed','steps','tick','diagnostic','held','rail','far_tip'])
def test_b522_boundary_and_actual_pregrasp_context_are_mandatory(monkeypatch,fault):
    a,state,contacts,calls=blue_b522_context(monkeypatch)
    if fault=='variant':a.scene.spec['variant']='C'
    elif fault=='seed':a.scene.spec['seed']=4202
    elif fault=='steps':a._engineering_resume_checkpoint['source']['steps']=524
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=53240
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    elif fault=='held':state['blue_supply_1']['grasp'][1]=True
    elif fault=='rail':contacts.discard(frozenset(('blue_supply_1','fixture3')))
    else:a.tip=lambda side:state['blue_supply_1']['pos']+[.003,0,0]
    with pytest.raises(ToolExecutionError):segments.run_segment(a,'e20_b_grasp_and_lift_blue1',{})
    assert calls==[]


def test_b_native_core1_keeps_real_grip_and_finishes_in_five_actions(monkeypatch):
    a,state,contacts,calls=blue_b522_context(monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':1,'physics_ticks':111}
    state['blue_supply_1']['pos'][1]+=.004
    state['blue_supply_1']['grasp'][1]=True
    contacts.update(frozenset(('blue_supply_1','right_finger'+str(i)))for i in(1,2))
    original=ExecutionDesignAuthor.act
    def act(policy,side,token,**kwargs):
        original(policy,side,token,**kwargs)
        if token=='GRASP':state['blue_supply_1']['pos'][1]+=.0015
    monkeypatch.setattr(ExecutionDesignAuthor,'act',act)
    before=deepcopy(a.scene.spec)
    result=segments.run_segment(a,'e20_b_grasp_and_lift_blue1',{})
    assert result['local_completed']and calls==[('GRASP',None)]*2+[('UP',10.)]*3
    assert result['operations'][-1]['measured_xy_slide_m']==0.
    assert a.scene.spec==before


@pytest.mark.parametrize('fault',['no_grip','one_finger','wrong_tick','past_extraction'])
def test_b_native_core1_requires_the_real_first_pinch(monkeypatch,fault):
    a,state,contacts,calls=blue_b522_context(monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':1,'physics_ticks':111}
    state['blue_supply_1']['grasp'][1]=fault!='no_grip'
    contacts.update(frozenset(('blue_supply_1','right_finger'+str(i)))for i in(1,2))
    if fault=='one_finger':contacts.discard(frozenset(('blue_supply_1','right_finger2')))
    if fault=='wrong_tick':a._engineering_resume_checkpoint['source']['physics_ticks']=112
    if fault=='past_extraction':state['blue_supply_1']['pos'][1]+=.013
    with pytest.raises(ToolExecutionError):segments.run_segment(a,'e20_b_grasp_and_lift_blue1',{})
    assert len(calls)==(1 if fault=='past_extraction'else 0)
