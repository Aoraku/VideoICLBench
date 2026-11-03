"""One actual RELEASE/readback completing C's already witnessed upper placement."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    if segment!='e17_c_confirm_released_upper_blue_222'or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit E17C222 release-only completion with empty parameters required')
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)or d.get('condition')!='I'
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=222 or source.get('physics_ticks')!=22211):
        raise ToolExecutionError('Actual native E17C222 completed-release boundary required')
    p=ExecutionDesignAuthor(author);base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();before=p.c.steps
    def actual_goal():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'})
        if np.linalg.norm(pos-base)>.001 or np.linalg.norm(rot-rotation)>STAND_ROTATION_MATRIX_LIMIT:raise ToolExecutionError('Actual stand changed during C release completion')
        if any(state['blue_square']['grasp'])or frozenset(('blue_square','stand'))not in contacts or frozenset(('stand','table'))not in contacts:raise ToolExecutionError('Actual released blue/stand support required')
        region=next(r for r in d['local_regions']if r['id']=='upper')
        if 'blue_square'not in region['members']:raise ToolExecutionError('Original upper blue assignment required')
        local=(state['blue_square']['pos']-pos)@rot
        if np.any(local<region['lower'])or np.any(local>region['upper']):raise ToolExecutionError('Released blue is outside original upper region')
    actual_goal();p.stage('local-e17c222-confirm-real-release');p.act('right','RELEASE');actual_goal()
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
