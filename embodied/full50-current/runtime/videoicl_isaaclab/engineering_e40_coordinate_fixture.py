"""Strict single-variable E40 collision-coordinate engineering migration."""
import copy
import json
from pathlib import Path
import os
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS, _hash, identity, reseal
from .execution_design_clip_collision_coordinates import verify_only_coordinate_change


def materialize(controller, recipe, request):
    if (recipe.get('schema') != 'engineering-e40-coordinate-migration-v1'
            or recipe.get('diagnostic_only') is not True):
        raise ValueError('Explicit E40 numerical coordinate diagnostic required')
    checkpoint = copy.deepcopy(recipe['checkpoint'])
    digest = checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint) != digest:
        raise ValueError('Original E40 native checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256'] = digest
    old, new = recipe['source_scene'], controller.scene.spec
    if _hash({k: old.get(k) for k in PHYSICAL_KEYS}) != checkpoint['identity']['physical_geometry_sha256']:
        raise ValueError('Original E40 physical scene does not match checkpoint')
    changed = verify_only_coordinate_change(old, new)
    current = identity(controller)
    for key, value in checkpoint['identity'].items():
        if key != 'physical_geometry_sha256' and current.get(key) != value:
            raise ValueError('E40 migration identity mismatch: ' + key)
    differences = []
    unexpected = []
    native = {}
    baseline = recipe['native_mass_properties']
    corrected = recipe.get('corrected_native_mass_properties')
    if corrected:
        audit = recipe['corrected_native_cooking_audit']
        if (_hash(audit) != recipe['corrected_native_cooking_audit_sha256']
                or audit.get('schema') != 'e40-native-cooked-source-audit-v1'
                or audit.get('public_actions') != 0 or not audit.get('all_meshes_received')
                or audit.get('native_mass_properties') != corrected
                or len(audit.get('meshes', [])) != 87
                or max(r['max_cooked_outside_source_m'] for r in audit['meshes']) > .0001
                or max(r['max_source_outside_cooked_m'] for r in audit['meshes']) > .0001):
            raise ValueError('Measured source-faithful E40 cooked dynamics baseline required')
    for name, asset in controller.scene.mechanisms.items():
        if name not in baseline or list(asset.body_names) != baseline[name]['body_names']:
            raise ValueError('Missing source-bound E40 native body mass baseline')
        view = asset.root_physx_view
        native[name] = dict(body_names=list(asset.body_names))
        for key, value in (('masses_kg', view.get_masses()),
                           ('inertias_kg_m2', view.get_inertias()),
                           ('centres_of_mass', view.get_coms())):
            actual = np.asarray(value.cpu())
            native[name][key] = actual.tolist()
            if not np.allclose(actual, np.asarray(baseline[name][key]), rtol=1e-6, atol=1e-12):
                differences.append(dict(mechanism=name, property=key,
                                        old=baseline[name][key], new=actual.tolist()))
            expected = baseline[name][key] if key == 'masses_kg' or not corrected else corrected[name][key]
            if not np.allclose(actual, np.asarray(expected), rtol=1e-6, atol=1e-12):
                unexpected.append(dict(mechanism=name, property=key))
    report = dict(diagnostic_only=True, changed_mechanisms=changed,
                  original_native_mass_properties=baseline, new_native_mass_properties=native,
                  native_mass_differences=differences, unexpected_mass_differences=unexpected,
                  corrected_source_dynamics_baseline_used=bool(corrected), public_actions=0)
    audit_path = Path(os.environ['VIC_ENGINEERING_CHECKPOINT_REQUEST']).parent / 'e40-coordinate-native-mass-preflight.private.json'
    audit_path.write_text(json.dumps(report, indent=2) + '\n'); audit_path.chmod(0o600)
    audit_only = recipe.get('audit_native_mass_difference_only') is True
    if audit_only and request.get('entry') != 'e40-cooked-only':
        raise ValueError('E40 mass-difference measurement is restricted to zero-action geometry audit')
    if unexpected and not audit_only:
        raise ValueError('E40 coordinate migration changed original native mass properties')
    previous = copy.deepcopy(checkpoint['identity'])
    checkpoint['identity'] = current
    checkpoint['context']['e40_coordinate_migration'] = dict(
        old_identity=previous, new_identity=current, diagnostic_only=True,
        source_world_vertices_and_topology_verified_by_spawner=True,
        native_mass_properties_equal=not differences, zero_action_mass_difference_audit=audit_only)
    checkpoint['context']['e40_coordinate_migration']['corrected_source_dynamics_baseline_used'] = bool(corrected)
    checkpoint['limitations'].append('Explicit E40 numerical collision-coordinate diagnostic; original world vertices and topology retained, PhysX caches not serialized.')
    return reseal(checkpoint)
