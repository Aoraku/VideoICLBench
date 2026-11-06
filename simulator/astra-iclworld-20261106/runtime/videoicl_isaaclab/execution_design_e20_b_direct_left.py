"""B424: acquire the next original source blue directly with its destination hand."""
import numpy as np
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def run_segment(a,segment,parameters):
    cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{});s=a.scene.spec
    if (segment!='e20_b_pickup_blue_left_from424'or parameters!={}or s.get('id')!='E20'
            or s.get('variant')!='B'or s.get('seed')!=4201
            or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or s['execution_design'].get('condition')!='I'
            or not a.control_report.get('engineering_reference_only')or cp.get('diagnostic_only')is not True
            or source.get('steps')!=424 or source.get('physics_ticks')!=43240
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 B424 source-blue native boundary required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_e20_slots import _inside
    from .execution_design_segments_e17_e20 import _source,_source_rail,_held_with_contacts,DISK_SHA
    p=ExecutionDesignAuthor(a);name='blue_supply_1';_source(p,name,DISK_SHA,[.016,.01603,.000988]);_source_rail(p,name,3)
    state,contacts=p.snapshot();region=next(r for r in p.d['local_regions']if r['id']=='triangle')
    if any(any(v['grasp'])for v in state.values()):raise ToolExecutionError('B424 direct pickup requires actual empty hands')
    for n in('blue_supply_3','blue_supply_4'):
        if not _inside(p,region,n)or frozenset((n,region['actor']))not in contacts:
            raise ToolExecutionError('B424 previous blue support/containment required')
    initial=np.asarray(state[name]['pos'],float).copy();ref,side=p.pickup(name,side_override='left')
    _held_with_contacts(p,name,'left');current=np.asarray(p.snapshot()[0][name]['pos'])
    if side!='left'or float(current[2]-initial[2])<.020:
        raise ToolExecutionError('B424 direct true left source pickup lacks20mm payload rise')
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start,
        measured_payload_rise_m=float(current[2]-initial[2]),actual_held_actor=name,actual_hand=side)
