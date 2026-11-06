"""E23 v3 semantic calibration from the unchanged source collision meshes.

The former upper/middle base coordinates lay outside their physical rods,
reversing their Y directions. End-face centres and circumscribed cross-section
radii below were measured from each eight-vertex USD collision mesh by PCA.
This changes neither USD geometry nor evaluator success criteria.
"""
from copy import deepcopy

TREE_SHA256='131190e2d04c89da64838a7ea50f2f76172faf5e6293aa9b1e3d888f9d66ff42'
COLLISION_SOURCE_SHA256='734dc9d2fe0e32bb5f2d7764d9802141047a65c26d705e95612958e53d139a59'
BRANCHES={
    '0':dict(base_local=[0.,0.,.112496743],tip_local=[.090002405,0.,.12750132],radius=.007423710847933514),
    '1':dict(base_local=[0.,0.,.172496745],tip_local=[-.04500120175,.07794436725,.187501315],radius=.007423709728276175),
    '2':dict(base_local=[0.,0.,.232496745],tip_local=[-.04500120175,-.07794436725,.247501325],radius=.007423709728678308),
}


def calibrate_source_branches(spec):
    if spec['id']!='E23':raise ValueError('E23 source calibration only')
    tree=next(o for o in spec['objects'] if o['id']=='tree')
    asset=tree.get('mechanical_asset',{})
    if asset.get('sha256')!=TREE_SHA256 or asset.get('relative_path')!='three_level_mug_tree.usda':
        raise ValueError('Unreviewed E23 source tree; do not reuse measured branch geometry')
    deps={d['relative_path']:d['sha256']for d in asset.get('dependencies',[])}
    if deps.get('three_level_mug_tree_parts/visual.usda')!=COLLISION_SOURCE_SHA256:
        raise ValueError('E23 collision source checksum mismatch')
    old=deepcopy(spec['semantic']['branches'])
    if set(old)!=set(BRANCHES) or any(b['ref']!={'actor':'tree'}for b in old.values()):
        raise ValueError('Unreviewed E23 branch identities')
    spec['semantic']['branches']={key:dict(ref={'actor':'tree'},**deepcopy(value)) for key,value in BRANCHES.items()}
    spec['source_geometry_calibration']=dict(task='E23',kind='actual_usd_collision_end_face_centres',
        source_sha256=COLLISION_SOURCE_SHA256,tree_asset_sha256=TREE_SHA256,
        previous_branches=old,physical_asset_changed=False,native_validation_pending=True)

