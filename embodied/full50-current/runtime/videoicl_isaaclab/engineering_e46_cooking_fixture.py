"""Narrow E46 collider-coordinate migration with explicit native dynamics audit."""
import copy
import json
import os
from pathlib import Path
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS,_hash,identity,reseal
from .execution_design_e46_cooking import verify_only_cooking_change


def materialize(controller,recipe,request):
    if recipe.get('schema')!='engineering-e46-cooking-migration-v1'or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit E46 cooking diagnostic migration required')
    checkpoint=copy.deepcopy(recipe['checkpoint']);digest=checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint)!=digest:raise ValueError('Original E46 checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=digest
    old,new=recipe['source_scene'],controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Original E46 physical scene/checkpoint mismatch')
    verify_only_cooking_change(old,new);current=identity(controller)
    for key,value in checkpoint['identity'].items():
        if key!='physical_geometry_sha256'and current.get(key)!=value:
            raise ValueError('E46 cooking identity mismatch: '+key)
    native={};objects={o['id']:o for o in new['objects']}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view
        native[name]={key:value.cpu().tolist()for key,value in(
            ('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms()))}
        if not np.allclose(native[name]['masses_kg'],float(objects[name]['mass']),rtol=1e-5,atol=1e-10):
            raise ValueError('E46 numerical cooking changed source mass: '+name)
    audit_only=recipe.get('audit_native_dynamics_only')is True
    corrected=recipe.get('corrected_native_mass_properties')
    if audit_only:
        if request.get('entry')!='e46-cooked-blade-audit':raise ValueError('E46 dynamics preflight admits only zero-action ray audit')
    else:
        audit=recipe.get('corrected_cooking_audit',{})
        if (_hash(audit)!=recipe.get('corrected_cooking_audit_sha256')or
                audit.get('schema')!='e46-source-cooked-front-edge-audit-v1'or
                audit.get('public_actions_issued')!=0 or audit.get('native_surface_hits',0)<100 or
                audit.get('native_mass_properties')!=corrected or
                not audit.get('coordinate_reexpression')or
                any(r['world_vertex_max_error_m']>1e-7 or not r['source_topology_unchanged']for r in audit['coordinate_reexpression'])):
            raise ValueError('Source-bound zero-action E46 corrected cooking audit required')
        for name,row in native.items():
            if name not in corrected:raise ValueError('Missing corrected E46 body baseline')
            for key,actual in row.items():
                if not np.allclose(actual,corrected[name][key],rtol=1e-6,atol=1e-12):
                    raise ValueError('E46 corrected dynamics baseline mismatch: '+name+'/'+key)
    report=dict(diagnostic_only=True,audit_only=audit_only,actual_native_mass_properties=native,
        source_mass_unchanged=True,source_world_vertices_and_topology_verified_by_spawner=True)
    out=Path(os.environ['VIC_ENGINEERING_CHECKPOINT_REQUEST']).parent/'e46-cooking-native-dynamics-preflight.private.json'
    out.write_text(json.dumps(report,indent=2)+'\n');out.chmod(0o600)
    previous=copy.deepcopy(checkpoint['identity']);checkpoint['identity']=current
    checkpoint['context']['e46_cooking_migration']=dict(old_identity=previous,new_identity=current,
        diagnostic_only=True,audit_only=audit_only,source_mass_unchanged=True,
        source_world_vertices_and_topology_verified_by_spawner=True,actual_native_mass_properties=native)
    checkpoint['limitations'].append('Explicit E46-only source collision-coordinate conditioning; original source mass/geometry/topology retained, corrected cooked COM/inertia separately audited, PhysX caches not restored.')
    return reseal(checkpoint)
