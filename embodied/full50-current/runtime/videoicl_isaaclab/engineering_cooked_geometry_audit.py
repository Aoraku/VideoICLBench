"""Read-only source convex/cooked PhysX vertical-ray comparison for E50."""
import json
import numpy as np
from scipy.spatial import ConvexHull


def isolated_native_recook(mesh_prim,collision_prim,cooking):
    """Work around parent-Xform/proxy reader limits in a non-simulated stage."""
    from pxr import Usd,UsdGeom,UsdPhysics,UsdUtils,PhysxSchema,PhysicsSchemaTools
    scratch=Usd.Stage.CreateInMemory();UsdGeom.SetStageMetersPerUnit(scratch,UsdGeom.GetStageMetersPerUnit(mesh_prim.GetStage()))
    UsdGeom.SetStageUpAxis(scratch,UsdGeom.GetStageUpAxis(mesh_prim.GetStage()))
    source=UsdGeom.Mesh(mesh_prim);mesh=UsdGeom.Mesh.Define(scratch,'/Mesh')
    mesh.CreatePointsAttr(source.GetPointsAttr().Get());mesh.CreateFaceVertexCountsAttr(source.GetFaceVertexCountsAttr().Get());mesh.CreateFaceVertexIndicesAttr(source.GetFaceVertexIndicesAttr().Get());mesh.CreateSubdivisionSchemeAttr('none')
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim());UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr(UsdPhysics.MeshCollisionAPI(collision_prim).GetApproximationAttr().Get())
    old=PhysxSchema.PhysxConvexHullCollisionAPI(collision_prim);new=PhysxSchema.PhysxConvexHullCollisionAPI.Apply(mesh.GetPrim())
    new.CreateHullVertexLimitAttr(old.GetHullVertexLimitAttr().Get());new.CreateMinThicknessAttr(old.GetMinThicknessAttr().Get())
    cache=UsdUtils.StageCache.Get();stage_id=cache.Insert(scratch);rows=[];statuses=[]
    def receive(result,meshes):
        statuses.append(str(result))
        for item in meshes:rows.append(np.asarray(item.vertices,float))
    try:cooking.request_convex_collision_representation(stage_id.ToLongInt(),PhysicsSchemaTools.sdfPathToInt('/Mesh'),False,receive)
    finally:cache.Erase(stage_id)
    return rows,dict(origin='isolated_native_recook_same_mesh_parameters',statuses=statuses,
        live_stage_modified=False,live_physics_advanced=False,source_topology_unchanged=True)


def verify_cooked_body_rays(scene,body,meshes):
    import omni.physx,carb
    from pxr import PhysicsSchemaTools
    from .source_reviewed_collisions import ray_hit_value
    points=np.concatenate(meshes);centre=points.mean(0);low=points.min(0);high=points.max(0);rows=[]
    for axis in range(3):
        transverse=[i for i in range(3)if i!=axis]
        for sign in(-1.,1.):
            # Interior transverse sites avoid vertex-boundary ray ambiguity.
            origin=centre.copy();origin[axis]=(low[axis]-.005)if sign>0 else(high[axis]+.005)
            direction=np.eye(3)[axis]*sign;hits=[]
            def receive(hit):
                path=ray_hit_value(hit,'rigidBody','rigid_body');path=str(path if isinstance(path,str)else PhysicsSchemaTools.intToSdfPath(path))
                if path==body:hits.append(scene.world_to_task(np.asarray(ray_hit_value(hit,'position'),float)))
                return True
            world=scene.task_to_world(origin);wd=np.asarray(scene.layout.task_rotation)@direction
            omni.physx.get_physx_scene_query_interface().raycast_all(carb.Float3(*map(float,world)),carb.Float3(*map(float,wd)),float(high[axis]-low[axis]+.01),receive)
            intersections=[]
            for mesh in meshes:
                planes=ConvexHull(mesh).equations;n=planes[:,:3];den=n@direction;num=-(n@origin+planes[:,3]);tmin,tmax=0.,float('inf');valid=True
                for a,b in zip(den,num):
                    if abs(a)<1e-12:
                        if b<0:valid=False;break
                    elif a>0:tmax=min(tmax,b/a)
                    else:tmin=max(tmin,b/a)
                if valid and tmin<=tmax:intersections.append(origin+direction*tmin)
            expected=min(intersections,key=lambda x:float((x-origin)@direction))if intersections else None
            actual=min(hits,key=lambda x:float((x-origin)@direction))if hits else None
            error=None if expected is None or actual is None else float(np.linalg.norm(expected-actual))
            rows.append(dict(axis=axis,sign=sign,expected_task=None if expected is None else expected.tolist(),native_task=None if actual is None else actual.tolist(),error_m=error))
    errors=[r['error_m']for r in rows if r['error_m']is not None]
    return dict(rows=rows,passed=len(errors)==6 and max(errors)<.00002,maximum_error_m=max(errors,default=None),native_physics_advanced=False)


def vertical_source_surface(vertices,xy,direction):
    planes=ConvexHull(np.asarray(vertices,float)).equations;xy=np.asarray(xy,float)
    flat=np.abs(planes[:,2])<1e-12
    if np.any(planes[flat,:2]@xy+planes[flat,3]>1e-8):return None
    up=planes[planes[:,2]>1e-12];down=planes[planes[:,2]<-1e-12]
    if not len(up)or not len(down):return None
    zhi=-(up[:,:2]@xy+up[:,3])/up[:,2];zlo=-(down[:,:2]@xy+down[:,3])/down[:,2]
    i,j=int(np.argmin(zhi)),int(np.argmax(zlo))
    if zlo[j]>zhi[i]+1e-8:return None
    return dict(z_m=float(zhi[i]if direction<0 else zlo[j]),normal=(up[i,:3]if direction<0 else down[j,:3]).tolist())


def cooking_metadata(scene,actor,side):
    from pxr import Usd,UsdPhysics,PhysxSchema
    import omni.usd
    stage=omni.usd.get_context().get_stage();rows=[]
    for path in(f'{scene.root_path}/Props/{actor}',f'{scene.root_path}/{side}_robot/panda_leftfinger',f'{scene.root_path}/{side}_robot/panda_rightfinger'):
        root=stage.GetPrimAtPath(path)
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):continue
            attrs={a.GetName():str(a.Get())for a in prim.GetAttributes()if any(x in a.GetName().lower()for x in('convex','collision','vertexlimit','minthickness','margin','weld','simplif'))}
            rows.append(dict(path=str(prim.GetPath()),applied_schemas=list(prim.GetAppliedSchemas()),attributes=attrs))
    schemas={}
    for name in('PhysxConvexHullCollisionAPI','PhysxConvexMeshCollisionAPI','PhysxTriangleMeshCollisionAPI'):
        cls=getattr(PhysxSchema,name,None)
        if cls is None:continue
        names=list(cls.GetSchemaAttributeNames());record=dict(attributes=names,defaults={})
        try:
            definition=Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(name)
            for n in names:
                prop=definition.GetSchemaAttributeSpec(n)
                if prop:record['defaults'][n]=str(prop.default)
        except Exception as exc:record['default_readback_error']=type(exc).__name__+': '+str(exc)
        schemas[name]=record
    return dict(colliders=rows,registered_schemas=schemas,no_usd_attributes_written=True)


def native_cooked_meshes(author, policy, ref, side):
    """Read cooked vertices using the same body-local/native pose chain as source."""
    import omni.physx, omni.usd
    from pxr import Usd, UsdGeom, UsdPhysics, PhysicsSchemaTools
    from isaaclab.utils.math import matrix_from_quat
    scene=author.scene;stage=omni.usd.get_context().get_stage()
    cooking=omni.physx.get_physx_cooking_interface();cache=UsdGeom.XformCache();rows=[]
    bodies=[(ref['actor'],f'{scene.root_path}/Props/{ref["actor"]}',policy.frame(ref))]
    robot=scene.robots[side]
    for name in scene.embodiment.fingers:
        bid=robot.find_bodies(name)[0][0]
        rotation=np.asarray(scene.layout.task_rotation).T@matrix_from_quat(robot.data.body_quat_w[:,bid])[0].cpu().numpy()
        position=scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
        bodies.append((name,f'{scene.root_path}/{side}_robot/{name}',(position,rotation)))
    for name,path,(position,rotation) in bodies:
        body=stage.GetPrimAtPath(path);inverse=cache.GetLocalToWorldTransform(body).GetInverse()
        for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.MeshCollisionAPI):continue
            if not prim.HasAPI(UsdPhysics.CollisionAPI)or not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():continue
            # Panda applies both collision APIs to a parent Xform; its Mesh
            # child is the real vertex source. Query the actual collision
            # path while expressing source vertices in that same local frame.
            collision_inverse=cache.GetLocalToWorldTransform(prim).GetInverse();parts=[];source_parts=[];ancestor_audit=[]
            for mesh_prim in Usd.PrimRange(prim,Usd.TraverseInstanceProxies()):
                if not mesh_prim.IsA(UsdGeom.Mesh):continue
                chain=[];node=mesh_prim
                while node and node!=body:
                    if node.HasAPI(UsdPhysics.CollisionAPI):
                        chain.append(dict(path=str(node.GetPath()),collision_enabled=bool(UsdPhysics.CollisionAPI(node).GetCollisionEnabledAttr().Get())))
                    node=node.GetParent()
                ancestor_audit.append(dict(mesh=str(mesh_prim.GetPath()),collision_ancestors=chain,
                    any_explicit_disabled_collision=any(not x['collision_enabled']for x in chain)))
                points=np.asarray(UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get(),float)
                local=np.asarray(cache.GetLocalToWorldTransform(mesh_prim)*collision_inverse,float)
                parts.append(points@local[:3,:3]+local[3,:3])
                source_parts.append((mesh_prim,local))
            if not parts:continue
            source=np.concatenate(parts)
            relative=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
            def to_task(vertices):return(vertices@relative[:3,:3]+relative[3,:3])@np.asarray(rotation).T+position
            received=[];fallback=[]
            for mesh_prim,mesh_to_collision in source_parts:
                # The representation reader requires the underlying Mesh,
                # even when the native rigid collision path is its parent.
                def receive(result,meshes):
                    for mesh in meshes:
                        raw=np.asarray(mesh.vertices,float)
                        vertices=raw@mesh_to_collision[:3,:3]+mesh_to_collision[3,:3]
                        received.append(dict(result=str(result),requested_mesh_prim=str(mesh_prim.GetPath()),vertices_mesh_local=vertices.tolist(),vertices_task=to_task(vertices).tolist()))
                cooking.request_convex_collision_representation(omni.usd.get_context().get_stage_id(),PhysicsSchemaTools.sdfPathToInt(str(mesh_prim.GetPath())),False,receive)
                if not received:
                    values,audit=isolated_native_recook(mesh_prim,prim,cooking);fallback.append(audit)
                    for raw in values:
                        vertices=raw@mesh_to_collision[:3,:3]+mesh_to_collision[3,:3]
                        received.append(dict(result='verified_recook_pending_native_rays',requested_mesh_prim=str(mesh_prim.GetPath()),vertices_mesh_local=vertices.tolist(),vertices_task=to_task(vertices).tolist(),representation_origin=audit['origin']))
            declared=to_task(source);row=dict(name=name,body=path,collision=str(prim.GetPath()),
                approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()),
                source_mesh_local=source.tolist(),mesh_to_body_row_matrix=relative.tolist(),
                native_body_position_task=np.asarray(position).tolist(),native_body_rotation_task=np.asarray(rotation).tolist(),
                source_vertices_task=declared.tolist(),cooked_meshes=received,isolated_recook=fallback,
                mesh_ancestor_collision_audit=ancestor_audit)
            if fallback and received:
                row['native_ray_verification']=verify_cooked_body_rays(scene,path,[np.asarray(r['vertices_task'])for r in received])
                if not row['native_ray_verification']['passed']:
                    row['unverified_recook_meshes']=received;received=[];row['cooked_meshes']=[]
                    from .engineering_native_convex_rays import reconstruct
                    key=(path,str(prim.GetPath()))
                    stored=getattr(author,'_engineering_native_finger_hulls',{})
                    if key in stored:
                        local_vertices,ray_audit=stored[key]
                        local_vertices=np.asarray(local_vertices,float)
                        vertices=local_vertices@np.asarray(rotation).T+position
                        ray_audit=dict(ray_audit,reused_body_local_at_new_native_pose=True)
                    else:
                        vertices,ray_audit=reconstruct(scene,path,declared,
                            [np.asarray(r['vertices_task'])for r in row['unverified_recook_meshes']])
                        local_vertices=(vertices-position)@np.asarray(rotation)
                        planes=np.asarray(ray_audit['planes_task'])
                        ray_audit['planes_body_local']=np.c_[planes[:,:3]@np.asarray(rotation),
                            planes[:,3]+planes[:,:3]@np.asarray(position)].tolist()
                        ray_audit['vertices_body_local']=local_vertices.tolist()
                        if ray_audit['passed']:
                            stored[key]=(local_vertices.tolist(),ray_audit)
                            author._engineering_native_finger_hulls=stored
                    row['native_plane_reconstruction']=ray_audit
                    if ray_audit['passed']:
                        # No cooked-reader identity claim: these are measured
                        # native planes, verified only at the toe/contact band.
                        received=[dict(result='native_raycast_single_convex_planes',
                            requested_mesh_prim=str(prim.GetPath()),vertices_task=vertices.tolist(),
                            vertices_body_local=local_vertices.tolist(),vertices_mesh_local=None,
                            representation_origin=ray_audit['origin'])]
                        row['cooked_meshes']=received
            if received:
                actual=np.concatenate([np.asarray(r['vertices_task'])for r in received]);hull=ConvexHull(declared);cooked=ConvexHull(actual)
                row.update(source_vertices=len(source),cooked_vertices=len(actual),source_volume_m3=float(hull.volume),cooked_volume_m3=float(cooked.volume),
                    max_cooked_vertex_outside_source_m=float((actual@hull.equations[:,:3].T+hull.equations[:,3]).max()),
                    max_source_vertex_outside_cooked_m=float((declared@cooked.equations[:,:3].T+cooked.equations[:,3]).max()),
                    source_bounds_task=[declared.min(0).tolist(),declared.max(0).tolist()],cooked_bounds_task=[actual.min(0).tolist(),actual.max(0).tolist()])
            rows.append(row)
    return dict(meshes=rows,all_meshes_received=bool(rows)and all(r['cooked_meshes']for r in rows),no_physics_or_geometry_writes=True)


def audit(author,policy,ref,side='left'):
    import omni.physx,carb
    from pxr import PhysicsSchemaTools
    from .source_reviewed_collisions import ray_hit_value
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task
    scene=author.scene;query=omni.physx.get_physx_scene_query_interface();root=scene.root_path
    card=material_collision_points_task(policy,ref);finger_names=scene.embodiment.fingers
    meshes=[dict(name=ref['actor']+suffix,vertices=card,expected_body=f'{root}/Props/{ref["actor"]}',direction=direction)for suffix,direction in(('_top',-1),('_bottom',1))]
    for name in finger_names:meshes.append(dict(name=name,vertices=actual_mesh(author,side,name),expected_body=f'{root}/{side}_robot/{name}',direction=1))
    low=min(float(m['vertices'][:,2].min())for m in meshes)-.03;high=max(float(m['vertices'][:,2].max())for m in meshes)+.03;rows=[]
    for mesh in meshes:
        points=np.asarray(mesh['vertices']);center=points.mean(0)
        if mesh['name'].startswith(ref['actor']+'_'):sites=[center[:2]+[dx,0]for dx in(0.,.035,-.035)]
        else:
            toe=points[int(np.argmin(points[:,2]))];inward=center[:2]-toe[:2];inward/=max(np.linalg.norm(inward),1e-9)
            sites=[toe[:2]+inward*delta for delta in(0.,.0002,.0005)]+[center[:2]]
        for xy in sites:
            source=vertical_source_surface(points,xy,mesh['direction'])
            if source is None:continue
            origin_task=np.array([*xy,high if mesh['direction']<0 else low]);origin=scene.task_to_world(origin_task);world_direction=np.asarray(scene.layout.task_rotation)[:,2]*mesh['direction'];hits=[]
            def report(hit):
                try:
                    body=ray_hit_value(hit,'rigidBody','rigid_body');body=str(body if isinstance(body,str)else PhysicsSchemaTools.intToSdfPath(body))
                    position=np.array(ray_hit_value(hit,'position'),float);normal=np.array(ray_hit_value(hit,'normal'),float);task=scene.world_to_task(position)
                    hits.append(dict(body=body,collision=str(ray_hit_value(hit,'collision')),position_world=position.tolist(),position_task=task.tolist(),normal_task=(np.asarray(scene.layout.task_rotation).T@normal).tolist(),frame_roundtrip_error_m=float(np.linalg.norm(scene.task_to_world(task)-position))))
                except Exception as exc:hits.append(dict(decode_error=type(exc).__name__+': '+str(exc)));return False
                return True
            query.raycast_all(carb.Float3(*map(float,origin)),carb.Float3(*map(float,world_direction)),float(high-low),report)
            matched=[h for h in hits if h.get('body')==mesh['expected_body']]
            selected=min(matched,key=lambda h:abs(h['position_task'][2]-source['z_m']))if matched else None
            rows.append(dict(name=mesh['name'],direction=mesh['direction'],origin_task=origin_task.tolist(),source=source,expected_body=mesh['expected_body'],native=selected,all_native_hits=hits,
                cooked_minus_source_z_m=float(selected['position_task'][2]-source['z_m'])if selected else None))
    metadata=cooking_metadata(scene,ref['actor'],side);cooked=native_cooked_meshes(author,policy,ref,side)
    mass_properties={}
    for name,asset in scene.objects.items():
        view=asset.root_physx_view
        mass_properties[name]=dict(masses_kg=view.get_masses().cpu().tolist(),
            inertias_kg_m2=view.get_inertias().cpu().tolist(),centres_of_mass=view.get_coms().cpu().tolist())
    result=dict(native_mass_properties=mass_properties,cooking_metadata=metadata,native_cooked_geometry=cooked,schema='e50-source-cooked-native-ray-audit-v3',public_actions=policy.c.steps,geometry_or_contact_parameters_changed=False,frame='room_task',scene_query_support=carb.settings.get_settings().get('/physics/enableSceneQuerySupport'),rows=rows,
        actual_source_collision_vertices={m['name']:m['vertices'].tolist()for m in meshes},native_queries_available=bool(rows and any(r['native']for r in rows)),
        all_bodies_observed=all(any(r['name']==m['name']and r['native']for r in rows)for m in meshes),native_whole_task_success=False)
    (author.out/'cooked-source-ray-audit.private.json').write_text(json.dumps(result,indent=2));return result
