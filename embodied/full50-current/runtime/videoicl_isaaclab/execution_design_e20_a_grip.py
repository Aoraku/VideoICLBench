"""Pinned A268 real pregrasp: current three pinches and measured30mm lift."""
import numpy as np
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    checkpoint=getattr(author,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{});spec=author.scene.spec
    if (segment!='e20_a_grasp_lift_blue_from268'or parameters!={}or spec.get('id')!='E20'
            or spec.get('variant')!='A'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec.get('execution_design',{}).get('condition')!='I'
            or not author.control_report.get('engineering_reference_only')
            or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=268 or source.get('physics_ticks')!=27640
            or not getattr(author.c,'_engineering_diagnostic_only',False)
            or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 A268 admitted native/fixture boundary required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_segments_e17_e20 import _source,_source_rail,_held_with_contacts,DISK_SHA
    p=ExecutionDesignAuthor(author);name='blue_supply_3';side='left'
    _source(p,name,DISK_SHA,[.016,.01603,.000988]);_source_rail(p,name,2)
    if any(any(b['grasp'])for b in p.snapshot()[0].values()):
        raise ToolExecutionError('A268 original pregrasp requires actual empty hands')
    if np.max(abs(p.point(p.ref(name))-p.tip(side)))>.0025:
        raise ToolExecutionError('A268 actual TCP is outside original pregrasp envelope')
    initial=np.asarray(p.snapshot()[0][name]['pos'],float).copy()
    p.stage('local-E20-A268-original-three-grasp')
    for _ in range(3):
        p.act(side,'GRASP');_held_with_contacts(p,name,side)
        if np.linalg.norm(np.asarray(p.snapshot()[0][name]['pos'])[:2]-initial[:2])>.012:
            raise ToolExecutionError('A268 actual source extraction exceeds12mm')
    origin=np.asarray(p.snapshot()[0][name]['pos'],float).copy();p.stage('local-E20-A268-short-lift')
    for _ in range(3):
        p.act(side,'UP',mm=10.);_held_with_contacts(p,name,side)
        current=np.asarray(p.snapshot()[0][name]['pos'],float)
        if np.linalg.norm(current[:2]-origin[:2])>.006:
            raise ToolExecutionError('A268 actual payload slides over6mm during lift')
    rise=float(current[2]-origin[2])
    if rise<.020:raise ToolExecutionError('A268 actual payload did not rise at least20mm')
    p.operations.append(dict(operation='actual_original_A_blue_three_pinch_short_lift',
        measured_payload_rise_m=rise,measured_xy_slide_m=float(np.linalg.norm(current[:2]-origin[:2]))))
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start)
