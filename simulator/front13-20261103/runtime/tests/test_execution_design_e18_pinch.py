"""Real authored collider geometry; no native contact acceptance implied."""
import json,math
from pathlib import Path
import numpy as np
from videoicl_isaaclab.execution_design_e18_pinch import bar_pinch_candidate
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def geometry():
    data=json.loads((Path(__file__).parent/'data/e18-native-hand-closed.json').read_bytes());closed=[]
    for i,b in enumerate(data['bodies']):
        c=np.concatenate([p['points_body']for p in b['collision_parts']]);c[:,2]-=.1034
        if i:c[:,2]+=.0584
        closed.append(c)
    closed=[closed[1],closed[2],closed[0]];opened=[c.copy()for c in closed]
    opened[0][:,1]+=.04;opened[1][:,1]-=.04
    return dict(source='actual_native_collision_mesh_current_body_pose',closed_clouds_tcp=closed,clouds_tcp=opened,jaw_axis_tcp=[0,1,0],table_top=.8)


def candidate(roll,tilt):
    base=np.array([[0,0,1],[-1,0,0],[0,-1,0.]])
    r=_axis_rotation([0,1,0],math.radians(tilt))@_axis_rotation([1,0,0],math.radians(roll))@base
    return bar_pinch_candidate(geometry(),r,[-.084,.075,.8779254],[-1,0,0],[0,-1,0])


def test_previous_oblique_open_aabb_candidate_cannot_reach_bar_on_closure():
    assert not candidate(30,25)['feasible']


def test_source_bar_can_be_pinched_without_palm_in_table_or_open_fingers_in_panel():
    r=candidate(55,0)
    assert r['feasible'] and min(r['hand_floor_clearances_m'])>.005
    assert .003<r['closing_opening_m']<.035 and not r['open_fingers_intersect_bar']
    assert r['target_position'][0]>-.092
    assert not r['collision_verified'] and not r['native_grip_verified']


def test_vertical_jaw_still_rejects_palm_table_intersection():
    assert not candidate(0,0)['feasible']
