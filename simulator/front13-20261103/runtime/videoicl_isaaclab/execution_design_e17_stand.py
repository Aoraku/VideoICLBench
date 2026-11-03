"""Reset-only, explicitly versioned E17 two-tier stand geometry.

The 70 mm increment follows a continuous full-arm insertion/opening screen:
60 mm leaves less than 1 mm, while 65 mm clears the reviewed route by 2 mm.
The additional 5 mm is a candidate margin, pending native verification.
Source vertices remain preserved in their assets;
the generated visual and collision vertices have a separate content digest.
No live body pose, rule, or accepted action is modified by this module.
"""
import hashlib
import json
import numpy as np

VERSION = 'e17-two-tier-wrist-clearance-70mm-v2'
SOURCE_SHA = '6cd3a9ec1b8664a9bca2ed034ac49808e7fbf8b82d2482b927c4e2fa727f5186'
SOURCE_VISUAL_SHA = 'ae272179ee1f65b58ecb48604d01c0cee472a2f6f2c948d2df08a2b496825c8f'
LIFT_M = .070
ROD_TOP_M = .25200072
# Filled from the reviewed source-mesh derivation, not a launch-time fit.
GEOMETRY_SHA = '2b2d22d23fa00d50ba90af3c9562e7348e14d6073e9c89cc206f320dedc5af06'
MASS_KG = 0.46302993369100737


def transform_points(component, points):
    points = np.asarray(points, dtype=np.float32)
    if component not in range(7) or points.ndim != 2 or points.shape[1] != 3:
        raise ValueError('Unexpected E17 stand component geometry')
    if not np.isfinite(points).all():
        raise ValueError('Nonfinite E17 stand geometry')
    out = points.astype(np.float64)
    if component in (1, 2, 4, 5):
        out[:, 2] += LIFT_M
    elif component == 6:
        out[:, 2] *= (ROD_TOP_M + LIFT_M) / ROD_TOP_M
    return out.astype(np.float32)


def geometry_digest(parts):
    """Canonical little-endian float32 vertices and int32 topology by path."""
    digest = hashlib.sha256()
    for path, points, counts, indices in sorted(parts, key=lambda p:p[0]):
        digest.update(path.encode() + b'\0')
        for data, dtype in ((points, '<f4'), (counts, '<i4'), (indices, '<i4')):
            array = np.asarray(data, dtype=dtype)
            digest.update(np.asarray(array.shape, dtype='<i8').tobytes())
            digest.update(array.tobytes())
    return digest.hexdigest()


def descriptor():
    if GEOMETRY_SHA == 'PENDING':
        raise ValueError('Derived E17 stand geometry has not been reviewed')
    return dict(version=VERSION, source_asset_sha256=SOURCE_SHA,
                source_visual_sha256=SOURCE_VISUAL_SHA,
                derived_geometry_sha256=GEOMETRY_SHA,
                upper_tier_lift_m=LIFT_M, lower_geometry_unchanged=True,
                reviewed_continuous_path_minimum_lift_m=.065,
                candidate_additional_lift_margin_m=.005,
                empty_mass_estimate_kg=MASS_KG,
                mass_basis='Source 0.45kg uniform-density estimate; same density with longer solid rod',
                native_acceptance='pending')


def bind_environment_identity(design):
    """Keep semantic pairing but distinguish every old/new physical world."""
    physical=dict(version=VERSION,derived_geometry_sha256=GEOMETRY_SHA,
                  upper_tier_lift_m=LIFT_M,empty_mass_estimate_kg=MASS_KG)
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for key in ('environment_identity','assignment_identity_sha256','paired_input_identity'):
        original=design[key]
        design['source_'+key]=original
        design[key]=digest(dict(source_identity=original,physical_revision=physical))
    design['physical_configuration_sha256']=digest(physical)
    design['environment_revision_provenance']=dict(source_asset_sha256=SOURCE_SHA,**physical,
        purpose='Measured whole-palm and wrist clearance; local layer rule and score weights unchanged')


def apply_to_usd(root, obj):
    """Author only new reset-stage referenced meshes before PhysX creation."""
    from pxr import Usd, UsdGeom, Gf, Sdf
    entry = obj.get('e17_stand_geometry')
    if entry is None:
        return
    if (entry != descriptor() or obj.get('id') != 'stand'
            or not obj.get('dynamic_mechanical_asset')
            or obj.get('mechanical_asset', {}).get('sha256') != SOURCE_SHA):
        raise ValueError('Unreviewed opt-in E17 stand derivation')
    parts = []
    for prim in Usd.PrimRange(root):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        relative = str(prim.GetPath()).removeprefix(str(root.GetPath()) + '/')
        if relative.split('/')[0] not in ('Visuals', 'Collisions'):
            raise ValueError('Unknown E17 stand mesh ' + relative)
        name = prim.GetName()
        try:
            component = int(name.rsplit('_', 1)[1])
        except ValueError as exc:
            raise ValueError('Unknown E17 stand component') from exc
        mesh = UsdGeom.Mesh(prim)
        points = transform_points(component, mesh.GetPointsAttr().Get())
        counts = mesh.GetFaceVertexCountsAttr().Get()
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        parts.append((relative, points, counts, indices))
        mesh.GetPointsAttr().Set([Gf.Vec3f(*map(float, p)) for p in points])
        mesh.CreateExtentAttr().Set([Gf.Vec3f(*map(float, points.min(0))),
                                    Gf.Vec3f(*map(float, points.max(0)))])
        if component == 6 and mesh.GetNormalsAttr().Get():
            normals = np.asarray(mesh.GetNormalsAttr().Get(), dtype=float)
            normals[:, 2] /= (ROD_TOP_M + LIFT_M) / ROD_TOP_M
            lengths = np.linalg.norm(normals, axis=1)
            if (lengths <= 0).any():
                raise ValueError('Invalid source rod normals')
            normals /= lengths[:, None]
            mesh.GetNormalsAttr().Set([Gf.Vec3f(*map(float, n)) for n in normals])
    if len(parts) != 14 or geometry_digest(parts) != GEOMETRY_SHA:
        raise ValueError('Derived E17 visual/collision content mismatch')
    root.CreateAttribute('videoicl:e17DerivedGeometrySha256', Sdf.ValueTypeNames.String).Set(GEOMETRY_SHA)


def native_readback(scene, stage=None):
    """Read actual authored geometry plus live PhysX mass properties only."""
    if scene.spec.get('id')!='E17':
        return None
    obj=next((o for o in scene.spec.get('objects',[]) if o.get('id')=='stand'),{})
    if not obj.get('e17_stand_geometry'):
        return None
    try:
        from pxr import Usd,UsdGeom
        if stage is None:
            import omni.usd
            stage=omni.usd.get_context().get_stage()
        root=stage.GetPrimAtPath(scene.root_path+'/Props/stand')
        if not root:raise ValueError('Missing native stand prim')
        parts=[]
        for prim in Usd.PrimRange(root):
            if not prim.IsA(UsdGeom.Mesh):continue
            mesh=UsdGeom.Mesh(prim)
            relative=str(prim.GetPath()).removeprefix(str(root.GetPath())+'/')
            parts.append((relative,mesh.GetPointsAttr().Get(),mesh.GetFaceVertexCountsAttr().Get(),mesh.GetFaceVertexIndicesAttr().Get()))
        actual_hash=geometry_digest(parts)
        if len(parts)!=14 or actual_hash!=GEOMETRY_SHA:raise ValueError('Native stand geometry digest mismatch')
        view=scene.objects['stand'].root_physx_view
        def values(method):
            value=getattr(view,method)()
            if hasattr(value,'cpu'):value=value.cpu()
            array=np.asarray(value,dtype=float)
            if not array.size or not np.isfinite(array).all():raise ValueError('Invalid native '+method)
            return array.tolist()
        return dict(measured=True,source='live_PhysX_and_actual_USD',
                    derived_geometry_sha256=actual_hash,mesh_count=len(parts),
                    kinematic_enabled=root.GetAttribute('physics:kinematicEnabled').Get(),
                    gravity_disabled=root.GetAttribute('physxRigidBody:disableGravity').Get(),
                    mass_kg=values('get_masses'),center_of_mass_local=values('get_coms'),
                    inertia_local=values('get_inertias'),transport_acceptance=False)
    except Exception as exc:
        return dict(measured=False,error=type(exc).__name__+': '+str(exc),transport_acceptance=False)
