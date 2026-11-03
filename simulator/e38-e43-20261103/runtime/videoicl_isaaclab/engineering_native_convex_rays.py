"""Read an existing single native convex collider without cooking/world writes.

Every reconstructed plane comes from a native hit point and native hit normal.
Independent toe/pad rays must agree before these vertices can guide a grasp.
"""
import math
import numpy as np
from scipy.optimize import linprog
from scipy.spatial import ConvexHull,HalfspaceIntersection


def unique_planes(samples):
    planes=[]
    for point,normal in samples:
        n=np.asarray(normal,float);n/=np.linalg.norm(n);d=-float(n@point)
        if any(np.linalg.norm(n-p[:3])<2e-5 and abs(d-p[3])<2e-6 for p in planes):continue
        planes.append(np.r_[n,d])
    return np.asarray(planes)


def convex_from_native_planes(samples):
    planes=unique_planes(samples)
    if len(planes)<4:raise ValueError('Too few distinct native convex planes')
    result=linprog([0.,0.,0.,-1.],A_ub=np.c_[planes[:,:3],np.ones(len(planes))],b_ub=-planes[:,3],bounds=[(None,None)]*3+[(0.,None)],method='highs')
    if not result.success or result.x[3]<1e-6:raise ValueError('Native planes lack a bounded three-dimensional interior')
    points=HalfspaceIntersection(planes,result.x[:3]).intersections
    if len(points)<4 or not np.isfinite(points).all():raise ValueError('Native planes do not form a finite hull')
    return points,planes


def line_entry(points,origin,direction):
    planes=ConvexHull(points).equations;tmin=0.;tmax=float('inf')
    for plane in planes:
        den=float(plane[:3]@direction);num=-float(plane[:3]@origin+plane[3])
        if abs(den)<1e-12:
            if num<0:return None
        elif den>0:tmax=min(tmax,num/den)
        else:tmin=max(tmin,num/den)
    return None if tmin>tmax else np.asarray(origin)+np.asarray(direction)*tmin


def reconstruct(scene,body,source_points,candidate_meshes):
    import carb,omni.physx
    from pxr import PhysicsSchemaTools
    from .source_reviewed_collisions import ray_hit_value
    points=np.asarray(source_points,float);center=points.mean(0);extent=np.ptp(points,axis=0);radius=float(np.linalg.norm(extent)+.01)
    query=omni.physx.get_physx_scene_query_interface();samples=[];raw=[]
    def cast(origin,direction,length):
        direction=np.asarray(direction,float);direction/=np.linalg.norm(direction);hits=[]
        def receive(hit):
            path=ray_hit_value(hit,'rigidBody','rigid_body');path=str(path if isinstance(path,str)else PhysicsSchemaTools.intToSdfPath(path))
            if path==body:
                point=scene.world_to_task(np.asarray(ray_hit_value(hit,'position'),float));normal=np.asarray(scene.layout.task_rotation).T@np.asarray(ray_hit_value(hit,'normal'),float)
                hits.append((point,normal))
            return True
        world=scene.task_to_world(origin);wd=np.asarray(scene.layout.task_rotation)@direction
        query.raycast_all(carb.Float3(*map(float,world)),carb.Float3(*map(float,wd)),float(length),receive)
        return min(hits,key=lambda h:float((h[0]-origin)@direction))if hits else None
    def collect(origin,direction,length):
        hit=cast(origin,direction,length)
        if hit is not None:samples.append(hit);raw.append(dict(point_task=hit[0].tolist(),normal_task=hit[1].tolist()))
    # Copy no collision parameters. Rays observe the already existing body.
    for mesh in [points,*candidate_meshes]:
        hull=ConvexHull(mesh)
        for triangle,plane in zip(hull.simplices,hull.equations):
            site=np.asarray(mesh)[triangle].mean(0);normal=plane[:3]
            collect(site+normal*radius,-normal,2*radius)
    for i in range(96):
        z=1-2*(i+.5)/96;phi=i*math.pi*(3-math.sqrt(5));d=np.array([math.sqrt(1-z*z)*math.cos(phi),math.sqrt(1-z*z)*math.sin(phi),z])
        collect(center+d*radius,-d,2*radius)
    actual,planes=convex_from_native_planes(samples)
    # Hold out a task-Z toe grid and side-axis pad rays. These samples do not
    # participate in reconstruction and must agree to 20 micrometres.
    checks=[];lo=points.min(0);hi=points.max(0)
    sites=[]
    for fx in(.2,.5,.8):
        for fy in(.15,.35,.5,.65,.85):
            p=center.copy();p[:2]=lo[:2]+[fx,fy]*(hi-lo)[:2];sites.append((p,2))
    for fx in(.25,.5,.75):
        for fz in(.003,.006,.012,.025,.05,.15,.4):
            p=center.copy();p[0]=lo[0]+fx*(hi[0]-lo[0]);p[2]=lo[2]+fz*(hi[2]-lo[2]);sites.append((p,1))
    for site,axis in sites:
        for sign in(-1.,1.):
            direction=np.eye(3)[axis]*sign;origin=site-direction*radius
            expected=line_entry(actual,origin,direction);hit=cast(origin,direction,2*radius)
            error=None if expected is None or hit is None else float(np.linalg.norm(hit[0]-expected))
            # A matched miss is also useful evidence for the empty toe corners.
            agreement=bool(expected is None and hit is None)or(error is not None and error<.00002)
            critical=bool((axis==2 and sign>0)or(axis==1 and site[2]<=lo[2]+.001))
            checks.append(dict(axis=axis,sign=sign,site_task=site.tolist(),expected_task=None if expected is None else expected.tolist(),native_task=None if hit is None else hit[0].tolist(),error_m=error,agrees=agreement,critical_toe_side_band=critical))
    errors=[r['error_m']for r in checks if r['error_m']is not None]
    key=[r for r in checks if r['critical_toe_side_band']]
    key_errors=[r['error_m']for r in key if r['error_m']is not None]
    passed=bool(key_errors)and all(r['agrees']for r in key)
    return actual,dict(origin='native_raycast_single_convex_planes',body=body,source_vertices=len(points),native_planes=len(planes),reconstructed_vertices=len(actual),native_hits=raw,planes_task=planes.tolist(),holdout_toe_pad_rays=checks,maximum_holdout_error_m=max(errors,default=None),maximum_critical_band_error_m=max(key_errors,default=None),passed=passed,validation_scope='toe_floor_and_low_one_mm_side_band; other facets diagnostic',live_stage_modified=False,live_physics_advanced=False)
