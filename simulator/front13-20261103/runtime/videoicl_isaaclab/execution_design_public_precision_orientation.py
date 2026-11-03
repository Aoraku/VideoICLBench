"""Measured engineering wrist alignment using only valid public rotations.

A net correction below the public minimum uses an opposite legal leg followed
by a legal return. The native measured turn calibrates command undershoot;
no subminimum command or private target/state assignment is issued.
"""
import math
import numpy as np
from .author_orientation import _axis_angle


def orient(author,side,target,tolerance_deg=.03,max_actions=24):
    if not author.control_report.get('engineering_reference_only'):raise ValueError('Private engineering alignment only')
    if side not in author.scene.robots:raise ValueError('Named native hand required')
    target=np.asarray(target,float)
    if target.shape!=(3,3)or not np.isfinite(target).all()or not np.allclose(target.T@target,np.eye(3),atol=1e-6)or np.linalg.det(target)<.999999:
        raise ValueError('Proper finite measured orientation target required')
    lower,upper=map(float,author.scene.embodiment.config['control']['rotation_deg']);upper=min(10.,upper)
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    gain=np.ones(3)
    for _ in range(max_actions):
        before=np.asarray(author.tcp_rotation_task(side),float);axis,angle=_axis_angle(target@before.T)
        if math.degrees(angle)<=tolerance_deg:return
        component=np.asarray(axis)*math.degrees(angle);i=int(np.argmax(abs(component)));sign=1. if component[i]>0 else-1.
        if abs(component[i])<lower:sign=-sign;command=lower
        else:command=min(upper,max(lower,abs(component[i])/gain[i]))
        token=labels[i][int(sign<0)]
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm=1.,rotation_deg=command)
        # The rotation action may finish with a small tracking lag. A measured
        # pose at the desired angle is insufficient if its retained goal would
        # subsequently pull away during translation; let that SAME goal settle.
        author.act('STILL','STILL',mm=1.,rotation_deg=lower)
        after=np.asarray(author.tcp_rotation_task(side),float);observed_axis,observed_angle=_axis_angle(after@before.T)
        actual=float(observed_axis[i]*math.degrees(observed_angle)*sign)
        if actual<command*.1:raise RuntimeError('Measured public wrist alignment did not rotate')
        gain[i]=float(np.clip(actual/command,.5,1.1))
    raise RuntimeError('Bounded measured public wrist alignment did not converge')
