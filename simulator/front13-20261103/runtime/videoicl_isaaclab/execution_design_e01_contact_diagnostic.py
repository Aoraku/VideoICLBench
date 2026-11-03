"""Read the actual convex representation of enabled original source meshes."""
import numpy as np


def body_local_vertices(vertices,mesh_world,body_world):
    """Remove USD authored body pose before using live native body transforms."""
    vertices=np.asarray(vertices,float);relative=np.asarray(mesh_world,float)@np.linalg.inv(np.asarray(body_world,float))
    return vertices@relative[:3,:3]+relative[3,:3]


def read_source_convex_geometry(scene,actors):
    import omni.physx,omni.usd
    from pxr import Usd,UsdGeom,UsdPhysics,PhysxSchema,PhysicsSchemaTools
    from scipy.spatial import ConvexHull
    stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache()
    cooking=omni.physx.get_physx_cooking_interface();rows=[]
    for actor in actors:
        root=stage.GetPrimAtPath(scene.root_path+'/Props/'+actor)
        if not root:raise ValueError('Unknown source convex diagnostic actor')
        body_matrix=np.asarray(cache.GetLocalToWorldTransform(root),float)
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
                        vertices_world_m=(verts@matrix[:3,:3]+matrix[3,:3]).tolist(),
                        vertices_body_local_m=body_local_vertices(verts,matrix,body_matrix).tolist()))
            cooking.request_convex_collision_representation(omni.usd.get_context().get_stage_id(),
                PhysicsSchemaTools.sdfPathToInt(str(prim.GetPath())),False,received)
            if not received_rows:raise RuntimeError('No actual source convex representation: '+str(prim.GetPath()))
            actual=np.concatenate([np.asarray(r['vertices_world_m'])for r in received_rows])
            row=dict(actor=actor,path=str(prim.GetPath()),original_approximation=approximation,
                authored_body_world_matrix=body_matrix.tolist(),prim_type=prim.GetTypeName(),configured_hull_vertex_limit=PhysxSchema.PhysxConvexHullCollisionAPI(prim).GetHullVertexLimitAttr().Get(),
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


def install(author):
    """Passive independent native contact buffers, no actuation or material edits."""
    import json
    from .author_native_grip_probe import decode_patch,cpu_copy
    scene=author.a.scene;c=author.c
    if scene.spec['id']!='E01' or not author.a.control_report.get('engineering_reference_only'):
        raise ValueError('E01 independent diagnostic scope required')
    path=author.a.out/'e01-tray-contact-patches.private.jsonl'
    sensor=next(iter(scene.contacts.values()))[0];view=sensor._physics_sim_view
    pairs=[('tray-fixture0',scene.root_path+'/Props/tray',scene.root_path+'/Task/fixture0'),
           ('tray-table',scene.root_path+'/Props/tray',scene.rig_root+'/Table')]
    pairs += [(side+'-'+body,scene.root_path+'/'+side+'_robot/'+body,scene.root_path+'/Props/tray')
              for side in ('left','right')for body in ('panda_leftfinger','panda_rightfinger')]
    views={name:view.create_rigid_contact_view(body,filter_patterns=[target],max_contact_data_count=1024)
           for name,body,target in pairs}
    tray=scene.objects['tray'].root_physx_view
    metadata=dict(read_only=True,source_geometry=read_source_convex_geometry(scene,['tray']),
        fixtures=scene.spec['fixtures'],tray_material=cpu_copy(tray.get_material_properties()).tolist(),
        tray_contact_offsets=cpu_copy(tray.get_contact_offsets()).tolist(),
        tray_rest_offsets=cpu_copy(tray.get_rest_offsets()).tolist(),tray_mass=cpu_copy(tray.get_masses()).tolist())
    # Physical COM and bottom support come from the actual cooked instance.
    local=np.concatenate([np.asarray(block['vertices_body_local_m'])for row in metadata['source_geometry']for block in row['actual_meshes']])
    bottom=local[local[:,2]<=local[:,2].min()+.0005]
    com=cpu_copy(tray.get_coms()).reshape(-1,7)[0,:3]
    if len(bottom)<3 or not np.isfinite(com).all():raise ValueError('E01 actual support geometry unavailable')
    author._e01_native_bottom_local=bottom.copy();author._e01_native_com_local=com.copy()
    metadata.update(tray_com_body_m=com.tolist(),actual_bottom_vertices_body_m=bottom.tolist(),bottom_layer_tolerance_m=.0005)
    (author.a.out/'e01-tray-cooked-and-material.private.json').write_text(json.dumps(metadata))
    last=[None]
    def record(controller,render):
        if controller.steps==last[0]:return
        last[0]=controller.steps;row=dict(step=controller.steps,tick=controller.physics_ticks,stage=author.a.stage,pairs={})
        for name,contact in views.items():
            try:
                normal=decode_patch(contact.get_contact_data(controller.dt))
                friction=decode_patch(contact.get_friction_data(controller.dt),True)
                row['pairs'][name]=dict(normal={k:v.tolist()for k,v in normal.items()},friction={k:v.tolist()for k,v in friction.items()})
            except Exception as exc:row['pairs'][name]=dict(error=repr(exc))
        with path.open('a')as stream:stream.write(json.dumps(row)+'\n')
    c.tick_hooks.append(record)
