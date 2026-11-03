"""Measured-control route regression tests; these are not native acceptance."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError, _axis_rotation


def test_loaded_tcp_residual_rechecks_measured_payload_without_relaxing_final_goal():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E17'
    tcp=np.zeros(3);payload=np.zeros(3);calls=[]
    a.tip=lambda side:tcp.copy();a.point=lambda ref:payload.copy()
    def move(side,target,guard,follower,tolerance):
        assert tolerance==.002
        # Native load-dependent TCP residual: no progress below 1.5 mm.
        delta=target-tcp;delta[np.argmax(abs(delta))]-=.0015
        tcp[:]+=delta;payload[:]+=delta;calls.append(payload.copy())
    a.move=move
    a.move_point('left',{'actor':'box'},[0,0,.03])
    assert len(calls)>1 and max(abs(payload-np.array([0,0,.03])))<=.002


def test_moving_tcp_does_not_substitute_for_a_stuck_payload():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E17'
    tcp=np.zeros(3);a.tip=lambda side:tcp.copy();a.point=lambda ref:np.zeros(3)
    a.move=lambda side,target,*args,**kwargs:tcp.__setitem__(slice(None),target)
    with pytest.raises(ToolExecutionError,match='working point failed'):
        a.move_point('left',{'actor':'box'},[0,0,.03])


def test_storage_extraction_enters_horizontally_then_lifts_and_exits(monkeypatch):
    from videoicl_isaaclab import author_clearance
    monkeypatch.setattr(author_clearance,'prepare_single_hand',lambda *args:None)
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    a.d={'storage_extraction':{'tray':dict(approach_offset_task=[-.18,0,0],lift_m=.015,exit_offset_task=[-.30,0,0])}}
    a.clearance=1.15;a.task='other'
    a.stage=lambda *args:None
    a.a=SimpleNamespace(align_gripper_axis=lambda *args:None,scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    a.ref=lambda n:dict(actor=n,local=[-.1,0,.005],jaw_axis_local=[1,0,0])
    a.hand_for=lambda n:'left'
    grasp=np.array([.05,.08,.830]);tcp=np.array([-.2,.2,1.])
    a.point=lambda ref:grasp.copy();a.frame=lambda ref:(np.zeros(3),np.eye(3))
    a.tip=lambda side:tcp.copy();moves=[];actions=[]
    def move(side,target,guard=None):
        if guard:guard()
        tcp[:]=target;moves.append(tcp.copy())
    a.move=move;a.act=lambda side,token:actions.append(token)
    a.held=lambda ref,side:True;a.require_held=lambda ref,side:None
    a.stage=lambda name:None
    a.pickup_from_storage('tray')
    np.testing.assert_allclose(moves[2],[-.13,.08,.830])
    np.testing.assert_allclose(moves[3],grasp)
    np.testing.assert_allclose(moves[4],[.05,.08,.845])
    np.testing.assert_allclose(moves[5],[-.25,.08,.845])
    assert actions==['RELEASE','GRASP','GRASP','GRASP']


def test_e01_lower_shelf_rechecks_z_y_before_advancing_x():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.min_mm=1.
    tcp=np.array([-.18,0.,.830]);goal=np.array([0.,0.,.830]);calls=[]
    a.tip=lambda side:tcp.copy();a.point=lambda ref:goal.copy()
    tokens={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}
    def act(side,token,mm):
        calls.append((token,tcp.copy()));axis,sign=tokens[token];tcp[axis]+=sign*mm/1000
        if token=='FWD':tcp[2]-=.0013;tcp[1]+=.0007
    a.act=act;a.approach_storage_tray({'actor':'tray'},'right')
    assert max(abs(tcp-goal))<=.002
    assert any(token=='UP' for token,_ in calls)
    assert all(abs(p[2]-goal[2])<=.002 and abs(p[1]-goal[1])<=.002 for token,p in calls if token=='FWD')


def test_e01_lower_shelf_stuck_actual_tcp_fails_without_closing():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.min_mm=1.
    a.tip=lambda side:np.array([-.1,0.,.83]);a.point=lambda ref:np.array([0.,0.,.83])
    calls=[];a.act=lambda side,token,mm:calls.append(token)
    with pytest.raises(ToolExecutionError,match='approach is blocked'):
        a.approach_storage_tray({'actor':'tray'},'right')
    assert len(calls)==20 and set(calls)=={'FWD'}


def test_e01_lower_shelf_side_entry_can_clear_actual_rim_before_descending():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.min_mm=1.
    tcp=np.array([-.33,0.,.83]);a.tip=lambda side:tcp.copy();a.point=lambda ref:np.array([-.15,0.,.83])
    moves=[];tokens={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}
    def act(side,token,mm):
        moves.append((token,tcp.copy()));axis,sign=tokens[token];tcp[axis]+=sign*mm/1000
    a.act=act;a.approach_storage_tray({'actor':'tray'},'right',entry_height=.854)
    assert all(p[2]>=.852 for token,p in moves if token=='FWD')
    assert tcp[2]==pytest.approx(.854)


def test_e01_stages_empty_container_and_tray_before_food():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E01'
    events=[];a.stage_on_table=lambda n:events.append(n);a.food=lambda:events.append('food')
    a.local_stage()
    assert events==['meal_box','tray','food']


def test_chip_slot_uses_measured_occupancy_and_rejects_full_well(monkeypatch):
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    a.task='E20'
    from videoicl_isaaclab import execution_design_e20_reference
    monkeypatch.setattr(execution_design_e20_reference,'robot_bases',lambda _:dict(left=np.array([-.65,.3,.81]),right=np.array([-.65,-.3,.81])))
    names=['new','one','two','three','four']
    a.objects={n:dict(size=[.016,.016,.004]) for n in names}
    state={n:dict(pos=np.array([x,y,.01]),mat=np.eye(3)) for n,(x,y) in zip(names,[(1,1),(-.019,-.019),(.019,-.019),(-.019,.019),(1,1)])}
    a.frame=lambda ref:(np.zeros(3),np.eye(3));a.snapshot=lambda:(state,set())
    r=dict(id='well',actor='tray',lower=[-.057,-.057,0],upper=[.057,.057,.05],candidates=names)
    np.testing.assert_allclose(a.free_chip_slot(r,'new'),[.019,.019,0])
    state['four']['pos']=np.array([.019,.019,.01])
    with pytest.raises(ToolExecutionError,match='No measured free'):a.free_chip_slot(r,'new')


def test_hinged_lid_tracks_actual_100_degree_initial_angle():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    a.spec={'joints':[dict(type='revolute',parent='box',child='lid',axis='X',anchor0=[0,-.1,.1],anchor1=[0,-.1,0],limits=[0,100])]}
    a.stage=lambda *args:None;a.ref=lambda n:dict(actor=n,local=[0,.1,0]);a.hand_for=lambda n:'left'
    a.acquire=lambda *args:None;a.require_held=lambda *args:None
    a.frame=lambda ref:(np.zeros(3),_axis_rotation([1,0,0],math.radians(100)) if ref['actor']=='lid' else np.eye(3))
    positions=[];rotations=[]
    a.move_point=lambda side,ref,p,*args,**kwargs:positions.append(np.asarray(p))
    a.rotate_actor=lambda name,side,r:rotations.append(r)
    a.release=lambda *args:None;a.move=lambda *args:None;a.tip=lambda side:np.zeros(3);a.wait=lambda *args:None
    a.close_lid(dict(lid='lid',container='box',hinge_joint_index=0))
    np.testing.assert_allclose(rotations[0],_axis_rotation([1,0,0],math.radians(100)))
    np.testing.assert_allclose(rotations[-1],np.eye(3),atol=1e-12)
    np.testing.assert_allclose(positions[0],[0,-.1+.2*math.cos(math.radians(100)),.1+.2*math.sin(math.radians(100))])
    assert len(rotations)>=51


def test_recycled_lid_is_placed_on_box_rim_not_through_box():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E17'
    a.d=dict(packages=[],cleanup_regions=[dict(actor='recycle',members=['packing_box','packing_lid'],lower=[-.1,-.1,-.039],upper=[.1,.1,.045])])
    a.objects={'packing_box':dict(size=[.09,.09,.018])};placed=[]
    a.place=lambda *args,**kwargs:placed.append((args,kwargs))
    a.package_stage()
    assert placed[1]==(('packing_lid','packing_box',[0,0,.018]),{'yaw':0.})


def test_lower_shelf_enters_and_retracts_outside_upper_plate_in_actor_frame(monkeypatch):
    from videoicl_isaaclab import execution_design_e17_reference
    monkeypatch.setattr(execution_design_e17_reference,'measured_shelf_entry',lambda *args:(-.15,1.0))
    monkeypatch.setattr(execution_design_e17_reference,'measured_shelf_release',lambda a,n,s,actor,layer,target:np.asarray(target)+[0,0,.001])
    monkeypatch.setattr(execution_design_e17_reference,'clear_lower_ingress',lambda a,n,s,actor,entry,target:[entry,target])
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    a.task='E17';a.objects={'stand':{}}
    a.d={'shelf_insertion':{'lower':dict(entry_abs_x=.15,carry_bottom_z=.025,retreat_lift_m=.025)}}
    a.clearance=1.15;a.stage=lambda *args:None
    a.pickup=lambda n:(dict(actor=n,local=[.015,0,0]),'right')
    a.require_held=lambda *args:None;a.bottom_local=lambda n:np.array([0,0,-.003])
    base=np.array([.075,.025,.8]);rot=_axis_rotation([0,0,1],math.pi/2)
    a.frame=lambda ref:(base,rot);a.point=lambda ref:np.array([-.2,-.1,.9])
    tcp=np.array([0,0,1.]);events=[]
    def move_point(side,control,target,guard):
        guard();tcp[:]=target;events.append(('held',tcp.copy()))
    def move(side,target):
        tcp[:]=target;events.append(('empty',tcp.copy()))
    a.move_point=move_point;a.move=move;a.tip=lambda side:tcp.copy()
    a.rotate_actor=lambda *args:None;a.release=lambda *args:events.append(('release',tcp.copy()))
    a.wait=lambda *args:None;a.contact=lambda *args:True
    target=[-.038,.038,.00343]
    a.place_lower_shelf('piece','stand',target)
    low_held=[p for phase,p in events if phase=='held' and p[2]<.9]
    np.testing.assert_allclose(low_held[0],base+rot@[-.15,.038,.025])
    np.testing.assert_allclose(low_held[1],base+rot@[-.038,.038,.025])
    np.testing.assert_allclose(low_held[2],base+rot@[-.038,.038,.00443])
    release_index=next(i for i,(phase,_)in enumerate(events)if phase=='release')
    retreat_local=rot.T@(events[release_index+2][1]-base)
    assert retreat_local[0]==pytest.approx(-.15)
    assert retreat_local[2]<.06
    assert events[-1][1][2]==pytest.approx(1.0)


def test_storage_lift_does_not_correct_xy_drift_before_payload_clears():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.min_mm=1.
    z=[1.];calls=[]
    a.require_held=lambda *args:None;a.measured_lowest_z=lambda name:z[0]
    def act(side,token,mm):
        calls.append((token,mm));z[0]+=mm/1000*.8
    a.act=act
    a.raise_payload_bottom('meal_box',{'actor':'meal_box'},'left',1.023)
    assert z[0]>=1.023
    assert len(calls)>1 and all(t=='UP' for t,_ in calls)


def test_storage_lift_rejects_stuck_payload_even_if_tcp_moves():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.min_mm=1.
    a.require_held=lambda *args:None;a.measured_lowest_z=lambda name:1.
    moves=[];a.act=lambda *args,**kw:moves.append(kw['mm'])
    with pytest.raises(ToolExecutionError,match='cannot clear'):
        a.raise_payload_bottom('meal_box',{'actor':'meal_box'},'left',1.023)
    assert len(moves)==15


def test_lowest_payload_bound_includes_rotation_and_attached_lid():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    a.spec={'joints':[dict(parent='box',child='lid')]}
    a.objects={'box':dict(size=[.1,.2,.09]),'lid':dict(size=[.1,.2,.003])}
    rot=_axis_rotation([1,0,0],math.pi/2)
    a.snapshot=lambda:({'box':dict(pos=np.array([0,0,1.2]),mat=np.eye(3)),
                        'lid':dict(pos=np.array([0,0,1.1]),mat=rot)},set())
    assert a.measured_lowest_z('box')==pytest.approx(.9)


def test_meal_box_pickup_defers_lift_to_measured_payload_clearance_route():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E01'
    a.ref=lambda n:dict(actor=n);a.hand_for=lambda n:'right'
    calls=[];a.acquire=lambda *args:calls.append(args)
    a.move=lambda *args:pytest.fail('No redundant fixed-height TCP lift before measured payload clearance')
    assert a.pickup('meal_box')==({'actor':'meal_box'},'right')
    assert calls==[({'actor':'meal_box'},'right')]


def test_lower_bound_clearance_overcomes_small_loaded_command_deadzone():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.min_mm=1.
    z=[1.02056];calls=[];a.require_held=lambda *args:None;a.measured_lowest_z=lambda n:z[0]
    def act(side,token,mm):
        calls.append(mm)
        if mm>=5:z[0]+=.003
    a.act=act;a.raise_payload_bottom('meal_box',{'actor':'meal_box'},'right',1.023)
    assert z[0]>=1.023 and calls==[5.]


@pytest.mark.parametrize('task',['E09','E20'])
@pytest.mark.parametrize('obstacle_top,expected',[(.87,1.0),(1.20,1.269)])
def test_low_transport_uses_measured_obstacle_and_finger_extent_without_clamping(task,obstacle_top,expected):
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task=task
    a.objects={'chip':dict(size=[.016,.016,.001]),'obstacle':dict(size=[.1,.1,.05])}
    a.spec={'fixtures':[dict(type='box',z=.804,size=[.1,.1,.004])]}
    a.snapshot=lambda:({'chip':dict(pos=np.array([0,0,.9]),mat=np.eye(3)),
                        'obstacle':dict(pos=np.array([0,0,obstacle_top-.05]),mat=np.eye(3))},set())
    a.bottom_local=lambda n:[0,0,-.001];a.point=lambda r:np.array([0,0,.899]);a.tip=lambda side:np.array([0,0,.9])
    a.a=SimpleNamespace(floor_clear_tcp=lambda side,floor:floor+.020)
    expected=obstacle_top+.069 if task=='E20' else expected
    assert a.measured_transport_clearance('chip','right')==pytest.approx(expected)


def test_e20_drop_keeps_fingers_above_rim_and_restores_other_route_clearance(monkeypatch):
    from videoicl_isaaclab import execution_design_e20_reference
    monkeypatch.setattr(execution_design_e20_reference,'pickup_via_transfer_support',lambda a,n,t:a.pickup(n,side_override='left'))
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E20';a.clearance=1.15
    a.d={'target_members':['chip']};a.objects={'compartment_tray':dict(size=[.195,.065,.018])}
    a.stage=lambda *args:None;a.pickup=lambda n,**kw:({'actor':n},kw['side_override'])
    base=np.array([0,.1,.82]);a.frame=lambda r:(base,np.eye(3))
    a.bottom_local=lambda n:np.array([0,0,-.001]);a.point=lambda r:np.array([0,0,.919]);a.tip=lambda s:np.array([0,0,.92])
    a.a=SimpleNamespace(control_report={},floor_clear_tcp=lambda side,floor:floor+.020)
    a.measured_transport_clearance=lambda n,s,**kw:1.0;calls=[]
    a.lower_place=lambda name,ref,side,local,target,rotation,support:calls.append((a.clearance,target.copy(),support))
    a.snapshot=lambda:({'compartment_tray':dict(pos=base.copy(),grasp=[False,False])},set())
    a.place('chip','compartment_tray',[.019,.019,-.012])
    assert calls[0][0]==1.0 and calls[0][1][2]==pytest.approx(.867)
    assert calls[0][2]=='compartment_tray' and a.clearance==1.15


def test_loaded_meal_box_moves_to_arm_side_before_lateral_target():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    a.d={'storage_lift':{'meal_box':dict(support_top_z=1.008,clearance_m=.015)}}
    a.stage=lambda *args:None;a.raise_payload_bottom=lambda *args:None
    a.rotate_actor=lambda *args:None;a.require_held=lambda *args:None
    a.measured_lowest_z=lambda n:1.04;a.bottom_local=lambda n:np.array([0,0,-.09])
    point=np.array([.10,-.04,1.04]);moves=[]
    a.point=lambda r:point.copy()
    def move_point(side,ref,target,guard):
        guard();point[:]=target;moves.append(point.copy())
    a.move_point=move_point;a.release=lambda *args:None;a.move=lambda *args:None
    def translate(name,ref,side,axis,target,height):
        point[axis]=target;moves.append(point.copy())
    a.translate_cleared_meal_box=translate
    a.lower_measured_meal_box=lambda ref,side,control,target:move_point(side,control,target,lambda:None)
    a.tip=lambda side:point.copy();a.wait=lambda *args:None;a.contact=lambda *args:True
    a.stage_meal_box('meal_box',{'actor':'meal_box'},'right',np.array([.15,-.38,.80]))
    np.testing.assert_allclose(moves[0],[.10,-.38,1.04])
    np.testing.assert_allclose(moves[1],[.15,-.38,1.04])
    np.testing.assert_allclose(moves[2],[.15,-.38,.801])


@pytest.mark.parametrize('side,y',[('left',.25),('right',-.25)])
def test_e39_stages_real_held_piece_on_same_arm_side_at_measured_low_height(side,y):
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E39';a.clearance=1.15
    a.d={'target_members':['red'],'staging':{'red':dict(xy=[-.22,-.25],xy_by_hand={'left':[-.22,.25],'right':[-.22,-.25]},surface_z=.8)}}
    a.pickup_from_storage=lambda n:({'actor':n},side);a.stage=lambda *args:None
    a.bottom_local=lambda n:np.array([0,0,-.005]);a.measured_transport_clearance=lambda n,s,**kw:1.0
    calls=[];a.lower_place=lambda *args,**kwargs:calls.append((a.clearance,args,kwargs))
    a.stage_on_table('red')
    assert calls[0][0]==1.0 and calls[0][1][4]==[-.22,y,.8]
    assert calls[0][2]['support']=='table' and a.clearance==1.15


def test_meal_box_transit_advances_measured_main_axis_without_chasing_lateral_substep():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E01'
    pos=np.array([.1,0,1.04]);a.point=lambda ref:pos.copy()
    a.bottom_local=lambda name:np.array([0,0,-.09]);a.require_held=lambda *args:None
    a.measured_lowest_z=lambda name:pos[2];calls=[]
    def act(side,token,mm):
        calls.append(token);assert token=='RIGHT'
        pos[1]-=mm/1000;pos[0]-=.0005;pos[2]-=.001
    a.act=act;a.raise_payload_bottom=lambda name,ref,side,height:pos.__setitem__(2,height)
    a.translate_cleared_meal_box('meal_box',{'actor':'meal_box'},'right',1,-.10,1.023)
    assert abs(pos[1]+.10)<=.002 and len(calls)==10 and pos[2]>=1.023


def test_meal_box_transit_refuses_lost_clearance_before_any_next_action():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E01'
    a.point=lambda ref:np.array([.1,0,1.02]);a.bottom_local=lambda n:np.array([0,0,-.09])
    a.require_held=lambda *args:None;a.measured_lowest_z=lambda n:1.02
    a.act=lambda *args,**kw:pytest.fail('Must stop before more horizontal movement')
    with pytest.raises(ToolExecutionError,match='lost real transit clearance'):
        a.translate_cleared_meal_box('meal_box',{'actor':'meal_box'},'right',1,-.1,1.023)

@pytest.mark.parametrize('side',['left','right'])
def test_e39_staging_requires_actual_named_cradle_contact(side):
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E39';a.clearance=1.15
    a.d={'target_members':['red'],'staging':{'red':dict(xy=[-.22,-.25],surface_z=.826,support_by_hand={'left':'fixture2','right':'fixture3'})}}
    a.pickup_from_storage=lambda n:({'actor':n},side);a.stage=lambda *args:None
    a.bottom_local=lambda n:np.zeros(3);a.measured_transport_clearance=lambda *args,**kw:1.1
    calls=[];a.lower_place=lambda *args,**kwargs:calls.append((args,kwargs))
    a.stage_on_table('red')
    assert calls[0][0][4][2]==.826
    assert calls[0][1]['support']==('fixture2' if side=='left' else 'fixture3')
    assert a.clearance==1.15


@pytest.mark.parametrize('initial_q,initial_axis',[(math.pi/4,math.pi/2),(2.31,0.),(2.31,.001),(2.31,-.001)])
def test_flat_piece_empty_axis_chooses_equivalent_rotation_away_from_wrist_upper_limit(initial_q,initial_axis):
    class CpuArray(np.ndarray):
        def cpu(self):return self
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    angle=[initial_axis];q=np.array([[initial_q]])
    robot=SimpleNamespace(find_joints=lambda n:([0],[]),data=SimpleNamespace(joint_pos=q,joint_pos_limits=np.array([[[-2.8973,2.8973]]]).view(CpuArray)))
    def geometry(side):
        v=np.array([math.cos(angle[0]),math.sin(angle[0]),0])*.08
        return {'fingers':[dict(body_origin_task_m=v.tolist()),dict(body_origin_task_m=[0,0,0])]}
    a.a=SimpleNamespace(scene=SimpleNamespace(robots={'right':robot}),finger_geometry=geometry)
    calls=[]
    def act(side,token,degrees):
        delta=math.radians(degrees)*(1 if token=='ROTATE_CCW' else -1)
        angle[0]+=delta;q[0,0]-=delta;calls.append(token)
    a.act=act;a.align_empty_chip_axis('right',np.array([1.,0,0]))
    assert calls and set(calls)=={'ROTATE_CCW'}
    assert q[0,0]<0 and abs(math.sin(angle[0]))<math.sin(math.radians(5))


def test_e20_empty_axis_rejects_nonhorizontal_geometry_before_action():
    class CpuArray(np.ndarray):
        def cpu(self):return self
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    robot=SimpleNamespace(find_joints=lambda n:([0],[]),data=SimpleNamespace(joint_pos=np.array([[0.]]),joint_pos_limits=np.array([[[-2.9,2.9]]]).view(CpuArray)))
    a.a=SimpleNamespace(scene=SimpleNamespace(robots={'right':robot}),finger_geometry=lambda side:{'fingers':[dict(body_origin_task_m=[0,0,.08]),dict(body_origin_task_m=[0,0,0])]})
    a.act=lambda *args,**kwargs:pytest.fail('No rotations for unreviewed geometry')
    with pytest.raises(ToolExecutionError,match='horizontal actual finger'):
        a.align_empty_chip_axis('right',np.array([1.,0,0]))


def test_e17_lid_low_l_route_checks_actual_swept_segments_not_empty_diagonal_corner():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E17'
    a.objects={'packing_lid':dict(size=[.09,.17,.021],local_bounds_center=[0,0,.018]),
               'packing_box':dict(size=[.09,.17,.018]),'stand':dict(size=[.105,.105,.14])}
    state={'packing_lid':dict(pos=np.array([-.2,-.12,.90]),mat=np.eye(3)),
           'packing_box':dict(pos=np.array([-.2,-.12,.826]),mat=np.eye(3)),
           'stand':dict(pos=np.array([.075,.08,.94]),mat=np.eye(3))}
    a.snapshot=lambda:(state,set());a.spec={'fixtures':[]}
    a.bottom_local=lambda n:np.array([0,0,-.003]);a.point=lambda r:np.array([-.2,-.12,.897]);a.tip=lambda s:np.array([-.2,-.12,.925])
    a.a=SimpleNamespace(floor_clear_tcp=lambda side,floor:floor+.010)
    path=[np.array([-.2,-.12]),np.array([-.2,-.36]),np.array([.15,-.36])]
    assert a.measured_staging_route_height('packing_lid','right',path)==pytest.approx(.98)
    # A real tall obstruction in the L corridor must raise the requirement;
    # there is no clamp to force the convenient lower route through it.
    state['stand']['pos']=np.array([-.2,-.25,1.0])
    assert a.measured_staging_route_height('packing_lid','right',path)>=1.19


def test_e01_descent_uses_actual_body_goal_and_keeps_full_2mm_precision():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E01'
    pos=np.array([.155,-.375,.83]);a.point=lambda r:pos.copy();a.require_held=lambda *a:None
    a.tip=lambda s:pytest.fail('Loaded descent must not target surrogate TCP')
    mapping={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}
    calls=[]
    def act(side,token,mm):
        axis,sign=mapping[token];pos[axis]+=sign*mm/1000*.8;calls.append(token)
    a.act=act;target=np.array([.15,-.38,.801])
    a.lower_measured_meal_box({'actor':'meal_box'},'right',{'actor':'meal_box'},target)
    assert max(abs(pos-target))<=.002 and 'DOWN'in calls and 'BACK'in calls and 'RIGHT'in calls


@pytest.mark.parametrize('obstacle_xy,expected',[([.23,.05],1.0),([-.18,.10],1.269),([-.22,.25],1.269)])
def test_e39_swept_corridor_keeps_crossing_obstacles_but_excludes_remote_lid(obstacle_xy,expected):
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E39'
    a.objects={'t':dict(size=[.03,.025,.003]),'lid':dict(size=[.02,.02,.05])}
    a.spec={'fixtures':[]};origin=np.array([-.12,0,.899])
    a.snapshot=lambda:({'t':dict(pos=np.array([-.12,0,.902]),mat=np.eye(3)),
                        'lid':dict(pos=np.array([*obstacle_xy,1.15]),mat=np.eye(3))},set())
    a.bottom_local=lambda n:[0,0,-.003];a.point=lambda r:origin.copy();a.tip=lambda s:origin+[0,0,.001]
    a.a=SimpleNamespace(floor_clear_tcp=lambda side,floor:floor+.020,
        finger_geometry=lambda side:{'fingers':[{'aabb_min_task_m':[-.15,-.04,.895],'aabb_max_task_m':[-.10,.04,.94]}]})
    assert a.measured_transport_clearance('t','left',target=[-.22,.25,.826])==pytest.approx(expected)
    assert a.measured_transport_clearance('t','left')==pytest.approx(1.269)


def test_e17_empty_hand_retracts_inward_after_real_lid_release_before_next_high_lift():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E17';a.clearance=1.15
    lid=dict(pos=np.array([.15,-.36,.803]),mat=np.eye(3),grasp=[False,False])
    a.objects={'packing_lid':dict(size=[.09,.17,.021],local_bounds_center=[0,0,.018])}
    a.snapshot=lambda:({'packing_lid':lid},{frozenset(('packing_lid','table'))})
    a.bottom_local=lambda n:np.array([0,0,-.003]);a.point=lambda ref:np.array([-.2,-.12,.9])
    a.measured_staging_route_height=lambda *args:.98;a.stage=lambda *args:None;a.require_held=lambda *args:None
    a.move_point=lambda *args:None;tip=np.array([.15,-.36,.89]);a.tip=lambda side:tip.copy()
    a.lower_place=lambda *args,**kwargs:None;a.a=SimpleNamespace(floor_clear_tcp=lambda side,floor:floor+.01)
    moves=[];a.move=lambda side,target:moves.append(np.asarray(target))
    a.stage_packing_lid('packing_lid',{'actor':'packing_lid'},'right',[.15,-.36,.8])
    assert len(moves)==1
    np.testing.assert_allclose(moves[0],[-.2,-.36,.89])
    assert a.clearance==1.15


def test_e39_parks_only_empty_other_arm_with_measured_home(monkeypatch):
    from videoicl_isaaclab import author_clearance
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.a=object();a.clearance=1.15
    a._e39_home={'left':np.array([-.19,.3,.9]),'right':np.array([-.19,-.3,.9])}
    pos=np.array([-.12,.12,.89]);a.tip=lambda side:pos.copy();a.stage=lambda n:None
    checked=[];monkeypatch.setattr(author_clearance,'_empty',lambda author,side:checked.append(side))
    moves=[]
    def move(side,target):
        assert side=='left';moves.append(np.array(target));pos[:]=target
    a.move=move;a.park_e39_idle_hand('right')
    np.testing.assert_allclose(moves,[[-.12,.12,1.15],[-.19,.3,1.15],[-.19,.3,.9]])
    assert checked==['left','left']
    a.park_e39_idle_hand('right');assert len(moves)==3


def test_e39_does_not_park_a_grasping_idle_hand(monkeypatch):
    from videoicl_isaaclab import author_clearance
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.a=object()
    def reject(*args):raise RuntimeError('requires empty')
    monkeypatch.setattr(author_clearance,'_empty',reject)
    a.move=lambda *args:pytest.fail('must not move holding idle arm')
    with pytest.raises(RuntimeError,match='requires empty'):a.park_e39_idle_hand('right')


def test_destination_pose_is_measured_after_pickup_for_other_workflows():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E17';a.d={'target_members':[]};a.stage=lambda *args:None
    base=np.array([0.,0.,.8]);a.frame=lambda ref:(base.copy(),np.eye(3));calls=[]
    def pickup(name):base[0]=.1;return {'actor':name},'right'
    a.pickup=pickup;a.bottom_local=lambda name:[0,0,-.003]
    a.lower_place=lambda name,ref,side,point,target,rotation,support:calls.append(target.copy())
    a.place('piece','stand',[.03,0,.1]);np.testing.assert_allclose(calls[0],[.13,0,.9])
