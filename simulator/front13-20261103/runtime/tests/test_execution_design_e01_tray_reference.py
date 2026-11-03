from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e01_tray_reference import transport_tray
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def fixture(grip_works=True,support=True):
    pos=np.array([-.20,0.,.83]);tips={side:np.array([-.3,0,.85])for side in ['left','right']}
    held={'left':False,'right':True};events=[]
    a=SimpleNamespace(task='E01',objects={'tray':{'size':[.11,.16,.014],'source_asset':{'sha256':'f3de40e9b8aeabc426e1f7056d596d9e01baaf8cb961274d7405b459349fa56c'}}},a=SimpleNamespace(control_report={'engineering_reference_only':True},align_gripper_axis=lambda *x:None))
    a.d={'storage_surfaces':{'rack_lower':{'xy':[.3,0],'half_size':[.14,.19]},'rack_upper':{'xy':[.1,0],'half_size':[.14,.19]}}}
    a.spec={'fixtures':[]}
    a.a.finger_geometry=lambda side:{'fingers':[{'aabb_min_task_m':(tips[side]+[-.01,-.01,-.009]).tolist(),'aabb_max_task_m':(tips[side]+[.01,.01,.04]).tolist()}]}
    a.a.tcp_rotation_task=lambda side:np.eye(3)
    a.snapshot=lambda:({'tray':{'pos':pos.copy(),'mat':np.eye(3)}},set())
    a.tip=lambda side:tips[side].copy();a.frame=lambda ref:(pos.copy(),np.eye(3));a.point=lambda ref:pos+np.asarray(ref['local'])
    def require(ref,side):
        if not held[side]:raise ToolExecutionError('real grip absent')
    a.require_held=require;a.held=lambda ref,side:held[side];a.stage=lambda name:events.append(('stage',name))
    directions={'FWD':[1,0,0],'BACK':[-1,0,0],'LEFT':[0,1,0],'RIGHT':[0,-1,0],'UP':[0,0,1],'DOWN':[0,0,-1]}
    def act(side,token,mm=1,follower=None):
        events.append((token,side,follower,dict(held)))
        if token in ['GRASP','RELEASE']:
            held[side]=bool(token=='GRASP'and grip_works)
            if follower:held[follower]=bool(token=='GRASP'and grip_works)
        else:
            assert follower and held['left']and held['right']
            delta=np.array(directions[token])*mm/1000
            pos[:]+=delta
            for tip in tips.values():tip[:]+=delta
    a.act=act
    def move(side,target,guard=None,follower=None):
        if guard:guard()
        tips[side][:]=target
    a.move=move;a.bottom_local=lambda name:np.array([0,0,-.014]);a.measured_staging_route_height=lambda *x:.98
    a.wait=lambda *x:None;a.contact=lambda *x:support
    return a,events,pos


def test_second_real_grip_precedes_releasing_original_and_all_transport_is_dual():
    a,events,pos=fixture();transport_tray(a,[-.18,.1,.8],'table',existing_side='right')
    right_release=next(e for e in events if e[:2]==('RELEASE','right'))
    assert right_release[3]['left'] is True
    transport=[e for e in events if e[0]in ['UP','DOWN','FWD','BACK','LEFT','RIGHT']]
    assert transport and all(e[2]=='right' and all(e[3].values())for e in transport)
    np.testing.assert_allclose(pos+[0,0,-.014],[-.18,.1,.801],atol=.002)


def test_rim_acquisition_resumes_lower_phase_without_releasing_or_repeating_approach():
    from videoicl_isaaclab.execution_design_e01_tray_reference import acquire_tray_rim
    a,events,_=fixture();original_move=a.move;calls=[];interrupt=[True]
    def move(side,target,guard=None):
        calls.append(a._e01_rim_acquisition['phase'])
        if calls[-1]=='lower'and interrupt[0]:
            interrupt[0]=False;raise RuntimeError('local budget')
        original_move(side,target,guard)
    a.move=move
    with pytest.raises(RuntimeError,match='local budget'):acquire_tray_rim(a,'left','right')
    assert a._e01_rim_acquisition['phase']=='lower'
    boundary=len(events);result=acquire_tray_rim(a,'left','right')
    assert result['local_completed']and result['whole_task_score']is None
    assert not any(e[0]=='RELEASE'for e in events[boundary:])
    assert calls==['raise','over','lower','lower']
    assert set(a._e01_verified_rim_grips)=={'left'}


def test_rim_acquisition_checks_original_support_material_point_before_any_action():
    from videoicl_isaaclab.execution_design_e01_tray_reference import acquire_tray_rim
    a,events,_=fixture();a._e01_support_grip_local=np.array([1.,0,0])
    with pytest.raises(ToolExecutionError,match='original material-point'):
        acquire_tray_rim(a,'left','right')
    assert events==[]


def test_changed_reviewed_rim_resumes_from_actual_empty_hand_without_new_release():
    from videoicl_isaaclab.execution_design_e01_tray_reference import acquire_tray_rim
    a,events,pos=fixture();a.snapshot=lambda:({'tray':{'pos':pos.copy(),'mat':np.eye(3),'grasp':[False,True]}},set())
    a._e01_rim_acquisition=dict(side='left',other='right',phase='lower',height=.98,stable=0)
    result=acquire_tray_rim(a,'left','right',rim_x=.055)
    assert result['local_completed']and a._e01_rim_acquisition['rim_x']==.055
    assert not any(e[0]=='RELEASE'for e in events)
    assert not any(e[0]=='stage'and e[1].endswith(('align','raise'))for e in events)


def test_failed_second_grip_never_releases_original_or_lifts():
    a,events,_=fixture(False)
    with pytest.raises(ToolExecutionError,match='actual left grip'):
        transport_tray(a,[-.18,.1,.8],'table',existing_side='right')
    assert not any(e[:2]==('RELEASE','right')for e in events)
    assert not any(e[0]=='UP'for e in events)


def test_dual_release_does_not_replace_actual_support_verification():
    a,_,_=fixture(support=False)
    with pytest.raises(ToolExecutionError,match='actual support'):
        transport_tray(a,[-.18,.1,.8],'table',existing_side='right')


def test_actual_bilateral_drift_corrected_with_public_half_mm_only():
    from videoicl_isaaclab.execution_design_e01_tray_reference import correct_dual_grip_drift
    pos=np.array([0.,0.,.83]);tips={'left':np.array([0.,.151,.83]),'right':np.array([0.,-.151,.83])};events=[]
    a=SimpleNamespace(frame=lambda ref:(pos,np.eye(3)),tip=lambda side:tips[side])
    def act(side,token,mm):
        events.append((side,token,mm));tips[side][1]+=(1 if token=='LEFT'else -1)*mm/1000
    a.act=act
    correct_dual_grip_drift(a,{'left':[0,.15,0],'right':[0,-.15,0]},lambda:None)
    assert events and all(mm==.5 for _,_,mm in events)
    assert max(abs(tips['left'][1]-.15),abs(tips['right'][1]+.15))<=.0005


def test_material_point_drift_never_overrides_lost_actual_grip():
    from videoicl_isaaclab.execution_design_e01_tray_reference import correct_dual_grip_drift
    a=SimpleNamespace()
    def lost():raise ToolExecutionError('actual grip lost')
    with pytest.raises(ToolExecutionError,match='actual grip lost'):
        correct_dual_grip_drift(a,{},lost)


@pytest.mark.parametrize('offset',[.007,float('nan')])
def test_large_or_nonfinite_grip_drift_never_moves_or_changes_tray(offset):
    from videoicl_isaaclab.execution_design_e01_tray_reference import correct_dual_grip_drift
    pos=np.array([0.,0.,.83]);before=pos.copy();events=[]
    a=SimpleNamespace(frame=lambda ref:(pos,np.eye(3)),tip=lambda side:np.array([offset,0.,.83]),act=lambda *args,**kwargs:events.append(args))
    with pytest.raises(ToolExecutionError):
        correct_dual_grip_drift(a,{'left':[0,0,0],'right':[0,0,0]},lambda:None)
    assert not events;np.testing.assert_array_equal(pos,before)


def test_loaded_vertical_deflection_does_not_push_supported_tray_down():
    from videoicl_isaaclab.execution_design_e01_tray_reference import correct_dual_grip_drift
    events=[];a=SimpleNamespace(frame=lambda ref:(np.array([0.,0.,.83]),np.eye(3)),tip=lambda side:np.array([0.,0.,.832]),act=lambda *args,**kwargs:events.append(args))
    correct_dual_grip_drift(a,{'left':[0,0,0],'right':[0,0,0]},lambda:None)
    assert not events


def test_asymmetric_actual_lift_lets_lower_hand_catch_up_without_down_or_pose_write():
    from videoicl_isaaclab.execution_design_e01_tray_reference import balanced_dual_step
    tips={'left':np.array([0.,.15,.8305]),'right':np.array([0.,-.15,.835])};events=[]
    a=SimpleNamespace(tip=lambda side:tips[side].copy(),act=lambda *args,**kwargs:events.append((args,kwargs)))
    before={side:point.copy()for side,point in tips.items()}
    balanced_dual_step(a,'UP',.5,{'left':.83,'right':.83})
    assert events==[(('left','UP'),{'mm':.5})]
    for side in tips:np.testing.assert_array_equal(tips[side],before[side])
    events.clear();balanced_dual_step(a,'DOWN',.5,{'left':.83,'right':.83})
    assert events==[(('right','DOWN'),{'mm':.5})]


def test_compliant_real_grip_is_checked_without_forcing_lateral_contact():
    from videoicl_isaaclab.execution_design_e01_tray_reference import validate_dual_grip_drift
    events=[];a=SimpleNamespace(a=SimpleNamespace(control_report={}),frame=lambda ref:(np.zeros(3),np.eye(3)),tip=lambda side:np.array([0.,.003,.005]),act=lambda *args,**kwargs:events.append(args))
    validate_dual_grip_drift(a,{'left':[0,0,0],'right':[0,0,0]},lambda:None)
    assert not events
    a.tip=lambda side:np.array([0.,.0061,0.])
    validate_dual_grip_drift(a,{'left':[0,0,0],'right':[0,0,0]},lambda:None)
    assert a.a.control_report['e01_dual_material_drift_diagnostic']['right']['former_macro_gate_exceeded']
    def lost():raise ToolExecutionError('actual grip lost')
    with pytest.raises(ToolExecutionError,match='actual grip lost'):validate_dual_grip_drift(a,{},lost)


def test_forward_grip_pinned_mesh_and_actual_finger_clearance():
    from videoicl_isaaclab.execution_design_e01_tray_reference import reviewed_forward_grips,require_finger_floor_clearance
    a,_,_=fixture();refs=reviewed_forward_grips(a)
    assert refs['left']['local']==[-.055,.147204,.005]
    assert refs['right']['local']==[-.055,-.144690,.005]
    require_finger_floor_clearance(a,'left')
    a.spec={'fixtures':[dict(type='box',xy=[-.3,0],size=[.03,.03,.01],z=.85)]}
    with pytest.raises(ToolExecutionError,match='support clearance'):require_finger_floor_clearance(a,'left')
    a.objects['tray']['source_asset']['sha256']='wrong'
    with pytest.raises(ToolExecutionError,match='pinned source'):reviewed_forward_grips(a)


def test_current_rim_error_regrasp_is_bounded_and_checks_both_hands():
    from videoicl_isaaclab.execution_design_e01_tray_reference import settle_current_dual_grips
    errors={'left':np.array([0.,0.,.014]),'right':np.array([0.,.0045,.002])};calls=[]
    a=SimpleNamespace(tip=lambda side:errors[side],point=lambda ref:np.zeros(3),stage=lambda name:None,a=SimpleNamespace(control_report={}))
    def acquire(side,other):calls.append((side,other));errors[side]=np.zeros(3)
    settle_current_dual_grips(a,{'left':{},'right':{}},acquire,lambda:None)
    assert calls==[('left','right')]
    errors['left']=np.array([0.,0.,.014]);calls.clear()
    def moves_other(side,other):calls.append((side,other));errors[side]=np.zeros(3);errors[other]=np.array([0.,0.,.014])
    with pytest.raises(ToolExecutionError,match='bounded regrasp'):
        settle_current_dual_grips(a,{'left':{},'right':{}},moves_other,lambda:None)
    assert len(calls)==1


@pytest.fixture(autouse=True)
def no_native_diagnostic_in_mock(monkeypatch):
    from videoicl_isaaclab import execution_design_e01_contact_diagnostic
    monkeypatch.setattr(execution_design_e01_contact_diagnostic,'install',lambda author:None)


def test_shelf_withdrawal_uses_native_com_support_and_never_lifts():
    from videoicl_isaaclab.execution_design_e01_tray_reference import extract_whole_tray_from_lower_shelf
    a,events,pos=fixture();a.d['storage_surfaces']['rack_lower']={'actor':'fixture0','xy':[-.05,0],'half_size':[.14,.19]}
    a.a.scene=SimpleNamespace(layout=SimpleNamespace(config={'table':{'position':[0,0,.75],'size':[.7,1.,.1]}}),world_to_task=lambda p:p)
    a._e01_native_bottom_local=np.array([[x,y,-.014]for x in(-.09,.09)for y in(-.14,.14)])
    a._e01_native_com_local=np.zeros(3)
    a.tip=lambda side:pos+np.array([-.1,0,.02])
    def act(side,token,mm):events.append((side,token,mm));pos[0]-=mm/1000
    a.act=act
    extract_whole_tray_from_lower_shelf(a,'right')
    assert pos[0]+.11<=-.206 and all(e[1]=='BACK'for e in events if len(e)==3)
    pos[:]=[-.2,0,.83];a.a.scene.layout.config['table']['size']=[.6,1.,.1]
    events.clear()
    with pytest.raises(ToolExecutionError,match='support polygon'):extract_whole_tray_from_lower_shelf(a,'right')
    assert not any(len(e)==3 for e in events)


def test_support_polygon_allows_overhang_but_rejects_com_outside_support():
    from videoicl_isaaclab.execution_design_e01_tray_reference import supported_com_margin
    points=np.array([[x,y,.8]for x in(-.426,-.206)for y in(-.16,.16)])
    margin,polygon=supported_com_margin(points,[-.316,0,.82],[-.35,-.7],[.35,.7])
    assert margin==pytest.approx(.034) and min(p[0]for p in polygon)==pytest.approx(-.35)
    margin,_=supported_com_margin(points,[-.36,0,.82],[-.35,-.7],[.35,.7])
    assert margin<0


def test_bottom_support_rejects_no_overlap_even_when_hand_is_holding():
    from videoicl_isaaclab.execution_design_e01_tray_reference import supported_com_margin
    points=np.array([[x,y,.8]for x in(-.6,-.4)for y in(-.1,.1)])
    margin,polygon=supported_com_margin(points,[-.5,0,.82],[-.35,-.7],[.35,.7])
    assert margin<0 and not polygon


def test_cooked_mesh_vertices_ignore_stale_authored_body_pose():
    from videoicl_isaaclab.execution_design_e01_contact_diagnostic import body_local_vertices
    vertices=np.array([[.01,.02,.03],[-.01,-.02,0.]])
    body=np.eye(4);body[:3,:3]=np.array([[0,1,0],[-1,0,0],[0,0,1]]);body[3,:3]=[10,20,30]
    child=np.eye(4);child[3,:3]=[.005,0,-.002]
    actual=body_local_vertices(vertices,child@body,body)
    np.testing.assert_allclose(actual,vertices+[.005,0,-.002],atol=1e-12)
    other=body.copy();other[3,:3]=[-99,45,25]
    np.testing.assert_allclose(body_local_vertices(vertices,child@other,other),actual,atol=1e-12)


@pytest.mark.parametrize('rack_present',[True,False])
def test_front_settles_using_public_down_before_withdrawal_or_refuses_lost_rack(rack_present):
    from videoicl_isaaclab.execution_design_e01_tray_reference import extract_whole_tray_from_lower_shelf
    a,events,pos=fixture();a.d['storage_surfaces']['rack_lower']={'actor':'fixture0','xy':[-.05,0],'half_size':[.14,.19]}
    a.a.scene=SimpleNamespace(layout=SimpleNamespace(config={'table':{'position':[0,0,.75],'size':[.7,1.,.1]}}),world_to_task=lambda p:p)
    a._e01_native_bottom_local=np.array([[x,y,-.014]for x in(-.09,.09)for y in(-.14,.14)])
    a._e01_native_com_local=np.zeros(3);tip=np.array([-.3,0,.85]);a.tip=lambda side:tip.copy()
    a.contact=lambda name,support:(tip[2]<=.8471)if support=='table'else rack_present
    def act(side,token,mm):
        events.append((side,token,mm))
        if token=='DOWN':tip[2]-=mm/1000
        elif token=='BACK':pos[0]-=mm/1000;tip[0]-=mm/1000
        else:raise AssertionError(token)
    a.act=act
    if not rack_present:
        with pytest.raises(ToolExecutionError,match='rack support'):extract_whole_tray_from_lower_shelf(a,'right')
        assert not any(len(e)==3 for e in events)
    else:
        extract_whole_tray_from_lower_shelf(a,'right')
        actions=[e for e in events if len(e)==3]
        assert actions[0]==('right','DOWN',.5)
        first_back=next(i for i,e in enumerate(actions)if e[1]=='BACK')
        assert all(e[1]=='DOWN'for e in actions[:first_back])
        assert all(e[1]=='BACK'for e in actions[first_back:])


def test_supported_tray_orientation_follows_measured_pitch_by_public_half_degree_only():
    from videoicl_isaaclab.execution_design_e01_tray_reference import follow_supported_tray_orientation
    from scipy.spatial.transform import Rotation
    events=[];a=SimpleNamespace(a=SimpleNamespace(tcp_rotation_task=lambda side:np.eye(3)),act=lambda *args,**kw:events.append((args,kw)))
    assert follow_supported_tray_orientation(a,'right',Rotation.from_euler('y',-2.,degrees=True).as_matrix())
    assert events==[(('right','PITCH_DOWN'),{'degrees':.5})]
    events.clear();assert not follow_supported_tray_orientation(a,'right',np.eye(3));assert not events


def test_verified_table_touch_can_continue_on_original_rack_with_actual_hold_and_material_band():
    from videoicl_isaaclab.execution_design_e01_tray_reference import extract_whole_tray_from_lower_shelf
    a,events,pos=fixture();a.d['storage_surfaces']['rack_lower']={'actor':'fixture0','xy':[-.05,0],'half_size':[.14,.19]}
    a.a.scene=SimpleNamespace(layout=SimpleNamespace(config={'table':{'position':[0,0,.75],'size':[.7,1.,.1]}}),world_to_task=lambda p:p)
    a._e01_native_bottom_local=np.array([[x,y,-.014]for x in(-.09,.09)for y in(-.14,.14)])
    a._e01_native_com_local=np.zeros(3);a.a.control_report['e01_table_support_previously_verified']=True
    a.tip=lambda side:pos+np.array([-.1,0,.02])
    a.contact=lambda name,support:(pos[0]<-.25)if support=='table'else(pos[0]>=-.25)
    def act(side,token,mm):events.append((side,token,mm));pos[0]-=mm/1000
    a.act=act;extract_whole_tray_from_lower_shelf(a,'right')
    assert pos[0]+.11<=-.206 and all(e[1]=='BACK'for e in events if len(e)==3)
    pos[:]=[-.2,0,.83];events.clear();a.contact=lambda *args:False
    with pytest.raises(ToolExecutionError,match='table and original rack support'):
        extract_whole_tray_from_lower_shelf(a,'right')
    assert not any(len(e)==3 for e in events)
