"""E44 v3->v4 guide-contact material only; preserve measured paper/robot state."""
from copy import deepcopy
from .engineering_checkpoint import _hash,identity,reseal,PHYSICAL_KEYS

SCHEMA='engineering-e44-guide-material-migration-v1'
MATERIAL=dict(static_friction=.03,dynamic_friction=.03,restitution=0.,friction_combine_mode='min')


def materialize(controller,recipe):
    if recipe.get('schema')!=SCHEMA or recipe.get('diagnostic_only')is not True:raise ValueError('Explicit guide-material engineering migration required')
    cp=deepcopy(recipe['checkpoint']);signature=cp.pop('checkpoint_sha256',None)
    if cp.get('schema')!='engineering-native-checkpoint-v1'or cp.get('state_quality')!='measured_native_state'or signature!=_hash(cp):raise ValueError('Sealed measured-native checkpoint required')
    cp['checkpoint_sha256']=signature;current=identity(controller)
    if current['task']!='E44':raise ValueError('E44 only')
    if _hash(controller.scene.embodiment.config)!=current['embodiment_config_sha256']:raise ValueError('Actual profile configuration mismatch')
    for key,value in cp['identity'].items():
        if key!='physical_geometry_sha256'and current.get(key)!=value:raise ValueError('Guide material changed case/source/profile: '+key)
    old={k:deepcopy(controller.scene.spec.get(k))for k in PHYSICAL_KEYS}
    marker=old['semantic']['execution_design_fold_fixture']
    if marker.get('schema')!='e44-passive-folding-rails-v4'or marker.get('guide_material_approximation')!='low_friction_passive_or_roller_guide_mu003_min_v1':raise ValueError('Explicit v4 passive guide approximation required')
    if len(old['fixtures'])!=4:raise ValueError('Reviewed four open guide surfaces required')
    for row in old['fixtures']:
        if row.get('source_fixture')!='e44-passive-folding-rails-v4'or row.get('engineering_guide_material')!=MATERIAL:raise ValueError('Unexpected guide material or fixture')
        row.pop('engineering_guide_material');row['source_fixture']='e44-passive-folding-rails-v3'
    marker['schema']='e44-passive-folding-rails-v3';marker.pop('guide_material_approximation');marker['fixed_geometry_sha256']=_hash(old['fixtures'])
    if _hash(old)!=cp['identity']['physical_geometry_sha256']:raise ValueError('Change extends beyond guide material/schema metadata')
    cp['identity']=current;cp.setdefault('limitations',[]).append('Only new passive guide contact material changes: low-friction/roller-guide approximation mu=.03/min. Original paper geometry, mass, friction, crease constitutive material, native measured pose/velocity/drive and task goals preserved.')
    return reseal(cp)
