"""Pure numerical helpers for opt-in private author joint-velocity targets.

NumPy is the CPU reference backend. Passing torch as ``array_module`` keeps the
same algebra on existing native device tensors; this module never imports torch
or Isaac. The caller supplies the already TCP-corrected, base-frame Jacobian.
"""
import math
import numpy as np


def minimum_jerk_phase_rate(phase,duration):
    """Analytic ds/dt of 10u^3-15u^4+6u^5; both endpoint rates are zero."""
    if (not math.isfinite(phase) or not 0<=phase<=1
            or not math.isfinite(duration) or duration<=0):
        raise ValueError('Invalid minimum-jerk phase or physical duration')
    return 30*phase**2*(1-phase)**2/duration


def damped_joint_velocity(jacobian,twist,velocity_limits,damping,*,array_module=np):
    """Compute J.T solve(J J.T + damping^2 I, twist), then native joint caps.

    Inputs are (..., 6, N), (..., 6), and scalar/(N,)/(...,N) positive speed
    limits. A zero limit explicitly locks that joint. No synthetic velocities,
    position writes or physics timing are supplied by this helper.
    """
    xp=array_module
    if xp is np:
        jacobian=np.asarray(jacobian,dtype=float)
        twist=np.asarray(twist,dtype=float)
        velocity_limits=np.asarray(velocity_limits,dtype=float)
    if (jacobian.ndim<2 or jacobian.shape[-2]!=6
            or twist.shape!=jacobian.shape[:-1]
            or not math.isfinite(damping) or damping<=0):
        raise ValueError('Expected finite damped base-frame Jacobian and six-vector twist')
    if (not bool(xp.isfinite(jacobian).all()) or not bool(xp.isfinite(twist).all())
            or not bool(xp.isfinite(velocity_limits).all())
            or bool((velocity_limits<0).any())):
        raise ValueError('Nonfinite actuation input or negative native speed limit')
    if velocity_limits.shape not in ((),(jacobian.shape[-1],),jacobian.shape[:-2]+(jacobian.shape[-1],)):
        raise ValueError('Joint velocity limits must match the native arm DOFs')
    transpose=jacobian.swapaxes(-1,-2)
    eye_kwargs={'dtype':jacobian.dtype}
    if xp is not np:eye_kwargs['device']=jacobian.device
    identity=xp.eye(6,**eye_kwargs)
    solved=xp.linalg.solve(jacobian@transpose+damping*damping*identity,twist[...,None])
    velocity=(transpose@solved)[...,0]
    if not bool(xp.isfinite(velocity).all()):raise ValueError('DLS produced nonfinite joint velocity')
    return xp.minimum(xp.maximum(velocity,-velocity_limits),velocity_limits)
