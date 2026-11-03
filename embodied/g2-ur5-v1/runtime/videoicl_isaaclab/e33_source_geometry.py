"""Explicit E33 acceptance-only binding upgrade from pinned source geometry."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import numpy as np

PACKAGE = 'configs/source_geometry/e33'

def augment_e33_bindings(bindings, runtime_root):
    """Return a copy; never change a physical asset, reset pose or task bound."""
    root=Path(runtime_root)
    manifest=json.loads((root/PACKAGE/'e33-acceptance-geometry.json').read_text())
    if manifest.get('schema')!='e33-source-acceptance-geometry-v1':
        raise ValueError('Unknown E33 source geometry schema')
    out=deepcopy(bindings); task=out['tasks']['E33']
    if set(task['objects'])!=set(manifest['objects']):
        raise ValueError('E33 source object set mismatch')
    for name,obj in task['objects'].items():
        record=manifest['objects'][name]; source=obj['source_asset']
        if (source['sha256']!=record['source_asset_sha256'] or
            not np.allclose(obj['size'],record['descriptor_half_size'],atol=1e-12,rtol=0) or
            not np.allclose(source['source_rotation'],record['source_rotation_wxyz'],atol=1e-12,rtol=0)):
            raise ValueError('E33 source geometry identity/dimensions/rotation mismatch: '+name)
        if name!='bin': obj['source_containment_hull']=deepcopy(record)
    wall=deepcopy(manifest['objects']['bin']); wall['path']=PACKAGE+'/'+wall['path']
    if hashlib.sha256((root/wall['path']).read_bytes()).hexdigest()!=wall['sha256']:
        raise ValueError('E33 source wall archive mismatch')
    for variant in task['variants'].values():
        for name,override in variant.get('object_overrides',{}).items():
            if any(key in override for key in ('size','source_asset','local_bounds_center','source_containment_hull')):
                raise ValueError('E33 variant changes measured source geometry: '+name)
        variant['semantic']['containers']['bin']['source_sidewall_triangles']=deepcopy(wall)
        variant['semantic']['source_acceptance_geometry']='e33-source-acceptance-geometry-v1'
    return out

def validate_e33_geometry(objects, semantic):
    """A versioned candidate may not silently fall back if packaging drops data."""
    if semantic.get('source_acceptance_geometry')!='e33-source-acceptance-geometry-v1': return
    for name in semantic['groups']['bottles']:
        obj=objects[name]; geometry=obj.get('source_containment_hull',{})
        if (geometry.get('source_asset_sha256')!=obj['source_asset']['sha256'] or
            not np.allclose(geometry.get('descriptor_half_size',[]),obj['size'],atol=1e-12,rtol=0) or
            not np.allclose(geometry.get('source_rotation_wxyz',[]),obj['source_asset']['source_rotation'],atol=1e-12,rtol=0)):
            raise ValueError('E33 source acceptance geometry missing or stale: '+name)
    if not semantic['containers']['bin'].get('source_sidewall_triangles'):
        raise ValueError('E33 source wall archive declaration missing')
