"""Explicit same-state diagnostic migration for three reviewed E45 ball colliders."""
import copy
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from .execution_design_e45_balls import verify_only_ball_adapters,NATIVE_MASS_PROPERTIES,BASELINE_ARTIFACT_SHA,BALLS,NATIVE_SOURCE_MASS_PROPERTIES


def materialize(controller,recipe):
    if recipe.get('schema')!='engineering-e45-balls-migration-v1'or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit E45 ball diagnostic migration required')
    checkpoint=copy.deepcopy(recipe['checkpoint']);digest=checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint)!=digest:raise ValueError('Original checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=digest
    old=recipe['source_scene'];new=controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Original checkpoint/source geometry SHA mismatch')
    changed=verify_only_ball_adapters(old,new);target=identity(controller)
    for key,value in checkpoint['identity'].items():
        if key!='physical_geometry_sha256'and target.get(key)!=value:
            raise ValueError('E45 adapter identity mismatch: '+key)
    baseline=recipe['native_mass_properties']
    if baseline!=NATIVE_SOURCE_MASS_PROPERTIES or recipe.get('native_mass_baseline_sha256')!=BASELINE_ARTIFACT_SHA:
        raise ValueError('Pinned native E45 ball mass baseline required')
    actual={}
    for name,asset in controller.scene.objects.items():
        if name not in baseline and name in('cup',*BALLS):raise ValueError('Every changed ball and unchanged cup mass baseline is required')
        view=asset.root_physx_view;actual[name]={}
        for key,values in [('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms())]:
            measured=np.asarray(values.cpu());actual[name][key]=measured.tolist()
            if name in baseline and not np.allclose(measured,np.asarray(baseline[name][key]),rtol=1e-6,atol=1e-12):
                raise ValueError('E45 adapter changed original native '+key+': '+name)
        if name not in baseline:
            obj=next(o for o in new['objects']if o['id']==name)
            if not np.allclose(actual[name]['masses_kg'],[[obj['mass']]],rtol=1e-6,atol=1e-12):
                raise ValueError('Unchanged source actor native mass differs from its source declaration')
    prior=copy.deepcopy(checkpoint['identity']);checkpoint['identity']=target
    checkpoint['context']['e45_ball_migration']=dict(old_identity=prior,new_identity=target,changed_objects=changed,
        only_collision_approximation_changed=True,source_visual_mesh_unchanged=True,
        old_native_mass_properties=baseline,new_native_mass_properties=actual,
        exact_solver_cache_restored=False,diagnostic_only=True,
        seeded_old_poses_only=True,post_settle_ball_motion_is_new_geometry=True,
        exact_native_mass_property_baselines_compared=sorted(baseline),
        remaining_actors_unchanged_by_physical_keys=sorted(set(actual)-set(baseline)))
    checkpoint['limitations'].append('Only the three reviewed E45 ball colliders changed; native mass/COM/inertia are pinned and read back. Original poses/velocities/controller targets are restored without evaluator history.')
    checkpoint['limitations'].append('This is a changed-contact-geometry diagnostic; ball motion during startup is explicitly measured and is not asserted to preserve the old settled ball state. Never eligible as a source-initial full positive.')
    return reseal(checkpoint)
