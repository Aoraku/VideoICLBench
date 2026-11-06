"""Read-only E43 guide-plane choices which keep the hand out of the ball path.

The two choices are the same source guide plane with opposite long-axis
directions. Only a public-action path proposal is returned. Native grip,
contact and trajectory checks remain necessary after actuation.
"""
import itertools
import json
import numpy as np

from .realworld_tool_expert import ToolExecutionError


GUIDE_SOURCE_SHA = '9e71af43eaa1afcf63198dfc5653f11472fae47d498264b065aa269aa26be611'
LAUNCHER_SOURCE_SHA = 'e4b604171aa6c8c861951de1bd76093010c9cbd649c9580e144fe8b4492717ca'


def collision_shape_vertices(prim, geom, physics):
    """Read a direct enabled shape; parent collision flags are not inherited.

    This asset's visible Mesh explicitly disables collision. Its separate
    enabled Cube is the real collider. USD's collisionEnabled is the shape's
    own property, not an ancestor visibility flag or a compound logical AND.
    """
    if not prim.HasAPI(physics.CollisionAPI):
        return None
    if physics.CollisionAPI(prim).GetCollisionEnabledAttr().Get() is False:
        return None
    if prim.IsA(geom.Mesh):
        points = np.asarray(geom.Mesh(prim).GetPointsAttr().Get(), float)
    elif prim.IsA(geom.Cube):
        size = float(geom.Cube(prim).GetSizeAttr().Get())
        if not np.isfinite(size) or size <= 0:
            raise ToolExecutionError('Finite positive actual launcher Cube size required')
        points = box_points([0., 0., 0.], [size / 2] * 3)
    else:
        raise ToolExecutionError('Unsupported enabled source launcher collision shape: ' + str(prim.GetPath()))
    if (points.ndim != 2 or points.shape[1] != 3 or len(points) < 4
            or not np.isfinite(points).all()):
        raise ToolExecutionError('Finite actual source launcher collision vertices required')
    return points


def launcher_collision_parts(policy, obj, actual):
    """Read the actual source ramp parts, not its sloping empty AABB corners.

    The fixed launcher is one SHA-bound published plank assembly. Each enabled
    collision shape is transformed from its composed USD hierarchy to the
    measured launcher frame. Its convex envelope is conservative for that
    part; distinct parts are kept separate. No physics or USD attribute writes.
    """
    asset = obj.get('mechanical_asset', {})
    if (obj.get('id') != 'launcher' or asset.get('sha256') != LAUNCHER_SOURCE_SHA
            or asset.get('relative_path') != 'source_plank_gravity_ramp_v2.usda'
            or not any(d.get('sha256') == GUIDE_SOURCE_SHA for d in asset.get('dependencies', []))):
        raise ToolExecutionError('Exact source E43 inclined plank collision required')
    from pxr import Usd, UsdGeom, UsdPhysics
    import omni.usd
    stage = omni.usd.get_context().get_stage(); cache = UsdGeom.XformCache()
    body = stage.GetPrimAtPath(f'{policy.a.scene.root_path}/Props/launcher')
    if not body:
        raise ToolExecutionError('Actual fixed source launcher body missing')
    inverse = cache.GetLocalToWorldTransform(body).GetInverse()
    parts = []
    for prim in Usd.PrimRange(body, Usd.TraverseInstanceProxies()):
        points = collision_shape_vertices(prim, UsdGeom, UsdPhysics)
        if points is None:
            continue
        matrix = np.asarray(cache.GetLocalToWorldTransform(prim) * inverse, float)
        local = points @ matrix[:3, :3] + matrix[3, :3]
        if (local.ndim != 2 or local.shape[1] != 3 or len(local) < 4
                or not np.isfinite(local).all()):
            raise ToolExecutionError('Finite source launcher collision part required')
        world = local @ np.asarray(actual['mat']).T + np.asarray(actual['pos'])
        parts.append((str(prim.GetPath()), world))
    if not parts:
        raise ToolExecutionError('Enabled source launcher collision shapes missing')
    return parts


def first_route_failure(local, position, rotation, poses, obstacles, floor):
    """Explain the same conservative whole-route rejection without actuation."""
    from .author_orientation import _axis_angle
    from .execution_design_clip_grasp import convex_meshes_clear
    position, rotation = np.asarray(position), np.asarray(rotation)
    for index, pose in enumerate(poses):
        end_p, end_r = np.asarray(pose['position']), np.asarray(pose['rotation'])
        angle = _axis_angle(end_r @ rotation.T)[1]
        for name, mesh in local:
            sagitta = float(np.linalg.norm(mesh, axis=1).max() * (1 - np.cos(angle / 2)))
            sweep = np.vstack((mesh @ rotation.T + position, mesh @ end_r.T + end_p))
            low = float(sweep[:, 2].min() - sagitta)
            if low < floor + .0002:
                return dict(waypoint=index, carried=name, reason='table', minimum_z_task_m=low,
                            sagitta_m=sagitta, target_position=end_p.tolist())
            for obstacle_name, obstacle in obstacles:
                if not convex_meshes_clear(sweep, obstacle, clearance=.0005 + 2 * sagitta):
                    return dict(waypoint=index, carried=name, reason='obstacle', obstacle=obstacle_name,
                                sagitta_m=sagitta, target_position=end_p.tolist())
        position, rotation = end_p, end_r
    return None


def box_points(center, half):
    center, half = np.asarray(center, float), np.asarray(half, float)
    if (center.shape != (3,) or half.shape != (3,) or np.any(half <= 0)
            or not np.isfinite(np.r_[center, half]).all()):
        raise ValueError('Finite positive source box required')
    return center + np.asarray(list(itertools.product((-1., 1.), repeat=3))) * half


def equivalent_planes(rotation):
    """Reverse the actual guide's local X/Y together, preserving its plane."""
    r = np.asarray(rotation, float)
    if (r.shape != (3, 3) or not np.isfinite(r).all()
            or not np.allclose(r.T @ r, np.eye(3), atol=1e-5)
            or np.linalg.det(r) < .999):
        raise ValueError('Proper measured guide rotation required')
    return (r.copy(), r @ np.diag([-1., -1., 1.]))


def ball_corridor(start, contact, target, floor, radius, allowance=.006):
    """Conservative swept sphere boxes for incoming and outgoing motion.

    The source ball is spherical. Bounding its path by a swept cube is a
    conservative rejection filter, not an alteration of its native collider.
    The short height band includes the planned intercept and real table roll.
    """
    start, contact, target = (np.asarray(x, float).copy() for x in (start, contact, target))
    if (any(x.shape != (3,) for x in (start, contact, target))
            or not np.isfinite(np.r_[start, contact, target, floor, radius, allowance]).all()
            or radius <= 0 or not 0 <= allowance <= .01):
        raise ValueError('Finite source sphere and path required')
    roll = float(floor) + float(radius)
    target[2] = roll
    contact_low = contact.copy(); contact_low[2] = min(roll, contact[2])
    contact_high = contact.copy(); contact_high[2] = max(roll, contact[2])
    pad = np.full(3, float(radius) + float(allowance))
    incoming = np.vstack([box_points(p, pad) for p in (start, contact_low, contact_high)])
    outgoing = np.vstack([box_points(p, pad) for p in (contact_low, contact_high, target)])
    return [incoming, outgoing]


def hand_corridor_clear(hand_meshes, corridors):
    from .execution_design_clip_grasp import convex_meshes_clear
    return all(convex_meshes_clear(mesh, corridor, clearance=.0005)
               for mesh in hand_meshes for corridor in corridors)


def public_turns(position,current,rotations,maximum_degrees=10.):
    from .execution_design_push_rotation_path import actor_rotation_poses
    stopped=np.asarray(current);poses=[]
    for desired in rotations:
        part=actor_rotation_poses(position,stopped,desired,maximum_degrees)
        poses+=part
        if part:stopped=np.asarray(part[-1]['rotation'])
    return poses,stopped


def public_route(position, current, desired, approach, maximum_step_m=.025,
                 maximum_degrees=10.,rotation_waypoints=None):
    """The same dominant-axis wrist turns and axiswise translations as expert."""
    from .execution_design_push_rotation_path import actor_rotation_poses
    from .execution_design_tool_pose_paths import append_public_move
    position, approach = np.asarray(position, float), np.asarray(approach, float)
    turns,stopped=public_turns(position,current,
        [desired]if rotation_waypoints is None else rotation_waypoints,maximum_degrees)
    poses = list(turns)
    height = max(float(position[2]), float(approach[2]) + .055)
    cursor = append_public_move(poses, position, [*position[:2], height], stopped, maximum_step_m)
    cursor = append_public_move(poses, cursor, [*approach[:2], height], stopped, maximum_step_m)
    append_public_move(poses, cursor, approach, stopped, maximum_step_m)
    return poses, stopped


def select(policy, tool, grip, side, guide_plan, point):
    """Select one of two equivalent planes without issuing any action.

    Caller must execute ``target_actor_rotation`` with ``rotate_actor`` and
    then move the real working point to ``point``. This helper takes no world
    ticks, changes no actuator/evaluator state, and rejects both on failure.
    """
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_tool_route_clearance import swept_route_clear
    from .execution_design_push_rotation_path import actor_rotation_poses

    if (policy.task != 'E43' or side not in ('left', 'right')
            or not policy.a.control_report.get('engineering_reference_only')
            or policy.spec.get('execution_design', {}).get('revision') != 'embodied50-execution-v3-20261102'):
        raise ToolExecutionError('Explicit E43 v3 engineering guide reference required')
    objects = {o['id']: o for o in policy.spec['objects']}
    obj = objects[tool['actor']]
    if (tool['actor'] != 'guide' or obj.get('source_asset', {}).get('sha256') != GUIDE_SOURCE_SHA
            or not np.allclose(obj['size'], [.09, .003, .015], atol=1e-10, rtol=0)):
        raise ToolExecutionError('Exact unchanged source guide required')
    policy.require_held(grip, side)
    values, _ = policy.snapshot(); body = values[tool['actor']]
    point = np.asarray(point, float); body_r = np.asarray(body['mat']); body_p = np.asarray(body['pos'])
    measured = capture(policy.a, policy.c, side)
    tcp = np.asarray(measured['position']); current = np.asarray(measured['rotation_task'])
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ToolExecutionError('Finite actual guide intercept required')
    relative_hand = body_r.T @ current
    offset = body_r.T @ (tcp - body_p)
    work = np.asarray(tool['working_local'], float)
    names = ('panda_hand', *policy.a.scene.embodiment.fingers)
    hand_local = [(actual_mesh(policy.a, side, n) - tcp) @ current for n in names]
    source_local = box_points(obj.get('local_bounds_center', (0, 0, 0)), obj['size'])
    guide_local = (source_local @ body_r.T + body_p - tcp) @ current
    named_local = [('guide_source_box', guide_local), *zip(names, hand_local)]
    local = [m for _, m in named_local]
    other = 'left' if side == 'right' else 'right'
    named_obstacles = [(other + '/' + n, actual_mesh(policy.a, other, n)) for n in names]
    named_obstacles += [('launcher/' + path, mesh)
                        for path, mesh in launcher_collision_parts(policy, objects['launcher'], values['launcher'])]
    fixture = objects['gate']; actual = values['gate']
    mesh = box_points(fixture.get('local_bounds_center', (0, 0, 0)), fixture['size'])
    named_obstacles.append(('gate_source_box', mesh @ np.asarray(actual['mat']).T + actual['pos']))
    floor = table_bounds_task(policy.a.scene)['top']
    radius = float(max(objects['ball']['size']))
    if not np.isclose(radius, .014, atol=1e-10, rtol=0):
        raise ToolExecutionError('Unchanged source E43 ball radius required')
    contact = np.asarray(guide_plan['predicted_ball_contact_center'], float)
    target = np.asarray(policy.destination('ball'), float)
    corridors = ball_corridor(values['ball']['pos'], contact, target, floor, radius)
    # Do not prepare the guide through the still-retained physical source ball.
    named_obstacles.append(('retained_ball_conservative_box',
                            box_points(values['ball']['pos'], np.full(3, radius))))
    obstacles = [m for _, m in named_obstacles]
    if (work.shape != (3,) or not np.isfinite(work).all()
            or not any(np.allclose(work, candidate, atol=1e-10, rtol=0)
                       for candidate in ([0., 0., 0.], [.020, 0., 0.]))):
        raise ToolExecutionError('Reviewed central or +20mm real guide contact patch required')
    # A second source-face patch is allowed only if neither equivalent central
    # pose works. It slides the same physical plane tangentially; the whole
    # guide/launcher sweep is still forbidden, including the upstream tip.
    patches = [work]
    if np.allclose(work, 0., atol=1e-12):
        patches.append(np.array([.020, 0., 0.]))
    rows = []; candidates = []
    for selected_work in patches:
        for equivalent_index, actor_target in enumerate(equivalent_planes(guide_plan['rotation'])):
            candidate_plan=guide_plan;candidate_point=point
            if not np.allclose(selected_work,work,atol=1e-12):
                # A tangential patch shift moves the board's upstream tip.
                # Recompute its real launcher gap for this exact equivalent
                # direction, instead of sliding an old plane into the ramp.
                from .execution_design_e43_guide_plan import response_plan,NATIVE_RESPONSE
                launcher=values['launcher'];fixture=objects['launcher']
                candidate_plan=response_plan(point,policy.s['launcher']['release_direction_task'],target,
                    values['ball']['pos'],
                    launcher['pos']+np.asarray(launcher['mat'])@np.asarray(fixture.get('local_bounds_center',[0,0,0])),
                    launcher['mat'],fixture['size'],body_r,obj['size'],tool['guide_normal_local'],radius,
                    center_relative_work=np.asarray(obj.get('local_bounds_center',[0,0,0]))-selected_work,
                    response=NATIVE_RESPONSE,equivalent_plane=equivalent_index)
                actor_target=np.asarray(candidate_plan['rotation']);candidate_point=np.asarray(candidate_plan['point'])
            corridors=ball_corridor(values['ball']['pos'],candidate_plan['predicted_ball_contact_center'],
                                    target,floor,radius)
            desired = actor_target @ relative_hand
            turns = actor_rotation_poses(tcp, current, desired, float(policy.max_deg))
            stopped = np.asarray(turns[-1]['rotation']) if turns else current
            stopped_actor = stopped @ relative_hand.T
            approach = candidate_point + stopped_actor @ (offset - selected_work)
            poses, stopped = public_route(tcp, current, desired, approach,
                                           policy.max_mm / 1000., float(policy.max_deg))
            placed_hand = [mesh @ stopped.T + approach for mesh in hand_local]
            corridor_clear = hand_corridor_clear(placed_hand, corridors)
            route_clear = swept_route_clear(local, tcp, current, poses, obstacles, floor)
            path = (solve_local_pose_path(measured['position'], measured['rotation_task'], measured['jacobian'],
                                         measured['q'], measured['limits'], poses,max_seconds=15.)
                    if corridor_clear and route_clear else None)
            actor_waypoints=[actor_target];winding_fallback=None
            if (path and not path['feasible']and path['rows']
                    and path['rows'][-1].get('reason')=='joint_margin'):
                # The same end plane has two real yaw windings. A shortest
                # turn can drive joint7 into its bound; use one explicit
                # opposite90degree waypoint, without reducing any margin.
                from .realworld_tool_expert import _axis_rotation
                delta=np.arctan2(actor_target[1,0],actor_target[0,0])-np.arctan2(body_r[1,0],body_r[0,0])
                delta=(delta+np.pi)%(2*np.pi)-np.pi
                if abs(delta)>np.deg2rad(120.):
                    intermediate=_axis_rotation([0.,0.,1.],-np.sign(delta)*np.pi/2)@body_r
                    alternate_targets=[intermediate@relative_hand,desired]
                    _,alternate_stop=public_turns(tcp,current,alternate_targets,float(policy.max_deg))
                    alternate_actor=alternate_stop@relative_hand.T
                    alternate_approach=candidate_point+alternate_actor@(offset-selected_work)
                    alternate_poses,_=public_route(tcp,current,desired,alternate_approach,
                        policy.max_mm/1000.,float(policy.max_deg),rotation_waypoints=alternate_targets)
                    alternate_corridor=hand_corridor_clear(
                        [mesh@alternate_stop.T+alternate_approach for mesh in hand_local],corridors)
                    alternate_clear=swept_route_clear(local,tcp,current,alternate_poses,obstacles,floor)
                    alternate_path=(solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],
                        measured['q'],measured['limits'],alternate_poses,max_seconds=15.)
                        if alternate_corridor and alternate_clear else None)
                    winding_fallback=dict(shortest_yaw_radians=float(delta),original_path=path,
                        alternative_corridor_clear=bool(alternate_corridor),alternative_route_clear=bool(alternate_clear),
                        alternative_path=alternate_path,minimum_margin_not_reduced=True)
                    if alternate_path and alternate_path['feasible']:
                        path=alternate_path;poses=alternate_poses;stopped=alternate_stop
                        stopped_actor=alternate_actor;approach=alternate_approach
                        corridor_clear=alternate_corridor;route_clear=alternate_clear
                        placed_hand=[mesh@stopped.T+approach for mesh in hand_local]
                        actor_waypoints=[intermediate,actor_target]
            hand_center = np.mean(np.concatenate(placed_hand), axis=0)
            outgoing = target - contact; outgoing[2] = 0.; outgoing /= np.linalg.norm(outgoing)
            downstream = float((hand_center - contact) @ outgoing)
            index = len(rows)
            normal = stopped_actor @ np.asarray(tool['guide_normal_local'], float)
            row = dict(index=index, equivalent_index=equivalent_index,
                       target_actor_rotation=actor_target.tolist(),
                       actor_orientation_waypoints=[r.tolist()for r in actor_waypoints],
                       winding_fallback=winding_fallback,
                       predicted_stopped_actor_rotation=stopped_actor.tolist(),
                       working_local=selected_work.tolist(), working_point_task=candidate_point.tolist(),
                       predicted_guide_center_task=(candidate_point - stopped_actor @ selected_work).tolist(),
                       guide_plane_normal_task=normal.tolist(), plane_offset_m=float(normal @ candidate_point),
                       response_plan=candidate_plan,
                       turn_tcp_position=tcp.tolist(), approach_tcp_position=approach.tolist(),
                       ball_corridor_clear=bool(corridor_clear), whole_route_clear=bool(route_clear),
                       route_failure=(first_route_failure(named_local, tcp, current, poses,
                                                         named_obstacles, floor) if not route_clear else None),
                       hand_downstream_projection_m=downstream, continuous_path=path,
                       route_poses=poses)
            rows.append(row)
            if path and path['feasible']:
                candidates.append((downstream, index))
        if candidates:
            break
    chosen = min(candidates)[1] if candidates else None
    report = dict(schema='e43-equivalent-plane-hand-clearance-v1', chosen=chosen, candidates=rows,
                  geometry_modified=False, actuation_performed=False, native_contact_verified=False,
                  ball_corridor_allowance_m=.006, measured_reference=measured)
    report['geometry'] = dict(coordinate_frame='room_task', carried_frame='initial_actual_TCP',
                             carried_local=[dict(name=n, vertices=m.tolist()) for n, m in named_local],
                             obstacles_task=[dict(name=n, vertices=m.tolist()) for n, m in named_obstacles],
                             launcher_source_sha256=LAUNCHER_SOURCE_SHA,
                             launcher_geometry='enabled_direct_USD_collision_shapes_at_actual_rigid_pose',
                             native_cooked_mesh_claimed=False)
    (policy.a.out / 'e43-equivalent-plane-hand-clearance.private.json').write_text(json.dumps(report))
    if chosen is None:
        raise ToolExecutionError('Neither equivalent source guide plane has a hand-clear continuous public route')
    return dict(rows[chosen], candidate_index=chosen, native_contact_verified=False)
