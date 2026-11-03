"""Physical mechanism adapters built from published meshes and joint sources.

Imports are CPU-safe. No animation, state teleportation, target-conditioned
geometry, or invisible solid replacement is used. USD/PhysX cooking and robot
interaction still require a simulator validation after the CPU build.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_path(root, relative, checksum):
    root = Path(root).resolve()
    relative = Path(relative)
    path = (root / relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(root):
        raise ValueError('Mechanism source must remain inside its configured root')
    if not checksum or not path.is_file() or file_sha256(path) != checksum:
        raise ValueError('Mechanism dependency missing or SHA256 mismatch: ' + str(path))
    return path


@dataclass
class PressReleaseCounter:
    """Count actual contact-driven travel cycles, with release hysteresis.

    Displacement is measured from the simulated plunger joint, positive down.
    A held button cannot repeatedly count; movement without contact cannot count.
    """
    press_travel_m: float = .002
    release_travel_m: float = .0005
    count: int = 0
    armed: bool = True

    def __post_init__(self):
        if not 0 <= self.release_travel_m < self.press_travel_m:
            raise ValueError('Release threshold must be below press threshold')

    def update(self, displacement_m, has_external_contact):
        if not math.isfinite(displacement_m):
            raise ValueError('Nonfinite physical joint reading')
        if not self.armed and displacement_m <= self.release_travel_m:
            self.armed = True
        event = bool(self.armed and has_external_contact and displacement_m >= self.press_travel_m)
        if event:
            self.count += 1
            self.armed = False
        return event


@dataclass
class ElastoPlasticHinge:
    """Rate-independent crease plasticity, driven solely by physical angle.

    Return this torque to the simulated joint as an effort. Plastic rest angle
    changes only when elastic moment exceeds yield; it never reads a task target.
    This is a lumped crease material model, not a deformable-sheet simulation.
    """
    stiffness_nm_per_rad: float = 1.
    yield_moment_nm: float = .015
    damping_nm_s_per_rad: float = .003
    plastic_rest_angle_rad: float = 0.

    def __post_init__(self):
        if self.stiffness_nm_per_rad <= 0 or self.yield_moment_nm <= 0 or self.damping_nm_s_per_rad < 0:
            raise ValueError('Physical crease stiffness/yield must be positive and damping nonnegative')

    def effort(self, physical_angle_rad, physical_velocity_rad_s):
        if not all(math.isfinite(v) for v in (physical_angle_rad, physical_velocity_rad_s)):
            raise ValueError('Nonfinite physical hinge state')
        trial = self.stiffness_nm_per_rad * (physical_angle_rad - self.plastic_rest_angle_rad)
        elastic = max(-self.yield_moment_nm, min(self.yield_moment_nm, trial))
        if elastic != trial:
            self.plastic_rest_angle_rad = physical_angle_rad - elastic / self.stiffness_nm_per_rad
        return -elastic - self.damping_nm_s_per_rad * physical_velocity_rad_s


def spawn_mechanical_asset(stage, prim_path, record, translation=(0, 0, 0), orientation=(1, 0, 0, 0)):
    """Reference a metric, Z-up mechanical USD and preserve its real joints.

    The converted asset contains its own masses, collisions and passive drives.
    This function only positions the whole asset and relocates its world anchor.
    Root scaling is intentionally unavailable: geometry and linear joint limits
    are scaled together at conversion time.
    """
    from pxr import Gf, Usd, UsdGeom, UsdPhysics
    root = os.environ.get(record.get('root_env', 'VIC_MECHANISM_ASSETS'))
    if not root:
        raise ValueError('Set mechanism asset root environment variable')
    path = checked_path(root, record['relative_path'], record['sha256'])
    for item in record.get('dependencies', []):
        checked_path(root, item['relative_path'], item['sha256'])
    prim = UsdGeom.Xform.Define(stage, prim_path).GetPrim()
    prim.GetReferences().AddReference(str(path))
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(Gf.Vec3d(*translation))
    xform.AddOrientOp().Set(Gf.Quatf(orientation[0], Gf.Vec3f(*orientation[1:])))
    xforms = UsdGeom.XformCache()
    joints = []
    moving = []
    for child in Usd.PrimRange(prim):
        if child.IsA(UsdPhysics.Joint):
            joint = UsdPhysics.Joint(child)
            joints.append(str(child.GetPath()))
            if child.IsA(UsdPhysics.PrismaticJoint) or child.IsA(UsdPhysics.RevoluteJoint):
                moving.append(child.GetName())
            body0 = joint.GetBody0Rel().GetTargets()
            body1 = joint.GetBody1Rel().GetTargets()
            if not body0 and body1:
                if not child.IsA(UsdPhysics.FixedJoint):
                    raise ValueError('Only a fixed joint can serve as a world anchor')
                body = stage.GetPrimAtPath(body1[0])
                world = xforms.GetLocalToWorldTransform(body)
                local = joint.GetLocalPos1Attr().Get() or Gf.Vec3f(0)
                quat = joint.GetLocalRot1Attr().Get() or Gf.Quatf(1)
                joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*world.Transform(Gf.Vec3d(*local))))
                rotation = Gf.Rotation(world.ExtractRotationQuat()) * Gf.Rotation(Gf.Quatd(quat))
                q = rotation.GetQuat()
                joint.CreateLocalRot0Attr().Set(Gf.Quatf(q.GetReal(), Gf.Vec3f(*q.GetImaginary())))
    expected = record.get('joint_count')
    if expected is not None and len(joints) != expected:
        raise ValueError('Mechanism joint count differs from CPU receipt')
    contacts = {}
    for name, relative in record.get('contact_links', {}).items():
        if relative.startswith('/') or '..' in Path(relative).parts:
            raise ValueError('Contact link path must be relative to the mechanism')
        target = str(prim.GetPath()) + '/' + relative
        if not stage.GetPrimAtPath(target):
            raise ValueError('Unknown contact link: ' + target)
        contacts[name] = target
    return dict(root=prim, joint_paths=joints, moving_joint_names=moving,
                contact_prim_paths=contacts, source_path=str(path), kind=record.get('kind','articulation'))


def convert_urdf_mechanism(urdf_path, out, converter, scale=1., link_mass=.25):
    """Convert mesh-only URDF links/joints using the existing mesh converter.

    Mesh visuals/materials and separate collision sources are retained. The
    original link/joint coordinate frames and limits are scaled consistently.
    Existing output is never overwritten. Units are metres and radians in URDF,
    metres and degrees in USD. Only fixed/revolute/prismatic joints are accepted.
    """
    import numpy as np
    import trimesh
    from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdPhysics
    urdf_path, out = Path(urdf_path).resolve(), Path(out).resolve()
    if scale <= 0 or out.exists():
        raise ValueError('Positive scale and fresh output path required')
    document = ET.parse(urdf_path).getroot()
    links = {node.attrib['name']: node for node in document.findall('link')}
    joints = document.findall('joint')
    child_names = {j.find('child').attrib['link'] for j in joints}
    roots = set(links) - child_names
    if len(roots) != 1:
        raise ValueError('URDF must have exactly one rooted link tree')
    root_name = next(iter(roots))
    out.parent.mkdir(parents=True, exist_ok=True)
    part_dir = out.parent / (out.stem + '_parts')
    part_dir.mkdir(exist_ok=True)
    stage = Usd.Stage.CreateNew(str(out))
    asset = UsdGeom.Xform.Define(stage, '/Asset').GetPrim()
    stage.SetDefaultPrim(asset)
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdPhysics.ArticulationRootAPI.Apply(asset)
    link_paths = {name: '/Asset/Links/' + Tf.MakeValidIdentifier(name) for name in links}
    sources = {str(urdf_path): file_sha256(urdf_path)}
    records, piece_cache = [], {}

    def origin(element):
        xyz = np.array([float(v) for v in element.get('xyz', '0 0 0').split()]) if element is not None else np.zeros(3)
        rpy = [float(v) for v in element.get('rpy', '0 0 0').split()] if element is not None else [0, 0, 0]
        result = trimesh.transformations.euler_matrix(*rpy)
        result[:3, 3] = xyz * scale
        return result

    def set_transform(prim, matrix, mesh_scale=None):
        x = UsdGeom.Xformable(prim)
        x.AddTranslateOp().Set(Gf.Vec3d(*map(float, matrix[:3, 3])))
        q = trimesh.transformations.quaternion_from_matrix(matrix)
        x.AddOrientOp().Set(Gf.Quatf(float(q[0]), Gf.Vec3f(*map(float, q[1:]))))
        if mesh_scale is not None:
            x.AddScaleOp().Set(Gf.Vec3f(*map(float, mesh_scale)))

    transforms = {root_name: np.eye(4)}
    remaining = list(joints)
    while remaining:
        count = len(remaining)
        for j in list(remaining):
            parent, child = j.find('parent').get('link'), j.find('child').get('link')
            if parent in transforms:
                transforms[child] = transforms[parent] @ origin(j.find('origin'))
                remaining.remove(j)
        if len(remaining) == count:
            raise ValueError('Joint tree is cyclic or has an unknown parent')
    for name, link in links.items():
        prim = UsdGeom.Xform.Define(stage, link_paths[name]).GetPrim()
        set_transform(prim, transforms[name])
        UsdPhysics.RigidBodyAPI.Apply(prim)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(link_mass))
        for role in ('visual', 'collision'):
            for index, element in enumerate(link.findall(role)):
                mesh = element.find('geometry/mesh')
                if mesh is None:
                    raise ValueError('Only published mesh geometry is supported; no generated primitive fallback')
                source = (urdf_path.parent / mesh.attrib['filename']).resolve()
                if not source.is_relative_to(urdf_path.parent):
                    raise ValueError('URDF source escapes source package')
                checksum = file_sha256(source)
                sources[str(source)] = checksum
                if source not in piece_cache:
                    target = part_dir / (source.stem + '_' + checksum[:10] + '.usda')
                    if target.exists():
                        provenance = json.loads(target.with_suffix('.provenance.json').read_text())
                        if provenance['output_sha256'] != file_sha256(target) or provenance['visual'] != str(source):
                            raise ValueError('Existing conversion does not match source')
                    else:
                        provenance = converter.convert(source, source, target, 'convexDecomposition')
                    piece_cache[source] = target
                    for entry in provenance['sources']:
                        sources[entry['path']] = entry['sha256']
                target = piece_cache[source]
                member = stage.DefinePrim(link_paths[name] + '/' + role + '_' + str(index), 'Xform')
                member.GetReferences().AddReference(target.relative_to(out.parent).as_posix())
                set_transform(member, origin(element.find('origin')), np.array([float(v) for v in mesh.get('scale', '1 1 1').split()]) * scale)
                inactive = '/Collisions' if role == 'visual' else '/Visuals'
                stage.OverridePrim(str(member.GetPath()) + inactive).SetActive(False)
    for node in joints:
        kind, name = node.attrib['type'], node.attrib['name']
        cls = {'fixed': UsdPhysics.FixedJoint, 'revolute': UsdPhysics.RevoluteJoint, 'prismatic': UsdPhysics.PrismaticJoint}.get(kind)
        if cls is None:
            raise ValueError('Unsupported joint type: ' + kind)
        joint = cls.Define(stage, '/Asset/Joints/' + Tf.MakeValidIdentifier(name))
        parent, child = node.find('parent').get('link'), node.find('child').get('link')
        joint.CreateBody0Rel().SetTargets([link_paths[parent]])
        joint.CreateBody1Rel().SetTargets([link_paths[child]])
        matrix = origin(node.find('origin'))
        axis_node = node.find('axis')
        axis = np.array([float(v) for v in axis_node.get('xyz', '1 0 0').split()]) if axis_node is not None else np.array([1., 0, 0])
        axis /= np.linalg.norm(axis)
        align = trimesh.geometry.align_vectors([1, 0, 0], axis)
        def quat(m):
            q = trimesh.transformations.quaternion_from_matrix(m)
            return Gf.Quatf(float(q[0]), Gf.Vec3f(*map(float, q[1:])))
        joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*map(float, matrix[:3,3])))
        joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0))
        joint.CreateLocalRot0Attr().Set(quat(matrix @ align))
        joint.CreateLocalRot1Attr().Set(quat(align))
        limits = None
        if kind != 'fixed':
            joint.CreateAxisAttr('X')
            limit = node.find('limit')
            if limit is None:
                raise ValueError('Physical joint limits are required')
            factor = scale if kind == 'prismatic' else 180 / math.pi
            limits = [float(limit.get(key)) * factor for key in ('lower', 'upper')]
            joint.CreateLowerLimitAttr(limits[0])
            joint.CreateUpperLimitAttr(limits[1])
        joint.CreateCollisionEnabledAttr(False)
        records.append(dict(name=name, type=kind, parent=parent, child=child, source_axis=axis.tolist(), usd_limits=limits))
    anchor = UsdPhysics.FixedJoint.Define(stage, '/Asset/Joints/WorldAnchor')
    anchor.CreateBody1Rel().SetTargets([link_paths[root_name]])
    anchor.CreateLocalPos0Attr().Set(Gf.Vec3f(0))
    anchor.CreateLocalPos1Attr().Set(Gf.Vec3f(0))
    stage.GetRootLayer().Export(str(out))
    # Reopen to resolve all references against their final on-disk anchor.
    check = Usd.Stage.Open(str(out))
    mesh_count = sum(p.IsA(UsdGeom.Mesh) for p in check.Traverse())
    if not mesh_count:
        raise ValueError('Converted URDF resolves no meshes')
    report = dict(schema='realworld-urdf-mechanism-v1', source_urdf=str(urdf_path), source_scale=scale,
                  output=str(out), sha256=file_sha256(out), joint_count=len(records)+1,
                  joints=records, source_files=[dict(path=p,sha256=h) for p,h in sources.items()],
                  mesh_count=mesh_count, gpu_used=False, physx_cooking_verified=False,
                  physical_interaction_verified=False, limitations=['Mesh collision decomposition is authored, not CPU-cooked by this importer.', 'URDF inertias unavailable: explicit uniform link masses assigned.'])
    report['dependencies'] = [dict(relative_path=p.relative_to(out.parent).as_posix(),sha256=file_sha256(p)) for p in sorted(part_dir.rglob('*')) if p.is_file()]
    out.with_suffix('.mechanism.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
