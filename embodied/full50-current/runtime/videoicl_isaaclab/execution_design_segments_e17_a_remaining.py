"""Resume actual held green at nativeA37, then the original remaining workflow."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    boundaries={'e17_a_resume_held_green_and_remaining_37':(37,3702),
                'e17_a_regrasp_after_lost_green_1':(1,102),
                'e17_a_finish_from_actual_held40':(40,4002),
                'e17_a_edge_grip_floor_after1':(1,102)}
    if segment not in boundaries or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit native A37 held-green remaining workflow required')
    steps,tick=boundaries[segment]
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='A'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('condition')!='I'or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick):
        raise ToolExecutionError('Actual successful native A37/3702 complete checkpoint required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if (not actual or actual.get('measured')is not True or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']
            or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False):
        raise ToolExecutionError('Original actual dynamic E17 stand required')
    lower=next(r for r in d['local_regions']if r['id']=='lower');upper=next(r for r in d['local_regions']if r['id']=='upper')
    if lower['members']!=['green_square','green_triangle']or upper['members']!=['blue_square','blue_triangle']:
        raise ToolExecutionError('Original A layer assignment required')
    regions={name:r for r in d['local_regions']for name in r['members']};protected={'green_square'};delivering=False
    base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy()
    def supported(name):
        state,contacts=p.snapshot();row=state[name];pos,rot=p.frame({'actor':'stand'});obj=p.objects[name];region=regions[name]
        from .execution_design_e17_geometry import contained
        if (any(row['grasp'])or frozenset((name,'stand'))not in contacts
                or not contained(obj,row,state['stand'],region,d.get('geometry_tolerance_m',.003))):
            raise ToolExecutionError('Completed A piece lost original full-body layer/support: '+name)
    def guard():
        pos,rot=p.frame({'actor':'stand'})
        if not delivering and(np.linalg.norm(pos-base)>.005 or np.linalg.norm(rot-rotation)>.12):
            raise ToolExecutionError('Actual stand moved before original A delivery')
        for name in protected:supported(name)
    guard();ref=p.ref('green_triangle');state,contacts=p.snapshot()
    if steps in(37,40):p.require_held(ref,'right')
    if (any(row['grasp'][0]for row in state.values())or steps in(37,40) and not all(frozenset(('green_triangle','right_finger'+str(i)))in contacts for i in(1,2))
            or frozenset(('packing_lid','table'))not in contacts or frozenset(('stand','table'))not in contacts):
        raise ToolExecutionError('A37 actual right green bilateral grip and completed lid/stand support required')
    before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=2500:raise ToolExecutionError('A remaining workflow exhausted2500 public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        if steps==40:
            from .execution_design_segments_e17_e20 import _held_with_contacts
            supports=['packing_box','table',*(f'fixture{i}'for i in range(len(spec.get('fixtures',[]))))]
            p.stage('local-e17a40-continue-actual-held-clear-source')
            for _ in range(6):
                _held_with_contacts(p,'green_triangle','right')
                if not any(p.contact('green_triangle',support)for support in supports):break
                p.act('right','UP',mm=10.)
            else:raise ToolExecutionError('Actual held green remains source-supported after bounded lift')
        if steps==1:
            if segment=='e17_a_edge_grip_floor_after1':
                from .execution_design_e17_edge_grasp import acquire
                from .execution_design_segments_e17_e20 import _held_with_contacts
                acquire(p,ref,'right');origin=p.frame(ref)[0].copy();p.act('right','UP',mm=10.);_held_with_contacts(p,'green_triangle','right')
                if p.frame(ref)[0][2]-origin[2]<.005:raise ToolExecutionError('Actual edge-held green did not rise5mm')
            else:
                from .execution_design_e17_rail_top_grasp import acquire
                p.acquire_chip_with_wrist_margin=lambda reference,side:acquire(p,reference,side)
                ref,side=p.pickup('green_triangle',side_override='right')
                p.require_held(ref,side)
        from .execution_design_e17_insertion import front_lower_slot,place_held_lower
        place_held_lower(p,'green_triangle','stand',front_lower_slot(p,1,2),ref,'right')
        protected.add('green_triangle');guard()
        if steps==40 or segment=='e17_a_edge_grip_floor_after1':
            from .execution_design_e17_two_blue_remaining import place_right_column
            for name,xy in [('blue_square',[.030,-.035]),('blue_triangle',[.030,.035])]:
                place_right_column(p,name,xy,edge_grip=True);protected.add(name);guard()
        else:
            from .execution_design_segments_e17_remaining import _place_upper
            for name,xy in [('blue_square',[-.044,-.044]),('blue_triangle',[-.044,.044])]:
                _place_upper(p,name,xy);protected.add(name);guard()
        if segment=='e17_a_edge_grip_floor_after1':
            from .execution_design_e17_recycle_delivery import recycle_all,deliver_stand
            recycle_all(p);guard();delivering=True;deliver_stand(p);guard()
        else:p.package_stage();guard();delivering=True;p.deliver();guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
