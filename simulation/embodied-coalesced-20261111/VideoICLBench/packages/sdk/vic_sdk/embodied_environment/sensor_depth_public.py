"""Read-only public sensor queries over an already captured RGB-D observation.

No physics, object state, evaluator, or coordinate estimator is accessed here.
The agent chooses the pixel and computes coordinates from the returned K/T.
"""
import base64
from copy import deepcopy
import hashlib
import math

import numpy as np


CALIBRATION_FIELDS = (
    'available', 'reason', 'width', 'height', 'K', 'convention', 'units',
    'T_task_from_camera', 'T_world_from_camera', 'T_world_from_task',
    'T_task_from_camera_optical', 'T_world_from_camera_optical',
    'source', 'pixel_convention', 'optical_convention',
)


def _valid_calibration(c):
    """Reject corrupt sensor metadata before returning any nominally valid depth."""
    if c.get('units') != 'm' or c.get('convention') not in ('opengl', 'opencv'):
        return False
    def matrix(value, shape):
        if (type(value) is not list or len(value) != shape[0] or
            any(type(row) is not list or len(row) != shape[1] or
                any(type(v) not in (int,float) for v in row) for row in value)):
            raise ValueError('invalid matrix')
        a=np.asarray(value,dtype=float)
        if not np.isfinite(a).all():raise ValueError('nonfinite matrix')
        return a
    k=matrix(c.get('K'), (3,3))
    if (k[0,0] <= 0 or k[1,1] <= 0 or
        not np.allclose(k[2],[0,0,1],atol=1e-10,rtol=0) or np.linalg.cond(k) >= 1e12):
        return False
    transforms={}
    for name in ('T_task_from_camera','T_world_from_camera','T_world_from_task',
                 'T_task_from_camera_optical','T_world_from_camera_optical'):
        if name not in c:continue
        t=matrix(c[name],(4,4));r=t[:3,:3]
        if (not np.allclose(t[3],[0,0,0,1],atol=1e-8,rtol=0) or
            not np.allclose(r.T@r,np.eye(3),atol=1e-6,rtol=0) or
            abs(np.linalg.det(r)-1)>1e-6):return False
        transforms[name]=t
    if not any(k in transforms for k in ('T_task_from_camera','T_world_from_camera')):
        return False
    flip=np.diag([1.,-1.,-1.,1.]) if c['convention']=='opengl' else np.eye(4)
    for target in ('task','world'):
        base='T_'+target+'_from_camera';opt=base+'_optical'
        if base in transforms and opt in transforms:
            if not np.allclose(transforms[base]@flip,transforms[opt],atol=1e-6,rtol=0):return False
    if all(k in transforms for k in ('T_world_from_task','T_task_from_camera','T_world_from_camera')):
        if not np.allclose(transforms['T_world_from_task']@transforms['T_task_from_camera'],
                           transforms['T_world_from_camera'],atol=1e-6,rtol=0):return False
    return True


def public_sensor_query(snapshot, *, frame_id, camera, row=None, col=None, dense=False):
    """Return scalar depth or a validated dense packet, never computed XYZ.

    Pixel centres are integer indices; nearest pixel is selected half-up. No
    smoothing/interpolation across object edges and no invalid-depth filling.
    """
    common = dict(frame_id=frame_id, camera=camera, physical_action=False,
                  measurement_source='simulator_depth', method='simulator_axial_depth',
                  sensor_source='isaac_camera_distance_to_image_plane', estimated=False)
    def invalid(reason):
        return dict(common, valid=False, reason=reason)
    try:
        from .sensor_depth import decode_depth_packet, depth_packet_metadata
        if not isinstance(snapshot, dict):
            return invalid('sensor_snapshot_unavailable')
        packet = snapshot.get('depth', {}).get(camera)
        if not isinstance(packet, dict):
            return invalid('sensor_depth_unavailable')
        rgb = snapshot.get('images', {}).get(camera)
        if not isinstance(rgb, str) or not rgb:
            return invalid('rgb_unavailable')
        digest = hashlib.sha256(base64.b64decode(rgb, validate=True)).hexdigest()
        if packet.get('rgb_sha256') != digest:
            return invalid('rgb_depth_frame_mismatch')
        tick = snapshot.get('observation_tick')
        if type(tick) is not int or tick < 0 or packet.get('observation_tick') != tick:
            return invalid('rgb_depth_tick_mismatch')
        c = snapshot.get('camera_calibration', {}).get(camera)
        if not isinstance(c, dict) or c.get('available') is not True:
            return invalid('calibration_unavailable')
        try:
            if not _valid_calibration(c):
                return invalid('invalid_camera_calibration')
        except (ValueError, TypeError, np.linalg.LinAlgError):
            return invalid('invalid_camera_calibration')
        z = decode_depth_packet(packet)
        if z.shape != (c.get('height'), c.get('width')):
            return invalid('image_calibration_size_mismatch')
        # Decoding must never permit another source or another depth quantity to
        # silently enter the sensor-labelled lane.
        if packet.get('source') != common['sensor_source'] or packet.get('quantity') != 'axial_z':
            return invalid('unsupported_depth_source')
        calibration = {k: deepcopy(c[k]) for k in CALIBRATION_FIELDS if k in c}
        calibration.update(frame_id=frame_id, camera=camera)
        common.update(observation_tick=tick, units='m', width=z.shape[1], height=z.shape[0],
                      depth_convention='optical_axis_m', pixel_order='row_col',
                      pixel_space='native_image', rgb_sha256=digest,
                      target_frame='world' if 'T_world_from_camera' in calibration else 'task',
                      camera_calibration=calibration,
                      surface_note='Visible rendered surface depth, not object centre or grasp pose.')
        if dense:
            # Reconstruct packet through the strict codec so private extra keys
            # can never hitchhike on the public response.
            # Whitelist the actual validated wire fields instead of forwarding
            # arbitrary scene records. Metadata contains no private object data.
            allowed = ('schema','available','encoding','depth_m_base64','width','height','units',
                       'quantity','optical_convention','invalid_value','valid_pixel_count',
                       'source','rgb_sha256','observation_tick')
            public_packet = {k: deepcopy(packet[k]) for k in allowed if k in packet}
            return dict(common, valid=True, depth=public_packet,
                        depth_metadata=depth_packet_metadata(public_packet))
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (row, col)):
            return invalid('invalid_pixel')
        if not (0 <= row < z.shape[0] and 0 <= col < z.shape[1]):
            return invalid('pixel_out_of_bounds')
        r, u = int(math.floor(row + .5)), int(math.floor(col + .5))
        if r >= z.shape[0] or u >= z.shape[1]:
            return invalid('pixel_out_of_bounds')
        value = float(z[r, u])
        if not math.isfinite(value) or value <= 0:
            return dict(invalid('no_valid_surface_depth'), pixel=[r,u])
        return dict(common, valid=True, pixel=[r,u], requested_pixel=[row,col],
                    depth_m=value, sampling='nearest_pixel_half_up_no_interpolation')
    except (ValueError, TypeError, KeyError, OverflowError):
        return invalid('invalid_sensor_packet')
