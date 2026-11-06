"""E38 private engineering: align the actual ring above the actual post.

Only public actions are issued. A successful approach is not a successful
threading receipt: native contact, support and ordering still judge the release.
"""
import json
import numpy as np

from .execution_design import REVISION_V3


def release_target(post_tip, ring_half_height, tcp_offset_z, finger_clear_tcp_z,
                   hole_radius, post_radius):
    tip = np.asarray(post_tip, float)
    values = np.asarray([ring_half_height, tcp_offset_z, finger_clear_tcp_z,
                         hole_radius, post_radius], float)
    if tip.shape != (3,) or not np.isfinite(tip).all() or not np.isfinite(values).all():
        raise ValueError('Finite actual ring and post geometry required')
    clearance = float(hole_radius - post_radius)
    if ring_half_height <= 0 or post_radius <= 0 or clearance <= 0:
        raise ValueError('Actual ring hole must clear the post')
    target = tip.copy()
    target[2] = max(tip[2] + ring_half_height + .004,
                    finger_clear_tcp_z - tcp_offset_z)
    # Bound the Euclidean XY error, rather than accepting 2 mm on each axis
    # when the whole radial insertion allowance is only about 2.5 mm.
    return target, min(.0008, clearance / 3.)


def track_center(read, act, target, radial_tolerance, z_tolerance=.001,
                 max_actions=600, record=lambda row: None):
    target = np.asarray(target, float)
    if target.shape != (3,) or not np.isfinite(target).all() or radial_tolerance <= 0:
        raise ValueError('Finite ring waypoint and positive tolerance required')
    errors = []
    for i in range(max_actions + 1):
        center, held, up = read()
        center = np.asarray(center, float)
        if center.shape != (3,) or not np.isfinite(center).all() or not np.isfinite(up):
            raise RuntimeError('Invalid actual ring pose')
        if not held:
            raise RuntimeError('Actual ring grip lost before aligned release')
        if abs(up) < .995:
            raise RuntimeError('Ring tilted before aligned release')
        error = target - center
        radial = float(np.linalg.norm(error[:2]))
        record(dict(iteration=i, center=center.tolist(), target=target.tolist(),
                    radial_error_m=radial, vertical_error_m=float(error[2]), held=True))
        if radial <= radial_tolerance and abs(error[2]) <= z_tolerance:
            return
        if i == max_actions:
            raise RuntimeError('Actual ring alignment action bound exhausted')
        residual = float(np.linalg.norm(error))
        errors.append(residual)
        if len(errors) >= 25 and errors[-25] - min(errors[-24:]) < .0002:
            raise RuntimeError('Actual ring alignment stalled')
        axis = int(np.argmax(np.abs(error)))
        token = (('FWD', 'BACK'), ('LEFT', 'RIGHT'), ('UP', 'DOWN'))[axis][int(error[axis] < 0)]
        act(token, min(2., abs(float(error[axis])) * 1000.))


def align_above_post(author, name, side):
    spec = author.scene.spec
    if (not getattr(author, '_execution_design_reference_authorized', False)
            or spec['id'] != 'E38'
            or spec.get('execution_design', {}).get('revision') != REVISION_V3):
        raise ValueError('Explicit v3 E38 engineering reference required')
    index = ('left', 'right').index(side)
    state, _ = author.c.snapshot()
    semantic = spec['semantic']
    ring = state[name]
    obj = next(o for o in spec['objects'] if o['id'] == name)
    post = state[semantic['post']]
    tip = np.asarray(post['pos']) + np.asarray(post['mat']) @ np.asarray(semantic['post_tip'])
    half = float((np.abs(ring['mat']) @ np.asarray(obj['size']))[2])
    offset_z = float(author.tip(side)[2] - ring['pos'][2])
    target, radial = release_target(tip, half, offset_z,
        author.floor_clear_tcp(side, floor=float(tip[2]) + .008),
        obj['hole_radius'], semantic['post_radius'])
    author.stage = 'align-actual-ring-above-post-' + name
    def read():
        values, _ = author.c.snapshot()
        value = values[name]
        return value['pos'], bool(value['grasp'][index]), float(value['mat'][2][2])
    def act(token, mm):
        author.act(token if side == 'left' else 'STILL',
                   token if side == 'right' else 'STILL', mm=mm)
    with (author.out / 'actual-ring-alignment.private.jsonl').open('a') as stream:
        def record(row):
            stream.write(json.dumps(dict(row, object=name, side=side,
                action_step=author.c.steps, radial_tolerance_m=radial)) + '\n')
        track_center(read, act, target, radial, record=record)
