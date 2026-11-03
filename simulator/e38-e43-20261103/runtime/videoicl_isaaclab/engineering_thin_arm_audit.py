"""Zero-public-action source-mesh arm interference and full-palm readback."""
import json,math
import numpy as np
from scipy.spatial import ConvexHull
from scipy.optimize import linprog


def audit(author):
    from .execution_design_e33_grasp import actual_mesh
    from isaaclab.utils.math import matrix_from_quat
    meshes={};missing=[];poses={};down=np.diag([1.,-1.,-1.])
    for side,robot in author.scene.robots.items():
        actual=author.tcp_rotation_task(side)
        base=matrix_from_quat(robot.data.root_quat_w)[0].cpu().numpy()
        target=np.asarray(author.scene.layout.task_rotation).T@base@matrix_from_quat(author.c.targets[side][1])[0].cpu().numpy()
        poses[side]=dict(actual_tcp_task=author.tip(side).tolist(),actual_rotation=actual.tolist(),retained_rotation=target.tolist(),
            actual_retained_error_deg=math.degrees(math.acos(float(np.clip((np.trace(target@actual.T)-1)/2,-1,1)))),
            actual_full_down_error_deg=math.degrees(math.acos(float(np.clip((np.trace(down@actual.T)-1)/2,-1,1)))))
        meshes[side]={}
        for body in robot.body_names:
            try:points=actual_mesh(author,side,body)
            except ValueError as exc:missing.append(dict(side=side,body=body,error=str(exc)));continue
            meshes[side][body]=points
    candidates=[]
    for left,a in meshes['left'].items():
        for right,b in meshes['right'].items():
            if np.any(a.max(0)<b.min(0))or np.any(b.max(0)<a.min(0)):continue
            try:
                planes=np.vstack((ConvexHull(a).equations,ConvexHull(b).equations))
                r=linprog([0,0,0,-1],A_ub=np.column_stack((planes[:,:3],np.linalg.norm(planes[:,:3],axis=1))),b_ub=-planes[:,3],bounds=[(None,None)]*3+[(0,None)],method='highs')
                if r.success and r.x[3]>1e-7:candidates.append(dict(left=left,right=right,inscribed_overlap_radius_m=float(r.x[3]),point_task=r.x[:3].tolist(),source_convex_candidate_only=True))
            except Exception as exc:candidates.append(dict(left=left,right=right,error=type(exc).__name__+': '+str(exc)))
    result=dict(public_actions=author.c.steps,measurement_only=True,native_contact_claimed=False,
        full_palm_poses=poses,source_convex_interference_candidates=candidates,missing_meshes=missing,
        source_meshes_task={s:{n:p.tolist()for n,p in bodies.items()}for s,bodies in meshes.items()})
    (author.out/'thin-arm-geometry-audit.private.json').write_text(json.dumps(result,indent=2))
    return result
