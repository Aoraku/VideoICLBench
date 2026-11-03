"""Bound whole carried meshes through engineering public translation and turns."""
import numpy as np
import time


def swept_route_clear(local, position, start_rotation, poses, obstacles, floor,
                      clearance=.0005, floor_margin=.0002, deadline_monotonic=None):
    """A convex translation sweep plus rotation sagitta, with no actuation.

    Unlike a turn-only screen, this also checks the final low descent and the
    complete carried body. Callers decide which actual contact is intended;
    every supplied obstacle remains forbidden throughout the route.
    """
    from .author_orientation import _axis_angle
    from .execution_design_clip_grasp import convex_meshes_clear
    p=np.asarray(position,float);r=np.asarray(start_rotation,float)
    meshes=[np.asarray(m,float)for m in local]
    obstacles=[np.asarray(m,float)for m in obstacles]
    if (p.shape!=(3,)or r.shape!=(3,3)or not np.isfinite(p).all()
            or not np.isfinite(r).all()or not np.isfinite(floor)
            or not meshes or any(m.ndim!=2 or m.shape[1]!=3 or not np.isfinite(m).all()for m in meshes)
            or clearance<0 or floor_margin<0):
        raise ValueError('Finite measured carried meshes and public route required')
    for pose in poses:
        if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:
            raise TimeoutError('Private CPU collision proposal budget exhausted')
        end_p=np.asarray(pose.get('position',p),float);end_r=np.asarray(pose['rotation'],float)
        if end_p.shape!=(3,)or end_r.shape!=(3,3)or not np.isfinite(end_p).all()or not np.isfinite(end_r).all():
            raise ValueError('Finite public pose required')
        angle=_axis_angle(end_r@r.T)[1]
        for mesh in meshes:
            sagitta=float(np.linalg.norm(mesh,axis=1).max()*(1-np.cos(angle/2)))
            sweep=np.vstack((mesh@r.T+p,mesh@end_r.T+end_p))
            if sweep[:,2].min()-sagitta<floor+floor_margin:
                return False
            if any(not convex_meshes_clear(sweep,o,clearance=clearance+2*sagitta)for o in obstacles):
                return False
        p,r=end_p,end_r
    return True
