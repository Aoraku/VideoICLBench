"""Numerical conditioning of unchanged SHA-pinned E40 collision vertices."""
import copy

SOURCES = {
    'E40/clip_width_0.usda': '374a7d14bbf8fed34c207e256d0c750a3693542dcb6091e7311c5db8b38bbbb5',
    'E40/clip_width_1.usda': 'f5ca354c459cdcd5181d6d8063bb7712ccf2de15644904f3941d52a10f3d3df7',
    'E40/clip_width_2.usda': '9f5a9eede301b47358e5afa84bbe6f6098602365b476a1881277b39c56a71dad',
}
FACTOR = 100.
FIELD = 'reviewed_collision_coordinate_factor'


def verify_record(record):
    if (record.get('root_env') != 'VIC_EXECUTION_DESIGN_ASSETS'
            or SOURCES.get(record.get('relative_path')) != record.get('sha256')
            or record.get(FIELD) != FACTOR):
        raise ValueError('Exact source-bound E40 collision coordinate conditioning required')


def configure_spec(spec):
    if spec.get('id') != 'E40':
        raise ValueError('Collision coordinate pilot is limited to E40')
    changed = []
    for mechanism in spec['mechanisms']:
        record = mechanism['mechanical_asset']
        if FIELD in record:
            raise ValueError('Existing collision coordinate override is not replaced')
        record[FIELD] = FACTOR
        verify_record(record)
        changed.append(mechanism['id'])
    if not changed:
        raise ValueError('Actual source E40 mechanisms required')
    return changed


def verify_only_coordinate_change(old, new):
    from .engineering_checkpoint import PHYSICAL_KEYS
    if old.get('id') != 'E40' or new.get('id') != 'E40':
        raise ValueError('E40 coordinate migration task identity mismatch')
    expected = copy.deepcopy(old)
    changed = configure_spec(expected)
    if any(expected.get(k) != new.get(k) for k in PHYSICAL_KEYS):
        raise ValueError('E40 coordinate migration changed another physical input')
    return changed


def apply(stage, prefix, source_path, record):
    verify_record(record)
    from .author_collision_coordinates import prepare, verify
    prepared = prepare(stage, prefix, source_path, FACTOR)
    if not prepared:
        raise ValueError('E40 actual source collision meshes were not found')
    return verify(stage, prepared, FACTOR)
