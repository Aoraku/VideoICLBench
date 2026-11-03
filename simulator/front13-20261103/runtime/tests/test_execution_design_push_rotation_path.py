import numpy as np
from videoicl_isaaclab.execution_design_push_rotation_path import actor_rotation_poses,route_poses
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.author_orientation import _axis_angle


def test_turns_match_real_tool_maximum_ten_degrees_and_four_degree_stop():
    target=_axis_rotation([0,0,1],np.deg2rad(162));poses=actor_rotation_poses([-.19,-.25,.95],np.eye(3),target)
    previous=np.eye(3)
    for pose in poses:
        current=np.array(pose['rotation']);axis,angle=_axis_angle(current@previous.T)
        assert angle<=np.deg2rad(10)+1e-10
        assert np.allclose(pose['position'],[-.19,-.25,.95])
        previous=current
    assert _axis_angle(target@previous.T)[1]<np.deg2rad(4)


def test_route_includes_source_workpoint_lift_and_actual_ball_approach():
    target=_axis_rotation([0,0,1],np.deg2rad(90));point=np.array([-.10,-.05,.824])
    poses,turns=route_poses([-.07,-.01,.87],np.eye(3),target,[-.19,-.25,.95],point)
    assert turns and .948<=max(x['position'][2]for x in poses)<=.950001
    assert np.max(np.abs(np.array(poses[-1]['position'])-point))<=.002
