"""Exact two-control-field profile migration for a diagnostic thin-card suffix."""
from copy import deepcopy
from .engineering_checkpoint import _hash,identity,reseal

OLD_PROFILE='7548e7dcc5a5418ee460b31736e54ad1e917e7168db9a99a4a41c1897f2542be'
NEW_PROFILE='b0c2a24b43c8d4496a99aa033b2925a7cd79891e37b85b0f71cf388bd99abb97'
FIELDS=dict(public_gripper_reference_speed_m_s=.01,public_gripper_reference_acceleration_m_s2=.05)


def materialize(controller,recipe):
    if recipe.get('schema')!='engineering-gripper-reference-profile-migration-v1'or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit diagnostic gripper-reference migration required')
    if controller.scene.spec['id']not in('E47','E48','E49','E50'):
        raise ValueError('First gripper-reference migration is limited to source thin-card tasks')
    checkpoint=deepcopy(recipe['checkpoint']);signature=checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint)!=signature:raise ValueError('Original native checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256']=signature;old=recipe['source_profile']
    if _hash(old)!=OLD_PROFILE or checkpoint['identity']['embodiment_config_sha256']!=OLD_PROFILE:
        raise ValueError('Original reviewed source profile identity mismatch')
    if any(name in old['control']for name in FIELDS):raise ValueError('Old profile already has gripper reference controls')
    expected=deepcopy(old);expected['control'].update(FIELDS)
    actual=controller.scene.embodiment.config
    if _hash(expected)!=NEW_PROFILE or actual!=expected:
        raise ValueError('Migration permits exactly the two reviewed gripper command-reference controls')
    current=identity(controller);previous=checkpoint['identity']
    if current['embodiment_config_sha256']!=NEW_PROFILE:
        raise ValueError('New native profile fingerprint mismatch')
    if {k:v for k,v in current.items()if k!='embodiment_config_sha256'}!={k:v for k,v in previous.items()if k!='embodiment_config_sha256'}:
        raise ValueError('Gripper migration changed assignment/source/physical geometry')
    if any(k in checkpoint['controller']for k in('gripper_reference','gripper_reference_velocity')):
        raise ValueError('Old-profile checkpoint cannot declare new ramp state')
    readback=checkpoint.get('readback',{})
    if readback.get('available')is not True:raise ValueError('Empty-gripper native readback required for old-profile migration')
    if any(any(flags)for flags in readback.get('object_grasps',{}).values()):
        raise ValueError('Old-profile held payload cannot seed a softer reference from actual q')
    fingers={f'{side}_finger{i}'for side in('left','right')for i in(1,2)}
    if any(set(pair)&fingers and set(pair)-fingers-{'table'}for pair in readback.get('contacts',[])):
        raise ValueError('Old-profile grippers must have no payload or mechanism contacts')
    if any(value not in(0.,.04)for value in checkpoint['controller']['grips'].values()):
        raise ValueError('Migration requires original binary gripper goals')
    checkpoint['identity']=current
    checkpoint['context']['public_gripper_reference_migration']=dict(old_identity=previous,new_identity=current,
        only_added_control_fields=FIELDS,original_binary_gripper_goal_unchanged=True,
        geometry_material_mass_inertia_effort_gains_unchanged=True,diagnostic_only=True)
    checkpoint['assumptions'].append('Old checkpoint has no gripper-reference state; first restored tick seeds once from measured joint q and zero reference velocity')
    checkpoint['limitations'].append('Reviewed public gripper command ramp enabled; original open/close goal and hardware/physics parameters are unchanged')
    return reseal(checkpoint)
