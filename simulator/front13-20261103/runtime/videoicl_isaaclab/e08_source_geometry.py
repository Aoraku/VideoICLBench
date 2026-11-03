"""Offline source-bound geometry for generated G1 shoes; never mutates assets."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path


def augment_e08_bindings(bindings, runtime_root):
    result=deepcopy(bindings)
    task=result['tasks']['E08']
    root=Path(runtime_root)
    spec=importlib.util.spec_from_file_location('e08_geometry_g1_builder',root/'scripts/build_inference_g1_assets.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    for name in ('left_shoe','right_shoe'):
        obj=task['objects'][name];source=obj['source_asset']
        if source.get('root_env')!='VIC_INFERENCE_ASSETS':
            raise ValueError('E08 augmentation requires the generated G1 shoe asset')
        relative=Path(source['relative_path'])
        if relative.as_posix()!=f'g1/E08/{name}.usda':
            raise ValueError('Unexpected generated E08 asset path')
        raw=(root/'inference-generalization-v1/assets'/relative).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:
            raise ValueError('E08 asset SHA mismatch')
        mesh=builder.shape(name,builder.color_for(name));mesh.normalize(obj['size'])
        if mesh.text().encode()!=raw:
            raise ValueError('E08 authored geometry differs from pinned USD')
        builder.bind_shoe_containment(obj,mesh)
    for variant in task['variants'].values():
        variant['semantic']['source_acceptance_geometry']='E08-source-geometry-v1'
    return result
