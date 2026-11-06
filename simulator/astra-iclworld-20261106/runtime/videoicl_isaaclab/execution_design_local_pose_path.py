"""Read-only continuous-branch engineering IK screening from measured screws.

No random restarts, robot writes, joint commands, or collision claims. Each
Cartesian substep starts from the previous solution and bounds every joint's
change. Callers must supply the intended public-action orientation path.
"""
import math
import time
import numpy as np
from .execution_design_drawer_ik_probe import forward_at_delta, skew
from .author_orientation import _axis_angle


class _CPUPathBudgetExpired(Exception):
    pass


def _rotation_between(start, end, fraction):
    axis,angle=_axis_angle(end@start.T)
    k=skew(axis);theta=angle*fraction
    return (np.eye(3)+math.sin(theta)*k+(1-math.cos(theta))*(k@k))@start


def solve_local_pose_path(position, rotation, jacobian, q, limits, poses, *,
                          max_joint_step_rad=.18, minimum_joint_margin_rad=.06,
                          max_translation_step_m=.008,
                          max_rotation_step_rad=math.radians(5),
                          position_tolerance_m=.001,
                          orientation_tolerance_rad=math.radians(1.5),
                          max_nfev=120, max_seconds=None):
    """Return feasible/rows/first_failure; all q values are diagnostics only.

    `poses` contains dictionaries with position (optional) and rotation.
    Subdivision preserves the supplied waypoint order. A locally inaccessible
    waypoint fails closed; a distant endpoint IK branch is never substituted.
    """
    from scipy.optimize import least_squares
    p0=np.asarray(position,float).copy();r0=np.asarray(rotation,float).copy()
    jac=np.asarray(jacobian,float).copy();q0=np.asarray(q,float).copy();bounds=np.asarray(limits,float).copy()
    if (p0.shape!=(3,)or r0.shape!=(3,3)or jac.shape!=(6,7)or q0.shape!=(7,)or bounds.shape!=(7,2)
        or not all(np.isfinite(a).all()for a in (p0,r0,jac,q0,bounds))
        or not np.allclose(r0.T@r0,np.eye(3),atol=1e-5)or np.linalg.det(r0)<.999
        or not np.allclose(np.linalg.norm(jac[3:],axis=0),1,atol=.002)
        or np.any(bounds[:,0]>=q0)or np.any(bounds[:,1]<=q0)):
        raise ValueError('Invalid measured pose/Jacobian/joint limits')
    for value in (max_joint_step_rad,max_translation_step_m,max_rotation_step_rad,position_tolerance_m,orientation_tolerance_rad):
        if not np.isfinite(value)or value<=0:raise ValueError('Positive finite path limits required')
    if minimum_joint_margin_rad<0 or not np.isfinite(minimum_joint_margin_rad):raise ValueError('Invalid joint margin')
    if max_seconds is not None and (not np.isfinite(max_seconds)or max_seconds<=0):
        raise ValueError('Positive finite private CPU planning budget required')
    deadline=time.monotonic()+max_seconds if max_seconds is not None else None
    rows=[];previous=np.zeros(7);last_p=p0.copy();last_r=r0.copy()
    physical_lo=bounds[:,0]-q0+1e-7;physical_hi=bounds[:,1]-q0-1e-7
    constraints=dict(max_joint_step_rad=max_joint_step_rad,minimum_joint_margin_rad=minimum_joint_margin_rad,
        max_translation_step_m=max_translation_step_m,max_rotation_step_rad=max_rotation_step_rad,
        position_tolerance_m=position_tolerance_m,orientation_tolerance_rad=orientation_tolerance_rad)
    result=dict(schema='measured-local-continuous-pose-path-v1',feasible=True,rows=rows,first_failure=None,
        constraints=constraints,initial_joints_rad=q0.tolist(),collision_verified=False,actuation_performed=False,
        random_restarts=False,measured_reference=dict(position=p0.tolist(),rotation_task=r0.tolist(),
            jacobian=jac.tolist(),q=q0.tolist(),limits=bounds.tolist()))
    def budget_expired():
        result.update(feasible=False,first_failure=len(rows),cpu_budget_exhausted=True,
                      failure_reason='private_cpu_planning_budget',max_seconds=max_seconds)
        return result
    for waypoint,pose in enumerate(poses):
        if deadline is not None and time.monotonic()>=deadline:return budget_expired()
        end_p=np.asarray(pose.get('position',last_p),float);end_r=np.asarray(pose['rotation'],float)
        if (end_p.shape!=(3,)or end_r.shape!=(3,3)or not np.isfinite(end_p).all()or not np.isfinite(end_r).all()
            or not np.allclose(end_r.T@end_r,np.eye(3),atol=1e-5)or np.linalg.det(end_r)<.999):
            raise ValueError('Invalid Cartesian path waypoint')
        angle=_axis_angle(end_r@last_r.T)[1]
        count=max(1,int(math.ceil(np.linalg.norm(end_p-last_p)/max_translation_step_m)),int(math.ceil(angle/max_rotation_step_rad)))
        for substep in range(1,count+1):
            fraction=substep/count;target_p=last_p+(end_p-last_p)*fraction;target_r=_rotation_between(last_r,end_r,fraction)
            lo=np.maximum(physical_lo,previous-max_joint_step_rad);hi=np.minimum(physical_hi,previous+max_joint_step_rad)
            start=np.clip(previous,lo+1e-9,hi-1e-9)
            def residual(delta):
                if deadline is not None and time.monotonic()>=deadline:raise _CPUPathBudgetExpired()
                p,r=forward_at_delta(p0,r0,jac,delta);axis,angle=_axis_angle(target_r@r.T)
                return np.r_[10*(p-target_p),axis*angle,.001*(delta-previous)]
            try:fit=least_squares(residual,start,bounds=(lo,hi),max_nfev=max_nfev,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            except _CPUPathBudgetExpired:return budget_expired()
            p,r=forward_at_delta(p0,r0,jac,fit.x);joint=q0+fit.x
            pos_error=float(np.linalg.norm(p-target_p));rot_error=float(_axis_angle(target_r@r.T)[1])
            margin=float(np.min(np.minimum(joint-bounds[:,0],bounds[:,1]-joint)))
            step=float(np.max(np.abs(fit.x-previous)))
            reachable=pos_error<position_tolerance_m and rot_error<orientation_tolerance_rad
            continuous=step<=max_joint_step_rad+1e-8
            accepted=reachable and continuous and margin>=minimum_joint_margin_rad
            row=dict(waypoint_index=waypoint,substep_index=substep,substep_count=count,target_position=target_p.tolist(),
                target_rotation=target_r.tolist(),candidate_joints_rad=joint.tolist(),position_error_m=pos_error,
                orientation_error_rad=rot_error,minimum_joint_margin_rad=margin,maximum_joint_step_rad=step,
                joint_distance_from_initial_rad=float(np.linalg.norm(fit.x)),kinematically_reachable=reachable,
                joint_path_continuous=continuous,feasible=accepted,nfev=int(fit.nfev))
            rows.append(row)
            if not accepted:
                result['feasible']=False;result['first_failure']=len(rows)-1
                row['reason']='pose_error_with_local_joint_step_bound'if not reachable else'joint_margin'if margin<minimum_joint_margin_rad else'joint_step'
                return result
            previous=fit.x.copy()
        last_p=end_p.copy();last_r=end_r.copy()
    return result


def inspect_local_pose_path(author, controller, side, poses, **kwargs):
    """Capture actual native geometry, then run the read-only path screen."""
    from .execution_design_jacobian_reference import capture
    measured=capture(author,controller,side)
    return solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],
        measured['q'],measured['limits'],poses,**kwargs)
