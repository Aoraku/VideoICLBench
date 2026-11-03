"""Private E24 screens using the unchanged, enabled native collision meshes.

Triangle meshes retain separate faces. Cooked convex representations are
enclosed by their source convex envelope. A separating plane, normalized to
unit length, certifies a lower Euclidean distance bound.
"""
import numpy as np
from scipy.optimize import linprog
from .realworld_tool_expert import ToolExecutionError


def separation_certificate(a, b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    alo=a.min(0);ahi=a.max(0);blo=b.min(0);bhi=b.max(0)
    coarse=float(np.linalg.norm(np.maximum(np.maximum(alo-bhi,blo-ahi),0)))
    if coarse>.01:return coarse
    fit=linprog([0,0,0,0,-1],A_ub=np.r_[np.c_[a,-np.ones(len(a)),np.zeros(len(a))],
        np.c_[-b,np.ones(len(b)),np.ones(len(b))]],b_ub=np.zeros(len(a)+len(b)),
        bounds=[(-1,1)]*3+[(None,None)]*2,method='highs')
    if not fit.success:return coarse
    normal=fit.x[:3];length=float(np.linalg.norm(normal))
    if length<1e-8:return coarse
    return max(coarse,0.,float((np.min(b@normal)-np.max(a@normal))/length))


def actual_object_parts(policy):
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    author=policy.a;scene=author.scene
    if not hasattr(author,'_e24_object_collision_parts'):
        stage=omni.usd.get_context().get_stage();xforms=UsdGeom.XformCache();cache={}
        for name in policy.objects:
            root=stage.GetPrimAtPath(scene.root_path+'/Props/'+name)
            if not root:raise ToolExecutionError('Missing E24 native actor '+name)
            inverse=xforms.GetLocalToWorldTransform(root).GetInverse();parts=[]
            for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
                if not prim.IsA(UsdGeom.Gprim):continue
                parent=prim;enabled=False
                while parent:
                    if parent.HasAPI(UsdPhysics.CollisionAPI):
                        enabled=UsdPhysics.CollisionAPI(parent).GetCollisionEnabledAttr().Get() is not False;break
                    if parent==root:break
                    parent=parent.GetParent()
                if not enabled:continue
                if prim.IsA(UsdGeom.Cube):
                    size=float(UsdGeom.Cube(prim).GetSizeAttr().Get())
                    if not np.isfinite(size)or size<=0:
                        raise ToolExecutionError('Invalid native collision cube size')
                    points=np.asarray([[x,y,z]for x in(-.5,.5)for y in(-.5,.5)for z in(-.5,.5)])*size
                    t=np.asarray(xforms.GetLocalToWorldTransform(prim)*inverse,float)
                    parts.append(points@t[:3,:3]+t[3,:3])
                    continue
                if not prim.IsA(UsdGeom.Mesh):raise ToolExecutionError('Unreviewed E24 object collision primitive')
                mesh=UsdGeom.Mesh(prim);points=np.asarray(mesh.GetPointsAttr().Get(),float)
                t=np.asarray(xforms.GetLocalToWorldTransform(prim)*inverse,float)
                points=points@t[:3,:3]+t[3,:3]
                mode=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()
                component_envelope=(getattr(policy,'_engineering_conservative_tree_components',False)
                    and name=='tree'and policy.objects[name].get('mechanical_asset',{}).get('sha256')
                        =='131190e2d04c89da64838a7ea50f2f76172faf5e6293aa9b1e3d888f9d66ff42')
                if mode=='none'and component_envelope:
                    # Enclose each unchanged published tree component
                    # separately. A proof against this larger solid also
                    # covers all its original triangles; no container void
                    # or different component is merged into this envelope.
                    parts.append(points)
                elif mode=='none':
                    counts=mesh.GetFaceVertexCountsAttr().Get();indices=mesh.GetFaceVertexIndicesAttr().Get();offset=0
                    for count in counts:
                        if count!=3:raise ToolExecutionError('E24 triangle collision face required')
                        parts.append(points[list(indices[offset:offset+count])]);offset+=count
                elif mode in ('convexHull','convexDecomposition'):
                    # Every actual convex cook lies inside this source envelope.
                    parts.append(points)
                else:raise ToolExecutionError('Unreviewed E24 mesh collision approximation '+str(mode))
            if not parts:raise ToolExecutionError('Empty E24 native object collision geometry '+name)
            cache[name]=parts
        author._e24_object_collision_parts=cache
    state,_=policy.snapshot();result=[]
    for name,parts in author._e24_object_collision_parts.items():
        body=state[name];rotation=np.asarray(body['mat']);position=np.asarray(body['pos'])
        for i,local in enumerate(parts):
            points=local@rotation.T+position
            result.append(dict(name='object:'+name+':part'+str(i),lo=points.min(0),hi=points.max(0),points=points))
    return result
