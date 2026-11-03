"""Pinned physical E30 cabinet variants for explicit v3 I/E inputs."""
import hashlib,json
from copy import deepcopy
from pathlib import Path

def apply_cabinet_instance(cabinet,seed):
    root=Path(__file__).resolve().parents[1]/'execution-design-v3/assets'
    manifest=json.loads((root/'E30/instances.private.json').read_text())
    if manifest['schema']!='execution-e30-physical-instances-v1':raise ValueError('Cabinet instance manifest required')
    candidate=manifest['instances'][int(seed)%3]
    original=cabinet['mechanical_asset']
    if original['sha256']!=candidate['source_sha256']:raise ValueError('Cabinet source instance differs from pinned base')
    asset=candidate['asset']
    for entry in [asset,*asset['dependencies']]:
        path=root/entry['relative_path']
        if not path.is_file()or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Cabinet instance geometry/dependency hash mismatch: '+entry['relative_path'])
    height=float(candidate.get('base_lift_m',0.))
    if not 0.<=height<=.060:raise ValueError('Unsupported cabinet support height')
    cabinet['mechanical_asset']=deepcopy(asset)
    if height:
        cabinet['position']=list(cabinet['position']);cabinet['position'][2]+=height
        cabinet['instance_support_lift_m']=height
    return dict(kind='new_physical_cabinet_instance',instance_id=asset['id'],sha256=asset['sha256'],new_collision_components=candidate['new_collision_components'],side_thickness_m=candidate['side_thickness_m'],base_lift_m=height,native_verified=False)
