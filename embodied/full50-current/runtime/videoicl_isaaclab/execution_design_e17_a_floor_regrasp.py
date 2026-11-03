"""A99: physically move the low north tip off its divider before base pinch."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});s=cp.get('source',{})
    boundaries={'e17_a_floor_regrasp_green_99':(99,9902),'e17_a_floor_regrasp_after_close7':(7,702),'e17_a_continue_actual_push22':(22,2202),'e17_a_box_axis_grasp_floor33':(33,3302)}
    if (segment not in boundaries or not isinstance(parameters,dict)or parameters or spec.get('id')!='E17'or spec.get('variant')!='A'or spec.get('seed')!=4201
            or d.get('condition')!='I'or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)or author.smooth
            or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'or (s.get('steps'),s.get('physics_ticks'))!=boundaries[segment]):
        raise ToolExecutionError('Exact native A99/9902 low north-tip regrasp required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False:raise ToolExecutionError('Actual dynamic reviewed stand required')
    base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy()
    region=next(r for r in d['local_regions']if 'green_square'in r['members'])
    def guard():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'});row=state['green_square'];o=p.objects['green_square'];center=rot.T@(row['pos']+row['mat']@np.asarray(o.get('local_bounds_center',[0,0,0]))-pos);half=np.abs(rot.T@row['mat'])@np.asarray(o['size']);tol=float(d.get('geometry_tolerance_m',.003))
        if np.linalg.norm(pos-base)>.005 or np.linalg.norm(rot-rotation)>.12:raise ToolExecutionError('Stand moved materially during A floor regrasp')
        if any(row['grasp'])or frozenset(('green_square','stand'))not in contacts or np.any(center-half<np.asarray(region['lower'])-tol)or np.any(center+half>np.asarray(region['upper'])+tol):raise ToolExecutionError('Completed green square lost native region/support')
    guard();before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=350:raise ToolExecutionError('A low north-tip regrasp exhausted350 public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        if s['steps']==33:
            from .execution_design_e17_box_floor import acquire
        else:
            from .execution_design_e17_nudge_grasp import acquire
        from .execution_design_segments_e17_e20 import _held_with_contacts
        ref=p.ref('green_triangle')
        if s['steps']==33:acquire(p,ref,'right')
        else:acquire(p,ref,'right',lower_north_edge=True,prepared_empty=s['steps']==7,prepared_pusher=s['steps']==22)
        origin=p.frame(ref)[0].copy();p.stage('local-e17a99-real-base-grip-short-lift')
        for _ in range(2):p.act('right','UP',mm=10.);_held_with_contacts(p,'green_triangle','right')
        if p.frame(ref)[0][2]-origin[2]<.015 or p.contact('green_triangle','packing_box'):raise ToolExecutionError('Actual green did not lift clear after floor regrasp')
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
