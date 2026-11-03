"""Continue B's four real supported pieces with original recycling and delivery."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_e17_geometry import contained
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});s=cp.get('source',{})
    if (segment!='e17_b_recycle_deliver_after_release16'or not isinstance(parameters,dict)or parameters or spec.get('id')!='E17'or spec.get('variant')!='B'or spec.get('seed')!=4201
            or d.get('condition')!='I'or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)or author.smooth
            or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'or s.get('steps')!=16 or s.get('physics_ticks')!=1602):raise ToolExecutionError('Exact native B16/1602 post-release boundary required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False:raise ToolExecutionError('Actual dynamic reviewed stand required')
    regions={n:r for r in d['local_regions']for n in r['members']};base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();delivering=False
    def guard():
        state,contacts=p.snapshot();anchor=state['stand'];pos,rot=p.frame({'actor':'stand'})
        if not delivering and(np.linalg.norm(pos-base)>.005 or np.linalg.norm(rot-rotation)>.12):raise ToolExecutionError('Stand moved materially before intended delivery')
        for name in d['target_members']:
            row=state[name]
            if any(row['grasp'])or frozenset((name,'stand'))not in contacts or not contained(p.objects[name],row,anchor,regions[name],d.get('geometry_tolerance_m',.003)):
                raise ToolExecutionError('Real completed piece lost source geometry region/support: '+name)
    guard();before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=1800:raise ToolExecutionError('Original recycling/delivery suffix exhausted1800 actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        from .execution_design_segments_e17_remaining import _retreat
        _retreat(p,'green_triangle',-1);p.package_stage();guard();delivering=True;p.deliver();guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
