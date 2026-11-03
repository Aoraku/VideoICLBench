import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e43_guide_plan import plan
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


@pytest.mark.parametrize('target_y',[-.12,.12,0.])
def test_passive_projection_targets_zone_without_circumradius_overretreat(target_y):
    result=plan([-.1,.035,.818],[-1,0,0],[-.17,target_y,.8],[.117,.058,.8438],
        [.04,.035,.8],np.eye(3),[.1195,.045,.03],np.eye(3),[.09,.006,.018],[0,1,0])
    p=np.array(result['point']);assert -.17<p[0]<-.10 and p[1]==pytest.approx(.058)
    assert result['launcher_gap_m']==pytest.approx(.006,abs=1e-12)
    assert np.allclose(result['passive_projection_direction'],result['outgoing_tangent'])
    assert result['incoming_speed_projection']>.2
    assert not result['collision_or_material_modified'] and result['native_deflection_required']


def test_target_before_launcher_exit_is_not_a_feasible_passive_turn():
    with pytest.raises(ToolExecutionError,match='Target lies before'):
        plan([-.1,0,.818],[-1,0,0],[0,0,.8],[.117,0,.8438],
            [.04,0,.8],np.eye(3),[.1195,.045,.03],np.eye(3),[.09,.006,.018],[0,1,0])


@pytest.mark.parametrize('target_y',[-.12,.12,0.])
def test_native_response_model_accounts_for_real_ball_contact_point(target_y):
    from videoicl_isaaclab.execution_design_e43_guide_plan import response_plan,NATIVE_RESPONSE
    result=response_plan([-.1,.035,.817],[-1,0,0],[-.17,target_y,.8],[.117,.058,.8438],
        [.04,.035,.8],np.eye(3),[.1195,.045,.03],np.eye(3),[.09,.003,.015],[0,1,0],
        ball_radius=.014,response=NATIVE_RESPONSE)
    assert result['predicted_target_ray_miss_m']<.002
    assert result['predicted_ball_contact_center'][0]>result['point'][0]
    assert result['response_calibration']['source_native_trajectory_sha256']==NATIVE_RESPONSE['source_native_trajectory_sha256']
    assert not result['collision_or_material_modified'] and result['native_deflection_required']


@pytest.mark.parametrize('equivalent',[0,1])
def test_real_contact_patch_recomputes_upstream_board_gap_in_each_equivalent_direction(equivalent):
    from videoicl_isaaclab.execution_design_e43_guide_plan import response_plan,NATIVE_RESPONSE
    work=np.array([.020,0.,0.]);half=np.array([.09,.003,.015]);launcher_front=.04-.1195
    result=response_plan([-.1,.035,.817],[-1,0,0],[-.17,.12,.8],[.117,.058,.8438],
        [.04,.035,.8],np.eye(3),[.1195,.045,.03],np.eye(3),half,[0,1,0],
        ball_radius=.014,response=NATIVE_RESPONSE,center_relative_work=-work,
        equivalent_plane=equivalent)
    r=np.asarray(result['rotation']);center=np.asarray(result['point'])-r@work
    real_upstream_tip=center[0]+float(np.abs(r.T@np.array([1.,0.,0.]))@half)
    assert real_upstream_tip==pytest.approx(launcher_front-.006,abs=1e-9)
    assert result['predicted_target_ray_miss_m']<.002
    assert result['equivalent_plane']==equivalent and not result['collision_or_material_modified']
