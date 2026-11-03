"""Measured geometry/source gates; no real grasp success asserted by unit tests."""
import ast,re
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e24_lid import table_bounds,side_grasp_rotation,finger_table_clearance,LID_CENTER_LOCAL,pickup_lid_overhang
from videoicl_isaaclab.layout import Layout
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_table_edge_uses_real_rig_rotation_not_raw_world_size():
    import json
    cfg=json.loads((Path(__file__).parents[1]/'configs/embodiments/franka.json').read_text())
    p=SimpleNamespace(a=SimpleNamespace(scene=SimpleNamespace(layout=Layout(cfg['layout']))))
    lo,hi=table_bounds(p)
    np.testing.assert_allclose(lo[:2],[-.35,-.60],atol=1e-9)
    np.testing.assert_allclose(hi,[.35,.60,.8],atol=1e-9)


def test_side_pinch_axes_follow_actual_lid_and_never_imply_fixed_world_up():
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    lid=_axis_rotation([1,0,0],.06)@_axis_rotation([0,0,1],np.pi/2)
    r=side_grasp_rotation(lid)
    np.testing.assert_allclose(r[:,1],lid[:,2]);np.testing.assert_allclose(r[:,2],-lid[:,1])
    np.testing.assert_allclose(r.T@r,np.eye(3),atol=1e-12);assert np.linalg.det(r)==pytest.approx(1.)


def test_side_lid_point_uses_loaded_source_center_and_real_plate_thickness():
    source=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/removable_box_lid_parts/source_adapted.usda'
    text=source.read_text();pts=np.array(ast.literal_eval(re.search(r'point3f\[\] points = (\[.*?\])',text)[1]))
    faces=np.array(ast.literal_eval(re.search(r'int\[\] faceVertexIndices = (\[.*?\])',text)[1])).reshape(-1,3)
    center=(pts.min(0)+pts.max(0))/2;raw=LID_CENTER_LOCAL+center;hits=[]
    for face in faces:
        t=pts[face];matrix=np.column_stack((t[1,:2]-t[0,:2],t[2,:2]-t[0,:2]))
        if abs(np.linalg.det(matrix))<1e-12:continue
        u,v=np.linalg.solve(matrix,raw[:2]-t[0,:2])
        if u>=0 and v>=0 and u+v<=1:hits.append(t[0,2]+u*(t[1,2]-t[0,2])+v*(t[2,2]-t[0,2]))
    assert min(hits)<raw[2]<max(hits)
    assert max(hits)-min(hits)<.005
    # The old z=.008 would lie below the solid top plate after wrapper centering.
    assert .008+center[2]<min(hits)


def test_lower_open_finger_below_table_only_allowed_when_entire_mesh_outside():
    lo=np.array([-.35,-.6,.75]);hi=np.array([.35,.6,.8])
    rows=[dict(name=n,aabb_min_task_m=[-.443,.30,.778],aabb_max_task_m=[-.389,.33,.805])for n in ('panda_leftfinger','panda_rightfinger')]
    p=SimpleNamespace(a=SimpleNamespace(finger_geometry=lambda s:dict(source='actual_collision_mesh_current_body_pose',fingers=rows)))
    assert finger_table_clearance(p,'left',lo,hi)
    rows[0]['aabb_max_task_m'][0]=-.349
    with pytest.raises(ToolExecutionError,match='tabletop'):finger_table_clearance(p,'left',lo,hi)


@pytest.mark.parametrize('task,revision,engineering',[('E23','embodied50-execution-v3-20261102',True),('E24','old',True),('E24','embodied50-execution-v3-20261102',False)])
def test_side_lid_scope_rejects_before_controller_access(task,revision,engineering):
    p=SimpleNamespace(task=task,spec={'execution_design':{'revision':revision}},a=SimpleNamespace(control_report={'engineering_reference_only':engineering}))
    with pytest.raises(ToolExecutionError,match='independent'):pickup_lid_overhang(p)


@pytest.mark.parametrize('bad',['missing','duplicate','nan','inverted'])
def test_incomplete_or_nonfinite_fingers_fail_closed(bad):
    rows=[dict(name=n,aabb_min_task_m=[-.443,.30,.778],aabb_max_task_m=[-.389,.33,.805])for n in ('panda_leftfinger','panda_rightfinger')]
    if bad=='missing':rows.pop()
    elif bad=='duplicate':rows[1]['name']=rows[0]['name']
    elif bad=='nan':rows[1]['aabb_min_task_m'][0]=float('nan')
    else:rows[1]['aabb_min_task_m'][0]=0
    p=SimpleNamespace(a=SimpleNamespace(finger_geometry=lambda s:dict(source='actual_collision_mesh_current_body_pose',fingers=rows)))
    with pytest.raises(ToolExecutionError):finger_table_clearance(p,'left',np.array([-.35,-.6,.75]),np.array([.35,.6,.8]))


def transit_policy():
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    import math
    calls=[];tip=np.array([.15,.313,.894]);lid_rotation=_axis_rotation([0,0,1],math.pi/2)
    state={'lid':dict(pos=[.054,.313,.834],mat=lid_rotation,grasp=[False,False])}
    p=SimpleNamespace(task='E24',spec=dict(execution_design=dict(revision='embodied50-execution-v3-20261102')),
        objects={'lid':dict(size=[.175,.106,.022],source_asset=dict(sha256='180837493663657fecabc2cbfb1f3ffeedfc96c700ae4ae4a1c82eae5c412fde'))},
        c=SimpleNamespace(grips={'left':0.,'right':.04},steps=0,
            action_feedback=lambda:dict(control_feedback=dict(left={}))),
        a=SimpleNamespace(control_report=dict(engineering_reference_only=True),
            tcp_rotation_task=lambda _: _axis_rotation([0,1,0],math.radians(-10))@np.diag([-1.,1.,-1.]),
            finger_geometry=lambda _:dict(fingers=[dict(aabb_min_task_m=(tip-[.021,.01,.01]).tolist()),dict(aabb_min_task_m=(tip-[.020,.01,.01]).tolist())])),
        tip=lambda _:tip.copy(),snapshot=lambda:(state,[]),act=lambda *a,**k:calls.append(('act',a,k)),
        move=lambda *a,**k:calls.append(('move',a,k)),stage=lambda name:calls.append(('stage',name)))
    return p,calls,state


def test_continuation_recomputes_approach_without_repeating_public_setup(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    from videoicl_isaaclab import execution_design_e24_transit as transit
    p,calls,state=transit_policy();seen=[]
    monkeypatch.setattr(lid,'table_bounds',lambda _: (np.array([-.35,-.6,.75]),np.array([.35,.6,.8])))
    def stop(policy,side,approach):
        seen.append((side,approach.copy()));raise RuntimeError('stop at shared transit entry')
    monkeypatch.setattr(transit,'empty_pusher_transfer',stop)
    with pytest.raises(RuntimeError,match='shared transit'):lid.continue_lid_from_transit(p)
    assert calls==[]
    assert seen[0][0]=='left'
    np.testing.assert_allclose(seen[0][1],[.185,.313,.844])


@pytest.mark.parametrize('bad',['held','orientation','open_command'])
def test_continuation_rejects_wrong_restored_pusher_before_any_action(monkeypatch,bad):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    p,calls,state=transit_policy()
    monkeypatch.setattr(lid,'table_bounds',lambda _: (np.array([-.35,-.6,.75]),np.array([.35,.6,.8])))
    if bad=='held':state['lid']['grasp'][1]=True
    elif bad=='orientation':p.a.tcp_rotation_task=lambda _:np.eye(3)
    else:p.c.grips['left']=.04
    with pytest.raises(ToolExecutionError):lid.continue_lid_from_transit(p)
    assert calls==[]


def test_full_pickup_keeps_original_setup_then_delegates_to_shared_remaining_chain(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    p,calls,state=transit_policy();context=(p.objects['lid'],np.array([-.35,-.6,.75]),np.array([.35,.6,.8]),'left',np.array(state['lid']['pos']),-.30)
    monkeypatch.setattr(lid,'_lid_push_context',lambda _:context)
    monkeypatch.setattr(lid,'empty_rotation',lambda *args:calls.append(('rotation',)))
    def remaining(policy,*,_push_context):
        assert _push_context is context;calls.append(('remaining',));return {'actor':'lid'},'left'
    monkeypatch.setattr(lid,'continue_lid_from_transit',remaining)
    assert lid.pickup_lid_overhang(p)==({'actor':'lid'},'left')
    assert [(r[1][1])for r in calls if r[0]=='act']==['RELEASE','GRASP']
    assert [r[0]for r in calls]==['stage','act','move','rotation','act','remaining']


def test_push_plane_uses_real_plate_center_not_offset_side_pinch_point():
    from videoicl_isaaclab import execution_design_e24_lid as lid
    p,_,state=transit_policy()
    body=state['lid']
    plate=np.asarray(body['pos'])+np.asarray(body['mat'])@lid.LID_PLATE_CENTER_LOCAL
    edge=np.asarray(body['pos'])+np.asarray(body['mat'])@lid.LID_EDGE_GRASP_LOCAL
    assert plate[0]==pytest.approx(body['pos'][0])
    assert edge[0]==pytest.approx(body['pos'][0]-.098)
    target=lid._push_plane_target(p,'left',body)
    assert target[0]==pytest.approx(p.tip('left')[0])
    np.testing.assert_allclose(target[1:],[.313,.844])


def test_supported_push_uses_coarse_public_height_correction_and_stops_first_error(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    from videoicl_isaaclab import execution_design_e24_transit as transit
    p,calls,state=transit_policy();tip=p.tip('left');p.tip=lambda _:tip.copy()
    p.a.finger_geometry=lambda _:dict(fingers=[dict(aabb_min_task_m=tip-[.021,.01,.01]),dict(aabb_min_task_m=tip-[.020,.01,.01])])
    corrections=[];pushes=[]
    monkeypatch.setattr(lid,'table_bounds',lambda _: (np.array([-.35,-.6,.75]),np.array([.35,.6,.8])))
    monkeypatch.setattr(lid,'finger_table_clearance',lambda *args:True)
    monkeypatch.setattr(transit,'empty_pusher_transfer',lambda *args:None)
    def move(side,target,guard=None,**kwargs):
        if guard:guard()
        tip[:]=target
    def act(side,token,**kwargs):
        if token=='DOWN':
            corrections.append(kwargs['mm']);tip[2]-=kwargs['mm']/1000;return
        assert token=='BACK'
        pushes.append(tip.copy())
        if len(pushes)==2:raise ToolExecutionError('native public refusal')
        # A real public X action can leave a vertical servo residual.
        tip[0]-=.003;tip[2]+=.005;tip[1]+=.002
    p.move=move;p.act=act
    with pytest.raises(ToolExecutionError,match='native public refusal'):
        lid.continue_lid_from_transit(p)
    assert len(pushes)==2 and corrections==[3.]
    for point in pushes:assert np.max(np.abs(point[1:]-[.313,.844]))<=.004
    assert all(call[0]!='act'for call in calls)


def test_contact_band_entry_skips_transit_and_starts_original_corrected_push(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    from videoicl_isaaclab import execution_design_e24_transit as transit
    p,calls,state=transit_policy();tip=np.array([.185,.313,.844]);p.tip=lambda _:tip.copy()
    p.a.finger_geometry=lambda _:dict(fingers=[dict(aabb_min_task_m=tip-[.021,.01,.01]),dict(aabb_min_task_m=tip-[.020,.01,.01])])
    monkeypatch.setattr(lid,'table_bounds',lambda _: (np.array([-.35,-.6,.75]),np.array([.35,.6,.8])))
    monkeypatch.setattr(lid,'finger_table_clearance',lambda *args:True)
    monkeypatch.setattr(transit,'empty_pusher_transfer',lambda *args:pytest.fail('completed native transit must not repeat'))
    def stop(side,token,**kwargs):
        assert side=='left'and token=='BACK'and kwargs['mm']==3.
        raise RuntimeError('first original push')
    p.act=stop
    with pytest.raises(RuntimeError,match='first original push'):lid.push_from_contact_band(p)
    assert [c[0]for c in calls]==['stage']


@pytest.mark.parametrize('bad',['wrong_side','held','orientation','open_command'])
def test_contact_band_entry_rejects_bad_actual_boundary_before_actions(monkeypatch,bad):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    p,calls,state=transit_policy();tip=np.array([.185,.313,.844]);p.tip=lambda _:tip.copy()
    p.a.finger_geometry=lambda _:dict(fingers=[dict(aabb_min_task_m=tip-[.021,.01,.01]),dict(aabb_min_task_m=tip-[.020,.01,.01])])
    monkeypatch.setattr(lid,'table_bounds',lambda _: (np.array([-.35,-.6,.75]),np.array([.35,.6,.8])))
    if bad=='wrong_side':tip[0]=-.21
    elif bad=='held':state['lid']['grasp'][0]=True
    elif bad=='orientation':p.a.tcp_rotation_task=lambda _:np.eye(3)
    else:p.c.grips['left']=.04
    with pytest.raises(ToolExecutionError):lid.push_from_contact_band(p)
    assert calls==[]


def short_contact_policy(monkeypatch,*,travel=.0007,contact=True):
    from videoicl_isaaclab import execution_design_e24_lid as lid
    p,calls,state=transit_policy();tip=np.array([.167,.313,.844]);p.tip=lambda _:tip.copy()
    p.operations=[]
    p.snapshot=lambda:(state,{frozenset(('lid','left_finger1'))}if contact else set())
    p.c.contact_forces={frozenset(('lid','left_finger1')):1.0486}
    p.move=lambda *a,**k:pytest.fail('short loaded push must not chase a Cartesian waypoint')
    def act(side,token,mm):
        calls.append(('act',side,token,mm));p.c.steps+=1
        if token=='BACK':state['lid']['pos'][0]-=travel;tip[0]-=.002
    p.act=act
    monkeypatch.setattr(lid,'table_bounds',lambda _: (np.array([-.35,-.6,.75]),np.array([.35,.6,.8])))
    monkeypatch.setattr(lid,'finger_table_clearance',lambda *args:True)
    return p,calls,state


def test_short_contact_push_stops_after_first_real_motion_without_long_settle(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import push_contact_short
    p,calls,_=short_contact_policy(monkeypatch)
    result=push_contact_short(p)
    assert [c for c in calls if c[0]=='act']==[('act','left','BACK',3.)]
    assert result['actions']==1 and result['measured_lid_travel_x_m']==pytest.approx(.0007)
    assert result['observations'][0]['contact_force_n'][0]==pytest.approx(1.0486)
    assert result['full_supported_overhang_or_side_grasp_completed']is False


def test_short_push_has_four_push_bound_and_no_three_mm_push_without_real_contact(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import push_contact_short
    p,calls,_=short_contact_policy(monkeypatch,travel=0.)
    with pytest.raises(ToolExecutionError,match='less than0.5mm'):push_contact_short(p)
    assert len([c for c in calls if c[0]=='act'])==4
    p,calls,_=short_contact_policy(monkeypatch,contact=False)
    with pytest.raises(ToolExecutionError,match='within two public1mm steps'):push_contact_short(p)
    assert [c for c in calls if c[0]=='act']==[('act','left','BACK',1.),('act','left','BACK',1.)]


def test_short_push_stops_on_first_native_controller_refusal(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import push_contact_short
    p,calls,_=short_contact_policy(monkeypatch)
    p.c.action_feedback=lambda:dict(control_feedback=dict(left=dict(status='blocked')))
    with pytest.raises(ToolExecutionError,match='controller rejected'):push_contact_short(p)
    assert len([c for c in calls if c[0]=='act'])==1


def test_cold_contact_rebuild_is_real_bounded_and_counted_before_three_mm_push(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import push_contact_short
    p,calls,state=short_contact_policy(monkeypatch,contact=False)
    contact=[False];approaches=[]
    tip=p.tip('left');p.tip=lambda _:tip.copy()
    p.snapshot=lambda:(state,{frozenset(('lid','left_finger1'))}if contact[0]else set())
    def act(side,token,mm):
        calls.append(('act',side,token,mm));p.c.steps+=1
        tip[0]-=mm/1000
        if mm==1.:
            approaches.append(mm)
            if len(approaches)==2:contact[0]=True
        else:
            assert mm==3. and contact[0]
            state['lid']['pos'][0]-=.0007
    p.act=act
    result=push_contact_short(p)
    assert [c[3]for c in calls if c[0]=='act']==[1.,1.,3.]
    assert result['actions']==3 and len(result['observations'])==4
    assert result['observations'][0]['finger_contact']==[False,False]
    assert result['observations'][2]['finger_contact']==[True,False]
    assert result['measured_lid_travel_x_m']==pytest.approx(.0007)


def test_real_lid_drop_does_not_trigger_old_height_band_or_count_as_short_push(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import push_contact_short
    p,calls,state=short_contact_policy(monkeypatch,contact=False)
    contact=[False];tip=p.tip('left');p.tip=lambda _:tip.copy()
    p.snapshot=lambda:(state,{frozenset(('lid','left_finger1'))}if contact[0]else set())
    def act(side,token,mm):
        calls.append(('act',side,token,mm));p.c.steps+=1;tip[0]-=mm/1000
        if mm==1.:
            state['lid']['pos'][0]-=.0043;state['lid']['pos'][2]-=.0126;contact[0]=True
    p.act=act
    with pytest.raises(ToolExecutionError,match='less than0.5mm'):push_contact_short(p)
    assert [c[3]for c in calls if c[0]=='act']==[1.,3.,3.,3.,3.]


def test_rebuilt_contact_approach_must_actually_continue_back(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import push_contact_short
    p,calls,_=short_contact_policy(monkeypatch,contact=False);tip=p.tip('left');p.tip=lambda _:tip.copy()
    def act(side,token,mm):calls.append(('act',side,token,mm));p.c.steps+=1;tip[0]+=.001
    p.act=act
    with pytest.raises(ToolExecutionError,match='failed to advance BACK'):push_contact_short(p)
    assert len([c for c in calls if c[0]=='act'])==1


def settled_lid_policy(monkeypatch,*,contact_after=4,push_travel=.0007,support=True):
    from videoicl_isaaclab import execution_design_e24_lid as module
    p,calls,state=short_contact_policy(monkeypatch,travel=0.,contact=False)
    p.spec.update(id='E24',variant='A',seed=4201)
    p.spec['execution_design']['condition']='I';p.a.scene=SimpleNamespace(spec=p.spec)
    p.a._engineering_resume_checkpoint=dict(diagnostic_only=True,source=dict(steps=1,physics_ticks=102))
    p.c._engineering_diagnostic_only=True;p.c._engineering_checkpoint_readback_passed=True
    state['lid']['pos']=[.04388484,.314801,.824709];tip=np.array([.16660058,.315383,.84660089]);p.tip=lambda _:tip.copy()
    contact=[False];p.c.contact_forces[frozenset(('lid','table'))]=.8666
    p.c.physics_ticks=0;p.c.evaluator=SimpleNamespace(update=lambda state,contacts,dt:None)
    p.s=dict(cups={name:{}for name in('blue','green','red')})
    state.update({name:dict(grasp=[False,False])for name in p.s['cups']})
    monkeypatch.setattr(module,'_lid_source_vertical_table_gap',lambda *args:.0007)
    def snapshot():
        pairs={frozenset(('lid','table'))}if support else set()
        pairs.update(frozenset((name,'box'))for name in p.s['cups'])
        if contact[0]:pairs.add(frozenset(('lid','left_finger1')))
        return state,pairs
    p.snapshot=snapshot
    def act(side,token,mm):
        calls.append(('act',side,token,mm));p.c.steps+=1;tip[0]-=.0024
        if contact[0]:state['lid']['pos'][0]-=push_travel
        else:
            state['lid']['pos'][0]-=.0002
            if p.c.steps>=contact_after:contact[0]=True
        p.c.physics_ticks+=1;p.c.evaluator.update(*p.snapshot(),.004)
    p.act=act
    return p,calls,state


def test_settled_native1_approaches_at_most_four_times_then_measures_only_the_contact_push(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import approach_settled_lid1_and_push
    p,calls,_=settled_lid_policy(monkeypatch)
    result=approach_settled_lid1_and_push(p,{})
    assert len([c for c in calls if c[0]=='act'])==result['actions']==5
    assert result['maximum_total_public_actions']==6
    assert all(c[1:]==('left','BACK',3.)for c in calls if c[0]=='act')
    assert result['measured_lid_travel_after_contact_m']==pytest.approx(.0007)
    assert result['measured_lid_slide_during_approach_m']==pytest.approx(.0008)
    assert not result['full_supported_overhang_or_side_grasp_completed']


def test_settled_approach_never_pushes_without_true_contact_or_credits_approach_drift(monkeypatch):
    from videoicl_isaaclab.execution_design_e24_lid import approach_settled_lid1_and_push
    p,calls,_=settled_lid_policy(monkeypatch,contact_after=99)
    with pytest.raises(ToolExecutionError,match='after four public3mm'):approach_settled_lid1_and_push(p,{})
    assert len([c for c in calls if c[0]=='act'])==4
    p,calls,_=settled_lid_policy(monkeypatch,push_travel=0.)
    with pytest.raises(ToolExecutionError,match='less than0.5mm actual lid travel'):approach_settled_lid1_and_push(p,{})
    assert len([c for c in calls if c[0]=='act'])==5


@pytest.mark.parametrize('bad',['source_step','source_tick','variant','condition','readback'])
def test_settled_entry_requires_the_exact_admitted_case_and_actual_table_support(monkeypatch,bad):
    from videoicl_isaaclab.execution_design_e24_lid import approach_settled_lid1_and_push
    p,calls,_=settled_lid_policy(monkeypatch,support=bad!='support')
    if bad=='source_step':p.a._engineering_resume_checkpoint['source']['steps']=0
    elif bad=='source_tick':p.a._engineering_resume_checkpoint['source']['physics_ticks']=101
    elif bad=='variant':p.spec['variant']='B'
    elif bad=='condition':p.spec['execution_design']['condition']='E'
    elif bad=='readback':p.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ToolExecutionError):approach_settled_lid1_and_push(p,{})
    assert calls==[]


def test_no_table_pair_never_becomes_true_and_does_not_mask_real_finger_push(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_lid as module
    p,calls,_=settled_lid_policy(monkeypatch,contact_after=1,support=False)
    p.c.contact_forces[frozenset(('lid','table'))]=0.
    result=module.approach_settled_lid1_and_push(p,{})
    assert result['local_completed']
    assert all(not row['lid_table_contact']and row['lid_table_force_n']==0.
               and not row['endpoint_lid_table_support']for row in result['observations'])


def test_actual_support_during_action_keeps_zero_endpoint_explicit(monkeypatch):
    from videoicl_isaaclab import execution_design_e24_lid as module
    p,calls,_=settled_lid_policy(monkeypatch,contact_after=1)
    original_snapshot=p.snapshot;original_act=p.act;air=[False];pair=frozenset(('lid','table'))
    def snapshot():
        state,contacts=original_snapshot()
        return state,contacts-{pair}if air[0]else contacts
    def action(*args,**kwargs):
        air[0]=False;p.c.contact_forces[pair]=.8666;original_act(*args,**kwargs)
        air[0]=True;p.c.contact_forces[pair]=0.
    p.snapshot=snapshot;p.act=action
    monkeypatch.setattr(module,'_lid_source_vertical_table_gap',lambda *args:.0007)
    result=module.approach_settled_lid1_and_push(p,{})
    assert result['local_completed']
    for row in result['observations'][1:]:
        assert not row['lid_table_contact']and not row['endpoint_lid_table_support']
        assert row['lid_table_force_n']==0.
        assert row['actual_action_support']['positive_tick_count']==1
        assert row['actual_action_support']['positive_duration_s']==pytest.approx(.004)


def test_native_force_observer_restores_original_update_after_first_error():
    from videoicl_isaaclab.execution_design_e24_lid import _lid_table_support_during
    updates=[];original=lambda *args:updates.append(args)
    c=SimpleNamespace(evaluator=SimpleNamespace(update=original),contact_forces={},physics_ticks=2)
    p=SimpleNamespace(c=c)
    def fail():
        c.evaluator.update({},set(),.004);raise RuntimeError('native refused')
    with pytest.raises(RuntimeError,match='native refused'):_lid_table_support_during(p,fail)
    assert c.evaluator.update is original and len(updates)==1
