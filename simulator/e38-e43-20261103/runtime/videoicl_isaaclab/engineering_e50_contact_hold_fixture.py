"""Explicit practical-card rigid-payload contact-reference migration."""
import copy
from .engineering_checkpoint import _hash,identity,reseal,_array


def verify_profile(old,new):
    expected=copy.deepcopy(old)
    if 'public_gripper_payload_contact_hold'in expected['control']:
        raise ValueError('Contact hold migration must start disabled')
    expected['control']['public_gripper_payload_contact_hold']=True
    expected['control']['public_gripper_payload_preload_m']=.00005
    if expected!=new:raise ValueError('Contact hold changed additional configuration')


def materialize(controller,recipe):
    if recipe.get('schema')not in('engineering-e50-contact-hold-migration-v1','engineering-practical-card-contact-hold-migration-v1') or recipe.get('diagnostic_only')is not True:
        raise ValueError('Explicit payload-contact E50 engineering fixture required')
    cp=copy.deepcopy(recipe['checkpoint']);digest=cp.pop('checkpoint_sha256')
    if _hash(cp)!=digest:raise ValueError('Checkpoint digest mismatch')
    cp['checkpoint_sha256']=digest
    old=recipe['source_profile'];current=identity(controller)
    if _hash(old)!=cp['identity']['embodiment_config_sha256']:raise ValueError('Original profile mismatch')
    verify_profile(old,controller.scene.embodiment.config)
    if current['task']not in('E47','E48','E49','E50'):raise ValueError('Practical rigid-card task scope required')
    marker=controller.scene.spec.get('semantic',{}).get('engineering_card_approximation',{})
    if marker.get('schema')!='engineering-practical-card-1mm-v1'or marker.get('source_exact_geometry')is not False:
        raise ValueError('Explicit practical1mm source approximation required')
    from .execution_design_thin_cooking import SOURCES
    cards=[o for o in controller.scene.spec['objects']if o.get('source_asset',{}).get('relative_path')in SOURCES]
    if not cards:raise ValueError('Original SHA-pinned cards required')
    for card in cards:
        asset=card['source_asset']
        if SOURCES[asset['relative_path']]!=asset.get('sha256')or card['size'][2]!=.0005:
            raise ValueError('Unchanged original card identity and declared1mm thickness required')
    for key,value in cp['identity'].items():
        if key!='embodiment_config_sha256'and current.get(key)!=value:raise ValueError('Payload-contact fixture identity mismatch: '+key)
    if any(any(v)for v in cp.get('readback',{}).get('object_grasps',{}).values()):raise ValueError('Empty hands only')
    for side,goal in cp['controller']['grips'].items():
        if goal==.04:continue
        if goal!=0.:raise ValueError('Only empty open or fully closed pusher goals may migrate')
        robot=cp.get('robots',{}).get(side,{})
        names=robot.get('joint_names',[]);joints=old.get('gripper',{}).get('joints',[])
        if len(joints)!=2 or any(n not in names for n in joints):raise ValueError('Empty open or verified fully closed pusher requires actual finger joints')
        indices=[names.index(n)for n in joints]
        q=_array(robot.get('joint_pos'),(len(names),),'pusher actual q')[indices]
        target=_array(robot.get('drive_targets',{}).get('position'),(len(names),),'pusher drive')[indices]
        reference=_array(cp['controller'].get('gripper_reference',{}).get(side),(1,2),'pusher reference')
        if any(abs(float(v))>.001 for row in(q,target,reference.reshape(-1))for v in row):
            raise ValueError('Partially closed or loaded pusher cannot migrate')
    cp['identity']=current;cp['limitations'].append('Engineering actual-rigid-payload contact braking; logical goals and all physics unchanged.')
    return reseal(cp)
