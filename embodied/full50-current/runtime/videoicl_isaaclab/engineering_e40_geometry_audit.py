"""Read actual E40 PhysX convex hulls without issuing any public action."""
import json
import numpy as np
from scipy.spatial import ConvexHull


def audit(author, policy, clip):
    import omni.physx
    import omni.usd
    from pxr import Usd, UsdGeom, UsdPhysics, PhysicsSchemaTools
    if policy.task != 'E40' or not hasattr(author, '_engineering_resume_checkpoint'):
        raise ValueError('Explicit E40 checkpoint geometry diagnostic required')
    stage = omni.usd.get_context().get_stage()
    cooking = omni.physx.get_physx_cooking_interface()
    cache = UsdGeom.XformCache()
    mechanism = policy.mechanisms()[clip['mechanism']]
    rows = []
    for name in mechanism['body_names']:
        path = f'{author.scene.root_path}/Mechanisms/{clip["mechanism"]}/{name}'
        body = stage.GetPrimAtPath(path)
        if not body.IsValid():
            raise ValueError('Actual E40 mechanism body missing: ' + path)
        inverse = cache.GetLocalToWorldTransform(body).GetInverse()
        position = np.asarray(mechanism['body_pos_task'][name])
        rotation = np.asarray(mechanism['body_mat_task'][name])
        for prim in Usd.PrimRange(body, Usd.TraverseInstanceProxies()):
            if not (prim.IsA(UsdGeom.Mesh) and prim.HasAPI(UsdPhysics.MeshCollisionAPI)
                    and prim.HasAPI(UsdPhysics.CollisionAPI)
                    and UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()):
                continue
            source = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), float)
            relative = np.asarray(cache.GetLocalToWorldTransform(prim) * inverse, float)
            def to_task(vertices):
                return (vertices @ relative[:3, :3] + relative[3, :3]) @ rotation.T + position
            received = []
            def receive(result, meshes):
                for mesh in meshes:
                    vertices = np.asarray(mesh.vertices, float)
                    received.append(dict(result=str(result), vertices_mesh_local=vertices.tolist(),
                                         vertices_task=to_task(vertices).tolist()))
            cooking.request_convex_collision_representation(
                omni.usd.get_context().get_stage_id(),
                PhysicsSchemaTools.sdfPathToInt(str(prim.GetPath())), False, receive)
            declared = to_task(source)
            attributes = {a.GetName(): str(a.Get()) for a in prim.GetAttributes()
                          if any(s in a.GetName().lower() for s in ('convex', 'thickness', 'vertexlimit'))}
            row = dict(body=name, collision=str(prim.GetPath()), cooking_attributes=attributes,
                       source_vertices_mesh_local=source.tolist(),
                       source_vertices_task=declared.tolist(),
                       mesh_to_body_row_matrix=relative.tolist(),
                       native_body_position_task=position.tolist(),
                       native_body_rotation_task=rotation.tolist(), cooked_meshes=received,
                       approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()))
            if received:
                actual = np.concatenate([np.asarray(r['vertices_task']) for r in received])
                source_hull, cooked_hull = ConvexHull(declared), ConvexHull(actual)
                row.update(source_vertices=len(source), cooked_vertices=len(actual),
                           source_volume_m3=float(source_hull.volume),
                           cooked_volume_m3=float(cooked_hull.volume),
                           max_cooked_outside_source_m=float((actual @ source_hull.equations[:, :3].T +
                                                             source_hull.equations[:, 3]).max()),
                           max_source_outside_cooked_m=float((declared @ cooked_hull.equations[:, :3].T +
                                                             cooked_hull.equations[:, 3]).max()))
            rows.append(row)
    native_mass_properties = {}
    for name, asset in author.scene.mechanisms.items():
        view = asset.root_physx_view
        native_mass_properties[name] = dict(body_names=list(asset.body_names),
            masses_kg=view.get_masses().cpu().tolist(),
            inertias_kg_m2=view.get_inertias().cpu().tolist(),
            centres_of_mass=view.get_coms().cpu().tolist())
    result = dict(schema='e40-native-cooked-source-audit-v1', diagnostic_only=True,
                  public_actions=policy.c.steps, no_physics_or_geometry_writes=True,
                  native_mass_properties=native_mass_properties,
                  source_initial_full_positive=False, meshes=rows,
                  all_meshes_received=bool(rows) and all(r['cooked_meshes'] for r in rows))
    path = author.out / 'clip-cooked-source-audit.private.json'
    path.write_text(json.dumps(result, indent=2) + '\n'); path.chmod(0o600)
    return dict(task='E40', entry='e40-cooked-only', diagnostic_only=True,
                audit=str(path), actions=policy.c.steps, execution_finished=True,
                geometry_readback_complete=result['all_meshes_received'],
                physics_success_not_asserted=True)
