"""Explicit engineering rule branch on identical E44 physical inputs."""
from copy import deepcopy
from .engineering_checkpoint import _hash,identity,reseal
from .execution_design import build_task_contract,REVISION_V3

SCHEMA='engineering-e44-rule-branch-v1'


def materialize(controller,recipe):
    if recipe.get('schema')!=SCHEMA or recipe.get('diagnostic_only')is not True:raise ValueError('Explicit E44 rule-only diagnostic branch required')
    cp=deepcopy(recipe['checkpoint']);signature=cp.pop('checkpoint_sha256',None)
    if cp.get('schema')!='engineering-native-checkpoint-v1'or cp.get('state_quality')!='measured_native_state'or signature!=_hash(cp):raise ValueError('Sealed measured-native checkpoint required')
    cp['checkpoint_sha256']=signature;current=identity(controller);old=cp['identity'];design=controller.scene.spec.get('execution_design',{})
    if current['task']!='E44'or old['task']!='E44'or design.get('revision')!=REVISION_V3:raise ValueError('Source-verified E44 only')
    source=recipe.get('source_variant');target=recipe.get('target_variant')
    if source not in('A','B','C')or target not in('A','B','C')or source==target or old['variant']!=source or current['variant']!=target:raise ValueError('Explicit different matching source/target variants required')
    for key,value in old.items():
        if key not in('variant','assignment_identity_sha256')and current.get(key)!=value:raise ValueError('Rule branch changed physical/source/profile identity: '+key)
    source_contract=build_task_contract('E44',source,current['seed'],design['condition'],revision=REVISION_V3)['execution_design']
    target_contract=build_task_contract('E44',target,current['seed'],design['condition'],revision=REVISION_V3)['execution_design']
    if old['assignment_identity_sha256']!=source_contract['assignment_identity_sha256']or current['assignment_identity_sha256']!=target_contract['assignment_identity_sha256']:raise ValueError('Rule branch assignment differs from original source contract')
    cp['identity']=current;cp.setdefault('limitations',[]).append('Explicit E44 rule-only engineering branch '+source+'->'+target+' from identical physical inputs; original measured dynamics/drive/material preserved, original evaluator history discarded. Not target source-initial evidence.')
    return reseal(cp)
