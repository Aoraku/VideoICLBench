"""Passive E18 native contact offsets; no action or physics parameter writes."""
import json,numpy as np


def run_segment(author,entry,parameters):
    cp=getattr(author,'_engineering_resume_checkpoint',{});spec=author.scene.spec
    if (entry!='e18_contact_offsets_from102'or parameters!={}or
        (spec['id'],spec['variant'],spec['seed'])!=('E18','A',4201)or
        (cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=(102,10211)or
        not author.control_report.get('engineering_reference_only')or
        not getattr(author.c,'_engineering_diagnostic_only',False)or
        not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Explicit original E18 native102 passive diagnostic required')
    from .author_native_grip_probe import cpu_copy
    scene=author.scene;physics=scene.contacts['red'][0]._physics_sim_view
    targets={'left_finger1':f'{scene.root_path}/left_robot/{scene.embodiment.fingers[0]}',
             'left_finger2':f'{scene.root_path}/left_robot/{scene.embodiment.fingers[1]}',
             'left_palm':f'{scene.root_path}/left_robot/panda_hand'}
    cabinet=next(x for x in spec['mechanisms']if x['id']=='cabinet')
    for name,path in cabinet['mechanical_asset']['contact_links'].items():
        targets['cabinet_'+name]=f'{scene.root_path}/Mechanisms/cabinet/'+path
    result={}
    for name,path in targets.items():
        view=physics.create_rigid_body_view(path);row={}
        for method in ('get_contact_offsets','get_rest_offsets'):
            try:
                values=cpu_copy(getattr(view,method)());assert np.isfinite(values).all()
                row[method]=values.tolist()
            except Exception as exc:row[method]={'read_error':type(exc).__name__+': '+str(exc)[:120]}
        result[name]=row
    (author.out/'e18-passive-native-contact-offsets.private.json').write_text(json.dumps(dict(
        read_only=True,actions=0,physics_parameters_written=False,native_properties=result),allow_nan=False)+'\n')
    return dict(local_completed=True,read_only_physics_probe=True,actions=0,full_task_acceptance=False)
