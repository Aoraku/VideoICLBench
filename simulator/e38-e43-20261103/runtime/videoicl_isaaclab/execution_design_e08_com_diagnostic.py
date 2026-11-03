"""Explicit opt-in short public-action COM reference calibration, no task route."""
import json
import numpy as np


def run(policy,side,guard,*,stop_after=True):
    from .execution_design_jacobian_reference import capture
    from .execution_design_drawer_ik_probe import forward_at_delta
    from .author_orientation import _axis_angle
    from .execution_design_e33_grasp import actual_mesh
    a=policy.a
    if policy.task!='E08' or not a.control_report.get('engineering_reference_only'):
        raise ValueError('E08 independent engineering calibration only')
    policy.stage('e08-native-com-reference-diagnostic')
    bodies=[actual_mesh(a,side,n)for n in('panda_hand',*a.scene.embodiment.fingers)]
    if min(float(v[:,2].min())for v in bodies)<.92:raise RuntimeError('COM diagnostic hand lacks empty table clearance')
    baseline=capture(a,policy.c,side);p0=np.array(baseline['position']);r0=np.array(baseline['rotation_task']);q0=np.array(baseline['q']);j0=np.array(baseline['jacobian'])
    path=a.out/'e08-com-reference-diagnostic.private.jsonl'
    with path.open('a')as stream:stream.write(json.dumps(dict(phase='before',step=policy.c.steps,measured=baseline))+'\n')
    for token in('FWD','UP','PITCH_DOWN','STILL'):
        guard();policy.act(side,token,mm=2.,degrees=2.);guard()
        measured=capture(a,policy.c,side)
        p,r=forward_at_delta(p0,r0,j0,np.array(measured['q'])-q0)
        position_error=float(np.linalg.norm(p-np.array(measured['position'])))
        rotation_error=float(_axis_angle(np.array(measured['rotation_task'])@r.T)[1])
        with path.open('a')as stream:stream.write(json.dumps(dict(phase='after',step=policy.c.steps,token=token,measured=measured,
            prediction_position_error_m=position_error,prediction_rotation_error_rad=rotation_error,
            source_of_actuation='public_actions_only',task_route_executed=False))+'\n')
        if position_error>.00002 or rotation_error>.001:raise RuntimeError('Actual COM reference failed public-action FK cross-check')
    if stop_after:raise RuntimeError('E08 short COM diagnostic complete; task route intentionally withheld')
