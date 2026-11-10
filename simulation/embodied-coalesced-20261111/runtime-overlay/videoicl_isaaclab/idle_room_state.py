"""Hold measured rigid-body and articulation state across foreign physics ticks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StateField:
    name: str
    read: object
    write: object
    tolerance: float
    root_pose: bool = False


def _root_fields(asset, path, read_pose, read_velocity):
    def write_pose(xyzw):
        asset.write_root_pose_to_sim(xyzw[:, [0, 1, 2, 6, 3, 4, 5]])

    return (
        StateField(path + '/pose', read_pose, write_pose, 1e-6, root_pose=True),
        StateField(path + '/velocity', read_velocity, asset.write_root_velocity_to_sim, 1e-6),
    )


class IdleRoomSnapshot:
    def __init__(self, fields):
        import torch

        self.values = [(field, field.read().clone()) for field in fields]
        if any(not torch.isfinite(value).all() for _, value in self.values):
            raise RuntimeError('Nonfinite native state cannot be held')

    def _changed(self, field, value):
        import torch

        current = field.read()
        if not field.root_pose:
            return not torch.allclose(current, value, rtol=0., atol=field.tolerance)
        position, expected_position = current[..., :3], value[..., :3]
        if not torch.allclose(position, expected_position, rtol=0., atol=field.tolerance):
            # A room offset can make one representable float32 step exceed
            # the absolute tolerance. Permit that rounding only, up to 4 µm.
            lower = torch.nextafter(expected_position, torch.full_like(expected_position, -torch.inf))
            upper = torch.nextafter(expected_position, torch.full_like(expected_position, torch.inf))
            delta = (position - expected_position).abs()
            adjacent = ((position == lower) | (position == upper)) & (delta <= 4e-6)
            if not bool(torch.all((delta <= field.tolerance) | adjacent)):
                return True
        # PhysX can return either representative of the same quaternion.
        actual, expected = current[..., 3:], value[..., 3:]
        direct = (actual - expected).abs().amax(dim=-1)
        negated = (actual + expected).abs().amax(dim=-1)
        return not bool(torch.all(torch.minimum(direct, negated) <= field.tolerance))

    def restore(self):
        for field, value in self.values:
            if self._changed(field, value):
                field.write(value)

    def verify(self):
        for field, value in self.values:
            if self._changed(field, value):
                raise RuntimeError('Idle room native state drifted: ' + field.name)


class IdleRoomState:
    def __init__(self, stage, scene):
        from pxr import Usd, UsdPhysics

        fields = []
        tracked_bodies = set()
        for asset in scene.objects.values():
            view = asset.root_physx_view
            path, = view.prim_paths
            tracked_bodies.add(str(path))
            body = UsdPhysics.RigidBodyAPI(stage.GetPrimAtPath(path))
            if not body.GetKinematicEnabledAttr().Get():
                fields.extend(_root_fields(asset, str(path), view.get_transforms, view.get_velocities))

        for asset in (*scene.robots.values(), *scene.mechanisms.values()):
            path = asset.cfg.prim_path
            view = asset.root_physx_view
            if view.count != 1:
                raise ValueError('Idle room requires a single articulation instance: ' + path)
            if not asset.is_fixed_base:
                fields.extend(_root_fields(asset, path, view.get_root_transforms, view.get_root_velocities))
            tracked_bodies.update(str(prim.GetPath()) for prim in Usd.PrimRange(stage.GetPrimAtPath(path))
                                  if prim.HasAPI(UsdPhysics.RigidBodyAPI))
            if asset.num_joints:
                fields.extend((
                    StateField(path + '/joint_position', view.get_dof_positions,
                               asset.write_joint_position_to_sim, 1e-6),
                    StateField(path + '/joint_velocity', view.get_dof_velocities,
                               asset.write_joint_velocity_to_sim, 1e-6),
                ))

        for prim in Usd.PrimRange(stage.GetPrimAtPath(scene.root_path)):
            schemas = prim.GetAppliedSchemas()
            prim_type = prim.GetTypeName()
            if any(kind in schema for schema in (*schemas, prim_type)
                   for kind in ('Particle', 'Deformable', 'Cloth')):
                raise ValueError('Idle room cannot hold this physics schema: ' + str(prim.GetPath()))
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                body = UsdPhysics.RigidBodyAPI(prim)
                if (str(prim.GetPath()) not in tracked_bodies
                        and body.GetRigidBodyEnabledAttr().Get()
                        and not body.GetKinematicEnabledAttr().Get()):
                    raise ValueError('Idle room has an untracked dynamic body: ' + str(prim.GetPath()))
        self.fields = tuple(fields)
        self.snapshot().verify()

    def snapshot(self):
        return IdleRoomSnapshot(self.fields)
