import itertools
import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e13_release import native_orientation,plan_opening_height
from videoicl_isaaclab.realworld_semantic_checks import check_task
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation

SEMANTIC={'phone':'phone','camera_end_points':{'phone':[.07,0,0]},'back_normals':{'phone':[0,0,1]}}


@pytest.mark.parametrize('variant,rotation',[
    ('A',_axis_rotation([0,0,1],math.radians(12))@_axis_rotation([0,1,0],-1.0272375716022242)),
    ('B',np.array([[0,0,-1],[-1,0,0],[0,1,0]])),
    ('C',np.array([[0,0,-1],[1,0,0],[0,-1,0]]))])
def test_allowed_phone_orientation_matches_unchanged_native_rule_without6degree_recipe(variant,rotation):
    result=native_orientation(rotation,SEMANTIC,variant)
    native=check_task('E13',variant,dict(released=True,stable=True,camera_end=result['camera_end'],
        back_faces_operator=result['back_faces_operator'],stand_supported=True))
    assert result['allowed'] and native['success']


def test_wrong_camera_or_back_direction_does_not_pass_phone_geometry():
    assert not native_orientation(np.eye(3),SEMANTIC,'A')['allowed']
    r=np.array([[0,0,-1],[-1,0,0],[0,1,0]])
    assert not native_orientation(r,SEMANTIC,'C')['allowed']
    with pytest.raises(ValueError):native_orientation(np.zeros((3,3)),SEMANTIC,'A')


def box(center,half):return np.array(center)+np.array(list(itertools.product((-1,1),repeat=3)))*np.array(half)


def test_release_planning_includes_finger_opening_and_selects_geometry_clear_height():
    current=box([0,0,1.],[.002,.002,.002]);opened=current+[.04,0,0]
    bodies={'hand':box([-.04,0,1.],[.005,.005,.005]),'opening_finger':np.r_[current,opened]}
    support=box([.04,0,.9],[.01,.01,.01])
    result=plan_opening_height(bodies,[0,0,1.],.9,{'stand':[support]},.8,max_z=.95)
    assert .91<result['tcp_z']<=.94
    assert result['geometry_candidates_rejected']>0 and result['actual_task_landing_not_yet_verified']
