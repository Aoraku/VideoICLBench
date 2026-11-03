"""C117 has reached the real source-geometry region: release without centering."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_e17_geometry import contained
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});s=cp.get('source',{})
    if (segment!='e17_c_release_in_region_blue_117'or not isinstance(parameters,dict)or parameters or spec.get('id')!='E17'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or d.get('condition')!='I'or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)or author.smooth
            or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'or s.get('steps')!=117 or s.get('physics_ticks')!=11702):raise ToolExecutionError('Exact native C117/11702 current in-region release required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    from .execution_design_segments_e17_e20 import _held_with_contacts
    actual=native_readback(author.scene)
    if not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False:raise ToolExecutionError('Actual dynamic reviewed stand required')
    region=next(r for r in d['local_regions']if r['id']=='upper');state,contacts=p.snapshot();base,rot=p.frame({'actor':'stand'});base=base.copy();rot=rot.copy()
    if not contained(p.objects['blue_triangle'],state['blue_triangle'],state['stand'],region,d.get('geometry_tolerance_m',.003)):raise ToolExecutionError('Current actual blue vertices have not reached original upper region')
    _held_with_contacts(p,'blue_triangle','right')
    def guard():
        state,contacts=p.snapshot();pos,r=p.frame({'actor':'stand'});row=state['blue_square']
        if np.linalg.norm(pos-base)>.005 or np.linalg.norm(r-rot)>.12:raise ToolExecutionError('Stand moved materially during current release')
        if any(row['grasp'])or frozenset(('blue_square','stand'))not in contacts or not contained(p.objects['blue_square'],row,state['stand'],region,d.get('geometry_tolerance_m',.003)):raise ToolExecutionError('Completed blue square lost native region/support')
    guard();before=p.c.steps;p.stage('local-e17c117-release-current-actual-in-region-blue');p.act('right','RELEASE');guard();state,contacts=p.snapshot()
    if any(state['blue_triangle']['grasp'])or frozenset(('blue_triangle','stand'))not in contacts or not contained(p.objects['blue_triangle'],state['blue_triangle'],state['stand'],region,d.get('geometry_tolerance_m',.003)):raise ToolExecutionError('Actual released blue lacks original region and real stand support')
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
