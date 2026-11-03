import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e10_reference import contact_band_target
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
from types import SimpleNamespace
from videoicl_isaaclab.execution_design_e10_reference import acquire_thin_piece


def test_coarse_engineering_transit_keeps_public_limit_and_formal_policy_default():
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.realworld_structural_expert import StructuralAuthor
    spec=load('E10','A',4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    spec['execution_design']={'revision':'embodied50-execution-v3-20261102'}
    config={'control':{'step_mm':[.5,50.],'rotation_deg':[.5,10.]}}
    author=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config=config)),c=SimpleNamespace(steps=0),control_report={})
    assert StructuralAuthor(author).max_mm==10.
    author.control_report['engineering_reference_only']=True
    assert StructuralAuthor(author).max_mm==25.
    config['control']['step_mm'][1]=12.
    assert StructuralAuthor(author).max_mm==12.


def test_e10_native_toe_offset_no_longer_requests_descent_through_table():
    target=contact_band_target([-.13997,-.07878,.803],.8,.806,.8096025,.7999872)
    assert target[2]>.810
    assert target[2]-(.8096025-.7999872)==pytest.approx(.8008)
    np.testing.assert_allclose(target[:2],[-.13997,-.07878])


@pytest.mark.parametrize('bottom,top,tcp,toe',[(.8,.81,.81,.8),(.8,.806,.81,.82),(.8,.806,.85,.8)])
def test_unreviewed_body_or_actual_finger_geometry_fails_closed(bottom,top,tcp,toe):
    with pytest.raises(ToolExecutionError):contact_band_target([0,0,.803],bottom,top,tcp,toe)


def thin_mock(monkeypatch,held):
    from videoicl_isaaclab import author_clearance
    from videoicl_isaaclab import execution_design_e10_reference
    monkeypatch.setattr(author_clearance,'prepare_single_hand',lambda *args:None)
    monkeypatch.setattr(execution_design_e10_reference,'level_open_panda_pinch',lambda *args:None)
    monkeypatch.setattr(execution_design_e10_reference,'prepare_thin_hand',lambda *args:None)
    tcp=np.array([-.2,-.2,1.]);tokens=[]
    a=SimpleNamespace(task='E10',clearance=1.15,objects={'piece':{'size':[.02,.02,.003]}})
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True},align_gripper_axis=lambda *args:None,
                        finger_geometry=lambda side:{'lowest_z_task_m':tcp[2]-.0096})
    a.tip=lambda side:tcp.copy();a.point=lambda ref:np.array([0.,0.,.803]);a.frame=lambda ref:(np.zeros(3),np.eye(3))
    a.snapshot=lambda:({'piece':{'pos':[0,0,.803],'mat':np.eye(3)}},set())
    a.move=lambda side,target,**kw:tcp.__setitem__(slice(None),target)
    a.stage=lambda name:None;a.act=lambda side,token:tokens.append(token);a.held=lambda *args:held
    a.contact=lambda *args:False
    return a,tokens


def test_e10_reference_still_requires_real_hold(monkeypatch):
    a,tokens=thin_mock(monkeypatch,False)
    with pytest.raises(ToolExecutionError,match='actual hold'):
        acquire_thin_piece(a,{'actor':'piece','jaw_axis_local':[1,0,0]},'right')
    assert tokens==['RELEASE']+['GRASP']*5


def test_e10_reference_three_measured_holds_after_clear_toe(monkeypatch):
    a,tokens=thin_mock(monkeypatch,True)
    acquire_thin_piece(a,{'actor':'piece','jaw_axis_local':[1,0,0]},'right')
    assert tokens==['RELEASE']+['GRASP']*3
    assert a.a.finger_geometry('right')['lowest_z_task_m']==pytest.approx(.8008)


def route_mock(obstacle_z=.85, obstacle_x=.1, cargo_half_z=.003):
    a=SimpleNamespace(task='E10',spec={'fixtures':[]},objects={
        'piece':{'size':[.02,.02,cargo_half_z]},'obstacle':{'size':[.03,.03,.02]}})
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True},floor_clear_tcp=lambda side,floor:floor+.010)
    a.snapshot=lambda:({'piece':{'pos':[0,0,.9],'mat':np.eye(3)},
                       'obstacle':{'pos':[obstacle_x,0,obstacle_z],'mat':np.eye(3)}},set())
    a.point=lambda ref:np.array([0.,0.,.9]);a.tip=lambda side:np.array([0.,0.,.91])
    return a

def test_post_transport_measures_swept_obstacle_and_held_depth():
    from videoicl_isaaclab.execution_design_e10_reference import post_transport_height
    a=route_mock(.95,cargo_half_z=.04)
    height=post_transport_height(a,'piece','right',[0,0,0],[.2,0,.82],np.eye(3))
    assert height==pytest.approx(1.04)
    assert a.a.control_report['e10_measured_post_routes'][0]['obstacle_top_m']==pytest.approx(.97)

def test_post_transport_does_not_clamp_tall_obstacle_to_low_route():
    from videoicl_isaaclab.execution_design_e10_reference import post_transport_height
    a=route_mock(1.2)
    assert post_transport_height(a,'piece','right',[0,0,0],[.2,0,.82],np.eye(3))>1.25

def test_post_transport_ignores_off_corridor_actor():
    from videoicl_isaaclab.execution_design_e10_reference import post_transport_height
    a=route_mock(1.2,obstacle_x=-.5)
    assert post_transport_height(a,'piece','right',[0,0,0],[.2,0,.82],np.eye(3))==.94


def test_relay_site_is_real_table_and_avoids_actual_source_geometry():
    from videoicl_isaaclab.execution_design_e10_reference import relay_table_site
    a=route_mock();a.a.scene=SimpleNamespace(layout=SimpleNamespace(config={'table':{'position':[0,0,.78],'size':[.7,1.2,.04]}}),world_to_task=lambda p:p)
    point=relay_table_site(a,'piece')
    assert -.35<point[0]<-.20 and point[2]==pytest.approx(.804)
    assert np.linalg.norm(point[:2]-[.1,0])>.1


def test_relay_never_regrasps_without_actual_released_support(monkeypatch):
    from videoicl_isaaclab import execution_design_e10_reference as m
    a=route_mock();a.clearance=1.15;a.stage=lambda *x:None;a.frame=lambda ref:(np.zeros(3),np.eye(3));a.bottom_local=lambda name:[0,0,-.003]
    a.a.scene=SimpleNamespace(world_to_task=lambda p:p,robots={h:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([[-.45,y,.8]])))for h,y in [('left',.35),('right',-.35)]})
    a.lower_place=lambda *args,**kw:None
    a.snapshot=lambda:({'piece':{'pos':[0,0,.803],'mat':np.eye(3),'grasp':[False,False]}},set())
    monkeypatch.setattr(m,'relay_table_site',lambda *x:np.array([0,0,.804]));monkeypatch.setattr(m,'post_transport_height',lambda *x:.94)
    monkeypatch.setattr(m,'acquire_thin_piece',lambda *x:pytest.fail('Cannot regrasp unsupported relay'))
    with pytest.raises(ToolExecutionError,match='released table support'):
        m.relay_to_destination_hand(a,'piece',{'actor':'piece'},'right',[.15,.08,.82])
    assert a.clearance==1.15


def test_released_donor_physically_leaves_receiver_column():
    from videoicl_isaaclab.execution_design_e10_reference import park_released_donor
    a=route_mock();tip=np.array([-.28,0.,.87]);events=[]
    a.tip=lambda side:tip.copy();a.stage=lambda *x:None
    a.snapshot=lambda:({'piece':{'grasp':[False,False]}},set())
    def move(side,target,guard):guard();events.append(np.array(target));tip[:]=target
    a.move=move
    park_released_donor(a,'right',[-.45,-.3,.8])
    np.testing.assert_allclose(events[0],[-.28,0,.98]);np.testing.assert_allclose(tip,[-.28,-.3,.98])


def test_donor_must_not_retreat_while_still_touching_payload():
    from videoicl_isaaclab.execution_design_e10_reference import park_released_donor
    a=route_mock();a.snapshot=lambda:({'piece':{'grasp':[False,False]}},{frozenset(('piece','right_finger1'))})
    a.move=lambda *args:pytest.fail('no movement with residual actual contact')
    with pytest.raises(ToolExecutionError,match='actually empty'):
        park_released_donor(a,'right',[-.45,-.3,.8])


def test_near_side_pinch_changes_only_real_grasp_point_and_keeps_pinned_source_immutable():
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_e10_reference import near_side_piece_ref
    obj={'shape':'square','source_asset':{'sha256':'fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'}}
    a=SimpleNamespace(task='E10',a=SimpleNamespace(control_report={'engineering_reference_only':True}),objects={'piece':obj})
    ref={'actor':'piece','local':[.016,0.,0.],'jaw_axis_local':[1,0,0]};before=deepcopy((ref,obj))
    result=near_side_piece_ref(a,ref)
    assert result['local']==[0.,.010,0.] and result['jaw_axis_local']==[1,0,0]
    assert (ref,obj)==before
    obj['source_asset']['sha256']='wrong'
    with pytest.raises(ToolExecutionError,match='pinned source'):near_side_piece_ref(a,ref)


def test_preferred_grasp_offset_is_diagnostic_after_actual_hold_was_established(monkeypatch):
    a,tokens=thin_mock(monkeypatch,True)
    acquire_thin_piece(a,{'actor':'piece','jaw_axis_local':[1,0,0],'e10_reviewed_near_side':True},'left')
    assert len(a.a.control_report['e10_actual_near_side_grips'])==1
    assert a.a.control_report['e10_actual_near_side_grips'][0]['preferred_offset_band']is False


def test_closed_supported_pinch_accepts_real_side_material_without_a_precise_seating_coordinate():
    from videoicl_isaaclab.execution_design_e10_reference import seat_supported_contact_band
    toe=[.8038];commands=[]
    a=SimpleNamespace(objects={'piece':{'size':[.02,.02,.003]}},contact=lambda *x:True,stage=lambda *x:None)
    a.require_held=lambda *x:None;a.snapshot=lambda:({'piece':{'pos':[0,0,.803],'mat':np.eye(3)}},set())
    a.a=SimpleNamespace(finger_geometry=lambda side:{'lowest_z_task_m':toe[0]})
    a.tip=lambda side:np.array([0,0,toe[0]+.010])
    def act(side,token,mm):
        assert token=='DOWN' and .5<=mm<=1.
        commands.append(token);toe[0]-=mm/1000
    a.act=act
    seat_supported_contact_band(a,{'actor':'piece'},'right')
    assert not commands and toe[0]==.8038


def test_closed_pincher_stops_before_any_action_when_toe_already_hits_table():
    from videoicl_isaaclab.execution_design_e10_reference import seat_supported_contact_band
    a=SimpleNamespace(objects={'piece':{'size':[.02,.02,.003]}},contact=lambda *x:True,stage=lambda *x:None)
    a.require_held=lambda *x:None;a.snapshot=lambda:({'piece':{'pos':[0,0,.803],'mat':np.eye(3)}},set())
    a.a=SimpleNamespace(finger_geometry=lambda side:{'lowest_z_task_m':.8001})
    a.act=lambda *x,**kw:pytest.fail('No move through actual table')
    with pytest.raises(ToolExecutionError,match='table'):seat_supported_contact_band(a,{'actor':'piece'},'right')
