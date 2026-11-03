"""Conservative measured-geometry tests; these are not native acceptance."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e23_clearance import actor_bounds,separation,rotation_workspace
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def fixture():
    state={n:dict(pos=pos,mat=np.eye(3),grasp=[False,n=='red'])for n,pos in
           [('red',[0,0,1.1]),('blue',[0,.12,.85]),('tree',[.5,0,.9])]}
    objects={n:dict(size=[.04,.04,.05])for n in state}
    policy=SimpleNamespace(snapshot=lambda:(state,set()),tip=lambda side:np.array([0.,0.,1.15]),objects=objects,spec={'fixtures':[]})
    geometry=dict(source='actual_collision_mesh_live_native_body_pose',complete=True,robots={'right':[
        dict(name=n,lo=[-.02,-.02,z],hi=[.02,.02,z+.03],maximum_distance_to_tcp_m=.12)for n,z in
        [('panda_hand',1.18),('panda_leftfinger',1.13),('panda_rightfinger',1.13),('panda_link5',1.3)]]})
    return policy,geometry


def test_rotated_object_bounds_keep_offset_origin_not_half_extent_origin():
    rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
    bounds=actor_bounds(dict(size=[.01,.02,.03],local_bounds_center=[.1,0,0]),dict(pos=[1,2,3],mat=rotation))
    np.testing.assert_allclose(bounds['lo'],[.98,2.09,2.97]);np.testing.assert_allclose(bounds['hi'],[1.02,2.11,3.03])


def test_workspace_uses_full_rotation_radius_and_ignores_far_tall_objects():
    policy,geometry=fixture();policy.objects['tree']['size'][2]=3
    workspace=rotation_workspace(policy,'red','right',geometry)
    assert workspace['rotation_radius_m']>.11
    assert workspace['obstacle_top_z_m']==pytest.approx(.9)
    assert workspace['swept_obstacles']==['blue']
    assert workspace['target_tcp_z_m']>=workspace['obstacle_top_z_m']+workspace['rotation_radius_m']+.02
    assert workspace['minimum_separation_m']>0


def test_full_arm_overlap_detected_even_while_fingers_clear():
    policy,geometry=fixture();geometry['robots']['right'].append(dict(name='panda_link6',lo=[-.02,.1,.82],hi=[.02,.14,.95]))
    result=rotation_workspace(policy,'red','right',geometry)
    assert result['minimum_separation_m']==0
    collisions=[x for x in result['arm_object_separations']if x['separation_lower_bound_m']==0]
    assert collisions==[dict(side='right',body='panda_link6',object='blue',separation_lower_bound_m=0)]


@pytest.mark.parametrize('failure',['partial','missing_palm','badbounds'])
def test_missing_collision_evidence_never_certifies_clearance(failure):
    policy,geometry=fixture()
    if failure=='partial':geometry['complete']=False
    elif failure=='missing_palm':geometry['robots']['right']=geometry['robots']['right'][1:]
    else:geometry['robots']['right'][0]['hi'][0]=float('nan')
    with pytest.raises(ToolExecutionError):rotation_workspace(policy,'red','right',geometry)


def test_aabb_distance_is_conservative_and_overlap_not_contact_assertion():
    a=dict(lo=[0,0,0],hi=[1,1,1]);b=dict(lo=[2,3,1],hi=[3,4,2])
    assert separation(a,b)==pytest.approx(np.sqrt(5))
    assert separation(a,dict(lo=[.5,.5,.5],hi=[2,2,2]))==0


def test_post_public_clearance_failure_preserves_receipt_and_blocks_next_increment(monkeypatch):
    from videoicl_isaaclab import execution_design_e23_clearance as module
    policy=SimpleNamespace(tip=lambda side:np.array([0,0,1.]),require_held=lambda *args:None)
    called=[]
    monkeypatch.setattr(module,'record_geometry',lambda *a:called.append(a[-1])or dict(minimum_separation_m=0.,target_tcp_z_m=1.))
    with pytest.raises(ToolExecutionError,match='full-arm'):
        module.verify_rotation_clearance(policy,'red','right','after-axis-increment')
    assert called==['after-axis-increment']


def test_measured_station_moves_outward_to_exclude_tall_tree_without_lowering_margin():
    from videoicl_isaaclab.execution_design_e23_clearance import choose_rotation_station
    objects={'tree':dict(lo=[.005,-.081,.8],hi=[.171,.081,1.074]),
             'blue':dict(lo=[-.161,-.041,.8],hi=[-.079,.041,.888]),
             'red':dict(lo=[-.2,-.2,.9],hi=[-.1,-.1,1.])}
    result=choose_rotation_station([-.156,-.152,.944],.1563,objects,'red','right',[])
    assert result['chosen']['outward_distance_m']==.08
    assert result['chosen']['swept_obstacles']==[]
    assert result['chosen']['rotation_height_m']==pytest.approx(.9763)
    assert result['tracking_margin_m']==.010
    assert result['candidates'][0]['rotation_height_m']==pytest.approx(1.2503)
    assert result['chosen']['actual_path_not_verified']


def test_station_never_assigns_hypothetical_translation_to_actual_geometry():
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_e23_clearance import choose_rotation_station
    obstacles={'blue':dict(lo=[-.04,.1,.8],hi=[.04,.2,.9])};original=deepcopy(obstacles)
    tip=np.array([0,.22,.96]);before=tip.copy()
    result=choose_rotation_station(tip,.10,obstacles,'red','left',[])
    assert obstacles==original;np.testing.assert_array_equal(tip,before)
    assert result['chosen']['tcp_task_m'][1]>=tip[1]


def test_station_drift_is_corrected_by_public_move_and_never_rebased(monkeypatch):
    from videoicl_isaaclab import execution_design_e23_clearance as module
    tip=np.array([-.15,-.23,.980]);target=np.array([-.15,-.23,.986]);log=[]
    p=SimpleNamespace(_e23_rotation_station=('red','right',target.copy()),tip=lambda s:tip.copy(),
        require_held=lambda *args:log.append('held'),stage=lambda *a:None)
    def move(side,destination,guard,tolerance):
        guard();log.append(('public_move',destination.copy(),tolerance));tip[:]=destination
    p.move=move
    monkeypatch.setattr(module,'record_geometry',lambda *a:dict(minimum_separation_m=.015,target_tcp_z_m=.976))
    module.restore_rotation_station(p,'red','right')
    np.testing.assert_array_equal(p._e23_rotation_station[2],target)
    np.testing.assert_array_equal(tip,target)
    moves=[x for x in log if isinstance(x,tuple)];assert len(moves)==1
    assert moves[0][2]==.001


def test_station_large_drift_or_blocked_arm_cannot_move(monkeypatch):
    from videoicl_isaaclab import execution_design_e23_clearance as module
    p=SimpleNamespace(_e23_rotation_station=('red','right',np.array([0,0,1.])),tip=lambda s:np.array([0,0,.970]),
        require_held=lambda *a:None,stage=lambda *a:None)
    p.move=lambda *a,**kw:pytest.fail('Unsafe public translation must not be sent')
    with pytest.raises(ToolExecutionError,match='25mm'):module.restore_rotation_station(p,'red','right')
    p.tip=lambda s:np.array([0,0,.994])
    monkeypatch.setattr(module,'record_geometry',lambda *a:dict(minimum_separation_m=0,target_tcp_z_m=1.))
    def move(side,target,guard,tolerance):guard();pytest.fail('Guard failed to block')
    p.move=move
    with pytest.raises(ToolExecutionError,match='full-arm'):module.restore_rotation_station(p,'red','right')


def test_distal_wrist_radius_requires_real_mesh_radius_and_all_bodies():
    from videoicl_isaaclab.execution_design_e23_clearance import wrist_station_radius
    _,geometry=fixture()
    geometry['robots']['right'].extend([
        dict(name='panda_link6',maximum_distance_to_tcp_m=.29324196),
        dict(name='panda_link7',maximum_distance_to_tcp_m=.16445)])
    assert wrist_station_radius(geometry,'right',.1563)==pytest.approx(.29324196)
    geometry['robots']['right'][-2]['maximum_distance_to_tcp_m']=float('nan')
    with pytest.raises(ToolExecutionError,match='radius'):wrist_station_radius(geometry,'right',.1563)
    geometry['robots']['right'].pop()
    with pytest.raises(ToolExecutionError,match='collider'):wrist_station_radius(geometry,'right',.1563)


def test_wrist_station_excludes_tall_tree_and_retains_measured_vertical_margin():
    from videoicl_isaaclab.execution_design_e23_clearance import choose_rotation_station,rotation_obstacle_top
    obstacles={'tree':dict(lo=[.005,-.081,.8],hi=[.171,.081,1.074]),
               'blue':dict(lo=[-.161,-.041,.8],hi=[-.079,.041,.888]),
               'green':dict(lo=[-.161,.109,.8],hi=[-.079,.191,.888])}
    result=choose_rotation_station([-.156,-.152,.944],.293242,obstacles,'red','right',[],wrist_planning=True)
    chosen=result['chosen'];assert chosen['away_from_tree_x_m']<0
    assert chosen['swept_obstacles']==[]
    assert chosen['rotation_height_m']==pytest.approx(1.113242)
    assert chosen['actual_path_not_verified']
    assert rotation_obstacle_top(chosen['tcp_task_m'],.293242,obstacles,'red',[])[1]==[]
    assert len(result['candidates'])==30


def test_public_station_lift_preserves_wrist_envelope_not_only_hand_height(monkeypatch,tmp_path):
    from videoicl_isaaclab import execution_design_e23_clearance as module
    from videoicl_isaaclab.execution_design import REVISION_V3
    tip=np.array([-.156,-.152,.944]);moves=[]
    state={n:dict(pos=p,mat=np.eye(3),grasp=[False,n=='red'])for n,p in
           [('red',[-.15,-.15,.96]),('tree',[.08,0,.94]),('blue',[-.12,0,.844])]}
    p=SimpleNamespace(task='E23',spec={'execution_design':{'revision':REVISION_V3},'fixtures':[]},
        a=SimpleNamespace(control_report={'engineering_reference_only':True}),objects={n:dict(size=[.04,.04,.044])for n in state},
        snapshot=lambda:(state,set()),tip=lambda s:tip.copy(),require_held=lambda *a:None,operations=[],stage=lambda s:None)
    p.objects['tree']['size']=[.075,.081,.134]
    geometry={'complete':True,'robots':{'right':[dict(name=n,maximum_distance_to_tcp_m=radius)for n,radius in
             [('panda_link6',.293242),('panda_link7',.16445),('panda_hand',.1563),('panda_leftfinger',.054),('panda_rightfinger',.054)]]}}
    monkeypatch.setattr(module,'actual_robot_collision_geometry',lambda author:geometry)
    monkeypatch.setattr(module,'record_geometry',lambda *a:dict(rotation_radius_m=.1563,target_tcp_z_m=.9763,minimum_separation_m=.04))
    def move(side,target,guard):
        guard();moves.append(np.asarray(target).copy());tip[:]=target
    p.move=move;module.prepare_rotation_workspace(p,'red','right')
    assert len(moves)==2
    assert moves[1][2]>=1.123242-1e-9
    assert moves[1][2]>.9763+.01
    np.testing.assert_array_equal(p._e23_rotation_station[2],moves[-1])
