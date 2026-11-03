"""Narrow diagnostic migration: same measured state, source-faithful thin cook."""
import copy
import json,os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from .execution_design_thin_cooking import verify_only_cooking_change

# Exact native readback of the source-faithful100x E50 card cook, v38.
# Its former automatic inertia/COM came from the demonstrably distorted cook.
CORRECTED_CARD_PROPERTIES_SHA256='52997acdedd915b7b35e0f975abb480902f39b261a6d3a213851f382ee234050'


def materialize(controller,recipe):
    if (recipe.get('schema')!='engineering-thin-cooking-migration-v1' or
            recipe.get('diagnostic_only')is not True):
        raise ValueError('Explicit thin cooking diagnostic migration required')
    checkpoint=copy.deepcopy(recipe['checkpoint']);digest=checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint)!=digest:raise ValueError('Original native checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=digest
    old=recipe['source_scene'];new=controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Archived source scene does not match original checkpoint geometry')
    changed=verify_only_cooking_change(old,new);current=identity(controller)
    for key,value in checkpoint['identity'].items():
        if key!='physical_geometry_sha256'and current.get(key)!=value:
            raise ValueError('Thin cooking migration identity mismatch: '+key)
    original_properties=recipe['native_mass_properties'];baseline=original_properties
    corrected=recipe.get('corrected_native_mass_properties')
    if corrected is not None:
        if any(o.get('reviewed_collision_settings',{}).get('coordinate_factor')!=100 for o in new['objects']if o['id']in changed):
            raise ValueError('Corrected native dynamics requires the reviewed100x source-faithful cook')
        if set(corrected)!=set(original_properties):raise ValueError('Corrected dynamics actor identity changed')
        for name,values in corrected.items():
            if name in changed:
                if _hash(values)!=CORRECTED_CARD_PROPERTIES_SHA256:raise ValueError('Corrected card native dynamics SHA mismatch')
                if values['masses_kg']!=original_properties[name]['masses_kg']:raise ValueError('Source card mass changed')
            elif values!=original_properties[name]:raise ValueError('Non-card native dynamics changed')
        baseline=corrected
    actual_properties={}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view
        actual_properties[name]=dict(masses_kg=view.get_masses().cpu().tolist(),inertias_kg_m2=view.get_inertias().cpu().tolist(),centres_of_mass=view.get_coms().cpu().tolist())
    request_path=os.environ.get('VIC_ENGINEERING_CHECKPOINT_REQUEST')
    if request_path:
        from .engineering_cooked_geometry_audit import native_cooked_meshes
        author=SimpleNamespace(scene=controller.scene)
        def frame(ref):
            row=controller.snapshot()[0][ref['actor']]
            return np.asarray(row['pos']),np.asarray(row['mat'])
        cooked=native_cooked_meshes(author,SimpleNamespace(frame=frame),dict(actor=changed[0]),'left')
        report=dict(original_identity=checkpoint['identity'],new_identity=current,
            baseline_native_mass_properties=baseline,actual_native_mass_properties=actual_properties,native_cooked_geometry=cooked,
            public_actions=controller.steps,restore_admission_pending=True)
        (Path(request_path).parent/'thin-cooking-migration-preflight.private.json').write_text(json.dumps(report,indent=2))
    for name,asset in controller.scene.objects.items():
        if name not in baseline:raise ValueError('Missing original native mass/inertia binding')
        view=asset.root_physx_view;previous=baseline[name]
        for key,actual in [('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms())]:
            if not np.allclose(np.asarray(actual.cpu()),np.asarray(previous[key]),rtol=1e-6,atol=1e-12):
                raise ValueError('Thin cooking migration changed original native '+key+': '+name+
                    '; original='+repr(previous[key])+'; new='+repr(actual.cpu().tolist()))
    old_identity=copy.deepcopy(checkpoint['identity']);checkpoint['identity']=current
    checkpoint['context']['thin_cooking_migration']=dict(old_identity=old_identity,new_identity=current,
        changed_objects=changed,physical_fields_changed=['reviewed_collision_settings.hull_vertex_limit','reviewed_collision_settings.min_thickness_m']+
            (['reviewed_collision_settings.coordinate_factor']if any(o.get('reviewed_collision_settings',{}).get('coordinate_factor')for o in new['objects'])else[]),
        source_geometry_mass_unchanged=True,source_derived_native_dynamics_corrected=corrected is not None,
        original_native_mass_properties=original_properties,accepted_native_mass_properties=baseline,
        source_geometry_mass_inertia_unchanged=corrected is None,diagnostic_only=True)
    checkpoint['limitations'].append('Same measured state restored with explicitly reviewed thin-card cooking; PhysX solver caches are not recovered.')
    return reseal(checkpoint)
