import json
from pathlib import Path
import numpy as np
from videoicl_isaaclab.execution_design_push_rotation_path import route_poses
from videoicl_isaaclab.execution_design_local_pose_path import solve_local_pose_path


def test_actual_c_native_j_can_reach_real_rim_section_without_relaxing_limits():
    f=json.loads((Path(__file__).parent/'fixtures/e42_native_c_v13_front_sections.json').read_text())
    n=f['native'];p=np.asarray(n['position']);station=np.r_[p[:2],.90]
    def inspect(target):
        poses,_=route_poses(p,n['rotation_task'],f['rotation'],station,target,.025)
        return solve_local_pose_path(n['position'],n['rotation_task'],n['jacobian'],n['q'],n['limits'],poses)
    old=inspect(f['center_approach']);assert not old['feasible']
    passed=inspect(f['valid_approach']);assert passed['feasible']
    assert f['lateral']==-.020
    assert min(row['minimum_joint_margin_rad']for row in passed['rows'])>.25
    assert not passed['actuation_performed']and not passed['collision_verified']


def test_actual_c_reapproach_has_equivalent_source_pose_inside_existing_direction_guard():
    f=json.loads((Path(__file__).parent/'fixtures/e42_native_c_v15_yaw_reference.json').read_text())
    n=f['native'];p=np.asarray(n['position']);station=np.r_[p[:2],.90]
    relative=np.asarray(f['current_actor_rotation']).T@np.asarray(n['rotation_task'])
    def inspect(actor,approach):
        poses,_=route_poses(p,n['rotation_task'],np.asarray(actor)@relative,station,approach,.025)
        return solve_local_pose_path(n['position'],n['rotation_task'],n['jacobian'],n['q'],n['limits'],poses)
    assert not inspect(f['base_actor_target'],f['base_approach'])['feasible']
    passed=inspect(f['valid_actor_target'],f['valid_approach']);assert passed['feasible']
    assert min(row['minimum_joint_margin_rad']for row in passed['rows'])>.3
    # A6degree table yaw keeps the original tool-up axis and stays inside the
    # existing12degree push-direction guard; no source goal/shape is changed.
    before=np.asarray(f['base_actor_target']);after=np.asarray(f['valid_actor_target'])
    assert np.allclose(before[:,2],after[:,2],atol=1e-12)
    assert float(before[:,0]@after[:,0])>np.cos(np.deg2rad(7.))


def test_c17_source_handle_choice_avoids_wrist_stall_without_looser_ik_limits():
    f=json.loads((Path(__file__).parent/'fixtures/e42_native_c_v17_clear_handle.json').read_text())
    n=f['native'];relative=np.asarray(f['current_actor_rotation']).T@np.asarray(n['rotation_task'])
    poses,_=route_poses(n['position'],n['rotation_task'],np.asarray(f['target_actor'])@relative,
                        f['station'],f['approach'],.025)
    path=solve_local_pose_path(n['position'],n['rotation_task'],n['jacobian'],n['q'],n['limits'],poses)
    assert path['feasible'] and len(path['rows'])>=15
    assert path['constraints']['position_tolerance_m']==.001
    assert path['constraints']['minimum_joint_margin_rad']==.06
    assert f['source_handle_pitch_degrees']==7. and abs(f['yaw_degrees'])<12.
    assert abs(f['lateral_m'])<=.020


def test_c19_true_other_ball_is_cleared_by_upper_rim_contact_without_looser_ik():
    from scipy.spatial.transform import Rotation
    from videoicl_isaaclab.execution_design_tool_route_clearance import swept_route_clear
    f=json.loads((Path(__file__).parent/'fixtures/e42_native_c_v19_other_ball_clearance.json').read_text())
    n=f['native'];body=f['checkpoint']['objects']['spatula']['root_state_task']
    actor=Rotation.from_quat([*body[4:7],body[3]]).as_matrix()
    relative=actor.T@np.asarray(n['rotation_task']);desired=np.asarray(f['actor_target'])@relative
    def route(dz):
        approach=np.asarray(f['raised_approach'])+[0,0,dz]
        return route_poses(n['position'],n['rotation_task'],desired,f['station'],approach,.025)[0]
    old=route(-.003);new=route(0.)
    assert not swept_route_clear(f['carried_local'],n['position'],n['rotation_task'],old,f['obstacles'],f['floor'])
    assert swept_route_clear(f['carried_local'],n['position'],n['rotation_task'],new,f['obstacles'],f['floor'])
    path=solve_local_pose_path(n['position'],n['rotation_task'],n['jacobian'],n['q'],n['limits'],new)
    assert path['feasible'] and path['constraints']['position_tolerance_m']==.001
