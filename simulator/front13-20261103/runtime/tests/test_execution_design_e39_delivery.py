import numpy as np
import pytest
from itertools import product
from videoicl_isaaclab.execution_design_e39_delivery import clip_mesh_height
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_contact_uses_wall_height_hull_instead_of_above_wall_overhang():
    low=np.asarray(list(product((.05,.06),(-.01,.01),(0.,.02))))
    high=np.asarray(list(product((.04,.07),(-.03,.03),(.04,.06))))
    result=clip_mesh_height(np.vstack((low,high)),.002,.018)
    assert np.all(result[:,2]>=.002-1e-10)and np.all(result[:,2]<=.018+1e-10)
    # The above-wall shoulder cannot be mistaken for a physical wall contact.
    assert result[:,1].min()>-.03 and result[:,0].max()<.07


def test_actual_finger_missing_wall_slab_is_rejected():
    mesh=np.asarray(list(product((.05,.06),(-.01,.01),(.03,.05))))
    with pytest.raises(ToolExecutionError,match='misses wall'):
        clip_mesh_height(mesh,0.,.02)


def test_real_release_may_need_second_native_command_before_full_mesh_opens(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e39_delivery as route
    from videoicl_isaaclab import execution_design_e33_grasp as mesh
    class Policy:
        def __init__(self):
            self.q=0.;self.calls=0;self.c=SimpleNamespace(steps=0)
            self.a=SimpleNamespace(out=tmp_path,tcp_rotation_task=lambda s:np.eye(3),scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['f1','f2'])))
        def tip(self,s):return np.zeros(3)
        def snapshot(self):return ({'box':dict(grasp=[False,False])},set())
        def act(self,s,t):
            assert t=='RELEASE';self.q=[.0346,.0393][self.calls];self.calls+=1;self.c.steps+=1
    p=Policy()
    def vertices(a,s,n):
        return np.array([[0.,0.,.05]])if n=='panda_hand'else np.array([[0.,p.q*(1 if n=='f1'else-1),0.]])
    monkeypatch.setattr(mesh,'actual_mesh',vertices)
    expected=[np.array([[0.,0.,.05]]),np.array([[0.,.04,0.]]),np.array([[0.,-.04,0.]])]
    actual=route._actual_open(p,'right',expected)
    assert p.calls==2
    assert max(np.linalg.norm(a-b,axis=1).max()for a,b in zip(actual,expected))<.001


def test_station_acceptance_checks_full_rotated_box_not_only_center():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_delivery import station_axis_contains
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    rotation=np.eye(3)
    p=SimpleNamespace(d={'destination_zone':'station'},spec={'zones':[dict(id='station',xy=[.225,-.30],half_size=[.087,.204])]},
        objects={'protective_box':dict(size=[.077,.197,.036]),'protective_box_lid':dict(size=[.077,.197,.003])},
        frame=lambda ref:(np.array([.225,-.295,.836]),rotation))
    assert station_axis_contains(p,1)
    rotation[:]=_axis_rotation([0,0,1],np.deg2rad(6))
    assert not station_axis_contains(p,1)


def test_delivery_suffix_continues_past_handover_without_reset(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e39_delivery as route
    from videoicl_isaaclab import engineering_e39_suffix as suffix
    phases=[]
    monkeypatch.setattr(route,'push_wall',lambda p,side,axis,target,**kwargs:phases.append(('wall',side,axis))or True)
    monkeypatch.setattr(route,'drag_cover',lambda p,**kwargs:phases.append(('cover','right',1))or True)
    monkeypatch.setattr(route,'station_axis_contains',lambda *args:True)
    monkeypatch.setattr(suffix,'verify_released_boxed_tray',lambda *args:True)
    p=SimpleNamespace(d={'packages':[dict(container='protective_box')]},a=SimpleNamespace(out=__import__('pathlib').Path('/tmp/room/engineering-reference')),stage=lambda s:None)
    assert route.deliver_supported_package(p)
    assert phases==[('wall','left',1),('cover','right',1),('wall','right',0)]


def test_full_source_reference_uses_verified_contact_routes_with_private_authorization(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    from videoicl_isaaclab import execution_design_e39_package as lid
    from videoicl_isaaclab import execution_design_e39_delivery as delivery
    calls=[];p=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);p.task='E39';p.d={};p.a=SimpleNamespace(control_report={'engineering_reference_only':True})
    def check(name):
        assert p.a._execution_design_reference_authorized is True;calls.append(name)
    monkeypatch.setattr(lid,'preflight_lid_phase',lambda policy:check('screen'))
    monkeypatch.setattr(lid,'close_lid_by_contact',lambda policy,package:check('lid'))
    monkeypatch.setattr(delivery,'deliver_supported_package',lambda policy:check('delivery')or True)
    p.close_lid({});p.deliver()
    assert calls==['screen','lid','delivery']and p.a._execution_design_reference_authorized is False


def test_restored_normal_escape_requires_zero_penetration_and_forbids_low_cross_motion(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e39_delivery as route
    from videoicl_isaaclab import execution_design_thin_edge as floor
    from videoicl_isaaclab import execution_design_e33_grasp as native
    monkeypatch.setattr(floor,'table_bounds_task',lambda s:{'top':-.1})
    monkeypatch.setattr(native,'actual_mesh',lambda *args:np.asarray(list(product((9.,10.),repeat=3))))
    p=SimpleNamespace(objects={'reference':dict(size=[.02,.1,.01])},spec={'fixtures':[]},
        frame=lambda r:(np.array([0.,0.,-.01]),np.eye(3)),tip=lambda s:np.zeros(3),
        a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['f1','f2'])),out=tmp_path),c=SimpleNamespace(steps=0))
    mesh=np.asarray(list(product((-.01,.01),(-.01,.01),(.0005,.01))))
    route._screen_translations(p,'left',[mesh],np.eye(3),[np.zeros(3),[0.,.035,0.],[0.,.035,.003]],set(),initial_escape_axis=1)
    with pytest.raises(ToolExecutionError,match='protected body'):
        route._screen_translations(p,'left',[mesh],np.eye(3),[np.zeros(3),[.01,0.,0.]],set(),initial_escape_axis=1)
    penetrating=mesh-np.array([0.,0.,.001])
    with pytest.raises(ToolExecutionError,match='protected body'):
        route._screen_translations(p,'left',[penetrating],np.eye(3),[np.zeros(3),[0.,.035,0.]],set(),initial_escape_axis=1)


def test_measured_right_handover_skips_completed_left_push_and_continues_both_right_legs(monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    from videoicl_isaaclab import execution_design_e39_delivery as route
    from videoicl_isaaclab import engineering_e39_suffix as suffix
    phases=[]
    monkeypatch.setattr(route,'clear_left_wall_contact',lambda p:phases.append('clear-left'))
    monkeypatch.setattr(route,'record_loaded_package_com',lambda p:None)
    monkeypatch.setattr(route,'push_wall',lambda p,side,axis,target,**kw:phases.append((side,axis))or True)
    monkeypatch.setattr(route,'wall_yaw_offset',lambda p,**kw:0.)
    monkeypatch.setattr(route,'station_axis_contains',lambda *args:True)
    monkeypatch.setattr(suffix,'verify_released_boxed_tray',lambda *args:True)
    p=SimpleNamespace(d={'packages':[dict(container='protective_box')]},a=SimpleNamespace(out=Path('/tmp/room/engineering-reference')),stage=lambda s:None)
    assert route.deliver_wall_package(p,from_right=True)
    assert phases==['clear-left',('right',1),('right',0)]


def test_rotated_wall_contact_meets_real_plane_instead_of_empty_aabb_corner():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_delivery import wall_plan
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    rotation=_axis_rotation([0,0,1],np.deg2rad(-7.))
    origin=np.array([.225,-.3,.836]);half=np.array([.077,.197,.036])
    p=SimpleNamespace(d={'packages':[dict(container='protective_box',lid='protective_box_lid')]},
        objects={'protective_box':dict(size=half),'protective_box_lid':dict(size=[.077,.197,.003])},
        frame=lambda r:(origin+(rotation@np.array([0.,0.,.039])if r['actor'].endswith('_lid')else 0),rotation),
        tip=lambda s:np.array([-.19,-.3,.92]))
    palm=np.asarray(list(product((-.03,.03),(-.03,.03),(.05,.1))))
    finger=np.asarray(list(product((.05,.06),(-.01,.01),(-.01,.02))))
    plan=wall_plan(p,'right',0,.233,np.eye(3),[palm,finger,finger],cross_offset=-.06)
    surface=plan['contact']+plan['leading']+np.array([.004,0,0])
    actual_local=rotation.T@(surface-origin)
    assert actual_local[0]==pytest.approx(-half[0])
    assert abs(actual_local[1])<half[1]
    enclosing_min_x=origin[0]-(np.abs(rotation)@half)[0]
    assert surface[0]-enclosing_min_x>.014


def test_contact_change_unloads_normal_pressure_before_friction_blocked_lateral_move(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e39_delivery as route
    from videoicl_isaaclab import execution_design_e33_grasp as native
    class Policy:
        d={'target_members':[]}
        def __init__(self):
            self.position=np.array([.1,-.28,.85]);self.contact=True;self.calls=[]
            self.a=SimpleNamespace(out=tmp_path,tcp_rotation_task=lambda s:np.eye(3),scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['f1','f2'])))
        def tip(self,s):return self.position.copy()
        def move(self,s,goal,guard):
            goal=np.asarray(goal);self.calls.append(goal.copy());guard()
            if goal[0]<self.position[0]-.005:self.contact=False
            if self.contact and abs(goal[1]-self.position[1])>.003:return
            self.position=goal.copy()
            if goal[0]>=.099:self.contact=True
    p=Policy();monkeypatch.setattr(native,'actual_mesh',lambda *a:np.asarray(list(product((-.01,.01),repeat=3))))
    monkeypatch.setattr(route,'wall_plan',lambda *a,**kw:dict(direction=1,z=.85,contact=np.array([.1,-.32,.85]),leading=np.zeros(3),cross_offset=kw['cross_offset']))
    monkeypatch.setattr(route,'_native_route',lambda *a:None);monkeypatch.setattr(route,'_screen_translations',lambda *a,**kw:None)
    route.reposition_wall_contact(p,'right',0,.225,-.02,lambda:None)
    assert np.allclose(p.calls[0],[.088,-.28,.85])
    assert np.allclose(p.tip('right'),[.1,-.32,.85])
    assert p.contact


def test_only_high_preflighted_empty_travel_uses_legal_25mm_requests_and_restores_contact_limit():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_delivery import move_clear_air
    class P:
        max_mm=10.
        def __init__(self):
            self.position=np.array([0.,0.,.92]);self.held=False;self.limits=[]
            self.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50.]}})))
        def tip(self,s):return self.position.copy()
        def snapshot(self):return {'box':{'grasp':[False,self.held]}},set()
        def move(self,s,g,guard):self.limits.append(self.max_mm);self.position=np.array(g)
    p=P();move_clear_air(p,'right',[.2,0.,.92],lambda:None)
    assert p.limits[-1]==25. and p.max_mm==10.
    move_clear_air(p,'right',[.3,0.,.85],lambda:None)
    assert p.limits[-1]==10.
    p.position=np.array([0.,0.,.92]);p.held=True;move_clear_air(p,'right',[.2,0.,.92],lambda:None)
    assert p.limits[-1]==10. and p.max_mm==10.


def test_native_toe_sag_near_reference_rim_is_caught_before_contact():
    from videoicl_isaaclab.execution_design_e39_delivery import required_protected_vertical_clearance
    toe=np.array([[.032,.08,.8375],[.064,.13,.87]])
    rim=np.array([[.047,-.18,.80],[.055,.18,.836]])
    assert required_protected_vertical_clearance([toe],[rim])==pytest.approx(.0015)
    assert required_protected_vertical_clearance([toe+[0,0,.006]],[rim])==0
