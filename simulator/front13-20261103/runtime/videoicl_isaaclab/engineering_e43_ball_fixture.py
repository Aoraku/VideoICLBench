"""Explicit same-state diagnostic migration for one reviewed E43 ball collider."""
import copy
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from .execution_design_e43_ball import verify_only_ball_adapter,NATIVE_MASS_PROPERTIES,BASELINE_ARTIFACT_SHA


def materialize(controller,recipe):
    if recipe.get('schema')!='engineering-e43-ball-migration-v1'or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit E43 ball diagnostic migration required')
    checkpoint=copy.deepcopy(recipe['checkpoint']);digest=checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint)!=digest:raise ValueError('Original checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=digest
    old=recipe['source_scene'];new=controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Original checkpoint/source geometry SHA mismatch')
    changed=verify_only_ball_adapter(old,new);target=identity(controller)
    for key,value in checkpoint['identity'].items():
        if key!='physical_geometry_sha256'and target.get(key)!=value:
            raise ValueError('E43 adapter identity mismatch: '+key)
    baseline=recipe['native_mass_properties']
    if baseline.get('ball')!=NATIVE_MASS_PROPERTIES or recipe.get('native_mass_baseline_sha256')!=BASELINE_ARTIFACT_SHA:
        raise ValueError('Pinned native E43 ball mass baseline required')
    actual={}
    for name,asset in controller.scene.objects.items():
        if name not in baseline:raise ValueError('Every original body mass property is required')
        view=asset.root_physx_view;actual[name]={}
        for key,values in [('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms())]:
            measured=np.asarray(values.cpu());actual[name][key]=measured.tolist()
            if not np.allclose(measured,np.asarray(baseline[name][key]),rtol=1e-6,atol=1e-12):
                raise ValueError('E43 adapter changed original native '+key+': '+name)
    prior=copy.deepcopy(checkpoint['identity']);checkpoint['identity']=target
    checkpoint['context']['e43_ball_migration']=dict(old_identity=prior,new_identity=target,changed_objects=changed,
        only_collision_approximation_changed=True,source_visual_mesh_unchanged=True,
        old_native_mass_properties=baseline,new_native_mass_properties=actual,
        exact_solver_cache_restored=False,diagnostic_only=True)
    checkpoint['limitations'].append('Only the reviewed E43 ball collider changed; native mass/COM/inertia are pinned and read back. Original poses/velocities/controller targets are restored without evaluator history.')
    return reseal(checkpoint)
