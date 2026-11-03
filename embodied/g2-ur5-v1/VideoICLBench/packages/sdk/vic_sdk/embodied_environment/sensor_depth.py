"""Explicit, lossless axial sensor depth transport. No object or score inputs."""
import base64
import hashlib
import numpy as np

SCHEMA = 'videoicl-sensor-depth-v1'

def encode_depth_packet(depth, *, rgb_bytes, observation_tick):
    z = np.asarray(depth, dtype='<f4')
    if z.ndim == 4 and z.shape[0] == 1 and z.shape[-1] == 1:
        z = z[0, :, :, 0]
    elif z.ndim == 3 and z.shape[0] == 1:
        z = z[0]
    elif z.ndim == 3 and z.shape[-1] == 1:
        z = z[:, :, 0]
    if z.ndim != 2 or not all(z.shape):
        raise ValueError('Depth must be a nonempty H x W axial image')
    z = z.copy()
    valid = np.isfinite(z) & (z > 0)
    z[~valid] = np.nan
    return dict(schema=SCHEMA, available=True, source='isaac_camera_distance_to_image_plane',
                quantity='axial_z', units='m', optical_convention='opencv',
                encoding='base64-f32le', invalid_value='NaN', width=int(z.shape[1]),
                height=int(z.shape[0]), valid_pixel_count=int(valid.sum()),
                rgb_sha256=hashlib.sha256(rgb_bytes).hexdigest(), observation_tick=observation_tick,
                depth_m_base64=base64.b64encode(z.tobytes(order='C')).decode('ascii'))

def decode_depth_packet(packet):
    if (packet.get('schema') != SCHEMA or packet.get('available') is not True
            or packet.get('encoding') != 'base64-f32le' or packet.get('quantity') != 'axial_z'
            or packet.get('units') != 'm' or packet.get('optical_convention') != 'opencv'
            or packet.get('source') != 'isaac_camera_distance_to_image_plane'):
        raise ValueError('Unsupported axial depth packet')
    h, w = packet.get('height'), packet.get('width')
    if type(h) is not int or type(w) is not int or min(h,w) <= 0 or h*w > 16777216:
        raise ValueError('Invalid depth dimensions')
    raw=base64.b64decode(packet['depth_m_base64'], validate=True)
    if len(raw) != h*w*4:
        raise ValueError('Depth packet byte count mismatch')
    z=np.frombuffer(raw,dtype='<f4').reshape(h,w).copy()
    z[~np.isfinite(z) | (z <= 0)] = np.nan
    return z

def depth_packet_metadata(packet):
    fields = ('schema', 'available', 'source', 'quantity', 'units', 'optical_convention',
              'encoding', 'invalid_value', 'width', 'height', 'valid_pixel_count',
              'rgb_sha256', 'observation_tick')
    return {k:packet[k] for k in fields if k in packet}
