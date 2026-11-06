"""Source-faithful E37 blade collider; the original screw and slot are retained."""
import copy

SOURCE_SHA='a4a58fbf36b5d003c83df395c8de25d283620932605ac1210d1a35b396751077'


def configure_spec(spec):
    if spec.get('id')!='E37':raise ValueError('E37 source blade cooking only')
    driver=next(o for o in spec['objects']if o['id']=='driver')
    if driver.get('source_asset',{}).get('sha256')!=SOURCE_SHA or driver.get('reviewed_collision_settings'):
        raise ValueError('Unmodified original SHA-pinned E37 driver required')
    driver['reviewed_collision_settings']=dict(source_sha256=SOURCE_SHA,
        approximation='sdf',sdf_resolution=384)
    return ['driver']


def verify_only_cooking_change(old,new):
    expected=copy.deepcopy(old);changed=configure_spec(expected)
    from .engineering_checkpoint import PHYSICAL_KEYS
    if new.get('id')!='E37'or any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):
        raise ValueError('E37 fidelity migration changed other source physical inputs')
    return changed
