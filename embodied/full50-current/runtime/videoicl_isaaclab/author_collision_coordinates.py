"""Opt-in numerical reexpression of unchanged source collision geometry."""
import hashlib
import numpy as np


def prepare(stage,prefix,reference,factor):
    from pxr import Usd,UsdGeom,UsdPhysics,Gf,Vt
    from .source_assets import configure_source_collisions
    source=Usd.Stage.Open(str(reference));source.SetEditTarget(source.GetSessionLayer())
    default=source.GetDefaultPrim()
    if not default:raise ValueError('Coordinate conditioning requires a source default prim')
    selected=configure_source_collisions(list(source.Traverse()),reference)
    selected_paths={p.GetPath() for p in selected};collision=[p for p in source.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI)]
    result=[]
    for prim in source.Traverse():
        if not prim.IsA(UsdGeom.Mesh):continue
        ancestors=[p for p in collision if prim.GetPath().HasPrefix(p.GetPath())]
        if not ancestors or not all(UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get() for p in ancestors):continue
        if not any(p.GetPath() in selected_paths for p in ancestors):continue
        if not prim.HasAPI(UsdPhysics.MeshCollisionAPI):continue
        approximation=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()
        if approximation not in ('convexHull','convexDecomposition'):continue
        xform=UsdGeom.Xformable(prim)
        if xform.GetResetXformStack() or any(p.IsA(UsdGeom.Gprim) for p in Usd.PrimRange(prim) if p!=prim):
            raise ValueError('Conditioning requires a leaf collision mesh without a reset stack')
        mesh=UsdGeom.Mesh(prim);points=np.asarray(mesh.GetPointsAttr().Get(),float)
        relative=str(prim.GetPath().MakeRelativePath(default.GetPath()))
        path=prefix+('/'+relative if relative!='.' else '')
        target=UsdGeom.Mesh(stage.OverridePrim(path));transformed=(points*factor).astype('float32')
        target.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(transformed))
        extent=mesh.GetExtentAttr().Get()
        if extent is not None:
            target.CreateExtentAttr(Vt.Vec3fArray.FromNumpy((np.asarray(extent,float)*factor).astype('float32')))
        target_xform=UsdGeom.Xformable(target)
        operation=target_xform.AddScaleOp(UsdGeom.XformOp.PrecisionDouble,'private_collision_coordinates')
        operation.Set(Gf.Vec3d(1/factor))
        original_order=list(xform.GetXformOpOrderAttr().Get() or [])
        target_xform.GetXformOpOrderAttr().Set(Vt.TokenArray(original_order+[operation.GetOpName()]))
        result.append(dict(path=path,points=points,
            counts=np.asarray(mesh.GetFaceVertexCountsAttr().Get(),int),
            indices=np.asarray(mesh.GetFaceVertexIndicesAttr().Get(),int),
            local=np.asarray(xform.GetLocalTransformation(),float),approximation=approximation))
    return result


def verify(stage,prepared,factor):
    from pxr import UsdGeom
    cache=UsdGeom.XformCache();audit=[]
    for row in prepared:
        mesh=UsdGeom.Mesh(stage.GetPrimAtPath(row['path']));points=np.asarray(mesh.GetPointsAttr().Get(),float)
        matrix=np.asarray(cache.GetLocalToWorldTransform(mesh.GetPrim()),float)
        parent=np.asarray(cache.GetLocalToWorldTransform(mesh.GetPrim().GetParent()),float)
        expected_matrix=row['local']@parent
        actual=points@matrix[:3,:3]+matrix[3,:3]
        expected=row['points']@expected_matrix[:3,:3]+expected_matrix[3,:3]
        error=float(np.linalg.norm(actual-expected,axis=1).max())
        if error>1e-7:raise ValueError('Collision world geometry changed by more than 0.1 micrometre')
        if (not np.array_equal(row['counts'],np.asarray(mesh.GetFaceVertexCountsAttr().Get(),int))
                or not np.array_equal(row['indices'],np.asarray(mesh.GetFaceVertexIndicesAttr().Get(),int))):
            raise ValueError('Source collision topology changed')
        audit.append(dict(path=row['path'],world_vertex_max_error_m=error,vertices=len(points),
            uniform_coordinate_factor=factor,inverse_mesh_scale=1/factor,
            original_approximation=row['approximation'],source_topology_unchanged=True,
            source_points_sha256=hashlib.sha256(row['points'].tobytes()).hexdigest(),
            original_file_modified=False,body_pose_written=False))
    return audit
