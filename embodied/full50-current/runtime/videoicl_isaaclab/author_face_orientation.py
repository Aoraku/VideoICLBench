"""Private minimal normal alignment for source face-up / face-down tasks.

Produces actuator rotation requests from measured orientations. It neither
updates physics state nor evaluates task success, and never constrains yaw.
"""
import math
import numpy as np

from .author_orientation import _rotation


def face_alignment(measured_matrix, local_up_axis, face, tolerance_degrees=10.):
    matrix = _rotation(measured_matrix, 'measured source face')
    axis = np.asarray(local_up_axis, float)
    if (axis.shape != (3,) or not np.isfinite(axis).all()
            or np.linalg.norm(axis) < 1e-9 or face not in ('up', 'down')):
        raise ValueError('Reviewed finite source up axis and up/down face required')
    tolerance = float(tolerance_degrees)
    # A private author margin remains substantially tighter than the unchanged
    # native upright dot>.85 acceptance (about31.8deg).
    if not math.isfinite(tolerance) or not 0 < tolerance <= 10.:
        raise ValueError('Private face margin must be in (0,10] degrees')
    measured = matrix @ (axis / np.linalg.norm(axis))
    target = np.array([0., 0., 1. if face == 'up' else -1.])
    cross = np.cross(measured, target)
    sine = float(np.linalg.norm(cross))
    cosine = float(np.clip(measured @ target, -1., 1.))
    angle = math.atan2(sine, cosine)
    reached = angle <= math.radians(tolerance)
    delta = np.eye(3)
    if not reached:
        if sine < 1e-10:
            # A true half-turn: a reproducible perpendicular axis, not a zero
            # cross product or a substituted object pose. For upright +Z this
            # selects +Y, matching the reviewed plate pitch inversion route.
            basis = np.eye(3)[int(np.argmin(np.abs(measured)))]
            rotation_axis = np.cross(measured, basis)
            rotation_axis /= np.linalg.norm(rotation_axis)
        else:
            rotation_axis = cross / sine
        x, y, z = rotation_axis
        skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
        delta = np.eye(3) + math.sin(angle)*skew + (1-math.cos(angle))*(skew @ skew)
    return dict(delta_task=delta, reached=reached, face=face,
                local_up_axis=(axis/np.linalg.norm(axis)).tolist(),
                measured_normal_task=measured.tolist(), target_normal_task=target.tolist(),
                normal_error_degrees=math.degrees(angle), tolerance_degrees=tolerance)
