"""Typed recursive whitelist for browser-visible robot observations.

These functions copy only declared public fields. They never look up simulator
state or scores. Unknown keys and malformed leaves are omitted, including
mappings smuggled into nominal vectors or strings. Dense depth is absent from
observations; a separately requested depth-map may carry its encoded packet.
"""
import math

_MISSING = object()

def _text(x):
    return x if type(x) is str else _MISSING

def _number(x):
    return x if type(x) in (int, float) and math.isfinite(x) else _MISSING

def _integer(x):
    return x if type(x) is int and x >= 0 else _MISSING

def _boolean(x):
    return x if type(x) is bool else _MISSING

def _nullable(fn):
    return lambda x: None if x is None else fn(x)

def _array(fn, length=None, maximum=64):
    def clean(x):
        if type(x) is not list or len(x) > maximum or (length is not None and len(x) != length):
            return _MISSING
        out=[fn(v) for v in x]
        return _MISSING if any(v is _MISSING for v in out) else out
    return clean

def _record(spec):
    def clean(x):
        if type(x) is not dict:return _MISSING
        out={}
        for k, fn in spec.items():
            if k in x:
                v=fn(x[k])
                if v is not _MISSING:out[k]=v
        return out
    return clean

def _fields(names, fn):
    return {name:fn for name in names.split()}

_vec3=_array(_number,3)
_quat=_array(_number,4)
_numeric=_array(_number)
_names=_array(_text)
_mat3=_array(_array(_number,3),3)
_mat4=_array(_array(_number,4),4)
_sides=lambda fn:_record({'left':fn,'right':fn})
_cameras=lambda fn:_record({k:fn for k in ('head','left_wrist','right_wrist')})

_CALIBRATION={
    **_fields('available',_boolean),
    **_fields('reason convention units source pixel_convention optical_convention frame_id camera',_text),
    **_fields('width height',_integer), 'K':_mat3,
    **_fields('T_task_from_camera T_world_from_camera T_world_from_task T_task_from_camera_optical T_world_from_camera_optical',_mat4),
}
_DEPTH_METADATA={
    **_fields('schema source quantity units optical_convention encoding invalid_value rgb_sha256',_text),
    **_fields('width height valid_pixel_count observation_tick',_integer),'available':_boolean,
}

def _sensor(value):
    return _record({'available':_boolean,'reason':_text,'value':_nullable(value)})

_ARM={
    **_fields('tcp_position tcp_position_world_m',_vec3),
    **_fields('tcp_quaternion_wxyz tcp_quaternion_world_wxyz',_quat),
    'joint_names':_names,'joint_positions_rad':_numeric,
    'finger_joint_positions':_numeric,'gripper_open_fraction':_nullable(_number),
    **_fields('finger_joint_position_units holding_status contact_status',_text),
    'measured_sensors':_record({
        'joint_velocities_rad_s':_sensor(_numeric),
        'finger_joint_velocities_m_s':_sensor(_numeric),
        'joint_soft_limits_rad':_sensor(_array(_array(_number,2))),
        'tcp_linear_velocity_task_m_s':_sensor(_vec3),
    }),
}
_CONTROL={
    'status':_text,'reason':_nullable(_text),
    **_fields('requested_delta_m actual_delta_m',_vec3),
    **_fields('position_error_m orientation_error_rad',_number),'joint_limit_names':_names,
}
_LAST_ACTION={
    **_fields('left right',_text),**_fields('step_mm rotation_deg',_number),
    'tracking_error_m':_nullable(_sides(_number)),
    'orientation_error_rad':_sides(_number),'control_feedback':_sides(_record(_CONTROL)),
}
_ROBOT={
    'coordinate_frame':_text,
    'units':_record(_fields('position orientation joints',_text)),
    'observation_tick':_integer,'arms':_sides(_record(_ARM)),
    'camera_calibration':_cameras(_record(_CALIBRATION)),
    'depth_sensors':_cameras(_record(_DEPTH_METADATA)),
    'last_action':_record(_LAST_ACTION),
}
_CONTRACT={
    **_fields('schema depth_source coordinates',_text),
    'sensor_depth_cameras':_array(_text,maximum=3),
    **_fields('simulator_depth_assisted task_object_state_exposed evaluator_exposed',_boolean),
}
_BOUNDS=_record(_fields('min max minimum maximum default',_number))
_ACTION={'tokens':_names,'step_mm':_BOUNDS,'rotation_deg':_BOUNDS}


def public_observation(raw):
    """Project a browser's {frame_id, state} onto the public robot contract."""
    if type(raw) is not dict or type(raw.get('state')) is not dict:
        raise ValueError('Expected browser observation with state')
    frame=raw.get('frame_id')
    if type(frame) is not str or not frame:
        raise ValueError('Expected displayed native frame id')
    state=raw['state']
    if 'frame_id' in state and state['frame_id'] != frame:
        raise ValueError('Browser and state frame mismatch')
    out=_record({'robot_feedback':_record(_ROBOT),'action_schema':_record(_ACTION),
                 'observation_contract':_record(_CONTRACT),'condition':_text,
                 'demo_available':_boolean})(state)
    return dict(schema='videoicl-structured-observation-v1',native_frame_id=frame,**out)


_DEPTH_RESPONSE={
    **_fields('frame_id camera measurement_source method sensor_source units depth_convention pixel_order pixel_space rgb_sha256 target_frame surface_note sampling reason',_text),
    **_fields('valid physical_action estimated',_boolean),
    **_fields('observation_tick width height',_integer),
    'pixel':_array(_number,2),'requested_pixel':_array(_number,2),'depth_m':_number,
    'camera_calibration':_record(_CALIBRATION),
    'depth_metadata':_record(_DEPTH_METADATA),
    'depth':_record(dict(_DEPTH_METADATA,depth_m_base64=_text)),
}

def public_depth_measurement(raw):
    """Project a depth-query response; retain provenance, never computed XYZ."""
    if type(raw) is not dict:raise ValueError('Expected depth response object')
    return _record(_DEPTH_RESPONSE)(raw)
