"""Read-only references to upstream USD assets, normalized at an instance wrapper.

No primitive fallback: missing files, articulation assets, absent collisions or
unreviewed asset records fail explicitly. Original meshes/materials/collisions
remain referenced, and every runtime instance records its source hash.
"""
from pathlib import Path
import hashlib
import json
import os


def resolve_asset(record):
    root = os.environ.get(record.get('root_env', 'VIC_REALWORLD_ASSETS'))
    relative = Path(record['relative_path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Asset path must remain relative to its configured root')
    if not root:
        raise ValueError('Set asset root ' + record.get('root_env', 'VIC_REALWORLD_ASSETS'))
    root = Path(root).expanduser().resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError(path)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not record.get('sha256') or actual != record['sha256']:
        raise ValueError('Upstream asset hash mismatch: ' + str(path))
    for dependency in record.get('dependencies', []):
        member = Path(dependency['relative_path'])
        candidate = (root / member).resolve()
        if member.is_absolute() or '..' in member.parts or not candidate.is_relative_to(root):
            raise ValueError('Asset dependency escapes configured root')
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != dependency['sha256']:
            raise ValueError('Asset dependency missing or hash mismatch: ' + str(candidate))
    return path


def resolve_source_reference(record):
    """Resolve an explicit, pinned USD-version compatibility derivative.

    The original source and all its dependencies are always verified first.
    An opt-in manifest may select a separately hashed same-root derivative;
    absent mappings keep the original source. No unverified fallback occurs.
    """
    original=resolve_asset(record)
    manifest_path=os.environ.get('VIC_SOURCE_COMPATIBILITY_MANIFEST')
    if not manifest_path:return original,original
    manifest_bytes=Path(manifest_path).read_bytes()
    expected=os.environ.get('VIC_SOURCE_COMPATIBILITY_MANIFEST_SHA256')
    if not expected or hashlib.sha256(manifest_bytes).hexdigest()!=expected:
        raise ValueError('Source compatibility manifest hash mismatch or absent pin')
    manifest=json.loads(manifest_bytes)
    if manifest.get('schema')!='videoicl-source-compatibility-v1':
        raise ValueError('Unknown source compatibility manifest schema')
    entry=manifest.get('assets',{}).get(record['sha256'])
    if entry is None:return original,original
    root_env=record.get('root_env','VIC_REALWORLD_ASSETS')
    if (entry.get('source_relative_path')!=record['relative_path']
            or entry.get('source_root_env')!=root_env):
        raise ValueError('Source compatibility mapping identity mismatch')
    runtime=dict(entry['runtime'])
    if runtime.get('root_env',root_env)!=root_env:
        raise ValueError('Source compatibility derivative must use original asset root')
    runtime['root_env']=root_env
    return original,resolve_asset(runtime)


def configure_source_collisions(prims, asset_path='upstream asset'):
    """Keep published enabled shapes; never activate a disabled source shape.

    A CollisionAPI on an Xform may cover real child geometry. Preserve enabled
    collision ancestors needed by a selected child, and let an explicitly
    disabled child (or ancestor) continue to exclude that subtree.
    """
    from pxr import UsdGeom, UsdPhysics

    prims = list(prims)
    collisions = [p for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)]
    enabled = {p.GetPath(): bool(UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get())
               for p in collisions}

    def ancestors(prim):
        return [p for p in collisions if prim.GetPath().HasPrefix(p.GetPath())]

    active = [p for p in collisions if all(enabled[a.GetPath()] for a in ancestors(p))]
    dedicated = [p for p in active if 'collision' in str(p.GetPath()).lower()]
    selected = dedicated or active
    # Disabling a non-dedicated parent must not suppress a selected child.
    selected_paths = {a.GetPath() for p in selected for a in ancestors(p)}
    selected = [p for p in active if p.GetPath() in selected_paths]
    has_shape = any(
        prim.IsA(UsdGeom.Gprim)
        and any(a.GetPath() in selected_paths for a in ancestors(prim))
        and all(enabled[a.GetPath()] for a in ancestors(prim))
        for prim in prims)
    if not has_shape:
        raise ValueError('Upstream asset has no enabled collision geometry: ' + str(asset_path))
    for prim in collisions:
        UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr(prim.GetPath() in selected_paths)
    return selected


def spawn_source_asset(stage, prim_path, obj, translation, orientation):
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Gf, Sdf
    import numpy as np
    from .scene import transform, material, enable_continuous_prop_contacts
    record = obj['source_asset']
    source_path,path = resolve_source_reference(record)
    coordinate_factor=obj.get('reviewed_collision_settings',{}).get('coordinate_factor') or os.environ.get('VIC_SOURCE_COLLISION_COORDINATE_FACTOR') or None
    if os.environ.get('VIC_SOURCE_COLLISION_THIN_ONLY')=='1' and min(obj['size'])>=.02:
        coordinate_factor=None
    prepared_coordinates=[]
    if coordinate_factor is not None:
        coordinate_factor=float(coordinate_factor)
        if coordinate_factor not in (100.,1000.):raise ValueError('Unsupported private collision coordinate factor')
        from .author_collision_coordinates import prepare
        prepared_coordinates=prepare(stage,prim_path+'/Model/SourceFrame/Asset',path,coordinate_factor)
    root = UsdGeom.Xform.Define(stage, prim_path).GetPrim()
    transform(root, translation, orientation)
    wrapper = UsdGeom.Xform.Define(stage, prim_path + '/Model').GetPrim()
    frame = UsdGeom.Xform.Define(stage, prim_path + '/Model/SourceFrame').GetPrim()
    transform(frame, quaternion=record.get('source_rotation', (1,0,0,0)))
    source = stage.DefinePrim(prim_path + '/Model/SourceFrame/Asset')
    if not source.GetReferences().AddReference(str(path)):
        raise RuntimeError('Cannot reference upstream USD: ' + str(path))
    prims = list(Usd.PrimRange(source))
    if any(p.HasAPI(UsdPhysics.ArticulationRootAPI) or p.IsA(UsdPhysics.Joint) for p in prims):
        raise ValueError('Articulated asset requires its own joint adapter: ' + str(path))
    if any(p.IsInstance() for p in prims):
        raise ValueError('Instanceable object requires an explicit editable conversion: ' + str(path))
    # Measure before attaching the instance to the world pose. BBoxCache's
    # world-axis intermediate bounds can inflate after inverse-transforming a
    # rotated ancestor (e.g. the shoe at yaw .7). The asset's authored source
    # rotation still applies, but robot layout and object yaw must not affect
    # its intrinsic size or centering.
    measuring = Usd.Stage.CreateInMemory()
    measure_root = UsdGeom.Xform.Define(measuring, '/Measure').GetPrim()
    measure_frame = UsdGeom.Xform.Define(measuring, '/Measure/Frame').GetPrim()
    transform(measure_frame, quaternion=record.get('source_rotation', (1,0,0,0)))
    measuring.DefinePrim('/Measure/Frame/Asset').GetReferences().AddReference(str(path))
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render], useExtentsHint=False)
    # Mesh bounds must use transformed vertices, rather than rotating the
    # mesh's axis-aligned extent. The latter inflates thin oblique assets such
    # as the YCB spoon even in an otherwise isolated stage.
    xforms=UsdGeom.XformCache(Usd.TimeCode.Default())
    minima=[];maxima=[]
    for prim in measuring.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        imageable=UsdGeom.Imageable(prim)
        if imageable.ComputeVisibility()==UsdGeom.Tokens.invisible or imageable.ComputePurpose() not in (UsdGeom.Tokens.default_,UsdGeom.Tokens.render):
            continue
        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),dtype=float)
        if points.size==0:
            continue
        matrix=np.asarray(xforms.GetLocalToWorldTransform(prim),dtype=float)
        transformed=points@matrix[:3,:3]+matrix[3,:3]
        minima.append(transformed.min(axis=0));maxima.append(transformed.max(axis=0))
    if minima:
        low,high=np.min(minima,axis=0),np.max(maxima,axis=0)
    else:
        bounds=cache.ComputeLocalBound(measure_root).ComputeAlignedRange()
        low,high=np.array(bounds.GetMin()),np.array(bounds.GetMax())
    extent = high - low
    if not np.isfinite(extent).all() or np.any(extent <= 0):
        raise ValueError('Invalid source asset bounds: ' + str(path))
    size = np.array(obj['size']) * 2
    scale = size / extent
    # Asset-specific resizing is explicit in the contract, never rule dependent.
    if not record.get('allow_nonuniform_scale', False) and not np.allclose(scale, scale[0], rtol=.01):
        raise ValueError(f'Nonuniform resize needs an explicit asset adaptation record: {path}; native_extent={extent.tolist()}; requested_size={size.tolist()}; scale={scale.tolist()}')
    transform(wrapper, -(low + high) * .5 * scale, scale=scale)
    # Retain the published collision geometry. Several source packages also
    # enable collision on the textured visual duplicate: opt out explicitly.
    selected = configure_source_collisions(prims, path)
    if obj.get('reviewed_e10_extruded_collision'):
        from .execution_design_e10_collision import install
        selected=install(stage,obj,selected)
    reviewed=obj.get('reviewed_collision_settings')
    if reviewed:
        if reviewed.get('source_sha256')!=record['sha256']:
            raise ValueError('Reviewed collision settings need exact source identity')
        mode=reviewed.get('approximation','convexHull')
        if mode=='sourceConvexPartition':
            from .execution_design_e46_partition import install
            selected,audit=install(stage,root,obj,selected)
            root.SetCustomDataByKey('videoicl:reviewed_collision_fidelity',json.dumps(audit))
        elif mode=='analyticSphere':
            from .source_reviewed_collisions import analytic_source_sphere
            selected,audit=analytic_source_sphere(stage,root,obj,selected,low,high,scale)
            root.SetCustomDataByKey('videoicl:reviewed_collision_fidelity',json.dumps(audit))
        elif mode=='sdf':
            resolution=reviewed.get('sdf_resolution',256)
            if type(resolution)is not int or not 64<=resolution<=512:
                raise ValueError('Invalid reviewed source SDF resolution')
            changes=[]
            for prim in selected:
                if not prim.IsA(UsdGeom.Mesh):continue
                collision=UsdPhysics.MeshCollisionAPI.Apply(prim)
                old=collision.GetApproximationAttr().Get()
                collision.CreateApproximationAttr('sdf')
                PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(prim).CreateSdfResolutionAttr(resolution)
                changes.append(dict(path=str(prim.GetPath()),original_approximation=old,
                    reviewed_approximation='sdf',resolution=resolution,
                    original_source_vertices_and_topology_preserved=True))
            if not changes:raise ValueError('No source collision meshes for reviewed SDF')
            root.SetCustomDataByKey('videoicl:reviewed_collision_fidelity',json.dumps(changes))
        elif mode!='convexHull':raise ValueError('Unknown reviewed source collision representation')
    if reviewed and reviewed.get('approximation','convexHull')=='convexHull':
        limit=reviewed.get('hull_vertex_limit',255)
        if type(limit)is not int or not 32<=limit<=255:raise ValueError('Invalid reviewed convex fidelity limit')
        changes=[]
        for prim in selected:
            if not prim.IsA(UsdGeom.Mesh):continue
            collision=UsdPhysics.MeshCollisionAPI.Apply(prim)
            old=collision.GetApproximationAttr().Get()
            approximation=reviewed.get('approximation',old)
            if approximation!='convexHull':raise ValueError('Reviewed fidelity adapter currently supports source convex hulls only')
            collision.CreateApproximationAttr(approximation)
            hull_api=PhysxSchema.PhysxConvexHullCollisionAPI.Apply(prim)
            hull_api.CreateHullVertexLimitAttr(limit)
            if 'min_thickness_m'in reviewed:
                minimum=float(reviewed['min_thickness_m'])
                if not 0<minimum<=min(float(x)*2 for x in obj['size'])*.1+1e-12:
                    raise ValueError('Reviewed convex minimum must preserve the declared thin geometry')
                hull_api.CreateMinThicknessAttr(minimum)
            changes.append(dict(path=str(prim.GetPath()),original_approximation=old,
                reviewed_approximation=approximation,hull_vertex_limit=limit,
                **({'min_thickness_m':minimum}if 'min_thickness_m'in reviewed else{}),
                original_source_vertices_and_topology_preserved=True))
        if not changes:raise ValueError('No source collision meshes for reviewed fidelity adapter')
        root.SetCustomDataByKey('videoicl:reviewed_collision_fidelity',json.dumps(changes))
    for prim in prims:
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
        if prim.HasAPI(PhysxSchema.PhysxRigidBodyAPI):
            prim.RemoveAPI(PhysxSchema.PhysxRigidBodyAPI)
        if prim.HasAPI(UsdPhysics.MassAPI):
            prim.RemoveAPI(UsdPhysics.MassAPI)
    for prim in selected:
        api = PhysxSchema.PhysxCollisionAPI.Apply(prim)
        contact_offset=float(obj.get('contact_offset',.0005));rest_offset=float(obj.get('rest_offset',0.))
        if not 0<=rest_offset<contact_offset<=.01:
            raise ValueError('Invalid reviewed collision offsets')
        api.CreateContactOffsetAttr(contact_offset)
        api.CreateRestOffsetAttr(rest_offset)
    if prepared_coordinates:
        from .author_collision_coordinates import verify
        coordinate_audit=verify(stage,prepared_coordinates,coordinate_factor)
        root.SetCustomDataByKey('videoicl:collision_coordinates',json.dumps(coordinate_audit))
    physical = UsdShade.Material.Define(stage, prim_path + '/Friction')
    mat = UsdPhysics.MaterialAPI.Apply(physical.GetPrim())
    mat.CreateStaticFrictionAttr(float(obj.get('static_friction', .8)))
    mat.CreateDynamicFrictionAttr(float(obj.get('dynamic_friction', .6)))
    mat.CreateRestitutionAttr(float(obj.get('restitution', 0.)))
    for prim in selected:
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(physical, UsdShade.Tokens.strongerThanDescendants, 'physics')
    if obj.get('recolor'):
        color = material(stage, prim_path + '/Recolor', obj['rgba'][:3])
        for prim in prims:
            if prim.IsA(UsdGeom.Mesh):
                UsdShade.MaterialBindingAPI.Apply(prim).Bind(color, UsdShade.Tokens.strongerThanDescendants)
    UsdPhysics.RigidBodyAPI.Apply(root)
    UsdPhysics.MassAPI.Apply(root).CreateMassAttr(float(obj.get('mass', .05)))
    if obj.get('reviewed_collision_settings',{}).get('preserve_native_mass_properties'):
        from .execution_design_e45_balls import BASELINE_ARTIFACT_SHA as e45_mass_sha
        if obj['reviewed_collision_settings'].get('approximation')=='sourceConvexPartition':
            from .execution_design_e46_partition import bind_mass as apply_source_mass_binding
        elif obj['reviewed_collision_settings'].get('native_mass_baseline_sha256')==e45_mass_sha:
            from .execution_design_e45_balls import apply_source_mass_binding
        else:
            from .execution_design_e43_ball import apply_source_mass_binding
        apply_source_mass_binding(root,obj)
    PhysxSchema.PhysxContactReportAPI.Apply(root).CreateThresholdAttr(0.)
    rigid = PhysxSchema.PhysxRigidBodyAPI.Apply(root)
    rigid.CreateEnableCCDAttr(True)
    rigid.CreateSolverPositionIterationCountAttr(16)
    rigid.CreateSolverVelocityIterationCountAttr(4)
    rigid.CreateMaxDepenetrationVelocityAttr(1.)
    # PhysX 4.5 clears force reports once a body sleeps. These actors take
    # part in continuous support/contact scoring, so keep their real contact
    # constraints active instead of inferring support from a stale pose.
    rigid.CreateSleepThresholdAttr(0.)
    if obj.get('disable_gravity'):
        rigid.CreateDisableGravityAttr(True)
    enable_continuous_prop_contacts(root)
    root.CreateAttribute('realworld:sourceSha256', Sdf.ValueTypeNames.String).Set(record['sha256'])
    root.CreateAttribute('realworld:sourcePath', Sdf.ValueTypeNames.String).Set(str(source_path))
    root.CreateAttribute('realworld:runtimeSourceSha256', Sdf.ValueTypeNames.String).Set(hashlib.sha256(path.read_bytes()).hexdigest())
    root.CreateAttribute('realworld:runtimeSourcePath', Sdf.ValueTypeNames.String).Set(str(path))
    return root
