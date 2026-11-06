"""Opt-in continuous gripper command reference; original binary goal is retained."""
import math


def parameters(control):
    names=('public_gripper_reference_speed_m_s','public_gripper_reference_acceleration_m_s2')
    if not any(n in control for n in names):return None
    if not all(n in control for n in names):raise ValueError('Both public gripper reference limits are required')
    values=tuple(control[n]for n in names)
    if any(type(v)not in(int,float)or not math.isfinite(v)or v<=0 for v in values):
        raise ValueError('Public gripper reference limits must be finite and positive')
    return tuple(float(v)for v in values)


def advance(reference,velocity,goal,dt,speed,acceleration,array_module):
    """Integrate a trapezoidal command path, including within-tick switches.

    State contains the command reference and its velocity, never measured joint
    positions. Replanning the remaining path preserves acceleration continuity;
    an opposing new goal first brakes the existing reference motion.
    """
    x=reference.clone()if hasattr(reference,'clone')else reference.copy()
    v=velocity.clone()if hasattr(velocity,'clone')else velocity.copy()
    xp=array_module;z=xp.zeros_like(x);remaining=xp.full_like(x,float(dt))
    if not math.isfinite(float(dt))or dt<=0:raise ValueError('Positive reference timestep required')
    direction=xp.where(goal-x>=0,xp.ones_like(x),-xp.ones_like(x))
    u=v*direction
    away=xp.maximum(-u/acceleration,z);t=xp.minimum(remaining,away)
    x=x+v*t+.5*acceleration*direction*t*t;v=v+acceleration*direction*t;remaining=remaining-t
    distance=xp.abs(goal-x);u=xp.maximum(v*direction,z)
    # Existing profiles begin at measured q with zero reference velocity. The
    # exact acceleration/cruise/deceleration phases then remain inside bounds.
    peak=xp.minimum(xp.full_like(x,float(speed)),xp.sqrt(acceleration*distance+.5*u*u))
    accel_time=xp.maximum((peak-u)/acceleration,z);t=xp.minimum(remaining,accel_time)
    x=x+v*t+.5*acceleration*direction*t*t;v=v+acceleration*direction*t;remaining=remaining-t
    cruise_distance=xp.maximum(distance-(peak*peak-u*u)/(2*acceleration)-peak*peak/(2*acceleration),z)
    cruise_time=cruise_distance/xp.maximum(peak,xp.full_like(x,1e-15));t=xp.minimum(remaining,cruise_time)
    x=x+v*t;remaining=remaining-t
    decel_time=xp.maximum(v*direction/acceleration,z);t=xp.minimum(remaining,decel_time)
    x=x+v*t-.5*acceleration*direction*t*t;v=v-acceleration*direction*t;remaining=remaining-t
    arrived=remaining>0
    return xp.where(arrived,goal,x),xp.where(arrived,z,v)
