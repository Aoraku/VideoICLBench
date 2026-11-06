"""Single B2 native candidate: reseat thin disk higher on actual finger pads."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design import REVISION_V3


def run_segment(author,segment,parameters):
    checkpoint=getattr(author,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{});spec=author.scene.spec
    if (segment!='e20_b_reseat_lift_blue_from2'or parameters!={}or spec.get('id')!='E20'
            or spec.get('variant')!='B'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec.get('execution_design',{}).get('condition')!='I'
            or not author.control_report.get('engineering_reference_only')
            or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=2 or source.get('physics_ticks')!=202
            or not getattr(author.c,'_engineering_diagnostic_only',False)
            or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 B2 admitted native checkpoint required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_segments_e17_e20 import _source,_source_rail,_held_with_contacts,DISK_SHA
    p=ExecutionDesignAuthor(author);name='blue_supply_1';side='right'
    origin=supported_pad_reseat(p,name,side)
    p.stage('local-E20-B2-reseated-short-lift')
    for _ in range(3):
        p.act(side,'UP',mm=10.);_held_with_contacts(p,name,side)
        current=np.asarray(p.snapshot()[0][name]['pos'],float)
        if np.linalg.norm(current[:2]-origin[:2])>.006:
            raise ToolExecutionError('B2 disk slides sideways during actual short lift')
    rise=float(current[2]-origin[2])
    if rise<.020:raise ToolExecutionError('B2 actual disk did not rise at least20mm')
    p.operations.append(dict(operation='actual_supported_pad_reseat_and_short_lift',
        public_tcp_down_m=.003,requested_lift_m=.030,actual_payload_rise_m=rise,
        measured_xy_slide_m=float(np.linalg.norm(current[:2]-origin[:2]))))
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start)


def supported_pad_reseat(p,name,side):
    """Same single real DOWN3 used by native B2 and future source-initial B."""
    from .execution_design_segments_e17_e20 import _source,_source_rail,_held_with_contacts,DISK_SHA
    if (p.task!='E20'or p.variant!='B'or name!='blue_supply_1'or side!='right'
            or p.d.get('revision')!=REVISION_V3 or p.d.get('condition')!='I'
            or not p.a.control_report.get('engineering_reference_only')):
        raise ToolExecutionError('Original B right blue1 supported pad reseat required')
    _source(p,name,DISK_SHA,[.016,.01603,.000988]);_source_rail(p,name,3);_held_with_contacts(p,name,side)
    initial=np.asarray(p.snapshot()[0][name]['pos'],float).copy()
    if np.linalg.norm(initial[:2]-np.asarray(p.objects[name]['xy']))>.012:
        raise ToolExecutionError('B2 actual disk is outside original extraction envelope')
    p.stage('local-E20-B2-actual-pad-reseat')
    # Native B2 has the thin disk only about9mm above the finger toes. Move
    # the actual TCP down3mm against its actual source support; do not change
    # the material grasp point or use a closing/quiet waiting loop.
    p.act(side,'DOWN',mm=3.)
    _held_with_contacts(p,name,side);_source_rail(p,name,3)
    origin=np.asarray(p.snapshot()[0][name]['pos'],float).copy()
    if np.linalg.norm(origin[:2]-initial[:2])>.006:
        raise ToolExecutionError('B2 disk slid during actual pad reseating')
    return origin
