"""Explicit source-bound collision representation changes, never asset fallbacks."""
import numpy as np


def ray_hit_value(hit,legacy,modern=None):
    if isinstance(hit,dict):return hit.get(legacy,hit.get(modern or legacy))
    return getattr(hit,modern or legacy)


def analytic_source_sphere(stage,root,obj,selected,low,high,scale):
    from pxr import Usd,UsdGeom,UsdPhysics
    # The visual and its SHA-pinned source remain mandatory. This opt-in changes
    # the collision approximation of an already declared round ball; it does
    # not substitute a missing asset or claim to preserve the old convex cook.
    if obj.get('kind')!='sphere':raise ValueError('Analytic ball needs a source-declared sphere')
    radius=float(obj.get('sphere_radius',max(obj['size'])))
    if not 0<radius<=.1:raise ValueError('Invalid source ball radius')
    if max(abs(float(s)/radius-1.)for s in obj['size'])>.03:
        raise ValueError('Declared source bounds are not a round ball')
    cache=UsdGeom.XformCache();inverse=cache.GetLocalToWorldTransform(root).GetInverse()
    vertices=[];original=[]
    for prim in Usd.PrimRange(root):
        if not prim.IsA(UsdGeom.Mesh):continue
        if not any(prim.GetPath().HasPrefix(p.GetPath())for p in selected):continue
        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
        matrix=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
        vertices.append(points@matrix[:3,:3]+matrix[3,:3])
        original.append(str(prim.GetPath()))
    if not vertices:raise ValueError('Missing original ball collision mesh')
    points=np.concatenate(vertices);radial=np.linalg.norm(points,axis=1)
    error=float(np.max(np.abs(radial-radius)))
    if error>.08*radius:raise ValueError('Source mesh is not within reviewed 8 percent roundness bound')
    for prim in selected:UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr(False)
    collider=UsdGeom.Sphere.Define(stage,str(root.GetPath())+'/ReviewedSourceBallCollision')
    collider.CreateRadiusAttr(radius);collider.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
    UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
    return [collider.GetPrim()],dict(reviewed_approximation='analyticSphere',radius_m=radius,
        original_collision_paths=original,original_source_vertices=len(points),
        original_vertex_radial_min_max_m=[float(radial.min()),float(radial.max())],
        max_source_surface_radial_difference_m=error,
        source_visual_mesh_unchanged=True,source_file_modified=False,
        original_convex_collision_geometry_preserved=False,
        mass_friction_restitution_parameters_unchanged=True,
        body_pose_written=False)


def native_reviewed_collision_readback(scene):
    import carb,omni.physx,omni.usd,json
    from pxr import PhysicsSchemaTools,UsdGeom,UsdPhysics
    stage=omni.usd.get_context().get_stage();query=omni.physx.get_physx_scene_query_interface();rows={}
    for name,asset in scene.objects.items():
        path='/World/Props/'+name;root=stage.GetPrimAtPath(path)
        serialized=root.GetCustomDataByKey('videoicl:reviewed_collision_fidelity')
        if not serialized:continue
        audit=json.loads(serialized)
        if isinstance(audit,dict)and audit.get('reviewed_approximation')=='analyticSphere':
            prim=stage.GetPrimAtPath(path+'/ReviewedSourceBallCollision')
            radius=float(UsdGeom.Sphere(prim).GetRadiusAttr().Get())
            if not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():
                raise RuntimeError('Reviewed sphere collider disabled')
            centre=asset.data.root_pos_w[0].cpu().numpy();hits=[];all_hits=[]
            def report(hit):
                value=ray_hit_value(hit,'rigidBody','rigid_body')
                body=str(value if isinstance(value,str)else PhysicsSchemaTools.intToSdfPath(value))
                all_hits.append(dict(body=body,position=list(ray_hit_value(hit,'position'))))
                if body==path:
                    point=np.asarray(ray_hit_value(hit,'position'),float)
                    hits.append(dict(position_world_m=point.tolist(),radial_distance_m=float(np.linalg.norm(point-centre)),collision=str(ray_hit_value(hit,'collision'))))
                return True
            query.raycast_all(carb.Float3(*map(float,centre+[0.,0.,.06])),carb.Float3(0.,0.,-1.),.12,report)
            if not hits or any(abs(h['radial_distance_m']-radius)>1e-5 for h in hits):
                raise RuntimeError('Native ray surface differs from reviewed sphere radius: '+json.dumps(dict(
                    actor=name,radius_m=radius,centre_world_m=centre.tolist(),hits=hits,all_hits=all_hits,
                    scene_query_support=carb.settings.get_settings().get('/physics/enableSceneQuerySupport'))))
            audit['actual_native_ray_hits']=hits
        rows[name]=audit
    return rows
