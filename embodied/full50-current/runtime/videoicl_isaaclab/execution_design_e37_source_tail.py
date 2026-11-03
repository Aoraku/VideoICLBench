"""Engineering-only E37 continuation after the measured source handle prefix.

The source pickup, task history and scoring state are never replayed/restored.
All remaining turns, catches and placements use the existing native authors.
"""
from copy import deepcopy
import json
import numpy as np


def run(author,payload):
    from .realworld_structural_expert import StructuralAuthor
    from .execution_design_e37_regrip import _scope
    from .execution_design_e37_planned_approach import run as approach
    from .execution_design_e37_planned_slot import run as seat
    from .execution_design_e37_unscrew import finish_role
    from .execution_design_e37_free_screw import catch_and_clear
    from .execution_design_e37_source import place_caught_screw
    from .execution_design_e37_table_guard import guard_actions
    from .engineering_checkpoint import capture
    p=StructuralAuthor(author);_scope(p);spec=p.spec;context=payload.get('context',{})
    if not(getattr(p.c,'_engineering_diagnostic_only',False)
           and payload.get('diagnostic_only')is True
           and payload.get('identity',{}).get('variant')==p.variant
           and payload.get('source',{}).get('steps')==161):
        raise ValueError('Explicit native E37 source-prefix161 continuation required')
    driver=next(o for o in spec['objects']if o['id']=='driver')
    settings=driver.get('reviewed_collision_settings',{})
    if settings.get('approximation')!='sdf'or settings.get('sdf_resolution')!=384:
        raise ValueError('The measured original SDF384 driver must be retained')
    ref=dict(actor='driver',**deepcopy(p.geometry['driver_grasp']))
    side='left';author.carried_payload=('driver',side)
    roles=(['left'],['right'],['left','right'])[p.index]
    report=dict(task='E37',variant=p.variant,diagnostic_only=True,
        source_initial_episode=False,source_prefix_steps=161,
        source_prefix_root=context.get('original_source_root'),
        source_prefix_variant=context.get('source_prefix_variant',p.variant),
        original_rules_and_score_unchanged=True,history_not_restored=True,
        completed_roles=[],phases=[])
    path=author.out/'E37-source-tail-workflow.private.json'
    def write():path.write_text(json.dumps(report,default=lambda v:v.tolist(),indent=2)+'\n')
    def boundary(stage,role):
        state=capture(p.c,stage,context=dict(carried_payload=['driver',side],active_side=side,
            role=role,source_prefix_steps=161,source_initial_episode=False,
            original_source_root=report['source_prefix_root']))
        folder=author.out/'checkpoints';folder.mkdir(exist_ok=True)
        cp=folder/(stage+'.private.json');cp.write_text(json.dumps(state,indent=2)+'\n')
        report['phases'].append(dict(stage=stage,steps=p.c.steps,checkpoint=str(cp)));write()
    try:
        p.require_held(ref,side);p.act();p.require_held(ref,side)
        with guard_actions(p)as observer:
            p._e37_table_readback=observer['snapshot']
            for role in roles:
                entry=p.s['screw_roles'][role];fixture=entry['fixture']
                axis=p.frame(fixture['ref'])[1]@np.asarray(fixture['axis_local'],float)
                axis/=np.linalg.norm(axis)
                head=lambda entry=entry:p.body_point(dict(actor=entry['screw']),entry['head_socket_local'])
                approach(p,ref,side,entry,axis,head,slot_sign=-1,engage=False)
                boundary('e37-source-tail-'+role+'-approach-complete',role)
                seat(p,ref,side,entry,axis,head,torque_degrees=0.)
                boundary('e37-source-tail-'+role+'-seated',role)
                turned=finish_role(p,ref,side,entry,axis,head)
                boundary('e37-source-tail-'+role+'-thread-free',role)
                def free(entry=entry):
                    measured=p.c.evaluator.screw_measure(entry)
                    return measured['overlap']<=1e-6 and measured['fixture_contact']==0
                screw_ref=p.ref(entry['screw'])
                caught=catch_and_clear(p,screw_ref,ref,free,axis,main_side=side)
                placed=place_caught_screw(p,entry['screw'],screw_ref,caught,
                    p.geometry['removed_screw_placements'][role],ref,main_side=side)
                report['completed_roles'].append(dict(role=role,actual_turn=turned,actual_placement=placed))
                boundary('e37-source-tail-'+role+'-placed',role)
        p.wait(2);author.note('final')
        native=p.c.evaluator.result();report.update(segment_finished=True,
            segment_passed=bool(native.get('success')),original_native_result=native,
            native_task_acceptance=False,actions=p.c.steps-p.start)
        write();return report
    except Exception as error:
        report.update(error=type(error).__name__+': '+str(error),actions=p.c.steps-p.start,
            original_native_result=p.c.evaluator.result(),segment_finished=False,segment_passed=False)
        write();raise
