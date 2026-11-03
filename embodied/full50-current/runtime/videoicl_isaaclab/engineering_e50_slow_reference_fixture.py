"""One explicit E50 slow-reference engineering checkpoint migration."""
import copy
from .engineering_checkpoint import _hash,identity,reseal


def verify_profile(old,new):
    expected=copy.deepcopy(old)
    if expected['control'].get('public_gripper_reference_speed_m_s')!=.01:
        raise ValueError('Expected original 10mm/s explicit reference')
    expected['control']['public_gripper_reference_speed_m_s']=.001
    if expected!=new:raise ValueError('Slow reference changed additional configuration')


def materialize(controller,recipe):
    if recipe.get('schema')!='engineering-e50-slow-reference-migration-v1' or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit slow E50 engineering fixture required')
    cp=copy.deepcopy(recipe['checkpoint']);digest=cp.pop('checkpoint_sha256')
    if _hash(cp)!=digest:raise ValueError('Checkpoint digest mismatch')
    cp['checkpoint_sha256']=digest
    old=recipe['source_profile'];current=identity(controller)
    if _hash(old)!=cp['identity']['embodiment_config_sha256']:raise ValueError('Original profile mismatch')
    verify_profile(old,controller.scene.embodiment.config)
    if current['task']!='E50':raise ValueError('E50 only')
    for key,value in cp['identity'].items():
        if key!='embodiment_config_sha256'and current.get(key)!=value:raise ValueError('Slow fixture identity mismatch: '+key)
    if any(any(v)for v in cp.get('readback',{}).get('object_grasps',{}).values())or any(v!=.04 for v in cp['controller']['grips'].values()):raise ValueError('Empty open hands only')
    cp['identity']=current;cp['limitations'].append('Engineering reference speed 1mm/s; logical goals and all physics unchanged.')
    return reseal(cp)
