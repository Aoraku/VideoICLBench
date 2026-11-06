"""Align an actually opened clip across the tray wall using public yaw."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError, _axis_rotation


def jaw_points(policy, clip):
    return np.asarray([policy.point(dict(mechanism=clip['mechanism'], body=clip[k]['body'],
                         local=clip[k]['point_local'])) for k in ('left', 'right')])


def edge_yaw_turns(points, normal=(1., 0.)):
    delta = np.diff(np.asarray(points, float), axis=0)[0, :2]
    normal = np.asarray(normal, float)
    if normal.shape != (2,) or not np.isfinite(np.r_[delta, normal]).all() or min(np.linalg.norm(delta), np.linalg.norm(normal)) < .001:
        raise ValueError('Real opened jaw gap and finite wall normal required')
    angle = np.arctan2(delta[0]*normal[1]-delta[1]*normal[0], delta @ normal)
    angle = (angle + np.pi/2) % np.pi - np.pi/2
    angles = [angle] if abs(angle) < .01 else [angle, angle - np.sign(angle)*np.pi]
    return [_axis_rotation([0., 0., 1.], a) for a in angles]


def align_open_clip(policy, clip, handle_ref, side):
    from .execution_design_clip_handover import public_rotation_poses, rotation_clear, _log
    from .execution_design_native_finger_mesh import measured_mesh
    from .execution_design_mechanism_geometry import collision_parts
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_thin_edge import table_bounds_task
    from .author_orientation import _axis_angle
    policy.require_held(handle_ref, side)
    tcp = policy.tip(side); current = np.asarray(policy.a.tcp_rotation_task(side))
    measured = capture(policy.a, policy.c, side)
    names = ('panda_hand', *policy.a.scene.embodiment.fingers)
    meshes = [measured_mesh(policy.a, side, n) for n in names]
    meshes += [np.asarray(p['vertices_task']) for p in collision_parts(policy.a, clip['mechanism'])]
    local = [(m-tcp) @ current for m in meshes]
    other = 'right' if side == 'left' else 'left'
    obstacles = [measured_mesh(policy.a, other, n) for n in names]
    floor = table_bounds_task(policy.a.scene)['top']; chosen = None
    for turn in edge_yaw_turns(jaw_points(policy, clip)):
        desired = turn @ current; poses = public_rotation_poses(tcp, current, desired)
        path = solve_local_pose_path(measured['position'], measured['rotation_task'], measured['jacobian'],
            measured['q'], measured['limits'], poses, max_rotation_step_rad=np.deg2rad(1.))
        clear = rotation_clear(local, tcp, current, poses, obstacles, floor)
        _log(policy, 'clip-edge-alignment.private.jsonl', dict(path=path, collision_clear=clear, native_success=False))
        if path['feasible'] and clear:
            chosen = desired; break
    if chosen is None:
        raise ToolExecutionError('Opened clip has no real clear yaw path across tray wall')
    policy.stage('clip-align-mouth-across-tray-edge')
    for _ in range(60):
        policy.require_held(handle_ref, side)
        axis, angle = _axis_angle(chosen @ np.asarray(policy.a.tcp_rotation_task(side)).T)
        if angle < np.deg2rad(2.):
            return
        i = int(np.argmax(abs(axis)))
        token = (('ROLL_LEFT','ROLL_RIGHT'), ('PITCH_UP','PITCH_DOWN'), ('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
        policy.act(side, token, degrees=min(7., abs(np.rad2deg(angle*axis[i]))))
    raise ToolExecutionError('Real held clip yaw did not converge across tray edge')


def insertion_point(policy, clip, edge_point):
    target = np.asarray(edge_point, float).copy()
    # Both actual tips must pass the rim, rather than centring one tip above
    # it. This is physical insertion depth, not an extra accuracy condition.
    target[2] -= abs(float(np.diff(jaw_points(policy, clip), axis=0)[0, 2]))/2 + .003
    return target


def require_prior_physical_clamps(policy, count):
    """Keep already completed markers physically clamped across a resume."""
    markers=(['circle','cross'],['square','triangle'],['circle','triangle','cross'])[policy.index]
    clips=list(policy.s['clips'].values())
    for clip, marker in zip(clips[:count], markers[:count]):
        zone=next(z for z in policy.spec['zones'] if z['id']==marker)
        a,b=jaw_points(policy,clip);d=b-a;den=float(d@d)
        point=np.asarray(zone['edge_point'],float)
        t=float((point-a)@d/den) if den>1e-12 else -100.
        near=float(np.linalg.norm(point-(a+np.clip(t,0,1)*d)))
        bodies={clip['left']['contact_body'],clip['right']['contact_body'],
                policy.clip_ref(clip,'body_grasp')['contact_body']}
        hand_contact=any(policy.contact(body,f'{side}_finger{i}')for body in bodies
                         for side in ('left','right')for i in(1,2))
        if (not policy.clip_contact(clip,zone['support']) or hand_contact
                or not -.1<=t<=1.1 or near>clip['capture_radius']):
            raise ToolExecutionError('Checkpoint did not preserve actual clamp at '+marker)
