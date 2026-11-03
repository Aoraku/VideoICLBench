"""Explicit future engineering layout: source cabinet on a physical riser.

The source handle stays intact. Its original height leaves the measured
vertical Panda palm 22.5 mm below the table; 35 mm lift supplies 12.5 mm
nominal clearance. Native contact, reachability and task acceptance are pending.
"""
import hashlib
import json

VERSION='e18-source-cabinet-solid-riser-35mm-v1'
LIFT_M=.035
SOURCE_SHA='700a6ede3b467831c6f9995f4471040272cf247085d4d1db80fdf4aeb6248fd1'


def apply_support(spec):
    if spec.get('id')!='E18' or spec.get('e18_support_layout'):
        raise ValueError('Fresh canonical E18 scene required')
    cabinets=spec.get('mechanisms',[])
    if len(cabinets)!=1 or cabinets[0].get('id')!='cabinet':
        raise ValueError('One original E18 cabinet required')
    cabinet=cabinets[0];asset=cabinet['mechanical_asset']
    if asset.get('sha256')!=SOURCE_SHA or cabinet.get('yaw',0)!=0:
        raise ValueError('Pinned unrotated original E18 cabinet required')
    balls=spec['semantic']['groups']['balls']
    if set(balls)!=set(o['id']for o in spec['objects']) or len(balls)!=3:
        raise ValueError('Original three E18 balls required')
    lower,upper=asset['bounds'];position=list(cabinet['position'])
    # Author a real collidable solid from the tabletop to the cabinet base.
    # Preserve a 0.1 mm reset gap rather than overlapping the source collider.
    top=position[2]+LIFT_M+float(lower[2])-.0001
    if not .8<top<.86:raise ValueError('Unexpected E18 support/table height')
    # The asset's overall bound includes the projecting handle. Inset the
    # riser at the front so it cannot occupy the low finger's approach space.
    support_lower=[float(lower[0])+.020,float(lower[1])]
    fixture=dict(type='box',xy=[position[i]+(support_lower[i]+upper[i])/2 for i in range(2)],
                 z=(.8+top)/2,size=[(upper[i]-support_lower[i])/2 for i in range(2)]+[(top-.8)/2],
                 rgba=[.55,.55,.55,1.],literal_rgba=True)
    index=len(spec.setdefault('fixtures',[]));spec['fixtures'].append(fixture)
    cabinet['position']=position;position[2]+=LIFT_M
    for obj in spec['objects']:
        obj['center_z']+=LIFT_M
        obj['bottom']+=LIFT_M
    spec['e18_support_layout']=dict(version=VERSION,source_cabinet_sha256=SOURCE_SHA,
        lift_m=LIFT_M,front_support_inset_m=.020,support_fixture='fixture'+str(index),support_geometry=fixture,
        original_handle_and_joint_unchanged=True,native_verified=False)
    spec['source_asset_only']=False


def bind_identity(spec):
    physical=spec['e18_support_layout'];design=spec['execution_design']
    digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for key in ('environment_identity','assignment_identity_sha256','paired_input_identity'):
        design['source_'+key]=design[key]
        design[key]=digest(dict(source_identity=design[key],physical_revision=physical))
    design['physical_configuration_sha256']=digest(physical)
    design['engineering_layout_candidate']=physical
