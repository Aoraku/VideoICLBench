import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e13_camera_place import measured_stand_ledge,bottom_front_edge,edge_height_target


def phone():
    import itertools
    return np.array(list(itertools.product([-.075,.075],[-.037,.037],[-.0047,.0047])))


def test_bottom_edge_centers_both_corners_instead_of_aligning_one_low_corner():
    vertices=phone();edge=bottom_front_edge(vertices)
    np.testing.assert_allclose(edge,[-.075,0,-.0047])
    a=math.radians(18);r=np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
    ledge=np.array([-.032,-.11,.855]);target=edge_height_target(edge,vertices,r,ledge)
    np.testing.assert_allclose(target[:2],ledge[:2]);bottom=vertices[vertices[:,0]<0]
    assert ((bottom-edge)@r.T+target)[:,2].min()==pytest.approx(.857)


def test_stand_ledge_tracks_actual_body_shift_and_yaw():
    stand=dict(xy=[0,-.11],bottom=.802,size=[.037,.041,.0618],yaw=0)
    semantic=dict(stand_ledge_point_task=[-.032,-.11,.855]);nominal=np.array([0,-.11,.8638]);r=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    actual=nominal+[.01,.02,-.001]
    np.testing.assert_allclose(measured_stand_ledge(stand,semantic,actual,r),actual+[0,-.032,-.0088])


def test_bottom_edge_rejects_unreviewed_geometry():
    with pytest.raises(ValueError):bottom_front_edge(phone()*2)
    with pytest.raises(ValueError):bottom_front_edge([[0,0,0]])


def test_supported_release_rechecks_actual_camera_direction_before_any_open(monkeypatch):
    from types import SimpleNamespace
    import videoicl_isaaclab.execution_design_e13_branch as branch
    import videoicl_isaaclab.execution_design_e13_camera_place as place
    import videoicl_isaaclab.execution_design_branch_geometry as geometry
    import videoicl_isaaclab.execution_design_thin_edge as material
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    commands=[];r=np.eye(3);position=np.array([0,0,.9]);vertices=phone()+position
    state=dict(phone=dict(mat=r,pos=position),stand=dict(mat=r,pos=[0,-.11,.8638]))
    semantic=dict(stand='stand',phone='phone',camera_end_points={'phone':[.07,0,0]},back_normals={'phone':[0,0,1]},stand_ledge_point_task=[-.032,-.11,.855])
    p=SimpleNamespace(c=SimpleNamespace(steps=1600),variant='A',s=semantic,spec=dict(objects=[dict(id='stand',xy=[0,-.11],bottom=.802,size=[.037,.041,.0618],yaw=0)]),require_held=lambda *a:None,snapshot=lambda:(state,[]),contact=lambda *a:True,act=lambda *a:commands.append(a))
    monkeypatch.setattr(branch,'_policy',lambda *a:p);monkeypatch.setattr(geometry,'HeldGeometry',lambda *a,**k:None);monkeypatch.setattr(geometry,'install_public_guard',lambda *a:None)
    monkeypatch.setattr(material,'material_collision_points_task',lambda *a:vertices)
    context=dict(camera_end_strategy='actual_supported1337_right_camera_end_v1',camera_end_place_phase='open_release')
    with pytest.raises(ToolExecutionError,match='native orientation'):place.run_branch(SimpleNamespace(c=p.c),context,'camera_end_place')
    assert commands==[]


def test_supported_completion_routes_actual_slip_to_local_inset_not_lost_hold(monkeypatch):
    from types import SimpleNamespace
    import videoicl_isaaclab.execution_design_e13_camera as camera
    import videoicl_isaaclab.execution_design_e13_camera_place as place
    calls=[];author=SimpleNamespace(c=SimpleNamespace(steps=1558,snapshot=lambda:({'phone':{'grasp':[False,False]}},[])))
    def acquire(a,c,name):
        calls.append(name);return dict(local_completed=True,native_already_landed=True,whole_task_score=None)
    monkeypatch.setattr(camera,'run_branch',acquire)
    result=place.run_branch(author,dict(camera_end_phase='lift_above_stand'),'camera_end_complete_supported')
    assert calls==['camera_end_inset_regrasp']
    assert result['local_completed'] and result['whole_task_score']is None
