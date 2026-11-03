import copy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_cutlery_transfer import choose_stage,plan_transfers,verify_relay_release,initial_pickup_hand


def test_stage_avoids_actual_obstacles_and_reserved_destination():
    obstacles=[([-.21,.02],[.11,.11]),([-.03,.15],[.11,.022]),([-.03,-.15],[.11,.022])]
    half=np.array([.115,.04]);p=choose_stage([-.5,-.5],[.5,.5],half,obstacles,-.65)
    assert np.all(p-half>=-.5)and np.all(p+half<=.5)
    assert all(np.any(abs(p-center)>np.array(extent)+half)for center,extent in obstacles)


def test_no_empty_table_region_fails():
    with pytest.raises(RuntimeError):choose_stage([-.5,-.5],[.5,.5],[.1,.03],[([0,0],[1,1])],-.65)


def test_relay_requires_table_contact_and_real_release():
    state={'fork':dict(pos=np.array([-.3,-.24,.81]),grasp=[False,True])}
    contacts={frozenset(('fork','table'))}
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=dict(id='E27',execution_design=dict(revision=REVISION_V3))),c=SimpleNamespace(snapshot=lambda:(state,contacts)))
    goal=dict(object='fork',_cutlery_after_relay=dict(xy=[-.3,-.24],half_size=[.11,.04]))
    with pytest.raises(RuntimeError,match='actual release'):verify_relay_release(a,goal)
    state['fork']['grasp']=[False,False];contacts.clear()
    with pytest.raises(RuntimeError,match='table support'):verify_relay_release(a,goal)
    contacts.add(frozenset(('fork','table')));verify_relay_release(a,goal)
    state['fork']['pos'][0]=0
    with pytest.raises(RuntimeError,match='outside'):verify_relay_release(a,goal)


def test_copy_queue_preserves_source_rules_and_adds_two_real_legs(tmp_path,monkeypatch):
    from videoicl_isaaclab import execution_design_thin_edge
    monkeypatch.setattr(execution_design_thin_edge,'table_bounds_task',lambda scene:dict(lower=[-.5,-.5,.8],upper=[.5,.5,.8],top=.8))
    goals=[dict(object='fork',target='fork_target',yaw=0,required_support='table')]
    spec=dict(id='E27',execution_design=dict(revision=REVISION_V3),goals=goals,objects=[dict(id='fork',size=[.09,.012,.007],grasp_point_local=[-.05,0,0]),dict(id='plate',size=[.11,.11,.01])],zones=[dict(id='fork_target',xy=[-.03,.15],half_size=[.11,.022],surface_z=.8)])
    saved=copy.deepcopy(spec)
    state={'fork':dict(pos=np.array([.21,-.035,.81]),mat=np.eye(3)),'plate':dict(pos=np.array([-.21,.02,.81]),mat=np.eye(3))}
    scene=SimpleNamespace(spec=spec,robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=[np.array([-.65,y,.81])]))for side,y in [('left',.3),('right',-.3)]},world_to_task=lambda x:x)
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=scene,c=SimpleNamespace(snapshot=lambda:(state,{})),out=tmp_path)
    result=plan_transfers(a,goals)
    assert spec==saved and len(result)==2
    assert result[0]['_cutlery_arm']=='right'and result[1]['_cutlery_arm']=='left'
    assert initial_pickup_hand(a)==result[0]['_cutlery_arm']
    assert result[0]['_cutlery_target']['support']=='table'
    assert 'yaw'not in result[0]and result[1]['yaw']==0
    assert result[1]['required_support']=='table'
    assert json.loads((tmp_path/'cutlery-transfer-plan.private.json').read_text())['source_goals_unchanged']
    direct=plan_transfers(a,goals,prefer_single_hand=True)
    assert spec==saved and len(direct)==len(goals)
    assert direct[0]['_cutlery_arm']=='right'and direct[0]['_cutlery_direct']
    assert direct[0]['yaw']==0 and direct[0]['required_support']=='table'
    assert '_cutlery_target'not in direct[0]


def test_loaded_fork_clearance_encloses_full_swing_and_never_lowers_high_tcp(tmp_path,monkeypatch):
    from videoicl_isaaclab.execution_design_cutlery_transfer import loaded_clearance
    from videoicl_isaaclab import execution_design_e33_grasp
    tcp=np.array([.15,-.035,.93])
    state={'fork':dict(pos=np.array([.21,-.035,.93]),mat=np.eye(3),grasp=[False,True]),
           'plate':dict(pos=np.array([-.03,0,.812]),mat=np.eye(3),grasp=[False,False])}
    objects=[dict(id='fork',size=[.0893,.0117,.0076]),dict(id='plate',size=[.11,.11,.012])]
    spec=dict(id='E27',execution_design=dict(revision=REVISION_V3),objects=objects)
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),
        c=SimpleNamespace(snapshot=lambda:(state,{}),steps=172),out=tmp_path,carried_payload=('fork','right'),
        tip=lambda side:tcp.copy(),finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=tcp[2]-.02))
    monkeypatch.setattr(execution_design_e33_grasp,'actual_mesh',lambda *args:np.array([tcp+[0,0,.02],tcp+[0,0,.04]]))
    safe=loaded_clearance(a,'fork','right',.868)
    radius=np.sqrt((.06+.0893)**2+.0117**2+.0076**2)
    assert safe>=.824+radius+.025
    # Any rigid swing about the actual grip/TCP remains above the obstacle.
    assert safe-radius>=.849
    tcp[2]=1.10;state['fork']['pos'][2]=1.10
    assert loaded_clearance(a,'fork','right',.868)==pytest.approx(1.10)
    state['fork']['grasp']=[False,False]
    with pytest.raises(RuntimeError,match='actual payload grasp'):
        loaded_clearance(a,'fork','right',.868)


def test_released_return_keeps_native_high_pose_and_rejects_unreleased_payload():
    from videoicl_isaaclab.execution_design_cutlery_transfer import released_return_clearance
    state={'fork':dict(grasp=[False,False])}
    a=SimpleNamespace(_execution_design_reference_authorized=True,
        scene=SimpleNamespace(spec=dict(id='E27',execution_design=dict(revision=REVISION_V3))),
        c=SimpleNamespace(snapshot=lambda:(state,{})),carried_payload=None,
        tip=lambda side:np.array([-.236,-.24,1.016]))
    # Native v6 released successfully here; descending at this XY drove q6
    # into3.7523rad. Return at the existing safe height before parking.
    assert released_return_clearance(a,'right',.876)==pytest.approx(1.016)
    assert released_return_clearance(a,'right',1.10)==pytest.approx(1.10)
    state['fork']['grasp']=[False,True]
    with pytest.raises(RuntimeError,match='actual release'):
        released_return_clearance(a,'right',.876)


def test_direct_route_samples_only_public_cartesian_axes_and_keeps_endpoint():
    from videoicl_isaaclab.execution_design_cutlery_transfer import translation_samples
    start=np.array([.15,-.035,1.003]);target=np.array([-.085,.15,1.003])
    points=translation_samples(start,target)
    assert np.allclose(points[-1],target)
    for a,b in zip([start,*points],points):
        assert np.count_nonzero(np.abs(b-a)>1e-8)==1
        assert np.max(np.abs(b-a))<=.04000001
        assert b[2]>=1.003
    assert translation_samples(start,start)==[]


def test_direct_route_refuses_lost_grip_and_bad_native_margin(tmp_path):
    from videoicl_isaaclab.execution_design_cutlery_transfer import screen_direct_translation
    state={'fork':dict(grasp=[False,True])}
    a=SimpleNamespace(_execution_design_reference_authorized=True,
        scene=SimpleNamespace(spec=dict(id='E27',execution_design=dict(revision=REVISION_V3))),
        c=SimpleNamespace(snapshot=lambda:(state,{}),steps=206),carried_payload=('fork','right'),
        tip=lambda side:np.array([.15,-.035,1.003]),tcp_rotation_task=lambda side:np.eye(3),out=tmp_path)
    def bad(*args):
        return [dict(kinematically_reachable=True,position_error_m=0.,orientation_error_rad=0.,
                     minimum_joint_margin_rad=.0002,candidate_joints_rad=[0.]*7)for _ in args[-1]]
    with pytest.raises(RuntimeError,match='joint margin'):
        screen_direct_translation(a,'fork','right',[.15,.15,1.003],ik_probe=bad)
    state['fork']['grasp']=[False,False]
    with pytest.raises(RuntimeError,match='actual payload grasp'):
        screen_direct_translation(a,'fork','right',[.15,.15,1.003],ik_probe=bad)


def test_native_yaw_does_not_invent_flat_pitch_goal(tmp_path):
    from videoicl_isaaclab.execution_design_cutlery_transfer import orient_for_rule
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    rotation=_axis_rotation([0,1,0],np.deg2rad(57))
    state={'fork':dict(grasp=[False,True],mat=rotation.copy())};calls=[]
    spec=dict(id='E27',execution_design=dict(revision=REVISION_V3),semantic=dict(
        orientation_targets=dict(fork=dict(working_axis_local=[1,0,0],yaw=0,tolerance_rad=.25))))
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),
        c=SimpleNamespace(snapshot=lambda:(state,{}),steps=206),carried_payload=('fork','right'),
        out=tmp_path,act=lambda *args,**kwargs:calls.append((args,kwargs)))
    orient_for_rule(a,'fork','right')
    assert not calls and np.array_equal(state['fork']['mat'],rotation)
    spec['id']='E34';spec['semantic']={}
    orient_for_rule(a,'fork','right')
    assert not calls


def test_e34_hand_must_cover_source_and_tray_not_only_nearest_source():
    from videoicl_isaaclab.execution_design_cutlery_transfer import initial_pickup_hand
    class Value:
        def __init__(self,x):self.x=x
        def __getitem__(self,index):return self.x
    robots={s:SimpleNamespace(data=SimpleNamespace(root_pos_w=Value(np.array([-.65,y,.8]))))for s,y in [('left',.3),('right',-.3)]}
    spec=dict(id='E34',execution_design=dict(revision=REVISION_V3),goals=[dict(object='spoon',target='top_left')],objects=[dict(id='spoon',grasp_point_local=[-.058,0,0])],zones=[dict(id='top_left',xy=[.135,.17])])
    scene=SimpleNamespace(spec=spec,robots=robots,world_to_task=lambda x:x)
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=scene,c=SimpleNamespace(snapshot=lambda:({'spoon':dict(pos=np.array([0,-.06,.8]),mat=np.eye(3))},set())))
    assert initial_pickup_hand(a)=='left'
    # E27's demonstrated single initial pickup hand is unaffected.
    spec['id']='E27'
    assert initial_pickup_hand(a)=='right'
