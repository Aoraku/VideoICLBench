"""Versioned physical dimensions and calibrated, hand-mounted optical frames."""
import math

PROTOCOL = 'delivery8-isaaclab-v2'
CAMERA_PROFILE = 'isaaclab_delivery8_v2'

# RoboDojo env_cfg/camera/template.py: D435 pinhole intrinsics, 640 x 480.
# Its default X5 has a physical `camera` link; Franka does not have that link.
# Mount behind and beside the Panda hand, aim at its 103.4 mm grasp center,
# and put the gripper opening axis horizontally in the image.
WRIST_POSITION = (.09, 0., -.055)
GRASP_OFFSET = .1034
_pitch = -math.atan2(WRIST_POSITION[0], GRASP_OFFSET-WRIST_POSITION[2])
WRIST_ROTATION = (math.cos(_pitch/2)/math.sqrt(2),
                  math.sin(_pitch/2)/math.sqrt(2),
                  math.sin(_pitch/2)/math.sqrt(2),
                  math.cos(_pitch/2)/math.sqrt(2))
WRIST_INTRINSICS = dict(focal_length=13., horizontal_aperture=20.955,
                        vertical_aperture=15.71625, clipping_range=(.0001, 10.))


def revise_scene(spec):
    """Upgrade exported recipes; the frozen v1 source/manifest stay auditable."""
    spec['physics_revision'] = PROTOCOL
    if spec['id'] != 'F22':
        return spec
    objects = {o['id']: o for o in spec['objects']}
    for name, hx, hy in [('lower', .12, .14), ('upper', .13, .15)]:
        o = objects[name]
        hz, wall, floor = .032, .005, .004
        parts = [
            ([hx, hy, floor], [0, 0, -hz+floor]),
            ([wall, hy, hz], [-hx+wall, 0, 0]),
            ([wall, hy, hz], [hx-wall, 0, 0]),
            ([hx-wall, wall, hz], [0, -hy+wall, 0]),
            ([hx-wall, wall, hz], [0, hy-wall, 0]),
            ([.025, .018, .012], [0, -hy-.014, 0]),
            ([.025, .018, .012], [0, hy+.014, 0]),
        ]
        o.update(size=[hx, hy+.032, hz], inner_size=[hx-2*wall, hy-2*wall, hz],
                 components=[dict(size=s, pos=p) for s, p in parts],
                 collision_shapes=[dict(type='box', size=s, pos=p, quat=[1., 0., 0., 0.])
                                   for s, p in parts],
                 grasp_sides=[[0, -hy-.014, .005], [0, hy+.014, .005]])
    lower, upper = objects['lower'], objects['upper']
    lower['bottom'] = .802
    upper['bottom'] = lower['bottom']+2*lower['size'][2]+.001
    for name, tray in [('piece', lower), ('upper_piece', upper)]:
        for i in range(3):
            objects[name+str(i)]['bottom'] = tray['bottom']+.008+.001
    return spec
