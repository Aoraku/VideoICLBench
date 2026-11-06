"""NativeB213: keep its three supported pieces and finish the original workflow."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT,_empty
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    if segment!='e17_b_resume_remaining_after_upper_213'or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit B213 remaining workflow with empty parameters required')
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='B'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('condition')!='I'or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=213 or source.get('physics_ticks')!=21302):
        raise ToolExecutionError('Actual successful native B213/21302 complete checkpoint required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if (not actual or actual.get('measured')is not True or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']
            or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False):raise ToolExecutionError('Original actual dynamic E17 stand required')
    lower=next(r for r in d['local_regions']if r['id']=='lower');upper=next(r for r in d['local_regions']if r['id']=='upper')
    if lower['members']!=['blue_square','green_square']or upper['members']!=['blue_triangle','green_triangle']:
        raise ToolExecutionError('Original B layer assignment required')
    _empty(p);base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy()
    regions={name:r for r in d['local_regions']for name in r['members']};protected={'blue_square','green_square','blue_triangle'};delivering=False
    def guard():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'})
        if not delivering and(np.linalg.norm(pos-base)>.001 or np.linalg.norm(rot-rotation)>STAND_ROTATION_MATRIX_LIMIT):raise ToolExecutionError('Actual stand moved before original B delivery')
        for name in protected:
            row=state[name];obj=p.objects[name];region=regions[name];local=rot.T@(row['pos']+row['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]))-pos)
            radius=np.abs(rot.T@row['mat'])@np.asarray(obj['size']);tolerance=float(d.get('geometry_tolerance_m',.003))
            if (any(row['grasp'])or frozenset((name,'stand'))not in contacts or np.any(local-radius<np.asarray(region['lower'])-tolerance)or np.any(local+radius>np.asarray(region['upper'])+tolerance)):
                raise ToolExecutionError('Completed B piece lost original full-body layer/support: '+name)
    guard();state,contacts=p.snapshot()
    if frozenset(('packing_lid','table'))not in contacts or frozenset(('stand','table'))not in contacts:raise ToolExecutionError('B213 removed lid and stand support required')
    before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=2500:raise ToolExecutionError('B remaining workflow exhausted2500 public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        from .execution_design_segments_e17_remaining import _retreat,_place_upper
        from .execution_design_e17_rail_top_grasp import acquire
        _retreat(p,'blue_triangle',-1)
        p.acquire_chip_with_wrist_margin=lambda ref,side:acquire(p,ref,side)
        _place_upper(p,'green_triangle',[.044,-.044]);protected.add('green_triangle');guard()
        p.package_stage();guard();delivering=True;p.deliver();guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
