"""Internal shape pairs of ONE read-back native rigid body, never semantic groups."""
from __future__ import annotations
import itertools
import numpy as np


def native_compound_pairs(snapshot):
    witnesses=snapshot.get('native_rigid_body_witnesses',{});pairs=[]
    for actor in snapshot.get('attached_actors',[]):
        shapes=[s for s in snapshot['shapes']if s['actor']==actor]
        if len(shapes)<2:continue
        witness=witnesses.get(actor)
        if not isinstance(witness,dict):raise ValueError('Native compound requires actual rigid-root readback: '+actor)
        root=witness.get('native_root_path');paths=witness.get('native_view_prim_paths')
        if not root or paths!=[root]or witness.get('native_view_count')!=1:
            raise ValueError('Native compound must be one exact PhysX rigid-body view')
        if witness.get('usd_root_has_rigid_body_api')is not True or witness.get('usd_root_rigid_body_enabled')is not True:
            raise ValueError('Native compound root lacks enabled actual RigidBodyAPI')
        if witness.get('proof_source')not in('live_physx_view_and_nearest_usd_api','saved_physx_root_readback_and_usd_api_audit'):
            raise ValueError('Native compound root proof provenance missing')
        pose=np.asarray(witness.get('pose_world'),float)
        if pose.shape!=(4,4)or not np.isfinite(pose).all():raise ValueError('Native compound actual root pose unavailable')
        for shape in shapes:
            path=shape['source_prim']
            if shape.get('group')!='prop'or shape.get('owner')!=root or shape.get('native_rigid_root_path')!=root:
                raise ValueError('Compound shapes do not share one measured native rigid root')
            if not(path==root or path.startswith(root+'/')):raise ValueError('Compound source shape is outside its native root')
            if not np.allclose(np.asarray(shape['pose_world']),pose,rtol=0.,atol=1e-6):
                raise ValueError('Compound source geometry uses a different native root frame')
        for left,right in itertools.combinations(shapes,2):
            pairs.append(dict(pair=[left['name'],right['name']],native_rigid_root=root,actor=actor,
                              reason='Shapes of one actual native rigid body have no internal self collision',
                              proof_source=witness['proof_source']))
    return pairs


def allow_native_compound_internal_pairs(planner,snapshot,diagnostics,profile):
    if profile.get('allow_same_native_rigid_body_internal_shapes')is not True:return
    pairs=native_compound_pairs(snapshot)
    for row in pairs:planner.acm.set_entry(*row['pair'],True)
    diagnostics['native_compound_internal_shapes']=dict(pairs=pairs,source_shapes_preserved=True,
        external_pairs_ignored=False,robot_links_ignored=False,actor_semantics_used_as_identity=False)
    diagnostics['ignored_collision_pairs'].extend(pairs)
