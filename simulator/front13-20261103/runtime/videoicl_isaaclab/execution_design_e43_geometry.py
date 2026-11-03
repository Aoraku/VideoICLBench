"""E43 source ramp/gate assembly calibration, only at new v3 construction.

The published rectangular plank geometry is retained. Its exact baked rotation
and descriptor bounds recover the source top plane; the sliding gate starts
above that plane rather than intersecting it. No live state or score writes.
"""
import math

SOURCE_SHA='e4b604171aa6c8c861951de1bd76093010c9cbd649c9580e144fe8b4492717ca'
RAMP_ANGLE_DEGREES=6.8754935
GATE_CLEARANCE_M=.0015


def ramp_top_at_local_x(launcher, x):
    if launcher['mechanical_asset']['sha256']!=SOURCE_SHA:
        raise ValueError('E43 calibration requires reviewed source ramp')
    angle=math.radians(RAMP_ANGLE_DEGREES);c,s=math.cos(angle),math.sin(angle)
    hx,_,hz=launcher['size']
    # Invert the two rotated box extents to recover physical half thickness.
    thickness=(hz*c-hx*s)/(c*c-s*s)
    if not .0029<thickness<.0031:raise ValueError('Unexpected source plank thickness')
    return float(launcher.get('center_z',launcher['bottom'])
                 +launcher['local_bounds_center'][2]+thickness/c+math.tan(angle)*x)


def calibrate_gate(spec):
    if spec['id']!='E43':raise ValueError('E43-only source calibration')
    objects={o['id']:o for o in spec['objects']};ramp,gate=objects['launcher'],objects['gate']
    if abs(float(ramp.get('yaw',0)))>1e-9 or abs(float(gate.get('yaw',0)))>1e-9:
        raise ValueError('Source calibration expects canonical assembly axes')
    top=ramp_top_at_local_x(ramp,gate['xy'][0]+gate['size'][0]-ramp['xy'][0])
    old_bottom=float(gate['bottom']);new_bottom=top+GATE_CLEARANCE_M
    dz=new_bottom-old_bottom
    joints=[j for j in spec.get('joints',[])if j.get('child')=='gate'and not j.get('parent')]
    if len(joints)!=1 or joints[0]['type']!='prismatic' or joints[0]['axis']!='Y':
        raise ValueError('Expected one source world sliding gate constraint')
    joint=joints[0]
    if abs(joint['anchor0'][2]-(old_bottom+gate['size'][2]))>1e-6:
        raise ValueError('Source gate anchor does not match source center')
    gate['bottom']=new_bottom
    if 'center_z'in gate:gate['center_z']+=dz
    joint['anchor0'][2]+=dz
    spec['execution_geometry_calibration']=dict(task='E43',source_ramp_sha256=SOURCE_SHA,
        kind='remove_initial_gate_ramp_interpenetration',source_bottom_m=old_bottom,
        bottom_m=new_bottom,gate_ramp_clearance_m=GATE_CLEARANCE_M,
        source_geometry_and_dimensions_preserved=True,native_verified=False)
