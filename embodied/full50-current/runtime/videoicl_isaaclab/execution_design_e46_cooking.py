"""Source-bound E46 spatula numerical collision fidelity; E28 is unchanged."""
import copy
import numpy as np

SOURCE_SHA='80783d541400ad8ff889274efcecca551e08c9b12c28004427922e1a0a4f0966'


def configure_spec(spec):
    if spec.get('id')!='E46':raise ValueError('E46-only source blade cooking')
    obj=next(o for o in spec['objects']if o['id']=='spatula')
    if (obj.get('source_asset',{}).get('sha256')!=SOURCE_SHA or
            not np.allclose(obj['size'],[.14,.03761496517,.01481387076],atol=1e-9,rtol=0)or
            obj.get('reviewed_collision_settings')):
        raise ValueError('Exact reviewed original E46 spatula required')
    obj['reviewed_collision_settings']=dict(source_sha256=SOURCE_SHA,approximation='convexHull',
        hull_vertex_limit=255,coordinate_factor=100.)
    return ['spatula']


def verify_only_cooking_change(old,new):
    expected=copy.deepcopy(old);changed=configure_spec(expected)
    from .engineering_checkpoint import PHYSICAL_KEYS
    if old.get('id')!='E46' or new.get('id')!='E46' or any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):
        raise ValueError('E46 migration changed other source physical inputs')
    return changed
