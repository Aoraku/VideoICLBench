"""Explicit engineering checkpoint RGB-only 5Hz -> 1Hz migration.

The native world/controller is never reconfigured here. Scene construction
must already have opted into1Hz. Optional E50 control recipes are validated
against a read-only5Hz identity view, then this layer validates the sole RGB
cadence delta against the actual1Hz scene before native restoration.
"""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import hashlib,json,re
from .engineering_checkpoint import _hash,identity,reseal

SCHEMA='engineering-render-cadence-migration-v1'
INNER={
    'engineering-e50-contact-hold-migration-v1':'engineering_e50_contact_hold_fixture',
    'engineering-practical-card-contact-hold-migration-v1':'engineering_e50_contact_hold_fixture',
    'engineering-e50-slow-reference-migration-v1':'engineering_e50_slow_reference_fixture',
}
ENGINEERING_ROOT=Path('/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering')


def _pinned_source_profile(recipe):
    """Read original profile bytes on the same server, never transport them."""
    pin=recipe['source_profile_pin']
    if not isinstance(pin,dict)or set(pin)!={'path','sha256'}or not re.fullmatch('[a-f0-9]{64}',str(pin.get('sha256',''))):
        raise ValueError('Exact source profile path/SHA pin required')
    path=Path(pin['path']);checkpoint=Path(recipe.get('source_checkpoint_path',''))
    try:relative=path.relative_to(ENGINEERING_ROOT);cp_relative=checkpoint.relative_to(ENGINEERING_ROOT)
    except ValueError:raise ValueError('Pinned source profile must stay on engineering PFS')from None
    parts=relative.parts;cp_parts=cp_relative.parts
    if (len(parts)<4 or not re.fullmatch('execution-design-v3-20261102-[a-z0-9-]+',parts[0])
            or parts[1:3]!=('runtime','configs')or any(part in('.','..')for part in parts)
            or path.suffix!='.json'or not re.fullmatch('[a-zA-Z0-9_.-]+',path.name)
            or len(cp_parts)!=6 or cp_parts[0]!=parts[0]or cp_parts[1]!='result'
            or not re.fullmatch('room-[0-9]{2,3}-E[0-9]{2}-[ABC]-s[0-9]+',cp_parts[2])
            or cp_parts[3:5]!=('engineering-reference','checkpoints')or not cp_parts[5].endswith('.private.json')):
        raise ValueError('Pinned profile and native checkpoint require the same frozen root')
    for item in (path,*path.parents):
        if item==ENGINEERING_ROOT:break
        if item.is_symlink():raise ValueError('Pinned source profile cannot traverse symlinks')
    if not path.is_file()or path.stat().st_size>1024*1024:raise ValueError('Missing or oversized pinned source profile')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('Pinned source profile bytes SHA mismatch')
    config=json.loads(raw)
    if not isinstance(config,dict):raise ValueError('Pinned source profile JSON object required')
    return config,pin['sha256']

def materialize(controller,recipe):
    if recipe.get('schema')!=SCHEMA or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit diagnostic render-only migration required')
    source_hz=recipe.get('from_render_hz');target_hz=recipe.get('to_render_hz')
    e28=type(source_hz)is int and source_hz==30 and type(target_hz)is int and target_hz==5
    legacy=type(source_hz)is int and source_hz in(5,15)and type(target_hz)is int and target_hz==1
    if not(legacy or e28):
        raise ValueError('Only explicit5/15Hz to1Hz or E28 30Hz to5Hz engineering migration allowed')
    if (source_hz==15 or e28)and 'source_profile_pin'not in recipe:
        raise ValueError('Cadence migration requires pinned source profile bytes')
    current=identity(controller)
    allowed_tasks={f'E{i:02d}'for i in (*range(14,26),*range(44,51))}
    if (e28 and current['task']!='E28')or(not e28 and current['task']not in allowed_tasks):
        raise ValueError('Render-only migration scope is E14-E25 or E44-E50')
    actual=deepcopy(controller.scene.embodiment.config)
    if type(actual['physics'].get('render_hz'))is not int or actual['physics']['render_hz']!=target_hz:
        raise ValueError('Actual constructed scene must explicitly use target RGB cadence')
    if _hash(actual)!=current['embodiment_config_sha256']:
        raise ValueError('Actual scene configuration hash mismatch')
    old=deepcopy(actual);old['physics']['render_hz']=source_hz
    pinned=None
    if 'source_profile_pin'in recipe:
        config,raw_sha=_pinned_source_profile(recipe)
        if config!=old:raise ValueError('Pinned source profile differs beyond render cadence')
        pinned=dict(raw_sha256=raw_sha,canonical_sha256=_hash(config))
    cp=deepcopy(recipe['checkpoint'])
    if cp.get('schema')in INNER:
        if pinned is not None or source_hz!=5:raise ValueError('Nested control migration retains its separate5Hz admission')
        allowed={'E50'}if cp['schema']=='engineering-e50-slow-reference-migration-v1'else{'E47','E48','E49','E50'}
        if current['task']not in allowed:raise ValueError('Nested contact fixture task scope mismatch')
        import importlib
        module=importlib.import_module('.'+INNER[cp['schema']],__package__)
        spec=deepcopy(controller.scene.spec);spec['embodiment_config_sha256']=_hash(old)
        view=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config=old)))
        cp=module.materialize(view,cp)
    if cp.get('schema')!='engineering-native-checkpoint-v1' or cp.get('diagnostic_only')is not True:
        raise ValueError('Native engineering checkpoint required')
    digest=cp.pop('checkpoint_sha256',None)
    if digest!=_hash(cp):raise ValueError('Native checkpoint integrity mismatch')
    cp['checkpoint_sha256']=digest
    old_identity=deepcopy(cp['identity'])
    expected=deepcopy(old_identity)
    if pinned is not None:
        if old_identity['embodiment_config_sha256']not in pinned.values():raise ValueError('Native identity does not match pinned raw/canonical profile')
    else:expected['embodiment_config_sha256']=_hash(old)
    if cp['identity']!=expected:
        raise ValueError('Old profile differs beyond render cadence')
    expected['embodiment_config_sha256']=current['embodiment_config_sha256']
    if expected!=current:raise ValueError('Render migration assignment/source/physical identity mismatch')
    # Preserve every physical state/drive/velocity/history field byte-for-byte
    # at the JSON value level; only profile fingerprint and audit text change.
    cp['identity']=current
    cp['render_cadence_migration_receipt']=dict(
        from_render_hz=source_hz,to_render_hz=target_hz,source_identity=old_identity,
        source_profile_sha256=_hash(old),target_profile_sha256=current['embodiment_config_sha256'],
        source_native_checkpoint_integrity_sha256=digest,
        changed_config_fields=['physics.render_hz'],physics_parameters_unchanged=True,
        all_native_state_fields_preserved=True,history_reconstructed=False)
    if pinned is not None:
        cp['render_cadence_migration_receipt'].update(source_profile_raw_sha256=pinned['raw_sha256'],
            source_profile_pin_path=recipe['source_profile_pin']['path'],source_profile_pin_verified=True,
            source_profile_identity_encoding='raw_bytes_sha256'if old_identity['embodiment_config_sha256']==pinned['raw_sha256']else'canonical_json_sha256')
    cp.setdefault('limitations',[]).append('Explicit RGB cadence'+str(source_hz)+'Hz to'+str(target_hz)+'Hz only; physicsdt, native tick evidence, poses, drives and accepted actions unchanged.')
    return reseal(cp)
