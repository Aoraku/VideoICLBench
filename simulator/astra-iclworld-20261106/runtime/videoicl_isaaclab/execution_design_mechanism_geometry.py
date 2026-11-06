"""Read actual articulated collision parts using measured rigid-body frames."""
import numpy as np


def collision_parts(author, mechanism_id):
    from pxr import Usd, UsdGeom, UsdPhysics
    import omni.usd
    from isaaclab.utils.math import matrix_from_quat
    scene = author.scene
    asset = scene.mechanisms[mechanism_id]
    stage = omni.usd.get_context().get_stage()
    root = stage.GetPrimAtPath(scene.root_path + '/Mechanisms/' + mechanism_id)
    cache = UsdGeom.XformCache()
    parts = []
    for bid, name in enumerate(asset.body_names):
        bodies = [p for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()) if p.GetName() == name]
        if len(bodies) != 1:
            raise ValueError('Unique native articulated body required: ' + name)
        body = bodies[0]
        inverse = cache.GetLocalToWorldTransform(body).GetInverse()
        rotation = scene.layout.task_rotation.T @ matrix_from_quat(asset.data.body_quat_w[:, bid])[0].cpu().numpy()
        position = scene.world_to_task(asset.data.body_pos_w[0, bid].cpu().numpy())
        for prim in Usd.PrimRange(body, Usd.TraverseInstanceProxies()):
            if not prim.IsA(UsdGeom.Mesh):
                continue
            ancestor = prim; enabled = False
            while ancestor and ancestor != body:
                if ancestor.HasAPI(UsdPhysics.CollisionAPI):
                    enabled = UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get() is not False
                    break
                ancestor = ancestor.GetParent()
            if not enabled:
                continue
            points = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), float)
            transform = np.asarray(cache.GetLocalToWorldTransform(prim) * inverse, float)
            local = points @ transform[:3, :3] + transform[3, :3]
            parts.append(dict(body=name, path=str(prim.GetPath()),
                              vertices_task=(local @ rotation.T + position).tolist()))
    if not parts:
        raise ValueError('Actual articulated collision meshes required')
    return parts
