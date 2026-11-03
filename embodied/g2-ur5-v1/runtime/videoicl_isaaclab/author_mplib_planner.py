"""Private author-only MPlib planner. Never writes native state or scores.

World geometry comes from enabled native USD collision prims and measured body
poses. Native mesh convex hulls and primitive bounding hulls are conservative
planning proxies only. A failed coverage/calibration/collision gate returns no
trajectory. The public token controller does not import this module.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import math
import os
import time
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np

ARM_NAMES = [f'panda_joint{i}' for i in range(1, 8)]
SOURCE_URDF_SHA256 = '62c6bfdb6f4f4d09aba0d15269f0e164ebecbbfb66c323bccd2eba91fd6b9816'
NATIVE_USD_SHA256 = 'dcf184538ccd43c2a43b205b34a446222e7ac65b39326d3a192adc49e6bffc5f'
DT = .004


def _array(value, shape=None):
    value = np.asarray(value, dtype=float)
    if not np.isfinite(value).all() or shape is not None and value.shape != shape:
        raise ValueError('Nonfinite value or unexpected shape')
    return value


def _rotation(q):
    q = _array(q, (4,))
    if np.linalg.norm(q) < 1e-12: raise ValueError('Zero quaternion')
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def _matrix(p, q):
    out = np.eye(4); out[:3, :3] = _rotation(q); out[:3, 3] = _array(p, (3,))
    return out


def _quat(matrix):
    from transforms3d.quaternions import mat2quat
    return mat2quat(_array(matrix, (3, 3)))


def _angle(a, b):
    a = _array(a, (4,)); b = _array(b, (4,))
    return float(np.degrees(2*np.arccos(np.clip(abs(a @ b)/(np.linalg.norm(a)*np.linalg.norm(b)), -1, 1))))


def _pose(matrix, mplib):
    return mplib.Pose(matrix[:3, 3], _quat(matrix[:3, :3]))


def _vertices(matrix, vertices):
    return _array(vertices) @ matrix[:3, :3].T + matrix[:3, 3]


def _list(tensor):
    return tensor.detach().cpu().tolist()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _target(scene, controller, side, goal):
    """Task position; explicit task quaternion or controller's measured-base target."""
    request = goal if isinstance(goal, dict) else {'position': goal}
    tcp_world = _array(scene.task_to_world(request['position']), (3,))
    robot = scene.robots[side]
    base = _matrix(_list(robot.data.root_pos_w[0]), _list(robot.data.root_quat_w[0]))
    if 'quaternion' in request:
        task_r = _array(scene.layout.task_rotation, (3, 3))
        rotation = task_r @ _rotation(request['quaternion'])
    else:
        rotation = base[:3, :3] @ _rotation(_list(controller.targets[side][1][0]))
    out = np.eye(4); out[:3, :3] = rotation; out[:3, 3] = tcp_world
    return out, request.get('allowed_contact_pairs', [])


def capture_scene(scene, controller, side, task_tcp_goal):
    """Read a frozen native collision world, including measured movable frames.

    Mesh vertices are transformed relative to their actual rigid body before
    applying measured PhysX body poses. Static stage transforms are used only
    for genuinely static collision prims. Collision visibility has no effect.
    """
    from pxr import Usd, UsdGeom, UsdPhysics
    import omni.usd
    stage = omni.usd.get_context().get_stage(); cache = UsdGeom.XformCache()
    target_world, allowed = _target(scene, controller, side, task_tcp_goal)
    objects, contacts = controller.snapshot()
    native = {}; robots = {}
    for s, robot in scene.robots.items():
        body_names = list(robot.body_names)
        body_p = _list(robot.data.body_pos_w[0]); body_q = _list(robot.data.body_quat_w[0])
        for name, p, q in zip(body_names, body_p, body_q):
            native[f'/World/{s}_robot/{name}'] = _matrix(p, q)
        arm, fingers, bid = controller.ids[s]
        actual_p, actual_q = controller.pose(s)
        robots[s] = dict(joint_names=list(robot.joint_names), qpos=_list(robot.data.joint_pos[0]),qvel=_list(robot.data.joint_vel[0]),
                         base_world=_matrix(_list(robot.data.root_pos_w[0]), _list(robot.data.root_quat_w[0])).tolist(),
                         hand_world=_matrix(body_p[bid], body_q[bid]).tolist(),
                         actual_tcp_base=dict(p=_list(actual_p[0]), q=_list(actual_q[0])))
    rigid_body_witnesses={}
    for name, obj in scene.objects.items():
        native['/World/Props/'+name] = _matrix(_list(obj.data.root_pos_w[0]), _list(obj.data.root_quat_w[0]))
        try:
            view=obj.root_physx_view;paths=[str(p)for p in view.prim_paths];count=int(view.count)
            witness=dict(proof_source='live_physx_view_and_nearest_usd_api',native_view_prim_paths=paths,
                         native_view_count=count,native_stage_id=int(omni.usd.get_context().get_stage_id()))
            if count==1 and len(paths)==1:
                root=paths[0];root_prim=stage.GetPrimAtPath(root);api=UsdPhysics.RigidBodyAPI(root_prim)
                transform=_list(view.get_transforms())[0]
                witness.update(native_root_path=root,usd_root_has_rigid_body_api=bool(root_prim.HasAPI(UsdPhysics.RigidBodyAPI)),
                               usd_root_rigid_body_enabled=api.GetRigidBodyEnabledAttr().Get(),
                               pose_world=_matrix(transform[:3],[transform[6],*transform[3:6]]).tolist(),
                               native_mass_kg=_list(view.get_masses()),cached_owner_pose_world=native['/World/Props/'+name].tolist())
            rigid_body_witnesses[name]=witness
        except Exception as exc:
            rigid_body_witnesses[name]=dict(readback_error=repr(exc))
    for name, mechanism in getattr(scene, 'mechanisms', {}).items():
        for n, p, q in zip(mechanism.body_names, _list(mechanism.data.body_pos_w[0]), _list(mechanism.data.body_quat_w[0])):
            # USD body paths are looked up by exact body name under this mechanism.
            roots = [p for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Mechanisms/'+name), Usd.TraverseInstanceProxies()) if p.GetName() == n]
            if len(roots) == 1: native[str(roots[0].GetPath())] = _matrix(p, q)
    shapes = []; skipped_active = []; missing = []; enabled_paths = []
    for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
        if not prim.HasAPI(UsdPhysics.CollisionAPI): continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is False: continue
        path = str(prim.GetPath()); enabled_paths.append(path)
        if path.startswith(f'/World/{side}_robot/'):
            skipped_active.append(path)
        owner = next((p for p in sorted(native, key=len, reverse=True) if path == p or path.startswith(p+'/')), None)
        # Any dynamic body without a measured frame makes the world incomplete.
        ancestor = prim; dynamic = False; nearest_rigid_root=None
        while ancestor and not ancestor.IsPseudoRoot():
            dynamic |= ancestor.HasAPI(UsdPhysics.RigidBodyAPI)
            if nearest_rigid_root is None and ancestor.HasAPI(UsdPhysics.RigidBodyAPI) and UsdPhysics.RigidBodyAPI(ancestor).GetRigidBodyEnabledAttr().Get()is not False:
                nearest_rigid_root=str(ancestor.GetPath())
            ancestor = ancestor.GetParent()
        if dynamic and owner is None:
            missing.append(dict(path=path, reason='No measured rigid-body pose')); continue
        group = 'static'; actor = path
        if path.startswith('/World/Props/'):
            actor = path.split('/')[3]; group = 'prop'
        elif path.startswith('/World/Mechanisms/'):
            actor = '/'.join(path.split('/')[3:5]); group = 'mechanism'
        elif path.startswith('/World/') and '_robot/' in path:
            actor = owner or path; group = 'active_robot' if path.startswith(f'/World/{side}_robot/') else 'other_robot'
        source_world = np.array(cache.GetLocalToWorldTransform(prim), dtype=float).T
        frame = np.eye(4) if owner is None else native[owner]
        local = source_world if owner is None else np.linalg.inv(np.array(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(owner)), dtype=float).T) @ source_world
        proxy = 'native_mesh_convex_hull'
        if prim.IsA(UsdGeom.Mesh):
            points = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=float)
        else:
            # Exact native local extent; convex hull of transformed corners is a
            # conservative proxy for sphere/cylinder/capsule and exact for Cube.
            boundable = UsdGeom.Boundable(prim)
            if not boundable:
                # USD robot importer authors CollisionAPI on an Xform whose
                # instance-proxy child owns the actual STL mesh. Expand real
                # children, retaining one conservative hull per collision root.
                descendants = [p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh)]
                if not descendants:
                    missing.append(dict(path=path, reason='Unsupported collision subtree without native mesh')); continue
                pieces = []
                for child in descendants:
                    child_world = np.array(cache.GetLocalToWorldTransform(child), dtype=float).T
                    pieces.append(_vertices(np.linalg.inv(source_world) @ child_world, np.asarray(UsdGeom.Mesh(child).GetPointsAttr().Get(), dtype=float)))
                points = np.concatenate(pieces); proxy = 'native_collision_subtree_convex_hull'
            else:
                extent = boundable.ComputeExtent(Usd.TimeCode.Default())
                if extent is None or len(extent) != 2:
                    missing.append(dict(path=path, reason='Native local collision extent unavailable')); continue
                lo, hi = np.asarray(extent, dtype=float)
                points = np.array(list(itertools.product(*zip(lo, hi))))
                proxy = 'native_primitive_extent_hull'
        if len(points) < 4:
            missing.append(dict(path=path, reason='Fewer than four collision vertices')); continue
        vertices = _vertices(local, points)
        shapes.append(dict(name=path, actor=actor, group=group, owner=owner,
                           native_rigid_root_path=nearest_rigid_root,
                           pose_world=frame.tolist(), vertices=vertices.tolist(), proxy=proxy,
                           native_type=prim.GetTypeName(), source_prim=path))
    source_review=None
    if scene.spec['id']=='E42':
        from .author_e42_edge_policy import reviewed_source
        try:source_review=reviewed_source(scene.spec['objects'],scene.spec['semantic'],scene.spec.get('source_binding_sha256'))
        except KeyError:source_review=None  # Legacy noncandidate bindings keep prior behavior.
    profile = scene.embodiment.config.get('author_recording', {}).get('mplib_profile') or os.environ.get('VIC_AUTHOR_MPLIB_PROFILE')
    grasp = {name: bool(value.get('grasp', [False, False])[0 if side == 'left' else 1]) for name, value in objects.items()}
    attached = [name for name, held in grasp.items() if held]
    return dict(schema='author-mplib-scene-v1', task=scene.spec['id'], variant=scene.spec['variant'], side=side,
                native_rigid_body_witnesses=rigid_body_witnesses,
                physics_tick=controller.physics_ticks, dt=float(controller.dt), e42_source_review=source_review,
                native_contact_forces=[dict(pair=sorted(pair),force_n=float(force))for pair,force in controller.contact_forces.items()], robots=robots,
                native_robot_usd_sha256=_sha(scene.embodiment.asset_path()), tcp_offset_hand=list(scene.embodiment.tcp), target_tcp_world=target_world.tolist(),
                allowed_contact_pairs=allowed, attached_actors=attached, native_grasp=grasp,
                contacts=[sorted(pair) for pair in contacts], shapes=[s for s in shapes if s['group'] != 'active_robot'],
                active_native_geometry=[s for s in shapes if s['group'] == 'active_robot'], missing_geometry=missing,
                active_collision_prims=skipped_active, enabled_collision_prim_count=len(enabled_paths),
                object_ids=list(scene.objects), reviewed_grasp_points_local={o['id']:o['grasp_point_local'] for o in scene.spec['objects'] if o.get('grasp_point_local') is not None}, mechanism_ids=list(getattr(scene, 'mechanisms', {})),
                object_native_velocity_world={name:_list(obj.data.root_vel_w[0])for name,obj in scene.objects.items()},
                profile=str(profile) if profile else None, source_binding_sha256=scene.spec.get('source_binding_sha256'))


def validate_scene(snapshot, profile):
    """Strict coverage and contact-policy gate before constructing a planner."""
    if snapshot.get('schema') != 'author-mplib-scene-v1': raise ValueError('Wrong scene schema')
    if not math.isclose(snapshot['dt'], DT, abs_tol=1e-9): raise ValueError('Native physics dt must be 4ms')
    if snapshot.get('native_robot_usd_sha256') != NATIVE_USD_SHA256: raise ValueError('Native robot asset differs from calibrated source')
    if snapshot.get('missing_geometry'): raise ValueError('Native geometry coverage incomplete')
    side = snapshot['side']; other = 'left' if side == 'right' else 'right'
    if set(snapshot['robots']) != {'left', 'right'}: raise ValueError('Both measured native arms required')
    shapes = snapshot['shapes']
    if not any(s['source_prim'].startswith('/World/Table') for s in shapes): raise ValueError('Native table missing')
    if sum(s['group'] == 'other_robot' and f'/{other}_robot/' in s['source_prim'] for s in shapes) != profile['expected_active_collision_prims']: raise ValueError('Other native arm chain incomplete')
    if len(snapshot['active_collision_prims']) != profile['expected_active_collision_prims']:
        raise ValueError('Active native collision set differs from calibrated model')
    if len(snapshot['active_collision_prims']) + len(shapes) != snapshot['enabled_collision_prim_count']:
        raise ValueError('Collision coverage cardinality mismatch')
    for actor in snapshot['object_ids']:
        if not any(s['actor'] == actor for s in shapes): raise ValueError('Missing prop geometry: '+actor)
    if len(snapshot['attached_actors']) > 1: raise ValueError('Multiple held actors require explicit support')
    for actor in snapshot['attached_actors']:
        if not snapshot['native_grasp'].get(actor): raise ValueError('Held actor lacks real two-finger grasp')
    allowed = snapshot['allowed_contact_pairs']
    if len(allowed) > 1: raise ValueError('At most one active intended tool-target contact pair')
    for pair in allowed:
        if len(pair) != 2 or pair[0] not in snapshot['attached_actors'] or pair[1] not in snapshot['object_ids']:
            raise ValueError('Contact exemption must be held tool to named target prop')
        valid = profile.get('intentional_contacts', {}).get(snapshot['task'], [])
        if list(pair) not in valid: raise ValueError('Contact pair outside reviewed task policy')
    return True


def _convex(vertices, fcl):
    from scipy.spatial import ConvexHull
    vertices = _array(vertices)
    hull = ConvexHull(vertices)
    # Convex requires outward CCW faces, not QHull's arbitrary simplicial winding.
    faces = hull.simplices.copy()
    for i, (face, equation) in enumerate(zip(faces, hull.equations)):
        a, b, c = vertices[face]
        if np.dot(np.cross(b-a, c-a), equation[:3]) < 0: faces[i, 1], faces[i, 2] = face[2], face[1]
    keep = np.unique(faces); remap = np.full(len(vertices), -1, dtype=np.int32); remap[keep] = np.arange(len(keep))
    return fcl.Convex(vertices[keep].astype(np.float64), remap[faces].astype(np.int32), True)


def _native_collision_alignment(snapshot, model, planner, q, base):
    """Validate every planned link collider against actual captured native mesh."""
    from transforms3d.euler import euler2mat
    native = snapshot.get('active_native_geometry')
    if not native or len(native) != 11: raise ValueError('Actual native active-arm collision geometry calibration missing')
    urdf = ET.parse(model/'panda.urdf').getroot(); pin = planner.pinocchio_model
    pin.compute_forward_kinematics(q); rows = []
    for shape in native:
        link = shape['source_prim'].split('/')[3]
        collision = urdf.find(f"link[@name='{link}']/collision")
        if collision is None: raise ValueError('Native collider has no source link: '+link)
        mesh = collision.find('geometry/mesh'); filename = model/mesh.get('filename')
        scale = np.array(list(map(float, mesh.get('scale', '1 1 1').split())))
        with filename.open('rb') as stream:
            stream.read(80); count = int.from_bytes(stream.read(4), 'little')
            data = np.frombuffer(stream.read(count*50), dtype=np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3,3)), ('attr', '<u2')]))
        vertices = data['vertices'].reshape(-1, 3).astype(float)*scale
        origin = collision.find('origin'); matrix = np.eye(4)
        if origin is not None:
            matrix[:3, :3] = euler2mat(*map(float, origin.get('rpy', '0 0 0').split()))
            matrix[:3, 3] = list(map(float, origin.get('xyz', '0 0 0').split()))
        link_pose = pin.get_link_pose(planner.link_name_2_idx[link])
        predicted = _vertices(base @ _matrix(link_pose.p, link_pose.q) @ matrix, vertices)
        measured = _vertices(np.array(shape['pose_world']), shape['vertices'])
        error = float(np.max(abs(np.stack([predicted.min(0), predicted.max(0)]) - np.stack([measured.min(0), measured.max(0)]))))
        rows.append(dict(link=link, world_bounds_error_m=error, native_min=measured.min(0).tolist(), native_max=measured.max(0).tolist()))
    return rows


def _world_geometry_alignment(planner, snapshot, world_from_planning):
    """Read actual FCL shape transforms; compare with native world geometry.

    This deliberately inspects collision objects after attachment updates, not
    merely the intended input hand-relative transform. Any frame bug is fatal.
    """
    rows = []
    for shape in snapshot['shapes']:
        obj = planner.planning_world.get_object(shape['name'])
        if len(obj.shapes) != 1: raise ValueError('Unexpected compound wrapper for native source shape')
        actual = obj.shapes[0]; actual_pose = actual.get_pose()
        planning_matrix = _matrix(actual_pose.p, actual_pose.q)
        actual_world = world_from_planning @ planning_matrix
        native_world = _array(shape['pose_world'], (4,4))
        vertices = np.asarray(actual.get_collision_geometry().get_vertices(), dtype=float).reshape(-1,3)
        planned_vertices = _vertices(actual_world, vertices)
        native_vertices = _vertices(native_world, vertices)
        original_native_vertices = _vertices(native_world, shape['vertices'])
        vertex_error = float(np.max(np.linalg.norm(planned_vertices-native_vertices, axis=1)))
        bounds_error = float(np.max(abs(np.stack((planned_vertices.min(0),planned_vertices.max(0)))-np.stack((original_native_vertices.min(0),original_native_vertices.max(0))))))
        row = dict(name=shape['name'],actor=shape['actor'],attached=shape['actor'] in snapshot['attached_actors'],
                   fcl_object_pose_planning=_matrix(obj.pose.p,obj.pose.q).tolist(),
                   fcl_shape_local_pose=_matrix(obj.shape_poses[0].p,obj.shape_poses[0].q).tolist(),
                   fcl_shape_pose_planning=planning_matrix.tolist(),fcl_shape_pose_world=actual_world.tolist(),
                   native_pose_world=native_world.tolist(),max_vertex_error_m=vertex_error,bounds_error_m=bounds_error,
                   actual_fcl_bounds_world=[planned_vertices.min(0).tolist(),planned_vertices.max(0).tolist()],
                   native_bounds_world=[original_native_vertices.min(0).tolist(),original_native_vertices.max(0).tolist()])
        if row['attached']:
            attached = planner.planning_world.get_attached_object(shape['name'])
            pose = attached.get_attached_link_global_pose();relative = attached.get_pose()
            row.update(api_attached_link_pose_planning=_matrix(pose.p,pose.q).tolist(),
                       api_relative_pose=_matrix(relative.p,relative.q).tolist())
        rows.append(row)
    return rows


def _allow_grasp_palm_envelope(planner, snapshot, collisions, diagnostics, profile):
    """Allow only measured-held shape/palm grasp contact, never arm/environment."""
    if profile.get('allow_measured_grasp_palm_contact') is not True: return
    shape_map = {s['name']:s for s in snapshot['shapes']}
    palm = next((s for s in snapshot.get('active_native_geometry', []) if s['source_prim'].split('/')[3] == 'panda_hand'), None)
    if palm is None: raise ValueError('Actual native palm geometry required for grasp-envelope policy')
    palm_vertices = _vertices(np.array(palm['pose_world']),palm['vertices']); seen = set()
    for collision in collisions:
        names = (collision['link1'],collision['link2'])
        if 'panda_hand' not in names: continue
        name = names[1] if names[0] == 'panda_hand' else names[0]
        shape = shape_map.get(name)
        if shape is None or shape['actor'] not in snapshot['attached_actors'] or not snapshot['native_grasp'].get(shape['actor']): continue
        if name in seen: continue
        seen.add(name)
        attached = planner.planning_world.get_attached_object(name)
        touch = list(attached.get_touch_links())
        if 'panda_hand' not in touch: attached.set_touch_links(touch+['panda_hand'])
        planner.acm.set_entry(name,'panda_hand',True)
        vertices = _vertices(np.array(shape['pose_world']),shape['vertices'])
        overlap = np.maximum(0.,np.minimum(vertices.max(0),palm_vertices.max(0))-np.maximum(vertices.min(0),palm_vertices.min(0)))
        measured = snapshot['robots'][snapshot['side']];tcp = np.array(measured['hand_world']);offset = np.eye(4);offset[:3,3] = snapshot['tcp_offset_hand'];tcp = tcp@offset
        native_tcp_in_actor = (np.linalg.inv(np.array(shape['pose_world']))@tcp)[:3,3]
        diagnostics['ignored_collision_pairs'].append(dict(pair=[name,'panda_hand'],actors=[shape['actor'],snapshot['side']+'_palm'],reason='grasp envelope',
            bilateral_native_grasp_required=True,actual_fcl_palm_overlap_observed=True,native_aabb_overlap_extent_m=overlap.tolist(),
            overlap_metric_note='Conservative native collision-envelope AABB overlap, not measured PhysX penetration depth',
            native_tcp_in_actor_local=native_tcp_in_actor.tolist(),
            reviewed_grasp_point_local=snapshot.get('reviewed_grasp_points_local',{}).get(shape['actor']),
            allowed_links=['panda_hand','panda_leftfinger','panda_rightfinger'],
            excluded_links=['panda_link6','panda_link7','other_arm','Table','Ground']))


def _collisions(planner, q):
    return [dict(link1=c.link_name1, link2=c.link_name2, object1=getattr(c, 'object_name1', ''), object2=getattr(c, 'object_name2', '')) for c in planner.check_for_self_collision(q) + planner.check_for_env_collision(q)]


def _uniform(result, start):
    """TOPP samples use linspace with a variable dt; resample their actual times."""
    from scipy.interpolate import CubicHermiteSpline
    times = _array(result['time']); pos = _array(result['position']); vel = _array(result['velocity'])
    if len(times) < 2 or not np.all(np.diff(times) > 0): raise ValueError('Invalid TOPP time grid')
    count = math.ceil(float(times[-1])/DT); ts = np.arange(count+1)*DT
    curve = CubicHermiteSpline(times, pos, vel)
    clipped = np.minimum(ts, times[-1]); out = curve(clipped); velocity = curve(clipped, 1)
    out[ts >= times[-1]] = pos[-1]; velocity[ts >= times[-1]] = 0.
    if np.linalg.norm(out[0]-start, np.inf) > 1e-7: raise ValueError('Planner changed measured start q')
    out[0] = start
    return out, velocity


def _uniform_limited(result,start,velocity_limits,acceleration_limit):
    """Slow the unchanged Hermite path if interpolation exceeds private limits."""
    from scipy.interpolate import CubicHermiteSpline
    times=_array(result['time']);positions=_array(result['position']);velocities=_array(result['velocity'])
    if len(times)<2 or not np.all(np.diff(times)>0):raise ValueError('Invalid TOPP grid')
    if np.max(abs(velocities[-1]))>1e-7:raise ValueError('Time-only retiming requires the original TOPP endpoint velocity to be zero')
    curve=CubicHermiteSpline(times,positions,velocities);c=curve.c;h=np.diff(times)[:,None]
    critical=np.divide(-c[1],3*c[0],out=np.zeros_like(c[1]),where=abs(c[0])>1e-15);critical=np.clip(critical,0,h)
    v0=c[2];v1=3*c[0]*h*h+2*c[1]*h+c[2];vc=3*c[0]*critical*critical+2*c[1]*critical+c[2]
    vmax=np.maximum.reduce([abs(v0).max(0),abs(v1).max(0),abs(vc).max(0)])
    amax=np.maximum(abs(2*c[1]).max(0),abs(6*c[0]*h+2*c[1]).max(0))
    factor=max(1.,float(np.max(vmax/velocity_limits)),float(np.sqrt(np.max(amax/acceleration_limit))))*1.000001
    duration=float(times[-1])*factor;ts=np.arange(math.ceil(duration/DT)+1)*DT;tau=np.minimum(ts/factor,times[-1])
    p=curve(tau);v=curve(tau,1)/factor;p[ts>=duration]=positions[-1];v[ts>=duration]=0.
    if np.linalg.norm(p[0]-start,np.inf)>1e-7:raise ValueError('Planner changed measured start q')
    p[0]=start
    return p,v,dict(time_scale=factor,original_duration_s=float(times[-1]),duration_s=(len(p)-1)*DT,limits_relaxed=False,
                   original_max_joint_velocity_rad_s=vmax.tolist(),joint_velocity_cap_rad_s=np.asarray(velocity_limits).tolist(),
                   original_velocity_to_cap_ratio=(vmax/velocity_limits).tolist(),original_max_joint_acceleration_rad_s2=amax.tolist(),
                   joint_acceleration_cap_rad_s2=float(acceleration_limit),resampled_max_joint_velocity_rad_s=abs(v).max(0).tolist(),
                   resampled_max_joint_acceleration_rad_s2=(abs(np.diff(v,axis=0))/DT).max(0).tolist(),
                   method='Uniform time stretch of unchanged CubicHermite q(t); no velocity clipping')


def _resample_plan(result,start,velocity_limits,profile):
    """Explicit private retiming opt-in, independent of any contact policy."""
    if profile.get('retime_private_limits')is True:
        return _uniform_limited(result,start,velocity_limits,profile.get('joint_acceleration_cap',1.))
    position,velocity=_uniform(result,start)
    return position,velocity,None


def _verify_path(planner, position, velocity, qfull, indices, limits, vel_limits, diagnostics, sample_policy=None):
    try:
        if len(position) < 2 or (len(position)-1)*DT > 30.: raise ValueError('Path duration outside private 30s limit')
        if not np.isfinite(position).all() or not np.isfinite(velocity).all(): raise ValueError('Nonfinite path')
        if np.any(position < limits[:, 0]-1e-8) or np.any(position > limits[:, 1]+1e-8): raise ValueError('Path violates source joint limits')
        if np.any(abs(velocity) > vel_limits+1e-6): raise ValueError('Path violates source velocity limits')
        if np.any(abs(np.diff(position, axis=0)) > vel_limits*DT+1e-6): raise ValueError('Path finite differences violate source velocity limits')
        checked = 0
        for i, end in enumerate(position):
            start = position[max(0, i-1)]
            n = max(1, math.ceil(float(np.max(abs(end-start)))/.01))
            for fraction in np.linspace(1/n, 1, n):
                q = qfull.copy(); q[indices] = start + fraction*(end-start)
                if sample_policy is not None:sample_policy.apply_sample(q,index=i,fraction=float(fraction))
                collisions = _collisions(planner, q); checked += 1
                if collisions:
                    diagnostics['path_collision'] = dict(sample=i, fraction=float(fraction), pairs=collisions)
                    raise ValueError('Collision on resampled full path')
        diagnostics['path_check'] = dict(samples_checked=checked, command_dt=DT, max_extra_joint_step=.01,
                                       continuous_collision_detection=False,edge_pair_conditions_rechecked_each_sample=sample_policy is not None,
                                       scope='All output samples and refined joint segments against the declared world; permitted edge contact is conditional')
    finally:
        if sample_policy is not None:sample_policy.clear()



def _checked_seed_path(result,q,indices,limits,vel_limits,profile,planner,diagnostics,attempt,edge_policy=None):
    """Validate one solver proposal; explicit retry never relaxes a path gate."""
    diagnostics.pop('path_collision',None)
    try:
        position,velocity,retime=_resample_plan(result,q[indices],vel_limits,profile)
        if retime is not None:attempt['retime']=retime
        _verify_path(planner,position,velocity,q,indices,limits,vel_limits,diagnostics,sample_policy=edge_policy)
    except ValueError as exc:
        from copy import deepcopy
        attempt.update(verification_error=str(exc),path_collision=deepcopy(diagnostics.get('path_collision')))
        if edge_policy is None and profile.get('retry_unverified_seeds')is not True:raise
        return None
    return position,velocity


def plan_snapshot(snapshot, profile):
    """Plan a frozen capture. Refusal always has verified=False and empty arrays."""
    diagnostics = dict(world_coverage_verified=False, ignored_collision_pairs=[], geometry=[], attempts=[])
    output = dict(status='Unverified', verified=False, position=[], velocity=[], dt=DT, joint_names=ARM_NAMES,
                  target_world=snapshot.get('target_tcp_world'), metadata=dict(planner='mplib-0.2.1'), diagnostics=diagnostics)
    edge_policy=None
    try:
        validate_scene(snapshot, profile); diagnostics['world_coverage_verified'] = True
        model = Path(os.path.expandvars(profile['model_dir'])); receipt = json.loads((model/'model_receipt.json').read_text())
        if receipt['source_urdf_sha256'] != SOURCE_URDF_SHA256 or receipt['native_usd_sha256'] != NATIVE_USD_SHA256:
            raise ValueError('Model is not the calibrated native Panda source')
        if not receipt['source_joints_unchanged'] or not receipt['collisions']: raise ValueError('Source joints or collision model invalid')
        if _sha(model/'panda.urdf') != receipt['urdf_sha256']: raise ValueError('Planning URDF hash mismatch')
        for mesh in receipt['collisions']:
            if _sha(model/mesh['file']) != mesh['sha256']: raise ValueError('Native collision mesh hash mismatch')
        proxies = receipt.get('planning_convex_proxies', [])
        if len(proxies) != len(receipt['collisions']): raise ValueError('Native-source conservative convex model missing')
        for proxy in proxies:
            if _sha(model/proxy['convex_file']) != proxy['convex_sha256'] or proxy['source_vertices_containment_max_error_m'] > 1e-8: raise ValueError('Native-source convex proxy invalid')
        diagnostics['active_convex_proxies'] = proxies
        srdf = ET.parse(model/'panda.srdf').getroot()
        ignored = {tuple(sorted((n.get('link1'), n.get('link2')))) for n in srdf.findall('disable_collisions')}
        if ignored != {tuple(sorted(p)) for p in receipt['ignored_adjacent_pairs']}: raise ValueError('SRDF filtering differs from reviewed source adjacency')
        import mplib
        from mplib.collision_detection import fcl
        # plan_pose's public interface uses IK's default 20 samples. This private
        # subclass only raises that per-seed budget using the official IK method.
        class BudgetPlanner(mplib.Planner):
            def IK(self, goal_pose, start_qpos, mask=None, **kwargs):
                kwargs['n_init_qpos'] = max(profile.get('n_init_qpos', 30), kwargs.get('n_init_qpos', 20))
                kwargs['threshold'] = 1e-4
                return super().IK(goal_pose, start_qpos, mask, **kwargs)
        joints = ET.parse(model/'panda.urdf').getroot().findall('joint')
        source_vel = {j.get('name'):float(j.find('limit').get('velocity')) for j in joints if j.find('limit') is not None}
        vel_limits = np.array([min(source_vel[n], profile.get('joint_velocity_cap', .6)) for n in ARM_NAMES])
        planner = BudgetPlanner(urdf=str(model/'panda.urdf'), srdf=str(model/'panda.srdf'), move_group='panda_hand', use_convex=True,
                                joint_vel_limits=vel_limits, joint_acc_limits=np.full(7, profile.get('joint_acceleration_cap', 1.)))
        names = list(planner.user_joint_names); indices = [names.index(n) for n in ARM_NAMES]
        measured = snapshot['robots'][snapshot['side']]; values = dict(zip(measured['joint_names'], measured['qpos']))
        q = np.array([values[n] for n in names]); base = _array(measured['base_world'], (4, 4)); hand_world = _array(measured['hand_world'], (4, 4))
        # MPlib0.2.1 AttachedBody uses pinocchio FK without articulation base.
        # Keep its entire collision world in active-base coordinates so robot,
        # attachments, other arm and environment share one frame.
        planning_from_world = np.linalg.inv(base)
        planner.set_base_pose(mplib.Pose()); planner.robot.set_qpos(q, True)
        diagnostics['planning_frame'] = dict(name='active_robot_base', world_from_planning=base.tolist(),
                                             reason='MPlib0.2.1 AttachedBody omits nonidentity articulation base_pose')
        pin = planner.pinocchio_model; link = planner.link_name_2_idx['panda_hand']; pin.compute_forward_kinematics(q); actual = pin.get_link_pose(link)
        offset = _array(snapshot['tcp_offset_hand'], (3,)); tcp = np.asarray(actual.p)+_rotation(actual.q)@offset
        native_tcp = measured['actual_tcp_base']; pos_error = float(np.linalg.norm(tcp-native_tcp['p'])); rot_error = _angle(actual.q, native_tcp['q'])
        diagnostics['native_fk_gate'] = dict(position_error_m=pos_error, orientation_error_deg=rot_error)
        if pos_error >= .001 or rot_error >= 1.: raise ValueError('Measured native FK calibration failed')
        if np.linalg.norm(offset-[0, 0, .1034]) > 1e-9: raise ValueError('Unexpected actual hand TCP offset')
        diagnostics['native_collision_alignment'] = _native_collision_alignment(snapshot, model, planner, q, base)
        if max(r['world_bounds_error_m'] for r in diagnostics['native_collision_alignment']) >= .001: raise ValueError('Planned/native collider differs >=1mm')
        limits = planner.joint_limits[indices]
        if np.any(q[indices] < limits[:, 0]) or np.any(q[indices] > limits[:, 1]): raise ValueError('Measured start outside source limits; no clipping permitted')
        diagnostics['ignored_collision_pairs'].extend(dict(pair=p, reason='Reviewed fixed/one-joint source adjacency') for p in receipt['ignored_adjacent_pairs'])
        actors = {}; geometries = []
        for shape in snapshot['shapes']:
            geom = _convex(shape['vertices'], fcl); pose = _array(shape['pose_world'], (4, 4)); name = shape['name']
            planner.planning_world.add_object(name, fcl.CollisionObject(geom, _pose(planning_from_world @ pose, mplib)))
            actors.setdefault(shape['actor'], []).append(name); geometries.append(geom)
            diagnostics['geometry'].append({k:shape[k] for k in ('name', 'actor', 'group', 'proxy', 'source_prim')})
            if shape['actor'] in snapshot['attached_actors']:
                relative = np.linalg.inv(hand_world) @ pose
                # Explicit finger-only touch links. Never use auto-touch, which
                # could silently exempt an already intersecting forearm.
                touch = ['panda_leftfinger', 'panda_rightfinger']
                planner.planning_world.attach_object(name, planner.robot.get_name(), link, _pose(relative, mplib), touch)
                diagnostics['ignored_collision_pairs'].extend(dict(pair=[name, n], reason='Measured native two-finger grasp') for n in touch)
                diagnostics.setdefault('attachments', []).append(dict(actor=shape['actor'], shape=name, hand_relative=relative.tolist(), grasp_verified=True))
        for a, b in snapshot['allowed_contact_pairs']:
            for a_name, b_name in itertools.product(actors[a], actors[b]):
                planner.acm.set_entry(a_name, b_name, True)
                diagnostics['ignored_collision_pairs'].append(dict(pair=[a_name, b_name], reason='Explicit single active tool-target contact', actors=[a, b]))
        # Source base is rigidly mounted on the native table. Only base link0
        # may touch the matching native tabletop; no arm/table pair is exempt.
        if profile.get('allow_fixed_base_table_mount', False):
            for shape in snapshot['shapes']:
                if shape['source_prim'] == '/World/Table':
                    planner.acm.set_entry('panda_link0', shape['name'], True)
                    diagnostics['ignored_collision_pairs'].append(dict(pair=['panda_link0', shape['name']], reason='Explicit fixed native base/table mount'))
        collisions = _collisions(planner, q)
        diagnostics['world_geometry_alignment'] = _world_geometry_alignment(planner, snapshot, base)
        if any(max(row['max_vertex_error_m'], row['bounds_error_m']) >= .001 for row in diagnostics['world_geometry_alignment']): raise ValueError('Actual FCL/native world geometry mismatch >=1mm')
        if profile.get('allow_same_native_rigid_body_internal_shapes')is True:
            from .author_native_compound import allow_native_compound_internal_pairs
            diagnostics['start_collisions_before_native_compound']=collisions
            allow_native_compound_internal_pairs(planner,snapshot,diagnostics,profile)
            collisions=_collisions(planner,q)
        diagnostics['start_collisions_before_grasp_envelope'] = collisions
        _allow_grasp_palm_envelope(planner, snapshot, collisions, diagnostics, profile)
        edge_policy=None
        if profile.get('e42_edge_group',{}).get('enabled')is True:
            from .author_e42_edge_policy import E42EdgeGroupPolicy
            edge_policy=E42EdgeGroupPolicy(planner,snapshot,profile,base,hand_world,diagnostics)
            edge_policy.apply_sample(q,index='native start')
        collisions = _collisions(planner, q)
        diagnostics['start_collisions'] = collisions
        if collisions: raise ValueError('Measured start collides in declared conservative world')
        goal = _array(snapshot['target_tcp_world'], (4, 4)); hand_goal = goal.copy(); hand_goal[:3, 3] -= hand_goal[:3, :3] @ offset
        output['target_world'] = dict(tcp=goal.tolist(), hand=hand_goal.tolist())
        mask = np.array([n not in ARM_NAMES for n in names], dtype=bool)
        for seed in profile.get('seeds', [1, 2, 3]):
            if seed <= 0: raise ValueError('Positive OMPL seeds required')
            mplib.set_global_seed(seed)
            if edge_policy is not None:
                edge_policy.seed=seed;edge_policy.allow_search_goal(hand_goal)
            result = planner.plan_pose(_pose(planning_from_world @ hand_goal, mplib), q.copy(), mask=mask, time_step=DT,
                                       planning_time=profile.get('planning_time', 5.), rrt_range=.05,
                                       fix_joint_limits=False, wrt_world=False, simplify=True)
            attempt = dict(seed=seed, status=result['status']); diagnostics['attempts'].append(attempt)
            if result['status'] != 'Success': continue
            audit_start=len(edge_policy.data['sample_audit'])if edge_policy is not None else None
            checked=_checked_seed_path(result,q,indices,limits,vel_limits,profile,planner,diagnostics,attempt,edge_policy)
            if checked is None:continue
            position,velocity=checked
            if edge_policy is not None:edge_policy.data['accepted_sample_audit_range']=[audit_start,len(edge_policy.data['sample_audit'])]
            # Rejected-seed collisions remain in their attempt records. They
            # are not collisions on this independently reverified path.
            diagnostics.pop('path_collision',None)
            end = q.copy(); end[indices] = position[-1]; pin.compute_forward_kinematics(end); pose = pin.get_link_pose(link)
            tcp_base = np.asarray(pose.p)+_rotation(pose.q)@offset; end_tcp = base[:3, :3]@tcp_base+base[:3, 3]
            pos_error = float(np.linalg.norm(end_tcp-goal[:3, 3])); orientation_error = _angle(_quat(base[:3, :3]@_rotation(pose.q)), _quat(goal[:3, :3]))
            diagnostics['endpoint'] = dict(position_error_m=pos_error, orientation_error_deg=orientation_error)
            if pos_error >= .001 or orientation_error >= 1.: raise ValueError('Planned endpoint differs from requested TCP pose')
            output.update(status='Success', verified=True, position=position.tolist(), velocity=velocity.tolist())
            output['metadata'].update(schema='author-joint-path-v1', source_urdf_sha256=SOURCE_URDF_SHA256,
                                      world_physics_tick=snapshot['physics_tick'], planning_frame='active_robot_base',
                                      world_from_planning=base.tolist(), attached_world_geometry_validated=True, source_binding_sha256=snapshot.get('source_binding_sha256'),
                                      grasp_actors=snapshot['attached_actors'], requires_native_grasp_guard=bool(snapshot['attached_actors']),
                                      frozen_other_arm=True, other_arm_side='left' if snapshot['side'] == 'right' else 'right',
                                      other_arm_joint_names=snapshot['robots']['left' if snapshot['side'] == 'right' else 'right']['joint_names'],
                                      other_arm_qpos=snapshot['robots']['left' if snapshot['side'] == 'right' else 'right']['qpos'],
                                      full_world_sampled_collision_checked=True,
                                      requires_native_e42_contact_guards=edge_policy is not None,contact_entry_requires_first_real_contact_stop=edge_policy is not None,
                                      dynamic_target_motion_not_simulated=edge_policy is not None,
                                      validation_scope='Declared native/proxy geometry and conditional source edge contact at all output/refined samples; no continuous collision or dynamic target-motion guarantee')
            return output
        if edge_policy is not None:edge_policy.clear()
        output['status'] = 'PlanningFailed'; return output
    except Exception as exc:
        if edge_policy is not None:edge_policy.clear()
        diagnostics['error'] = repr(exc); return output


def plan(scene, controller, side, task_tcp_goal, *, task_tcp_quaternion=None):
    """Read native scene and return a private 4ms trajectory or explicit refusal."""
    try:
        if task_tcp_quaternion is not None:
            task_tcp_goal = dict(task_tcp_goal) if isinstance(task_tcp_goal, dict) else {'position': task_tcp_goal}
            if 'quaternion' in task_tcp_goal: raise ValueError('Provide task quaternion through one explicit channel')
            task_tcp_goal['quaternion'] = _array(task_tcp_quaternion, (4,)).tolist()
        snapshot = capture_scene(scene, controller, side, task_tcp_goal)
        audit_root=os.environ.get('VIC_AUTHOR_MPLIB_SNAPSHOT_DIR')
        if audit_root:
            destination=Path(audit_root);destination.mkdir(parents=True,exist_ok=True)
            (destination/f'tick-{snapshot["physics_tick"]}-{side}-{time.monotonic_ns()}.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        if not snapshot['profile']: raise ValueError('Private MPlib profile is not enabled')
        profile = json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text())
        if profile.get('e42_edge_group',{}).get('enabled')is True:
            guard=getattr(controller,'_e42_native_contact_guard',None)
            if not callable(guard)or getattr(guard,'covers_e42_native_contacts',False)is not True:
                raise ValueError('Live E42 edge-group planning requires registered full native contact guard')
            guard()
        return plan_snapshot(snapshot, profile)
    except Exception as exc:
        return dict(status='Unverified', verified=False, position=[], velocity=[], dt=DT, joint_names=ARM_NAMES,
                    metadata=dict(planner='mplib-0.2.1'), diagnostics=dict(error=repr(exc)))


def edge_preserving_tcp_goal(actual_tool_world, actual_tcp_world, edge_local,
                             support_normal_local, outward_local, push_direction_world,
                             edge_goal_world, handle_raise_degrees):
    """Pure rigid geometry: pitch handle while preserving the actual working edge.

    Source normal/outward may be nonorthogonal. Its tangent projection defines
    the forward axis; the unchanged source edge line must agree with source Y.
    No task rule, physical object pose or collision policy is modified here.
    """
    tool = _array(actual_tool_world, (4,4)); tcp = _array(actual_tcp_world, (4,4))
    normal = _array(support_normal_local, (3,))
    if np.linalg.norm(normal) < 1e-9: raise ValueError('Source support normal is zero')
    normal = normal/np.linalg.norm(normal)
    outward = _array(outward_local, (3,)); forward = outward-normal*float(outward@normal)
    if np.linalg.norm(forward) < 1e-9: raise ValueError('Source forward and normal are collinear')
    forward /= np.linalg.norm(forward); source_y = np.cross(normal,forward)
    source = np.column_stack((forward,source_y,normal))
    direction = _array(push_direction_world, (3,)).copy()
    if abs(direction[2]) > 1e-8: raise ValueError('Push direction must be world-horizontal')
    if np.linalg.norm(direction) < 1e-9: raise ValueError('Push direction is zero')
    direction /= np.linalg.norm(direction); up = np.array([0.,0.,1.])
    angle = math.radians(float(handle_raise_degrees))
    if not 0. <= angle <= math.pi/2 + 1e-12: raise ValueError('Reviewed E42 edge-push pitch search is limited to 0 through 90 degrees')
    f = math.cos(angle)*direction-math.sin(angle)*up
    y = np.cross(up,direction); n = math.sin(angle)*direction+math.cos(angle)*up
    rotation = np.column_stack((f,y,n)) @ source.T
    edge = _array(edge_local,(3,)); point = _array(edge_goal_world,(3,))
    goal_tool = np.eye(4); goal_tool[:3,:3] = rotation; goal_tool[:3,3] = point-rotation@edge
    goal_tcp = goal_tool @ np.linalg.inv(tool) @ tcp
    predicted_tool = goal_tcp @ np.linalg.inv(tcp) @ tool
    diagnostics = dict(handle_raise_degrees=float(handle_raise_degrees), edge_goal_world=point.tolist(),
                       predicted_edge_world=_vertices(predicted_tool,edge[None])[0].tolist(),
                       edge_error_m=float(np.linalg.norm(_vertices(predicted_tool,edge[None])[0]-point)),
                       tool_goal_world=goal_tool.tolist(), tcp_goal_world=goal_tcp.tolist(),
                       source_orthonormal_basis=source.tolist(), desired_orthonormal_basis=np.column_stack((f,y,n)).tolist(),
                       measured_tcp_to_tool=(np.linalg.inv(tcp)@tool).tolist(),
                       predicted_source_y_world=(rotation@source_y).tolist(),
                       desired_push_direction_world=direction.tolist(),
                       default_expert_changed=False,review_scope='E42 edge push only; not E28/E46 load support')
    return goal_tcp, diagnostics
