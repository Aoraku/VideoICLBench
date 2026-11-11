"""Pure back-projection of an explicitly public surface depth measurement.

No simulator, files, network, depth sensor, object pose or controller is accessed.
This is arithmetic, not a depth estimator or an authorization boundary: a caller
must obtain both inputs from the same trusted public observation. JSON labels
alone cannot prove the provenance of caller-supplied measurements.

``calibration`` is one camera's public K/T record, enriched with ``frame_id``
and ``camera``. ``measurement`` is the public depth-point result, enriched
by its producer with explicit ``width``, ``height``, ``units='m'``,
``pixel_order='row_col'``, ``pixel_space='native_image'``,
``depth_convention`` and ``target_frame``. Do not infer these from GUI display
size or from a model's guess. Width/height refer to the original calibrated RGB,
not the resized screenshot widget. Only simulator axial depth_m in metres is
accepted. In OpenGL the optical axis points along -Z; OpenCV uses +Z.

Only the named T_task_from_camera or T_world_from_camera is used. Task and world
are never assumed equal. All transforms use column vectors and metre units.
Invalid inputs return valid=False with no coordinates. No confidence is invented.
"""
from copy import deepcopy
import math

import numpy as np


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _finite_json(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_finite_json(v) for v in value)
    if type(value) is dict:
        return all(type(k) is str and _finite_json(v) for k, v in value.items())
    return False


def _matrix(value, shape, reason):
    _require(type(value) is list and len(value) == shape[0] and
             all(type(row) is list and len(row) == shape[1] and
                 all(type(v) in (int, float) for v in row) for row in value), reason)
    result = np.asarray(value, dtype=float)
    _require(np.isfinite(result).all(), reason)
    return result


def project_pixel(calibration, measurement):
    """Return a sensor-derived camera/target surface point, or a reason-only rejection.

    Unknown extra fields (including existing xyz_task_m) are never used as input
    geometry. Output depth remains explicitly tagged as simulator sensor depth.
    """
    try:
        _require(type(calibration) is dict and type(measurement) is dict,
                 'expected_json_objects')
        _require(_finite_json(calibration) and _finite_json(measurement), 'non_finite_or_non_json_input')
        c, m = calibration, measurement
        _require(c.get('available') is True, 'calibration_unavailable')
        _require(m.get('valid') is True, 'measurement_invalid')
        _require(type(c.get('frame_id')) is str and bool(c['frame_id']) and
                 c['frame_id'] == m.get('frame_id'), 'frame_mismatch')
        _require(type(c.get('camera')) is str and bool(c['camera']) and
                 c['camera'] == m.get('camera'), 'camera_mismatch')
        _require(c.get('units') == m.get('units') == 'm', 'metre_units_required')
        sensor = (m.get('measurement_source') == 'simulator_depth' and
                  m.get('method') == 'simulator_axial_depth' and
                  m.get('sensor_source') == 'isaac_camera_distance_to_image_plane' and
                  m.get('estimated') is False and
                  m.get('depth_convention') == 'optical_axis_m')
        _require(sensor and m.get('physical_action') is False,
                 'unsupported_measurement_provenance')
        for field in ('width', 'height'):
            _require(type(c.get(field)) is int and c[field] > 0 and
                     type(m.get(field)) is int and c[field] == m[field],
                     'image_calibration_size_mismatch')
        _require(m.get('pixel_order') == 'row_col' and m.get('pixel_space') == 'native_image',
                 'native_row_col_pixel_required')
        pixel = m.get('pixel')
        _require(type(pixel) is list and len(pixel) == 2 and
                 all(type(v) in (int, float) for v in pixel), 'invalid_pixel')
        row, col = pixel
        _require(0 <= row < c['height'] and 0 <= col < c['width'], 'pixel_out_of_bounds')
        depth = m.get('depth_m')
        _require(type(depth) in (int, float) and depth > 0, 'invalid_depth')
        depth_convention = m.get('depth_convention')
        _require(depth_convention == 'optical_axis_m', 'ambiguous_depth_convention')
        convention = c.get('convention')
        _require(convention in ('opengl', 'opencv'), 'unsupported_camera_convention')
        target = m.get('target_frame')
        _require(target in ('task', 'world'), 'explicit_target_frame_required')
        transform_key = 'T_' + target + '_from_camera'
        _require(transform_key in c, 'target_transform_unavailable')
        k = _matrix(c.get('K'), (3, 3), 'invalid_intrinsics')
        _require(k[0, 0] > 0 and k[1, 1] > 0 and
                 np.allclose(k[2], [0., 0., 1.], atol=1e-10, rtol=0), 'invalid_intrinsics')
        _require(math.isfinite(float(np.linalg.cond(k))) and np.linalg.cond(k) < 1e12,
                 'singular_or_ill_conditioned_intrinsics')
        transform = _matrix(c[transform_key], (4, 4), 'invalid_extrinsics')
        rotation = transform[:3, :3]
        _require(np.allclose(transform[3], [0., 0., 0., 1.], atol=1e-8, rtol=0) and
                 np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0) and
                 abs(float(np.linalg.det(rotation)) - 1.) < 1e-6, 'non_rigid_extrinsics')
        direction = np.linalg.solve(k, np.array([col, row, 1.], dtype=float))
        _require(abs(direction[2]) > 1e-12, 'invalid_camera_ray')
        direction /= direction[2]
        if convention == 'opengl':
            direction *= [1., -1., -1.]
        camera_point = direction * depth
        target_point = rotation @ camera_point + transform[:3, 3]
        _require(np.isfinite(camera_point).all() and np.isfinite(target_point).all(), 'non_finite_projection')
        return dict(valid=True, estimated=False, frame_id=m['frame_id'], camera=m['camera'],
                    pixel=deepcopy(pixel), pixel_order='row_col', pixel_space='native_image',
                    width=c['width'], height=c['height'], units='m',
                    camera_convention=convention, depth_convention=depth_convention,
                    depth_m=depth, xyz_camera_m=camera_point.tolist(),
                    coordinate_frame=target, **{'xyz_' + target + '_m': target_point.tolist()},
                    measurement_source=m['measurement_source'], method=m['method'], physical_action=False,
                    sensor_source=m['sensor_source'],
                    projection_note='Back-projected visible surface; not an object centre or grasp pose')
    except (ValueError, TypeError, KeyError, OverflowError, np.linalg.LinAlgError) as exc:
        return dict(valid=False, reason=str(exc), physical_action=False)
