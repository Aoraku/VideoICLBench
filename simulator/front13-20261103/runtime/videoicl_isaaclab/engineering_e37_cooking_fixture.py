"""Explicit diagnostic fixture migration from inflated VHACD to source SDF."""
import copy
import json
import os
from pathlib import Path
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from .execution_design_e37_cooking import verify_only_cooking_change


def materialize(controller,recipe,request):
    if (recipe.get('schema')!='engineering-e37-cooking-migration-v1'
            or recipe.get('diagnostic_only')is not True):
        raise ValueError('Explicit E37 source blade diagnostic migration required')
    checkpoint=copy.deepcopy(recipe['checkpoint']);digest=checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint)!=digest:raise ValueError('Original E37 checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=digest
    old,new=recipe['source_scene'],controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Original E37 scene/checkpoint physical identity mismatch')
    changed=verify_only_cooking_change(old,new);current=identity(controller)
    for key,value in checkpoint['identity'].items():
        if key!='physical_geometry_sha256'and current.get(key)!=value:
            raise ValueError('E37 source fidelity identity mismatch: '+key)
    native={};objects={o['id']:o for o in new['objects']}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view
        native[name]={key:value.cpu().tolist()for key,value in(
            ('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms()))}
        # Kinematic fixtures expose backend mass sentinels rather than their
        # source nominal mass. Only the changed dynamic driver needs this
        # additional native mass check; every source object field is already
        # compared exactly by verify_only_cooking_change above.
        if name in changed and not np.allclose(native[name]['masses_kg'],float(objects[name]['mass']),rtol=1e-5,atol=1e-10):
            raise ValueError('E37 source fidelity changed declared mass: '+name)
    previous=copy.deepcopy(checkpoint['identity']);checkpoint['identity']=current
    rebuild=recipe.get('rebuild_driver_grasp_with_public_close')is True
    if rebuild:
        if request.get('parameters',{}).get('rebuild_source_fidelity_grasp')is not True:
            raise ValueError('Migration requires explicit physical public grasp rebuild')
        if any('driver'in pair for pair in request.get('required_contacts',[]))or any(pair[0]=='driver'for pair in request.get('required_grasps',[])):
            raise ValueError('Old VHACD contacts cannot be asserted before source SDF grasp rebuild')
        # Readback metadata is not physics. The next author stage explicitly
        # closes the actual native fingers and requires opposed real contact.
        checkpoint.get('readback',{}).get('object_grasps',{}).pop('driver',None)
    report=dict(diagnostic_only=True,changed_objects=changed,
        old_identity=previous,new_identity=current,source_geometry_mass_friction_and_slot_unchanged=True,
        source_vertices_and_topology_preserved=True,collision_approximation='sdf',sdf_resolution=384,
        actual_native_mass_properties=native,
        automatically_derived_native_inertia_com_may_change_with_collision_fidelity=True,
        original_physx_solver_contact_cache_restored=False,
        source_grasp_not_assumed_after_collider_migration=rebuild)
    checkpoint.setdefault('context',{})['e37_source_cooking_migration']=report
    checkpoint.setdefault('limitations',[]).append(
        'Explicit E37 original-source SDF384 fidelity migration; original slot/shape/mass/friction retained, '
        'automatic native COM/inertia recorded, old PhysX friction caches not restored; '
        'diagnostic suffix cannot count as a whole source episode.')
    path=Path(os.environ['VIC_ENGINEERING_CHECKPOINT_REQUEST']).parent/'e37-source-cooking-migration.private.json'
    path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600)
    return reseal(checkpoint)
