"""CPU-safe timing for private continuous demo recording trajectories."""
import math


def scaled_motion_limits(speed,acceleration,scale=1.):
    """Retiming private actuator targets without changing the physics clock."""
    if not all(math.isfinite(v) for v in (speed,acceleration,scale)) or min(speed,acceleration)<=0 or not .5<=scale<=3.:
        raise ValueError('Invalid private trajectory speed scale or motion limits')
    return speed*scale,acceleration*scale**2


def minimum_jerk(phase):
    """Rest-to-rest quintic blend with zero endpoint velocity/acceleration."""
    if not math.isfinite(phase) or not 0 <= phase <= 1:
        raise ValueError('Trajectory phase must be finite and within [0, 1]')
    return phase ** 3 * (10 - 15 * phase + 6 * phase ** 2)


def trajectory_ticks(distance, dt, max_speed=.18, max_acceleration=.6):
    """Bound the analytic peak speed and acceleration of the quintic path."""
    if (not all(math.isfinite(x) for x in (distance, dt, max_speed, max_acceleration))
            or distance < 0 or min(dt, max_speed, max_acceleration) <= 0):
        raise ValueError('Invalid trajectory distance or physical timing limits')
    duration = max(.12, 1.875 * distance / max_speed,
                   math.sqrt((10 / math.sqrt(3)) * distance / max_acceleration))
    return max(1, math.ceil(duration / dt))


def frame_due(tick, dt, fps):
    """Sample physical time, including non-integral physics/render ratios."""
    if tick < 1 or not math.isfinite(dt) or not math.isfinite(fps) or dt <= 0 or fps <= 0 or dt*fps > 1:
        raise ValueError('Invalid physics/render clock')
    return math.floor(tick * dt * fps + 1e-8) > math.floor((tick-1) * dt * fps + 1e-8)
