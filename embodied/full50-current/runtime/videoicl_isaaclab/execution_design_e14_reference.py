"""Select one actual thin tower layer through public engineering actions."""
import numpy as np
from .execution_design import REVISION_V3


def _scope(author, side, name):
    spec = author.scene.spec
    if (not getattr(author, '_execution_design_reference_authorized', False)
            or spec.get('id') != 'E14'
            or spec.get('execution_design', {}).get('revision') != REVISION_V3
            or side not in ('left', 'right')
            or name not in spec['semantic']['groups']['blocks']):
        raise ValueError('E14 v3 independent layer reference required')
    return next(obj for obj in spec['objects'] if obj['id'] == name)


def measured_layer_band(body, obj):
    """Actual upright box faces; never use the initial authored stack height."""
    pos = np.asarray(body['pos'], float)
    rotation = np.asarray(body['mat'], float)
    half = np.asarray(obj['size'], float)
    if (pos.shape != (3,) or rotation.shape != (3, 3) or half.shape != (3,)
            or not np.isfinite(np.r_[pos, rotation.ravel(), half]).all()
            or rotation[2, 2] < .999 or not .005 <= 2 * half[2] <= .008):
        raise ValueError('Actual upright thin E14 layer geometry required')
    center = pos + rotation @ np.asarray(obj.get('local_bounds_center', [0, 0, 0]), float)
    slope = float(np.abs(rotation[2, :2]) @ half[:2])
    bottom = float(center[2] + slope - rotation[2, 2] * half[2])
    top = float(center[2] - slope + rotation[2, 2] * half[2])
    # Above the target's lower face, so the finger tip cannot also pinch the
    # layer underneath. At least 2 mm of target side remains for real contact.
    toe = float(bottom + .002)
    if bottom < .799 or top - toe < .002:
        raise ValueError('No supported layer side band')
    point = pos + rotation @ np.asarray(obj.get('grasp_point_local', [0, 0, 0]), float)
    return point, toe, float(top)


def align_single_layer(author, side, name):
    obj = _scope(author, side, name)
    for _ in range(8):
        state, _ = author.c.snapshot()
        if any(any(body.get('grasp', ())) for body in state.values()):
            raise RuntimeError('Layer alignment requires an empty open gripper')
        point, toe, top = measured_layer_band(state[name], obj)
        geometry = author.finger_geometry(side)
        if geometry.get('source') != 'actual_collision_mesh_current_body_pose':
            raise ValueError('Actual finger collision geometry required')
        lowest = float(geometry['lowest_z_task_m'])
        tip = np.asarray(author.tip(side), float)
        if not np.isfinite(np.r_[lowest, tip]).all():
            raise ValueError('Nonfinite actual layer grasp geometry')
        error = toe - lowest
        if abs(error) <= .0005 and np.max(np.abs(tip[:2] - point[:2])) <= .0008:
            if lowest > top - .0015:
                raise RuntimeError('Finger tip above the layer side band')
            return
        target = [*point[:2], float(tip[2] + np.clip(error, -.003, .003))]
        author.move_generated({side: target}, tolerance=.0004)
    raise RuntimeError('Actual E14 layer side band did not converge')


def require_single_layer_grasp(author, side, name):
    _scope(author, side, name)
    state, _ = author.c.snapshot()
    index = 0 if side == 'left' else 1
    held = {key for key, body in state.items() if body.get('grasp', [False, False])[index]}
    if held != {name}:
        raise RuntimeError('E14 requires exactly one physically grasped layer: ' + ','.join(sorted(held)))
