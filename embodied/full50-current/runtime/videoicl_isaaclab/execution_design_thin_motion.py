"""Measured engineering approach guard for thin-material reference routes."""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def checked_move(policy, side, target, guard=None, tolerance=.002):
    target = np.asarray(target, float)
    if target.shape != (3,) or not np.isfinite(target).all():
        raise ValueError('Finite thin-material waypoint required')
    distances = []
    for _ in range(180):
        if guard: guard()
        before = np.asarray(policy.tip(side), float).copy()
        error = target - before
        if np.max(np.abs(error)) <= tolerance:
            return
        axis = int(np.argmax(np.abs(error)))
        token = (('FWD', 'BACK'), ('LEFT', 'RIGHT'), ('UP', 'DOWN'))[axis][int(error[axis] < 0)]
        requested = max(float(getattr(policy, 'min_mm', .5)) / 1000.,
                        min(float(getattr(policy, 'max_mm', 12.)) / 1000., abs(error[axis])))
        policy.act(side, token, mm=requested * 1000.)
        if guard: guard()
        after = np.asarray(policy.tip(side), float)
        actual = after - before
        forward = float(actual[axis] * np.sign(error[axis]))
        lateral = float(np.linalg.norm(np.delete(actual, axis)))
        distance = float(np.linalg.norm(target - after))
        distances.append(distance)
        if hasattr(policy.a, 'out'):
            with (policy.a.out / 'thin-measured-approach.private.jsonl').open('a') as f:
                f.write(json.dumps(dict(side=side, target=target.tolist(),
                    step=policy.c.steps, requested_m=requested, forward_m=forward,
                    lateral_m=lateral, target_distance_m=distance)) + '\n')
        if requested >= .0005 and forward < requested * .02 and lateral > .002:
            raise ToolExecutionError('Thin-material approach moved sideways instead of requested axis')
        # Use target-distance progress, so contact jitter cannot extend a
        # blocked approach merely by moving more than the old 0.3mm radius.
        if len(distances) >= 12 and min(distances[-6:]) >= min(distances[-12:-6]) - .0001:
            raise ToolExecutionError('Thin-material approach made no measured target progress')
    raise ToolExecutionError('Unreachable measured thin-material waypoint')
