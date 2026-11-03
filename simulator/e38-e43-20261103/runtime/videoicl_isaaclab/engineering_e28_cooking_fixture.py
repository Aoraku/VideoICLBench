"""Explicit diagnostic old-hull to original-source SDF migration for E28."""
import copy,json,os
from pathlib import Path
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from .execution_design_e28_cooking import verify_only_cooking_change

SCHEMA='engineering-e28-cooking-migration-v1'


def materialize(controller,recipe,request):
    if recipe.get('schema')!=SCHEMA or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit E28 source-fidelity diagnostic required')
    if (recipe.get('rebuild_spatula_grasp_with_public_close')is not True
            or request.get('parameters',{}).get('rebuild_source_fidelity_grasp')is not True):
        raise ValueError('Three actual public GRASP samples required after E28 collider migration')
    if (any('spatula'in pair for pair in request.get('required_contacts',[]))
            or any(pair[0]=='spatula'for pair in request.get('required_grasps',[]))):
        raise ValueError('Old hull grasp/contact cannot be asserted for new SDF')
    checkpoint=copy.deepcopy(recipe['checkpoint']);digest=checkpoint.pop('checkpoint_sha256',None)
    if _hash(checkpoint)!=digest:raise ValueError('Original E28 checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=digest
    old,new=recipe['source_scene'],controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Original E28 scene/checkpoint mismatch')
    changed=verify_only_cooking_change(old,new);current=identity(controller)
    for key,value in checkpoint['identity'].items():
        if key!='physical_geometry_sha256'and current.get(key)!=value:
            raise ValueError('E28 fidelity assignment/source/profile mismatch: '+key)
    native={};objects={o['id']:o for o in new['objects']}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view
        native[name]={key:value.cpu().tolist()for key,value in(
            ('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms()))}
        if name in changed and not np.allclose(native[name]['masses_kg'],float(objects[name]['mass']),rtol=1e-5,atol=1e-10):
            raise ValueError('E28 source fidelity changed nominal spatula mass')
    previous=copy.deepcopy(checkpoint['identity']);checkpoint['identity']=current
    checkpoint.get('readback',{}).get('object_grasps',{}).pop('spatula',None)
    report=dict(diagnostic_only=True,changed_objects=changed,old_identity=previous,new_identity=current,
        source_vertices_topology_food_mass_friction_table_and_task_unchanged=True,
        collision_approximation='sdf',sdf_resolution=384,actual_native_mass_properties=native,
        automatically_derived_inertia_com_may_change_with_cooking=True,
        old_solver_contact_or_grasp_cache_restored=False,requires_three_public_grasp_samples=True)
    checkpoint.setdefault('context',{})['e28_source_cooking_migration']=report
    checkpoint.setdefault('limitations',[]).append(
        'Explicit E28 whole-hull to original-triangle SDF384 migration. Physical signature changes honestly; '
        'poses/q/qd/drives are original, automatic native inertia/COM read back, old contacts/history not restored. '
        'Three genuine public GRASP samples required; diagnostic suffix is not source-initial acceptance.')
    p=Path(os.environ['VIC_ENGINEERING_CHECKPOINT_REQUEST']).parent/'e28-source-cooking-migration.private.json'
    p.write_text(json.dumps(report,indent=2)+'\n');p.chmod(0o600)
    return reseal(checkpoint)
