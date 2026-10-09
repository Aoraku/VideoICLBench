"""Distance-configurable Cartesian commands; no object-level actions or state reads."""
import math
import numpy as np

MOTION = {
    "FWD": (0, 1), "BACK": (0, -1), "LEFT": (1, 1), "RIGHT": (1, -1),
    "UP": (2, 1), "DOWN": (2, -1), "ROLL_POS": (3, 1), "ROLL_NEG": (3, -1),
    "PITCH_POS": (4, 1), "PITCH_NEG": (4, -1), "YAW_POS": (5, 1), "YAW_NEG": (5, -1),
}
TOKENS = ("STILL", "GRASP", "RELEASE", *MOTION,
          *(t+"_FINE" for t in MOTION))


def finite_number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("Distance/angle outside supported range")


def move(env, left="STILL", right="STILL", step_mm=None, rotation_deg=None):
    """One desired Cartesian increment, followed by 8 simulation steps (0.4s).

    An explicit value overrides _FINE too. Without values, legacy semantics are
    exactly 20mm/10deg and 2mm/1deg. This is a requested increment, not a claim
    that contact, workspace limits or the controller permit that displacement.
    """
    if left not in TOKENS or right not in TOKENS:
        raise ValueError("Unknown action token")
    if step_mm is not None:
        finite_number(step_mm, .5, 50.)
    if rotation_deg is not None:
        finite_number(rotation_deg, .5, 20.)
    command = np.zeros(14)
    for i, token in enumerate((left, right)):
        if token == "GRASP": env.grips[i] = 1.
        if token == "RELEASE": env.grips[i] = -1.
        fine = token.endswith("_FINE")
        base = token[:-5] if fine else token
        if base in MOTION:
            axis, sign = MOTION[base]
            if axis < 3:
                delta = (step_mm if step_mm is not None else (2. if fine else 20.))/1000
                command[i*7+axis] = sign*delta/.05
            else:
                delta = rotation_deg if rotation_deg is not None else (1. if fine else 10.)
                command[i*7+axis] = sign*math.radians(delta)/.5
        command[i*7+6] = env.grips[i]
    for _ in range(8):
        env.step(command)
        env.track()
        command[:6] = 0.
        command[7:13] = 0.
