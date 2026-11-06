"""Read the actual convex representation of enabled original source meshes."""
import numpy as np


def read_source_convex_geometry(scene,actors):
    import omni.physx,omni.usd
    from pxr import Usd,UsdGeom,UsdPhysics,PhysxSchema,PhysicsSchemaTools
    from scipy.spatial import ConvexHull
    stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache()
    cooking=omni.physx.get_physx_cooking_interface();rows=[]
    for actor in actors:
        root=stage.GetPrimAtPath('/World/Props/'+actor)
        if not root:raise ValueError('Unknown source convex diagnostic actor')
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            if not prim.IsA(UsdGeom.Mesh) or not prim.HasAPI(UsdPhysics.MeshCollisionAPI):continue
            if not prim.HasAPI(UsdPhysics.CollisionAPI) or not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():continue
            approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get())
            if approximation not in ('convexHull','convexDecomposition'):continue
            mesh=UsdGeom.Mesh(prim);source=np.asarray(mesh.GetPointsAttr().Get(),float)
            matrix=np.asarray(cache.GetLocalToWorldTransform(prim),float)
            points=source@matrix[:3,:3]+matrix[3,:3];received_rows=[]
            def received(result,meshes):
                for value in meshes:
                    verts=np.asarray(value.vertices,float)
                    received_rows.append(dict(vertices_mesh_local=verts.tolist(),
                        vertices_world_m=(verts@matrix[:3,:3]+matrix[3,:3]).tolist()))
            cooking.request_convex_collision_representation(omni.usd.get_context().get_stage_id(),
                PhysicsSchemaTools.sdfPathToInt(str(prim.GetPath())),False,received)
            if not received_rows:raise RuntimeError('No actual source convex representation: '+str(prim.GetPath()))
            actual=np.concatenate([np.asarray(r['vertices_world_m'])for r in received_rows])
            row=dict(actor=actor,path=str(prim.GetPath()),original_approximation=approximation,
                prim_type=prim.GetTypeName(),configured_hull_vertex_limit=PhysxSchema.PhysxConvexHullCollisionAPI(prim).GetHullVertexLimitAttr().Get(),
                declared_vertices_world_m=points.tolist(),declared_vertices=len(points),
                actual_meshes=received_rows,actual_vertices=len(actual),
                declared_bounds_world_m=[points.min(0).tolist(),points.max(0).tolist()],
                actual_bounds_world_m=[actual.min(0).tolist(),actual.max(0).tolist()],
                sdf_surface_claimed=False)
            try:
                hull=ConvexHull(points);cooked=ConvexHull(actual)
                row.update(actual_to_declared_convex_volume_ratio=float(cooked.volume/hull.volume),
                    max_actual_vertex_outside_declared_convex_m=float((actual@hull.equations[:,:3].T+hull.equations[:,3]).max()))
            except Exception as exc:row['convex_analysis_error']=repr(exc)
            rows.append(row)
    return rows
