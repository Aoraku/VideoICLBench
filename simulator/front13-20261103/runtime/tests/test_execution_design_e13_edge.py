import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e13_edge import plan_edge,acquire_edge
from types import SimpleNamespace

def box(center,half):return np.array(center)+np.array(list(itertools.product((-1,1),repeat=3)))*np.array(half)
def test_actual_phone_edge_preserves_supported_center():
    material=box([0,0,.805],[.075,.037,.005]);b=dict(lower=np.array([-.35,-.6,.8]),upper=np.array([.35,.6,.8]),top=.8)
    fingers=[box([-.015,0,z],[.01,.01,.01])for z in(-.03,.03)]
    p=plan_edge(material,[0,0,.805],fingers,b,[1,0,0]);assert p['translated_center'][0]<.345;assert p['target_grasp'][0]>.35

def test_edge_plan_refuses_losing_supported_center():
    material=box([0,0,.805],[.015,.01,.005]);b=dict(lower=np.array([-.35,-.6,.8]),upper=np.array([.35,.6,.8]),top=.8)
    with pytest.raises(ValueError,match='support'):plan_edge(material,[0,0,.805],[box([-.06,0,-.03],[.02,.01,.01])]*3,b,[1,0,0])
def test_other_task_cannot_use_phone_edge_path():
    with pytest.raises(ValueError):acquire_edge(SimpleNamespace(scene=SimpleNamespace(spec={'id':'E14'})),'left','phone')


def test_contact_gap_uses_clipped_faces_not_full_aabb():
    from videoicl_isaaclab.execution_design_e13_edge import trailing_contact_gap
    # Sloped toe has a far leading vertex above the phone. Only its section
    # through the actual phone height can make initial contact.
    material=box([0,0,.805],[.05,.03,.005])
    toe=np.array([[x,y,z] for y in [-.01,.01] for x,z in [(.06,.8),(.08,.8),(.04,.84),(.08,.84)]])
    assert trailing_contact_gap(material,[toe],[-1,0,0],.8)==pytest.approx(.005)

def test_contact_gap_reports_positive_remaining_clearance():
    from videoicl_isaaclab.execution_design_e13_edge import trailing_contact_gap
    material=box([0,0,.805],[.05,.03,.005]);finger=box([.060268,0,.805],[.01,.01,.005])
    assert trailing_contact_gap(material,[finger],[-1,0,0],.8)==pytest.approx(.000268)


def test_minimal_entry_clears_actual_whole_hand_and_entire_open_path():
    from videoicl_isaaclab.execution_design_e13_edge import side_entry,side_path_clearance
    material=box([.31,0,.805],[.076,.037,.005]);point=np.array([.38,0,.805])
    relative=[box([0,0,z],[.01,.01,.01])for z in(-.03,.03)]+[box([.06,0,0],[.02,.03,.04])]
    entry,receipt=side_entry(material,relative,point,[1,0,0])
    assert entry[0]==pytest.approx(.399)
    assert min((x+entry)[:,0].min()for x in relative)-material[:,0].max()==pytest.approx(.003)
    assert receipt['exterior_offset_m']<.03
    bounds=dict(lower=[-.35,-.6,.8],upper=[.35,.6,.8],top=.8)
    high=entry.copy();high[2]=.98
    assert side_path_clearance(material,relative,[high,entry,point],bounds)['entire_translation_sweeps_clear']
    # Descending straight to the endpoint would sweep the lower finger through
    # the phone even though the final open pose itself is collision free.
    high_direct=point.copy();high_direct[2]=.98
    with pytest.raises(Exception,match='phone'):
        side_path_clearance(material,relative,[high_direct,point],bounds)


def test_side_sweep_refuses_lower_finger_crossing_finite_table():
    from videoicl_isaaclab.execution_design_e13_edge import side_path_clearance
    material=box([.6,0,.805],[.07,.03,.005])
    relative=[box([0,0,z],[.01,.01,.01])for z in(-.03,.03)]+[box([.06,0,0],[.02,.03,.04])]
    bounds=dict(lower=[-.35,-.6,.8],upper=[.35,.6,.8],top=.8)
    with pytest.raises(Exception,match='table'):
        side_path_clearance(material,relative,[[.4,0,.805],[.34,0,.805]],bounds)


def test_planned_edge_keeps_original_guard_after_push_and_rotation_errors():
    from videoicl_isaaclab.execution_design_e13_edge import edge_planning_margin
    material=box([0,0,.805],[.075,.037,.005]);bounds=dict(lower=np.array([-.35,-.6,.8]),upper=np.array([.35,.6,.8]),top=.8)
    relative=[box([-.015,0,z],[.01,.01,.01])for z in(-.03,.03)]+[box([.04,0,.02],[.03,.025,.04])]
    margin=edge_planning_margin(relative);plan=plan_edge(material,[0,0,.805],relative,bounds,[1,0,0],margin=margin)
    angle=np.deg2rad(1.);r=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
    actual_grasp=plan['target_grasp']-[.001,0,0]
    for body in relative:
        points=body@r.T+actual_grasp;low=points[points[:,2]<.801]
        if len(low):assert low[:,0].min()>=.351
    assert plan['translated_center'][0]<.345


def test_candidate_uses_reviewed_equivalent_jaws_on_same_edge():
    from videoicl_isaaclab.execution_design_e13_edge import choose_edge_candidate
    plan={'axis':np.array([-1.,0.,0.])};reviewed=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
    old=reviewed@np.diag([-1.,-1.,1.])
    rows=[(.4,plan,old,None),(.40000001,plan,reviewed,None)]
    assert choose_edge_candidate(rows) is rows[1]
    with pytest.raises(Exception,match='continuous'):choose_edge_candidate(rows[:1])


def test_low_side_route_keeps_all_public_segments_axis_aligned():
    from videoicl_isaaclab.execution_design_e13_edge import side_waypoints,side_path_clearance
    tip=np.array([-.2,.1435,.98]);entry=np.array([-.399,.14,.805]);point=np.array([-.38,.14,.805])
    waypoints=side_waypoints(tip,entry,point)
    assert waypoints[1][2]==.92 and waypoints[2][0]==entry[0]
    for a,b in zip(waypoints[:-1],waypoints[1:]):assert np.count_nonzero(abs(a-b)>1e-10)<=1
    material=box([-.31,.14,.805],[.076,.037,.005])
    relative=[box([0,0,z],[.01,.01,.01])for z in(-.03,.03)]+[box([-.06,0,0],[.02,.03,.04])]
    bounds=dict(lower=[-.35,-.6,.8],upper=[.35,.6,.8],top=.8)
    assert side_path_clearance(material,relative,waypoints,bounds)['entire_translation_sweeps_clear']
    wrong=[p.copy()for p in waypoints];wrong[1][2]=.83
    with pytest.raises(Exception,match='phone|table'):side_path_clearance(material,relative,wrong,bounds)
