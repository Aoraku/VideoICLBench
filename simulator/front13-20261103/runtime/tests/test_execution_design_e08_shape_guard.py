import itertools
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
from videoicl_isaaclab.execution_design_branch_geometry import swept_pose_clearance
from videoicl_isaaclab.execution_design_e08_shape_guard import SourceShoeGeometry


def box(lo,hi):return np.array(list(itertools.product(*zip(lo,hi))))


def test_all_native_shoe_pieces_preserve_gap_and_still_reject_real_piece_collision(monkeypatch):
    import videoicl_isaaclab.execution_design_e08_shape_guard as module
    import videoicl_isaaclab.execution_design_e33_grasp as mesh
    import videoicl_isaaclab.execution_design_thin_edge as thin
    pieces=[box([-.04,-.04,1.],[.04,-.02,1.04]),box([-.04,.02,1.],[.04,.04,1.04])]
    wall=box([-.01,-.005,1.005],[.01,.005,1.035]);p=SimpleNamespace(a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['f1','f2']))),tip=lambda s:np.array([0.,0.,1.1]),require_held=lambda *a:None,snapshot=lambda:({'shoe':{},'box':{}},{}))
    monkeypatch.setattr(module,'collision_parts_task',lambda p,n:pieces if n=='shoe'else[wall])
    monkeypatch.setattr(mesh,'actual_mesh',lambda *a:box([.2,.2,1.2],[.22,.22,1.22]))
    monkeypatch.setattr(thin,'table_bounds_task',lambda s:dict(top=.8))
    with pytest.raises(ToolExecutionError):swept_pose_clearance({'payload':np.concatenate(pieces)},p.tip('right'),p.tip('right'),np.eye(3),{'box':[wall]},.8)
    guard=SourceShoeGeometry(p,'shoe','right');assert guard()['payload_convex_piece_count']==2
    pieces.append(wall.copy())
    with pytest.raises(ToolExecutionError,match='payload sweep intersects box'):guard()


def test_measured_up_departure_allows_padding_only_but_rejects_raw_penetration(monkeypatch,tmp_path):
    import videoicl_isaaclab.execution_design_e08_shape_guard as module
    import videoicl_isaaclab.execution_design_e33_grasp as mesh
    import videoicl_isaaclab.execution_design_thin_edge as thin
    import videoicl_isaaclab.execution_design_branch_rotation as rotation
    wall=box([-.02,-.02,.85],[.02,.02,.91]);shoe=[box([-.01,-.01,.911],[.01,.01,.94])]
    p=SimpleNamespace(a=SimpleNamespace(out=tmp_path,scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['f1','f2'])),tcp_rotation_task=lambda s:np.eye(3)),c=SimpleNamespace(steps=1259,contact_forces={},action_feedback=lambda:dict(control_feedback=dict(right=dict(orientation_error_rad=.001,orientation_tolerance_rad=.002)))),tip=lambda s:np.array([0.,0.,1.1]),require_held=lambda *a:None,snapshot=lambda:({'shoe':{},'box':{}},{}))
    monkeypatch.setattr(module,'collision_parts_task',lambda p,n:shoe if n=='shoe'else[wall])
    monkeypatch.setattr(mesh,'actual_mesh',lambda *a:box([.2,.2,1.2],[.22,.22,1.22]))
    monkeypatch.setattr(thin,'table_bounds_task',lambda s:dict(top=.8));monkeypatch.setattr(rotation,'accepted_pose_task',lambda *a:(p.tip('right'),np.eye(3)))
    context={};g=module.UpwardBoxDepartureGeometry(p,'shoe','right',context);g.check(target=p.tip('right')+[0,0,.012])
    assert context['right_box_up_departure_actual']['nonpenetrating_padding_departure'][0]['padding_only']
    shoe[0][:,2]-=.002
    with pytest.raises(ToolExecutionError,match='raw penetration'):g()
