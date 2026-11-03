"""E12 release: actual static triangle holes, never a filled mesh hull."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def convex_intersects_triangle(points,triangle):
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    points,triangle=np.asarray(points,float),np.asarray(triangle,float)
    if np.any(points.max(0)<triangle.min(0))or np.any(triangle.max(0)<points.min(0)):return False
    if np.linalg.norm(np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]))<1e-15:return False
    hull=ConvexHull(points,qhull_options='QJ')
    result=linprog(np.zeros(3),A_ub=hull.equations[:,:3]@triangle.T,
        b_ub=-hull.equations[:,3],A_eq=np.ones((1,3)),b_eq=[1.],
        bounds=[(0.,None)]*3,method='highs',
        options={'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9})
    if result.status not in(0,2):raise ToolExecutionError('E12 exact triangle separation unresolved')
    return bool(result.success)


def strip_collision_triangles(policy):
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    asset=policy.objects['strip'].get('mechanical_asset',{})
    if asset.get('sha256')!='3cd55cf1af39e00a5aec431420010c83841273e4d0967dbd117b15d21e00d18c':
        raise ToolExecutionError('E12 original triangle-hole strip source required')
    local=getattr(policy.a,'_e12_original_strip_triangles',None)
    if local is None:
        stage=omni.usd.get_context().get_stage();body=stage.GetPrimAtPath(policy.a.scene.root_path+'/Props/strip')
        transforms=UsdGeom.XformCache();inverse=transforms.GetLocalToWorldTransform(body).GetInverse()
        triangles=[];meshes=0
        for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
            if not prim.IsA(UsdGeom.Mesh):continue
            ancestor=prim;collidable=False;enabled=True
            while ancestor and ancestor!=body:
                if ancestor.HasAPI(UsdPhysics.CollisionAPI):
                    collidable=True;enabled=enabled and bool(UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get())
                ancestor=ancestor.GetParent()
            if not collidable or not enabled:continue
            approximation=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()
            if str(approximation)!='none':raise ToolExecutionError('E12 original static strip triangle representation changed')
            mesh=UsdGeom.Mesh(prim);matrix=np.asarray(transforms.GetLocalToWorldTransform(prim)*inverse,float)
            points=np.asarray(mesh.GetPointsAttr().Get(),float)@matrix[:3,:3]+matrix[3,:3]
            indices=np.asarray(mesh.GetFaceVertexIndicesAttr().Get(),int);offset=0
            for count in mesh.GetFaceVertexCountsAttr().Get():
                face=indices[offset:offset+count];offset+=count
                if count<3:raise ToolExecutionError('E12 invalid original collision polygon')
                for i in range(1,count-1):triangles.append(points[face[[0,i,i+1]]])
            meshes+=1
        if meshes!=9 or not triangles:raise ToolExecutionError('E12 original nine triangle collision meshes required')
        local=np.asarray(triangles);policy.a._e12_original_strip_triangles=local
    pos,r=policy.frame({'actor':'strip'})
    return local@r.T+pos


def require_actual_strip_clearance(policy,actor):
    from .execution_design_branch_geometry import collision_parts_task
    triangles=strip_collision_triangles(policy);parts=collision_parts_task(policy,actor);checked=0
    for index,points in enumerate(parts):
        points=np.asarray(points)
        mask=np.all(triangles.max(1)>=points.min(0),axis=1)&np.all(triangles.min(1)<=points.max(0),axis=1)
        for triangle in triangles[mask]:
            checked+=1
            if convex_intersects_triangle(points,triangle):
                raise ToolExecutionError('E12 actual charger part '+str(index)+' intersects an original strip triangle')
    result=dict(representation='original_static_triangle_collision_faces',
        original_meshes=9,triangle_faces=len(triangles),charger_cooked_convex_parts=len(parts),
        candidate_triangle_tests=checked,filled_convex_hole_surrogate=False)
    policy.a.control_report['e12_original_strip_release_geometry']=result
    return result
