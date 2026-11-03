"""Measured E08 heel grasp candidates for engineering controls only.

These are collision-hull-section midpoints, not a physical acceptance certificate.
Public actions and native contact/holding checks remain mandatory.
"""
from copy import deepcopy
import math

# Actual collision hulls, after source rotation and instance scaling.
# Band: X [-.120,-.085], Z [-.039,.015] metres in the shoe body frame.
# Evidence: verification/task-design-revision-20261102/e08-lowerheel-band-candidate.private.json
HEEL_BANDS = {
    'left_shoe': ('fdd7d78b574ad7bd52485d063fbb48621a02651cd174235cfd6bd9f7b2e40b32',
                  .04422009824739785, -.026378456840873962, .037888648107971296),
    'right_shoe': ('d47101e06a14ea63e22b76f3444fce6bd4faf4e1a33ed3c38c0cd603c339e3b2',
                   .04553283416401324, -.045532834164013235, .021953478150220432),
}


def e08_engineering_heel_grasps(spec, grasps):
    """Return private grasp candidates without changing task objects or rules."""
    if spec.get('id') != 'E08' or spec.get('execution_design', {}).get('revision') != 'embodied50-execution-v3-20261102':
        raise ValueError('E08 v3 engineering contract required')
    objects = {o['id']: o for o in spec['objects']}
    result = deepcopy(grasps)
    for name, (sha, half_y, lower, upper) in HEEL_BANDS.items():
        obj = objects[name]
        source = obj.get('source_asset', {})
        if source.get('sha256') != sha or source.get('source_rotation') != [.5,.5,.5,.5]:
            raise ValueError('E08 heel candidate requires measured source asset and rotation')
        if any(not math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-9)
               for a,b in zip(obj['size'], [.13, half_y, .051902870300350894])) or len(obj['size']) != 3:
            raise ValueError('E08 heel candidate requires measured instance dimensions')
        if result[name]['local'] != [-.1,0,-.005] or result[name]['jaw_axis_local'] != [0,1,0]:
            raise ValueError('E08 heel candidate refuses to overwrite another grasp revision')
        result[name]['local'][1] = (lower + upper) / 2
        # Reviewed tilted-heel candidate clears the actual palm sweep.
        # Source collision meshes/goals remain unchanged; runtime checks the
        # achieved orientation, swept clearance, and source-pose stability.
        result[name]['local'][0] = -.11
        # Native source convex cross-section at -25 mm has opposed heel
        # sidewalls; -15 mm lies on the upward-facing heel chamfer.
        result[name]['local'][2] = -.025
    return result
