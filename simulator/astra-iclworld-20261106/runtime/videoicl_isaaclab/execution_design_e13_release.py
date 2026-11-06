"""E13 task-native orientation and actual open-finger clearance at release."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_branch_geometry import swept_pose_clearance,collision_parts_task


def native_orientation(rotation,semantic,variant):
    """Same classification and thresholds as unchanged native E13 derive/check."""
    r=np.asarray(rotation,float)
    if variant not in('A','B','C')or r.shape!=(3,3)or not np.isfinite(r).all()or not np.allclose(r.T@r,np.eye(3),atol=1e-4)or np.linalg.det(r)<.999:
        raise ValueError('Finite actual phone rotation and ABC variant required')
    phone=semantic.get('phone','phone');direction=r@np.asarray(semantic['camera_end_points'][phone],float)
    direction=direction/max(float(np.linalg.norm(direction)),1e-9)
    back=r@np.asarray(semantic['back_normals'][phone],float)
    camera='up'if direction[2]>.7 else'left'if direction[1]>.7 else'right'if direction[1]<-.7 else'other'
    wanted=('up','right','left')['ABC'.index(variant)];correct=camera==wanted;faces=bool(back[0]<-.7)
    return dict(allowed=correct and faces,camera_end=camera,expected_camera_end=wanted,
                camera_end_direction=correct,back_faces_operator=faces,
                camera_direction_task=direction.tolist(),back_direction_task=back.tolist(),
                source='unchanged_realworld_native_evidence_E13_and_semantic_checks')


def plan_opening_height(bodies,tip,goal_z,obstacles,table_top,max_z=None):
    """Pure geometry search; each body already includes its full opening sweep."""
    tip=np.asarray(tip,float);goal_z=float(goal_z);high=max(float(tip[2])+.04,goal_z)if max_z is None else float(max_z)
    if tip.shape!=(3,)or not np.isfinite(np.r_[tip,goal_z,high]).all()or high<goal_z:
        raise ValueError('Finite ordered actual release height interval required')
    rejected=0
    for z in [*np.arange(goal_z,high,.002),high]:
        shifted={name:np.asarray(points)+[0,0,float(z)-tip[2]]for name,points in bodies.items()}
        point=np.array([*tip[:2],z])
        try:guard=swept_pose_clearance(shifted,point,point,np.eye(3),obstacles,table_top)
        except ToolExecutionError:
            rejected+=1;continue
        return dict(tcp_z=float(z),original_proposal_z=goal_z,extra_release_height_m=float(z-goal_z),
                    opening_sweep_guard=guard,geometry_candidates_rejected=rejected,
                    actual_task_landing_not_yet_verified=True)
    raise ToolExecutionError('No actual full-opening hand release clearance above stand')


def actual_opening_bodies(policy,side):
    from .execution_design_e33_grasp import actual_mesh
    a=policy.a;profile=a.scene.embodiment;robot=a.scene.robots[side]
    if profile.name!='franka'or profile.finger_joints!=['panda_finger_joint1','panda_finger_joint2']:
        raise ToolExecutionError('Reviewed actual Panda finger transmission required')
    ids,_=robot.find_joints(profile.finger_joints,preserve_order=True)
    measured=robot.data.joint_pos[0,ids].detach().cpu().numpy()
    opened=np.asarray(profile.gripper_values(1.),float);rotation=np.asarray(a.tcp_rotation_task(side),float)
    result={'panda_hand':actual_mesh(a,side,'panda_hand')}
    for i,name in enumerate(profile.fingers):
        points=actual_mesh(a,side,name);delta=rotation[:,1]*(1 if i==0 else-1)*(opened[i]-measured[i])
        result[name]=np.r_[points,points+delta]
    return result


def release_height(policy,side,goal_z):
    from .execution_design_thin_edge import table_bounds_task
    bodies=actual_opening_bodies(policy,side);state,_=policy.snapshot()
    obstacles={name:collision_parts_task(policy,name)for name in state if name!='phone'}
    return plan_opening_height(bodies,policy.tip(side),goal_z,obstacles,table_bounds_task(policy.a.scene)['top'])


def actual_opening_clearance(policy,side):
    """Recheck the achieved pose before the public gripper opening command."""
    from .execution_design_thin_edge import table_bounds_task
    bodies=actual_opening_bodies(policy,side);state,_=policy.snapshot();tip=policy.tip(side)
    obstacles={name:collision_parts_task(policy,name)for name in state if name!='phone'}
    return swept_pose_clearance(bodies,tip,tip,np.eye(3),obstacles,table_bounds_task(policy.a.scene)['top'])


def landing_conditions(policy):
    state,_=policy.snapshot();phone=state['phone'];orientation=native_orientation(phone['mat'],policy.s,policy.variant)
    support=policy.s['stand'];contact=bool(policy.contact('phone',support));released=not any(phone['grasp'])
    conditions=list(getattr(policy.c.evaluator,'current_conditions',[]))
    return dict(orientation=orientation,physical_stand_support=contact and released,
                actual_stand_contact=contact,native_grasp=list(phone['grasp']),released=released,
                native_current_conditions=conditions,
                native_current_conditions_passed=bool(conditions)and all(item.get('passed')is True for item in conditions),
                local_geometry_contact_allowed=orientation['allowed']and contact and released,whole_task_score=None)
