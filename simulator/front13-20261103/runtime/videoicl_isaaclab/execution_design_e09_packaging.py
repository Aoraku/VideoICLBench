"""Explicit E09-only revision of project-authored packaging, at reset only.

The nine source CAD bodies, their supply rails, grouping rules and evaluator
stay intact. Every added grip is collision geometry on the original rigid body.
Old native checkpoints belong to the old design and cannot restore this one.
"""
from copy import deepcopy
import hashlib
import itertools
import json

from .task_recipes import box, vessel

REVISION = 'e09-operable-packaging-v3-20261103'
CRATE_HALF = [.16, .38, .055]
CRATE_INITIAL_XY = [.155, -.40]
CRATE_STAGE_XY = list(CRATE_INITIAL_XY)
LID_GRIP = [0., 0., .016]
BOX_GRIP = [-.080, -.085, .061]
CRATE_GRIP = [-.180, -.24, .075]
BOX_SLOT_Y = [-.26, 0., .26]
BOX_SLOT_X = [-.05, 0., 0.]
GRIP_COLOR = [.18, .25, .31, 1.]
MATERIAL_DENSITY_KG_M3 = 900.


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                   allow_nan=False).encode()).hexdigest()


def union_volume(parts):
    """Exact union volume for these axis-aligned connected moulded additions."""
    lows = [[p['pos'][i]-p['size'][i] for i in range(3)] for p in parts]
    highs = [[p['pos'][i]+p['size'][i] for i in range(3)] for p in parts]
    cuts = [sorted({v[i] for v in lows+highs}) for i in range(3)]
    volume = 0.
    for cell in itertools.product(*(list(zip(c[:-1], c[1:])) for c in cuts)):
        mid = [(a+b)/2 for a,b in cell]
        if any(all(lo[i] <= mid[i] <= hi[i] for i in range(3))
               for lo,hi in zip(lows,highs)):
            volume += (cell[0][1]-cell[0][0])*(cell[1][1]-cell[1][0])*(cell[2][1]-cell[2][0])
    return volume


def sync_bounds(obj):
    """Pin the material origin; expand measured bounds around the full compound."""
    obj['center_z'] = obj.get('center_z', obj['bottom']+obj['size'][2])
    parts = obj['collision_shapes']
    if any(p['type'] != 'box' or p.get('quat', [1,0,0,0]) != [1,0,0,0] for p in parts):
        raise ValueError('E09 authored package bounds require axis-aligned physical boxes')
    low = [min(p['pos'][i]-p['size'][i] for p in parts) for i in range(3)]
    high = [max(p['pos'][i]+p['size'][i] for p in parts) for i in range(3)]
    obj['local_bounds_center'] = [(a+b)/2 for a,b in zip(low,high)]
    obj['size'] = [(b-a)/2 for a,b in zip(low,high)]
    return dict(lower=low, upper=high)


def addition(obj, parts, base_mass):
    for part in parts:
        part.update(rgba=list(GRIP_COLOR), literal_rgba=True)
    obj['collision_shapes'].extend(parts)
    # USD renders these same colliders. PhysX derives inertia and COM from the
    # complete compound with the explicit total mass, instead of a proxy body.
    added_mass = union_volume(parts)*MATERIAL_DENSITY_KG_M3
    obj['physical_mass_kg'] = base_mass+added_mass
    bounds = sync_bounds(obj)
    obj['e09_packaging_revision'] = REVISION
    obj['e09_added_mass_kg'] = added_mass
    return dict(mass_kg=obj['physical_mass_kg'], added_mass_kg=added_mass,
                added_material_density_kg_m3=MATERIAL_DENSITY_KG_M3,
                bounds=bounds, measured=False,
                inertia='PhysX auto from full native collision compound and explicit total mass',
                native_load_validation='pending')


def apply(spec):
    if spec['id'] != 'E09':
        raise ValueError('Operable packaging is an explicit E09-only design')
    d = spec['execution_design']
    if d.get('operable_packaging'):
        raise ValueError('E09 packaging revision was already applied')
    objects = {o['id']: o for o in spec['objects']}
    preserved = {n: deepcopy(objects[n]) for n in d['target_members']}
    fixtures = deepcopy(spec['fixtures'])
    previous = {n: deepcopy(o) for n,o in objects.items() if n.startswith('group_box') or n=='shipping_crate'}
    estimates = {}
    for i in range(3):
        name = 'group_box'+str(i)
        lid = objects[name+'_lid']
        estimates[lid['id']] = addition(lid, [box([.010,.009,.009], [0,0,.012])], .020)
        d['grasps'][lid['id']] = dict(local=list(LID_GRIP), jaw_axis_local=[1,0,0], hand='left')
        # Front/back grips keep the original X-jaw sorting-piece fingers clear.
        # Pick the inward-facing grip for each outer carrier slot. A 260 mm
        # pitch leaves real opening clearance from the adjacent group's bar.
        parts=[]
        for sign in (-1,1):
            # Keep the long bridge above the neighboring original cover.
            # A short upright overlaps this box's own wall instead of
            # penetrating the adjacent source box (native v16 failure).
            parts.extend([box([.005,.016,.002], [-.054,sign*.063,.020]),
                box([.005,.004,.009], [-.054,sign*.073,.029]),
                box([.028,.012,.003], [-.070,sign*.080,.035]),
                box([.004,.006,.0155], [-.094,sign*.084,.0475]),
                box([.004,.006,.0155], [-.066,sign*.084,.0475]),
                box([.018,.016,.006], [-.080,sign*.085,.061])])
        estimates[name] = addition(objects[name], parts, .050)
        objects[name]['e09_shell_half_size']=[.063,.055,.022]
        objects[name]['e09_handle_collider_indices']=[10,16]
        # Larger business packaging sits clear of the two right-hand source
        # boxes. Original CAD supply poses and all source fixtures stay fixed.
        # Keep the entire downward open-finger approach clear of the next
        # box's raised bar, not just the final low grasp configuration.
        lid['xy'] = [[-.20,.345],[-.05,.395],[-.20,.50]][i]
        if d['condition']=='E':lid['xy']=[lid['xy'][0]+.035,lid['xy'][1]-.025]
        d['grasps'][name] = dict(local=list(BOX_GRIP), jaw_axis_local=[0,1,0])
    crate = objects['shipping_crate']
    shift = [.035,-.025] if d['condition']=='E' else [0.,0.]
    replacement = vessel('shipping_crate', [CRATE_INITIAL_XY[i]+shift[i] for i in range(2)],
                         crate['rgba'], hx=CRATE_HALF[0], hy=CRATE_HALF[1], hz=CRATE_HALF[2],
                         bottom=crate['bottom'])
    # The floor, wall thickness and body origin follow the actual new carrier.
    for key in ('collision_shapes','size','inner_size','xy'):
        crate[key] = replacement[key]
    crate['center_z'] = crate['bottom']+CRATE_HALF[2]
    crate['e09_floor_half_size'] = list(CRATE_HALF)
    # The supported-drag grip is below the source rails in Y. It does not
    # obstruct the far supply circle's actual palm during the nine-piece sort.
    parts = [box([.016,.022,.005], [-.160,-.24,.055]),
             box([.016,.020,.018], [-.180,-.24,.075])]
    estimates['shipping_crate'] = addition(crate, parts, .550)
    d['grasps']['shipping_crate'] = dict(local=list(CRATE_GRIP), jaw_axis_local=[1,0,0], hand='right')
    package = next(p for p in d['packages'] if p['container']=='shipping_crate')
    package.update(lower=[-.152,-.372,-.049], upper=[.152,.372,.055])
    # The unchanged destination predicate checks the whole compound. The
    # visible station therefore encloses its real asymmetric exterior handle.
    b = estimates['shipping_crate']['bounds']
    for zone in spec['zones']:
        if zone['id'].startswith('delivery_'):
            zone['half_size'] = [crate['size'][i]+(.010 if i==0 else .007) for i in range(2)]
            # The wider real floor needs the same 10 mm gap from the unchanged
            # supply platform's X=-.05 edge at its actual receiving station.
            zone['xy'][0] = CRATE_INITIAL_XY[0]+crate['local_bounds_center'][0]+shift[0]
    d['packaging_mass_estimates'].update(estimates)
    changed = {n: objects[n] for n in previous}
    d['operable_packaging'] = dict(revision=REVISION, reset_time_only=True,
        source_packaging_sha256=digest(previous), geometry_sha256=digest(changed),
        source_members_sha256=digest(preserved), fixtures_sha256=digest(fixtures),
        default_enabled=False, old_checkpoint_geometry_compatible=False,
        original_rule_objects_unchanged=True, original_native_evaluator_unchanged=True,
        engineering_native_validated=False,
        staging=dict(xy=[CRATE_STAGE_XY[i]+shift[i] for i in range(2)],
                     supported_drag_only=True, load_order=[2,0,1],
                     slot_y=list(BOX_SLOT_Y),slot_x=list(BOX_SLOT_X)))
    d['physical_asset_revision'] = deepcopy(d['operable_packaging'])
    physical = dict(revision=REVISION, geometry_sha256=d['operable_packaging']['geometry_sha256'])
    for key in ('environment_identity','assignment_identity_sha256','paired_input_identity'):
        if key in d:
            d['source_'+key] = d[key]
            d[key] = digest(dict(source_identity=d[key], physical_revision=physical))
    d['physical_configuration_sha256'] = digest(physical)
    assert preserved == {n: objects[n] for n in preserved}
    assert fixtures == spec['fixtures']
    d['initial_actor_poses'] = {o['id']:dict(xy=list(o['xy']),bottom=o['bottom'],
        yaw=o.get('yaw',0), **({'center_z':o['center_z']} if 'center_z' in o else {})) for o in spec['objects']}
    return spec
