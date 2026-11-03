"""Strict same-state migration for one E50 contact-generation diagnostic."""
import copy
import numpy as np
from .engineering_checkpoint import PHYSICAL_KEYS, _hash, identity, reseal
from .engineering_thin_contact_skin import (PROFILE_FIELD, OFFSET, MARKER,
    verify_only_skin_change, native_readback, verify_native_finger_geometry)


def materialize(controller, recipe):
    if recipe.get('schema') != 'engineering-thin-skin50-migration-v1' or recipe.get('diagnostic_only') is not True:
        raise ValueError('Explicit E50 numerical contact-skin migration required')
    cp = copy.deepcopy(recipe['checkpoint'])
    digest = cp.pop('checkpoint_sha256')
    if _hash(cp) != digest:
        raise ValueError('Original native checkpoint integrity mismatch')
    cp['checkpoint_sha256'] = digest
    old = recipe['source_scene']
    new = controller.scene.spec
    if _hash({k: old.get(k) for k in PHYSICAL_KEYS}) != cp['identity']['physical_geometry_sha256']:
        raise ValueError('Original contact-skin scene identity mismatch')
    verify_only_skin_change(old, new)
    profile = recipe['source_profile']
    if _hash(profile) != cp['identity']['embodiment_config_sha256']:
        raise ValueError('Original skin diagnostic profile identity mismatch')
    expected = copy.deepcopy(profile)
    if PROFILE_FIELD in expected['physics']:
        raise ValueError('Original profile already has a skin override')
    expected['physics'][PROFILE_FIELD] = OFFSET
    if expected != controller.scene.embodiment.config:
        raise ValueError('Skin diagnostic changed another profile setting')
    current = identity(controller)
    for key, value in cp['identity'].items():
        if key not in ('physical_geometry_sha256', 'embodiment_config_sha256') and current.get(key) != value:
            raise ValueError('Contact-skin migration identity mismatch: ' + key)
    readback = cp.get('readback', {})
    if (readback.get('available') is not True or any(any(flags) for flags in readback.get('object_grasps', {}).values())
            or any(value != .04 for value in cp['controller']['grips'].values())):
        raise ValueError('Contact-skin comparison starts from empty open grippers only')
    from .engineering_thin_cooking_fixture import CORRECTED_CARD_PROPERTIES_SHA256
    baseline = recipe['native_card_properties']
    if _hash(baseline) != CORRECTED_CARD_PROPERTIES_SHA256:
        raise ValueError('Original corrected native card dynamics SHA mismatch')
    view = controller.scene.objects['card'].root_physx_view
    actual = {}
    for key, method in [('masses_kg', 'get_masses'), ('inertias_kg_m2', 'get_inertias'),
                        ('centres_of_mass', 'get_coms')]:
        raw = getattr(view, method)()
        values = np.asarray(raw.cpu() if hasattr(raw, 'cpu') else raw)
        actual[key] = values.tolist()
        if not np.allclose(values, baseline[key], rtol=1e-6, atol=1e-12):
            raise ValueError('Contact-skin diagnostic changed native card ' + key)
    offsets = native_readback(controller)
    geometry = verify_native_finger_geometry(controller)
    import os, json
    from pathlib import Path
    request = os.environ.get('VIC_ENGINEERING_CHECKPOINT_REQUEST')
    if request:
        (Path(request).parent/'thin-contact-skin-preflight.private.json').write_text(json.dumps(dict(
            actual_native_offsets=offsets, native_card_properties=actual,
            finger_cooked_geometry_against_original=geometry,
            fresh_scene_receipt=getattr(controller.scene,'engineering_thin_contact_skin_receipt',None),
            public_actions=0, restore_admission_pending=True),indent=2))
    if not geometry or not all(row['passed']for row in geometry.values()):
        raise ValueError('Contact-skin comparison changed measured native finger geometry')
    previous = copy.deepcopy(cp['identity'])
    cp['identity'] = current
    cp['context']['contact_skin_numeric_diagnostic'] = dict(diagnostic_only=True,
        old_identity=previous, new_identity=current, only_profile_field='physics.' + PROFILE_FIELD,
        marker=new['semantic'][MARKER], actual_native_offsets=offsets,
        actual_native_finger_geometry=geometry,
        actual_native_card_properties=actual, public_actions=0,
        geometry_material_mass_inertia_gains_gripper_goal_unchanged=True)
    cp['limitations'].append('Fresh-scene 50um card/two-finger contact-generation diagnostic only; never source-default or formal acceptance.')
    return reseal(cp)
