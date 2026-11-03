from pathlib import Path
from copy import deepcopy
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_e12_reference import horizontal_charger_grasps
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def source():
    b=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'
    s=load('E12','A',0,b,verify_files=False)
    s['execution_design']={'revision':'embodied50-execution-v3-20261102'}
    return s


def test_horizontal_source_body_grasp_does_not_modify_task_or_existing_geometry():
    s=source();before=deepcopy(s);g=horizontal_charger_grasps(s,s['semantic']['structural_grasps'])
    assert s==before
    rotation=_axis_rotation([1,0,0],np.pi/2)
    for name in s['semantic']['groups']['chargers']:
        np.testing.assert_allclose(rotation@g[name]['jaw_axis_local'],[1,0,0],atol=1e-10)
        assert (rotation@np.array(g[name]['local']))[2]==pytest.approx(.012)
        assert g[name]['local'][2]==s['semantic']['structural_grasps'][name]['local'][2]


def test_unreviewed_asset_never_silently_gets_this_candidate():
    s=source();next(o for o in s['objects']if o['id']=='charger_1')['source_asset']['sha256']='0'*64
    with pytest.raises(ValueError,match='reviewed charger collision'):
        horizontal_charger_grasps(s,s['semantic']['structural_grasps'])


def aperture_author(angle_deg=0,shift=(0,0,0)):
    from types import SimpleNamespace
    from videoicl_isaaclab.realworld_structural_evidence import _basis
    s=source();sem=s['semantic'];socket_rotation=_axis_rotation([0,0,1],np.pi/2)
    body_rotation=socket_rotation@_axis_rotation([0,1,0],np.radians(angle_deg))
    hole=sem['slots']['1']['holes'][0];pin=sem['pins']['charger_1'][0]
    socket_origin=np.array([.08,.04,.80001]);center=socket_origin+socket_rotation@np.array(hole['center_local'])
    body_origin=center+[0,0,.025]-body_rotation@np.array(pin['tip_local'])+np.array(shift)
    a=SimpleNamespace(s=sem)
    a.frame=lambda ref:(socket_origin,socket_rotation)if ref.get('actor')=='strip'else(body_origin,body_rotation)
    a.body_point=lambda ref,point:a.frame(ref)[0]+a.frame(ref)[1]@np.array(point)
    return a

def test_actual_both_pins_fit_at_exact_source_alignment():
    from videoicl_isaaclab.execution_design_e12_reference import pin_aperture_diagnostics
    rows=pin_aperture_diagnostics(aperture_author(),'charger_1',1)
    assert all(r['fits']for r in rows)
    for r in rows:np.testing.assert_allclose(r['margin_m'],[.0003,.0003],atol=1e-12)

def test_previous_native_2point8degree_rotation_is_not_safe_insertion():
    from videoicl_isaaclab.execution_design_e12_reference import pin_aperture_diagnostics
    assert not all(r['fits']for r in pin_aperture_diagnostics(aperture_author(2.8),'charger_1',1))

def test_centering_first_pin_does_not_hide_second_pin_sweep():
    from videoicl_isaaclab.execution_design_e12_reference import pin_aperture_diagnostics
    rows=pin_aperture_diagnostics(aperture_author(2.8),'charger_1',1)
    assert rows[0]['lateral_m']==pytest.approx([0,0])
    assert min(rows[0]['margin_m'])<0

def test_public_2mm_placement_tolerance_cannot_certify_tiny_socket():
    from videoicl_isaaclab.execution_design_e12_reference import pin_aperture_diagnostics
    assert not all(r['fits']for r in pin_aperture_diagnostics(aperture_author(shift=(.001,0,0)),'charger_1',1))


def test_channel_clearance_uses_only_material_that_has_entered_the_socket():
    from videoicl_isaaclab.execution_design_e12_reference import pin_aperture_diagnostics,insertion_channel_diagnostics
    a=aperture_author(.344,shift=(0,.0002,-.027))
    assert not all(row['fits']for row in pin_aperture_diagnostics(a,'charger_1',1))
    rows=insertion_channel_diagnostics(a,'charger_1',1)
    assert all(row['fits']and min(row['margin_m'])>.00005 for row in rows)
    air=insertion_channel_diagnostics(aperture_author(.344),'charger_1',1)
    assert all(row['occupied_vertices']==0 and row['margin_m']is None for row in air)


def insertion_mock(monkeypatch,misalign=False):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e12_reference as m
    a=aperture_author();a.task='E12';a.a=SimpleNamespace(control_report={'engineering_reference_only':True});a.clearance=1.15
    control=np.array([.08,.059,.86801]);events=[];calls=[0]
    a.require_held=lambda *args:None;a.point=lambda ref:control.copy();a.tip=lambda side:control.copy()
    a.move_point=lambda side,ref,target,guard:control.__setitem__(slice(None),target)
    a.rotate_actor=lambda *args:None;a.stage=lambda name:events.append(name)
    def act(side,token,mm=1.,degrees=1.):
        events.append(token)
        delta={'STILL':[0,0,0],'DOWN':[0,0,-mm/1000],'UP':[0,0,mm/1000],'FWD':[mm/1000,0,0],'BACK':[-mm/1000,0,0],'LEFT':[0,mm/1000,0],'RIGHT':[0,-mm/1000,0]}[token]
        control[:]+=delta
    a.act=act;a.release=lambda *args:events.append('RELEASE');a.move=lambda *args:events.append('RETREAT');a.wait=lambda *args:None;a.contact=lambda *args:'RELEASE'in events
    def geometry(*args):
        calls[0]+=1
        return [dict(fits=not(misalign and any(str(e).startswith('precision-insert')for e in events)),axial_m=.002 if misalign and any(str(e).startswith('precision-insert')for e in events)else .025,margin_m=[.0003,.0003])]*2
    monkeypatch.setattr(m,'pin_aperture_diagnostics',geometry)
    return a,events


def test_precision_insertion_uses_public_down_and_real_support(monkeypatch):
    from videoicl_isaaclab.execution_design_e12_reference import insert_charger_precisely
    a,events=insertion_mock(monkeypatch)
    insert_charger_precisely(a,'charger_1',{'actor':'charger_1'},'right',1,a.frame({'actor':'charger_1'})[1],.0119)
    assert events.count('DOWN')>=36
    assert events[-2:]==['RELEASE','RETREAT']


def test_lost_pin_clearance_prevents_next_down_and_release(monkeypatch):
    from videoicl_isaaclab.execution_design_e12_reference import insert_charger_precisely
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    a,events=insertion_mock(monkeypatch,True)
    with pytest.raises(ToolExecutionError,match='clearance lost'):
        insert_charger_precisely(a,'charger_1',{'actor':'charger_1'},'right',1,a.frame({'actor':'charger_1'})[1],.0119)
    assert 'DOWN'not in events[events.index('precision-insert-both-pins-slot-1')+1:] and 'RELEASE'not in events


def test_airborne_down_drift_recentered_before_next_down(monkeypatch):
    from videoicl_isaaclab import execution_design_e12_reference as m
    a,events=insertion_mock(monkeypatch);original=a.act;injected=[False];drifting=[False]
    def act(side,token,mm=1.,degrees=1.):
        original(side,token,mm=mm,degrees=degrees)
        if token=='DOWN'and not injected[0]and 'precision-insert-both-pins-slot-1'in events:
            original(side,'FWD',mm=.5);injected[0]=True;drifting[0]=True
        elif token=='BACK':drifting[0]=False
    a.act=act;a.contact=lambda *args:'RELEASE'in events
    monkeypatch.setattr(m,'pin_aperture_diagnostics',lambda *args:[dict(fits=not drifting[0],axial_m=.023,margin_m=[.0003,.0003])]*2)
    m.insert_charger_precisely(a,'charger_1',{'actor':'charger_1'},'right',1,a.frame({'actor':'charger_1'})[1],.0119)
    first_down=events.index('DOWN',events.index('precision-insert-both-pins-slot-1'));assert events[first_down:first_down+4]==['DOWN','FWD','BACK','DOWN']
    assert events[-2:]==['RELEASE','RETREAT']


@pytest.mark.parametrize('gap,contact',[(.002,False),(.023,True)])
def test_near_mouth_or_contact_never_recentered_under_load(monkeypatch,gap,contact):
    from videoicl_isaaclab import execution_design_e12_reference as m
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    a,events=insertion_mock(monkeypatch);calls=[0]
    def geometry(*args):
        calls[0]+=1;active='precision-insert-both-pins-slot-1'in events;return [dict(fits=not active,axial_m=gap if active else .025,margin_m=[.0003,.0003])]*2
    monkeypatch.setattr(m,'pin_aperture_diagnostics',geometry);a.contact=lambda *args:contact and 'precision-insert-both-pins-slot-1'in events
    with pytest.raises(ToolExecutionError,match='clearance lost'):
        m.insert_charger_precisely(a,'charger_1',{'actor':'charger_1'},'right',1,a.frame({'actor':'charger_1'})[1],.0119)
    assert not any(t in events[events.index('precision-insert-both-pins-slot-1')+1:]for t in ['DOWN','BACK','FWD','RELEASE'])


@pytest.mark.parametrize('held,contact',[(True,False),(False,True),(False,False)])
def test_next_charger_retreat_requires_actual_empty_hand(held,contact):
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e12_reference import prepare_next_charger_acquisition
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    moves=[];a=SimpleNamespace(task='E12',clearance=.94,
        a=SimpleNamespace(control_report={'engineering_reference_only':True,'e12_pin_alignment':[{}]}),
        snapshot=lambda:({'charger_1':{'grasp':[False,held]}},{frozenset(('charger_1','right_finger1'))}if contact else set()),
        tip=lambda side:np.array([.08,.06,.94]),point=lambda ref:np.array([-.1,-.12,.836]),stage=lambda s:None)
    def move(side,target,guard):guard();moves.append(target)
    a.move=move
    a.a.control_report['e12_actual_acquired_hand_frames']=[dict(side='right',relative_hand_rotation=np.eye(3).tolist())]
    a.frame=lambda ref:(np.zeros(3),np.eye(3));a.a.tcp_rotation_task=lambda side:np.eye(3)
    if held or contact:
        with pytest.raises(ToolExecutionError,match='empty hand'):prepare_next_charger_acquisition(a,{'actor':'charger_2'},'right')
        assert not moves
    else:
        prepare_next_charger_acquisition(a,{'actor':'charger_2'},'right')
        assert len(moves)==2 and np.allclose(moves[-1],[-.1,-.12,.94])


def test_restore_first_grasp_requires_actual_frame_and_uses_public_rotation():
    from videoicl_isaaclab.execution_design_e12_reference import restore_first_charger_hand
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    from types import SimpleNamespace
    from scipy.spatial.transform import Rotation
    angle=[10.];events=[];checks=[]
    a=SimpleNamespace(a=SimpleNamespace(control_report={}),tip=lambda s:np.array([0.,0.,1.]),frame=lambda ref:(np.zeros(3),np.eye(3)),stage=lambda s:None)
    with pytest.raises(ToolExecutionError,match='unavailable'):restore_first_charger_hand(a,{'actor':'charger_2'},'right',lambda:None)
    a.a.control_report['e12_actual_acquired_hand_frames']=[dict(side='right',relative_hand_rotation=np.eye(3).tolist())]
    a.a.tcp_rotation_task=lambda side:Rotation.from_euler('z',angle[0],degrees=True).as_matrix()
    def act(side,token,degrees):events.append((side,token,degrees));angle[0]-=degrees
    a.act=act;a.c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'right':{'orientation_error_rad':0.}}});restore_first_charger_hand(a,{'actor':'charger_2'},'right',lambda:checks.append(True))
    assert len(checks)==3 and events==[('right','ROTATE_CW',5.),('right','ROTATE_CW',5.)]


def test_empty_restore_pending_rotation_uses_explicit_still_not_larger_rotation():
    from videoicl_isaaclab.execution_design_e12_reference import restore_first_charger_hand
    from types import SimpleNamespace
    from scipy.spatial.transform import Rotation
    angle=[5.];pending=[0.];events=[]
    a=SimpleNamespace(a=SimpleNamespace(control_report={'e12_actual_acquired_hand_frames':[dict(side='right',relative_hand_rotation=np.eye(3).tolist())]}),tip=lambda side:np.array([0,0,1.]),frame=lambda ref:(np.zeros(3),np.eye(3)),stage=lambda s:None)
    a.a.tcp_rotation_task=lambda side:Rotation.from_euler('z',angle[0],degrees=True).as_matrix()
    a.c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'right':{'orientation_error_rad':pending[0]}}})
    def act(side,token,degrees=None):
        events.append((token,degrees))
        if token=='STILL':angle[0]=0.;pending[0]=0.
        else:angle[0]=3.;pending[0]=.052
    a.act=act;restore_first_charger_hand(a,{'actor':'charger_2'},'right',lambda:None)
    assert events==[('ROTATE_CW',5.),('STILL',None)]
    assert a.a.control_report['e12_empty_restore_public_holds']==1


def test_held_charger_pending_goal_settles_through_public_still_before_new_relative_rotation():
    from types import SimpleNamespace
    from scipy.spatial.transform import Rotation
    from videoicl_isaaclab.execution_design_e12_reference import rotate_charger_with_public_holds
    angle=[9.];pending=[0.];events=[];guards=[]
    a=SimpleNamespace(task='E12',a=SimpleNamespace(control_report={'engineering_reference_only':True}),
        s={'slots':{'1':{'ref':{'actor':'strip'}}}},contact=lambda *args:False,
        require_held=lambda *args:guards.append(True),
        frame=lambda ref:(np.zeros(3),Rotation.from_euler('z',angle[0],degrees=True).as_matrix()))
    a.c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'right':{'orientation_error_rad':pending[0]}}})
    def act(side,token,degrees=None):
        events.append((token,degrees))
        if token=='STILL':angle[0]=0.;pending[0]=0.
        else:angle[0]=6.;pending[0]=np.radians(6.)
    a.act=act
    rotate_charger_with_public_holds(a,'charger_2','right',np.eye(3))
    assert events[0][0]=='ROTATE_CW' and events[0][1]==pytest.approx(9.)
    assert events[1:]==[('STILL',None)]
    assert len(guards)==3 and a.a.control_report['e12_held_rotation_public_holds']==1


@pytest.mark.parametrize('lost,contact',[(True,False),(False,True)])
def test_held_charger_coarse_rotation_never_continues_with_lost_grip_or_socket_contact(lost,contact):
    from types import SimpleNamespace
    from scipy.spatial.transform import Rotation
    from videoicl_isaaclab.execution_design_e12_reference import rotate_charger_with_public_holds
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    events=[]
    def held(*args):
        if lost:raise ToolExecutionError('real grip lost')
    a=SimpleNamespace(task='E12',a=SimpleNamespace(control_report={'engineering_reference_only':True}),
        s={'slots':{'1':{'ref':{'actor':'strip'}}}},contact=lambda *args:contact,
        require_held=held,act=lambda *args,**kwargs:events.append(args),
        frame=lambda ref:(np.zeros(3),Rotation.from_euler('z',9,degrees=True).as_matrix()))
    with pytest.raises(ToolExecutionError):rotate_charger_with_public_holds(a,'charger_2','right',np.eye(3))
    assert not events
