"""Regression from the measured B275 wrist, not invented reachable joints."""
import json
from pathlib import Path
import numpy as np
from videoicl_isaaclab.execution_design_drawer_ik_probe import solve_candidates
from videoicl_isaaclab.execution_design_e34b_place import yaw_target


def test_measured_twenty_degree_yaw_avoids_low_joint_limit_without_tilt_change():
    data=json.loads((Path(__file__).parent/'fixtures/e34b_low_route_yaw_native.json').read_text())
    measured=data['measured_native_fk'];rotation=np.asarray(measured['rotation_task']);tcp=np.asarray(measured['position'])
    body=data['selected_body'];tray=data['tray'];point=np.asarray(data['handle_point'])
    handle=np.asarray(body['pos'])+np.asarray(body['mat'])@point
    relative=rotation.T@(handle-tcp);relative_body=rotation.T@body['mat']
    bounds=data['bounds'];wanted=np.asarray(tray['pos'])+np.asarray(tray['mat'])@((np.asarray(bounds['lower'])+bounds['upper'])/2)
    targets=[]
    for degrees in (0.,20.):
        changed=yaw_target(rotation,degrees);object_rotation=changed@relative_body
        target_handle=wanted.copy();target_handle[2]=float(tray['pos'][2])+(np.abs(object_rotation)@data['selected_object']['size'])[2]+(object_rotation@point)[2]+.003
        assert bounds['lower'][2]-.003<=target_handle[2]-tray['pos'][2]<=bounds['upper'][2]+.003
        assert np.allclose(object_rotation[2],np.asarray(body['mat'])[2],atol=1e-10)
        target=target_handle-changed@relative
        assert np.allclose(target+changed@relative,target_handle,atol=1e-10)
        targets.append(dict(position=target,rotation=changed))
    actual=solve_candidates(measured['position'],measured['rotation_task'],measured['jacobian'],measured['q'],measured['limits'],targets)
    assert actual[0]['minimum_joint_margin_rad']<.001
    assert actual[1]['kinematically_reachable']and actual[1]['minimum_joint_margin_rad']>.20
    assert actual[1]['position_error_m']<.001
    # Candidate reachability is a repair proposal; a real suffix still has to
    # demonstrate contacts, release, and support in the native simulator.
