"""Reject-only E15 winding check from one measured native kinematic model."""
import json
import math
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from .execution_design_drawer_ik_probe import forward_at_delta


def _diagnostic_json(value):
    """Preserve measured numeric values in the private read-only receipt."""
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError('Unsupported kinematic diagnostic value: '+type(value).__name__)


def solve_path(measured,targets):
    p0=np.asarray(measured['position'],float);r0=np.asarray(measured['rotation_task'],float)
    jac=np.asarray(measured['jacobian'],float);q=np.asarray(measured['q'],float)
    limits=np.asarray(measured['limits'],float)
    if (jac.shape!=(6,7)or q.shape!=(7,)or limits.shape!=(7,2)
            or not all(np.isfinite(x).all()for x in (p0,r0,jac,q,limits))
            or not np.allclose(np.linalg.norm(jac[3:],axis=0),1,atol=.002)):
        raise ValueError('Complete measured native E15 kinematics required')
    # Search only candidates that can satisfy the unchanged 20mrad rejection
    # gate. Keep the measured q intact; an out-of-margin start is rejected.
    lower=limits[:,0]-q+.0201;upper=limits[:,1]-q-.0201
    if np.any(lower>=0)or np.any(upper<=0):
        raise ValueError('Actual E15 joints at limit or within 20.1mrad optimizer margin; measured q not clipped')
    previous=np.zeros(7);old_p=p0;old_r=r0;rows=[]
    for index,target in enumerate(targets):
        goal_p=np.asarray(target['position'],float);goal_r=np.asarray(target['rotation'],float)
        rotvec=Rotation.from_matrix(goal_r@old_r.T).as_rotvec()
        count=max(1,math.ceil(np.linalg.norm(goal_p-old_p)/.01),math.ceil(np.linalg.norm(rotvec)/math.radians(5)))
        smallest=float('inf');largest=0.;valid=True;last=None
        for sample in range(1,count+1):
            fraction=sample/count;desired_p=old_p+(goal_p-old_p)*fraction
            desired_r=Rotation.from_rotvec(rotvec*fraction).as_matrix()@old_r
            def residual(delta):
                p,r=forward_at_delta(p0,r0,jac,delta)
                # Seven joints leave one null direction. Unregularized least
                # squares can jump along it at a singularity despite tiny TCP
                # motion. Prefer the preceding solution; independently retain
                # all original task-error, margin and increment rejection gates.
                return np.r_[10*(p-desired_p),Rotation.from_matrix(desired_r@r.T).as_rotvec(),
                             .01*(delta-previous)]
            result=least_squares(residual,previous,bounds=(lower,upper),max_nfev=180,
                                 ftol=1e-9,xtol=1e-9,gtol=1e-9)
            p,r=forward_at_delta(p0,r0,jac,result.x)
            position_error=float(np.linalg.norm(p-desired_p))
            angle_error=float(np.linalg.norm(Rotation.from_matrix(desired_r@r.T).as_rotvec()))
            margin=float(np.min(np.minimum(q+result.x-limits[:,0],limits[:,1]-q-result.x)))
            increment=float(np.linalg.norm(result.x-previous))
            smallest=min(smallest,margin);largest=max(largest,increment)
            last=dict(position_error_m=position_error,orientation_error_rad=angle_error,
                      candidate_joints_rad=(q+result.x).tolist(),sample=sample,sample_count=count)
            valid=position_error<.001 and angle_error<math.radians(1.5)and margin>.02 and increment<.35
            if not valid:break
            previous=result.x
        rows.append(dict(index=index,target_position=goal_p.tolist(),target_rotation=goal_r.tolist(),
            kinematically_reachable=valid,minimum_joint_margin_rad=smallest,
            maximum_nearby_joint_increment_rad=largest,
            joint_distance_rad=float(np.linalg.norm(np.asarray(last['candidate_joints_rad'])-q)),**last))
        if not valid:break
        old_p=goal_p;old_r=goal_r
    return rows


def inspect_path(author,controller,side,targets):
    from .execution_design_jacobian_reference import capture
    measured=capture(author,controller,side)
    rows=solve_path(measured,targets)
    record=dict(schema='e15-measured-continuous-winding-v1',side=side,step=controller.steps,
                measured=measured,targets=targets,candidates=rows,
                collision_verified=False,actuation_performed=False)
    with(author.out/'e15-continuous-winding.private.jsonl').open('a')as stream:
        stream.write(json.dumps(record,default=_diagnostic_json)+'\n')
    return rows
