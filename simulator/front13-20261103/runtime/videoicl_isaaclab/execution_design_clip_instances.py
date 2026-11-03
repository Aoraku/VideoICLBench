"""Pinned E40 physical width variants, with unchanged spring opening motion."""
from copy import deepcopy
from pathlib import Path
import hashlib,json

def apply_clip_instances(spec,seed):
    if spec['id']!='E40':raise ValueError('Clip width instances are restricted to E40')
    root=Path(__file__).resolve().parents[1]/'execution-design-v3/assets'
    manifest=json.loads((root/'E40/instances.private.json').read_text())
    if manifest['schema']!='execution-e40-width-instances-v1':raise ValueError('Pinned clip instance schema required')
    row=manifest['instances'][int(seed)%3];factor=row['width_scale'];rows=[]
    for m in spec['mechanisms']:
        old=m['mechanical_asset']
        if old['sha256']!=row['source_sha256']:raise ValueError('Clip instance differs from reviewed source')
        for item in [row['asset'],*row['asset']['dependencies']]:
            p=root/item['relative_path']
            if not p.is_file()or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError('Clip instance/dependency geometry hash mismatch')
        asset=deepcopy(old);asset.update(deepcopy(row['asset']));asset['source_modified']=True
        asset['instance_derivation']=dict(canonical_source_sha256=row['source_sha256'],hinge_x_scale=factor,
            jaws_yz_unchanged=True,joints_preserved=True)
        m['mechanical_asset']=asset
        sem=spec['semantic']['clips'][m['id']]
        for side in ('left','right'):sem[side]['point_local'][0]*=factor
        for grasp in ('handle_grasp','body_grasp'):sem['expert'][grasp]['local'][0]*=factor
        rows.append(dict(mechanism=m['id'],sha256=asset['sha256'],width_scale=factor))
    return dict(kind='same_category_physical_clip_width_instances',objects=rows,native_verified=False)
