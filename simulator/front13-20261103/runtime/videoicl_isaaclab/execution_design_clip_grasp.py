"""Measured E40 handle-pair geometry; no actuation or collision certificate."""
import numpy as np


def actual_handles(mechanism, body_geometry):
    points = []
    for name in ('JawPositive', 'JawNegative'):
        position = np.asarray(mechanism['body_pos_task'][name], float)
        rotation = np.asarray(mechanism['body_mat_task'][name], float)
        local = np.asarray(body_geometry[name]['handle_point_body_local'], float)
        if position.shape != (3,) or rotation.shape != (3, 3) or local.shape != (3,):
            raise ValueError('Actual clip body frame and source handle geometry required')
        point = position + rotation @ local
        if not np.isfinite(point).all():
            raise ValueError('Finite actual clip handles required')
        points.append(point)
    points = np.asarray(points)
    gap = float(np.linalg.norm(points[1] - points[0]))
    if gap < .001:
        raise ValueError('Distinct actual clip handles required')
    return points, points.mean(0), (points[1] - points[0]) / gap


def solve_finger_placement(handles, palm, fingers, jaw, floor,
                           maximum_closure=.039, margin=.0002, objective=None,
                           preferred_translation=None, pad_depth_m=None,
                           fixed_translation=None):
    """Find a translation/closure placing both handle points in real pad hulls.

    Meshes are offsets from TCP in a candidate task-frame orientation. LP
    represents ordinary symmetric jaw closing, not a native state assignment.
    The returned candidate still needs IK and a real public-action grasp test.
    """
    from scipy.optimize import linprog
    from scipy.spatial import ConvexHull
    handles = np.asarray(handles, float)
    palm = np.asarray(palm, float)
    fingers = [np.asarray(f, float) for f in fingers]
    jaw = np.asarray(jaw, float)
    if (handles.shape != (2, 3) or len(fingers) != 2 or jaw.shape != (3,)
            or not all(np.isfinite(x).all() for x in [handles, palm, jaw, *fingers])
            or abs(np.linalg.norm(jaw) - 1.) > 1e-6):
        raise ValueError('Finite actual finger and clip geometry required')
    if pad_depth_m is not None and (not np.isfinite(pad_depth_m) or pad_depth_m < margin):
        raise ValueError('Pad depth must be finite and at least the interior margin')
    if fixed_translation is not None:
        fixed_translation = np.asarray(fixed_translation, float)
        if (fixed_translation.shape != (3,) or not np.isfinite(fixed_translation).all()
                or preferred_translation is not None):
            raise ValueError('Finite fixed translation without another preferred pose required')
    candidates = []
    for ordered in (handles, handles[::-1]):
        a, b = [], []
        for point, mesh, sign in zip(ordered, fingers, (-1., 1.)):
            hull = ConvexHull(mesh).equations
            for plane in hull:
                normal, offset = plane[:3], plane[3]
                a.append([* -normal, -sign * float(normal @ jaw)])
                b.append(-offset - float(normal @ point) - margin)
            if pad_depth_m is not None:
                # A point anywhere inside the convex finger can lie behind
                # its toe or back. Require contact near the actual inward
                # face, whose outward normal follows this finger's closing
                # direction. This remains a candidate, never a grip label.
                alignment = hull[:, :3] @ (sign * jaw)
                face = hull[int(np.argmax(alignment))]
                if alignment.max() < .999:
                    break
                normal, offset = face[:3], face[3]
                a.append([*normal, sign * float(normal @ jaw)])
                b.append(float(pad_depth_m + normal @ point + offset))
            a.append([0., 0., -1., -sign * jaw[2]])
            b.append(float(mesh[:, 2].min()) - floor - margin)
            # Linear finger closing must clear the table at both ends, not
            # only after a tilted finger has already risen away from it.
            a.append([0., 0., -1., 0.])
            b.append(float(mesh[:, 2].min()) - floor - margin)
        if pad_depth_m is not None and alignment.max() < .999:
            continue
        a.append([0., 0., -1., 0.])
        b.append(float(palm[:, 2].min()) - floor - margin)
        bounds = [(None, None)] * 3 + [(0., maximum_closure)]
        if fixed_translation is not None:
            bounds[:3] = [(float(x), float(x)) for x in fixed_translation]
        cost = [0., 0., 1., .01] if objective is None else objective
        if preferred_translation is not None:
            preferred = np.asarray(preferred_translation, float)
            if preferred.shape != (3,) or not np.isfinite(preferred).all() or objective is not None:
                raise ValueError('A finite preferred translation without another LP objective is required')
            a = [row + [0., 0., 0.] for row in a]
            for i in range(3):
                for sign in (-1., 1.):
                    row = [0.] * 7; row[i] = sign; row[4+i] = -1.
                    a.append(row); b.append(float(sign * preferred[i]))
            cost = [0., 0., 0., .001, 1., 1., 1.]
            bounds += [(0., None)] * 3
        result = linprog(cost, A_ub=a, b_ub=b, bounds=bounds, method='highs')
        if result.success:
            translation, closure = result.x[:3], float(result.x[3])
            candidates.append(dict(tcp_translation=translation.tolist(), closure_m=closure,
                ordered_handles=ordered.tolist(), native_grasp_verified=False,
                whole_scene_collision_verified=False))
    return candidates


def convex_meshes_clear(first, second, clearance=.002):
    """Conservative geometry filter, never a native collision certificate."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    first, second = np.asarray(first, float), np.asarray(second, float)
    if not all(x.ndim == 2 and x.shape[1] == 3 and np.isfinite(x).all()
               for x in (first, second)):
        raise ValueError('Finite three-dimensional actual collision meshes required')
    if np.any(first.min(0) - second.max(0) > clearance) or np.any(second.min(0) - first.max(0) > clearance):
        return True
    one, two = ConvexHull(first).equations, ConvexHull(second).equations
    for planes, points in ((one, second), (two, first)):
        if np.any(np.min(planes[:, :3] @ points.T + planes[:, 3, None], axis=1) > clearance):
            return True
    planes = np.vstack((one, two))
    result = linprog(np.zeros(3), A_ub=planes[:, :3],
                     b_ub=-planes[:, 3] + clearance / 2,
                     bounds=[(None, None)] * 3, method='highs')
    return result.status == 2  # Infeasible padded-hull intersection only.


def hand_approach_clear(meshes, jaw, plan, obstacles, approach_height):
    """Check the full vertical open-hand sweep and closing at the grasp site."""
    target = np.asarray(plan['position'])
    # A swept convex hull includes all positions along each straight segment;
    # sparse endpoint checks alone can miss an intervening supporting finger.
    dz = np.array([0., 0., max(0., approach_height - target[2])])
    swept = [np.vstack((mesh + target, mesh + target + dz)) for mesh in meshes]
    closure = float(plan['closure_m'])
    for mesh, sign in zip(meshes[1:], (-1., 1.)):
        swept.append(np.vstack((mesh + target, mesh + target + sign * closure * jaw)))
    return all(convex_meshes_clear(mesh, obstacle) for mesh in swept for obstacle in obstacles)


def lift_supported_clip(policy, clip, handle_ref, side):
    """Grip the measured body, then verify the articulated spine really rises.

    The source spine grasp point remains the approach target. Native evidence
    showed the pads contact surrounding jaws under the legacy cooked geometry.
    Source-faithful conditioned geometry uses the original spine contact pair.
    This is only preparation; handle opening and final clamp scoring are separate.
    """
    from .realworld_tool_expert import ToolExecutionError
    bodies = handle_ref.get('grasp_contacts')
    if not isinstance(bodies, (list, tuple)) or len(bodies) != 2 or len(set(bodies)) != 2:
        raise ToolExecutionError('Actual distinct clip jaw contact bodies required')
    record = next((m.get('mechanical_asset', {}) for m in getattr(policy, 'spec', {}).get('mechanisms', [])
                   if m['id'] == clip.get('mechanism')), {})
    conditioned = record.get('reviewed_collision_coordinate_factor') == 100.
    body_ref = policy.clip_ref(clip, 'body_grasp')
    if not conditioned:
        body_ref = dict(body_ref, grasp_contacts=list(bodies))
    policy.acquire(body_ref, side)
    before = policy.frame(body_ref)[0].copy()
    policy.stage('lift-clip-body-for-real-handle-access')
    held = lambda: policy.require_held(body_ref, side)
    policy.move(side, policy.tip(side) + [0., 0., .10], held)
    held()
    after = policy.frame(body_ref)[0]
    if after[2] - before[2] < .08:
        raise ToolExecutionError('Clip spine did not follow preparatory physical lift')
    return body_ref


def squeeze_supported(policy, clip, ref, side):
    """Attempt real two-hand preparation; native evidence remains authoritative."""
    from .execution_design import REVISION_V3, source_sha256
    a = policy.a
    if (policy.task != 'E40' or policy.spec.get('execution_design', {}).get('revision') != REVISION_V3
            or policy.spec['execution_design'].get('source_sha256') != source_sha256(REVISION_V3)
            or not getattr(a, 'control_report', {}).get('engineering_reference_only')):
        raise ValueError('Explicit E40 v3 engineering reference required')
    from .execution_design_clip_handover import squeeze_with_handover
    if getattr(policy, '_e40_table_supported_reference', False):
        from .execution_design_clip_table_support import squeeze_from_table
        support = 'left' if side == 'right' else 'right'
        body_ref = lift_supported_clip(policy, clip, ref, support)
        return squeeze_from_table(policy, clip, ref, body_ref, support, side)
    return squeeze_with_handover(policy, clip, ref, side)
