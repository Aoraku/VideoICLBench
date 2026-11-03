"""A native57 floor-edge pinch: expose no new pose and perform no more pushes."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT,TRIANGLE_SHA
from .execution_design_segments_e17_regrasp import NAME,_bay,_bounds,_finger_offsets,_frame
from .realworld_tool_expert import ToolExecutionError


def edge_target(policy):
    """Put the real open pads in the bay, overlapping the exposed triangle base.

    The entire triangle need not lie in the empty bay. Only the open finger
    footprint must clear its walls/rails, and its pad strip must reach the
    actual source triangle. The native three-GRASP receipt decides grip.
    """
    obj,_,floor,low,high=_bay(policy);lo,hi,_=_bounds(policy)
    if abs(float(lo[2]-floor))>.003:raise ToolExecutionError('A57 triangle must actually be flat on the inner floor')
    pos,rotation=policy.frame({'actor':NAME});base,box=_frame(policy)
    desired=(pos+rotation@np.array([0.,-.017320508/3.,0.])-base)@box
    finger_lo,finger_hi=_finger_offsets(policy);inner=np.asarray(obj['inner_size'],float)
    limits=[(-inner[0]-finger_lo[0]+.0025,inner[0]-finger_hi[0]-.0025),
            (low-finger_lo[1]+.0025,high-finger_hi[1]-.0025)]
    if any(a>=b for a,b in limits):raise ToolExecutionError('Actual open fingers cannot clear floor-edge bay')
    for i,(lower,upper)in enumerate(limits):desired[i]=max(lower,min(upper,desired[i]))
    strip_low=max(lo[1],desired[1]+finger_lo[1]);strip_high=min(hi[1],desired[1]+finger_hi[1])
    if strip_high-strip_low<.003:raise ToolExecutionError('Actual finger pads cannot reach the exposed triangle base')
    # Open jaws must straddle the source piece before descending. Measured
    # opening is at least76mm here; the exact native close remains decisive.
    if lo[0]<desired[0]-.038 or hi[0]>desired[0]+.038:raise ToolExecutionError('Actual triangle is outside the open jaw span')
    desired[2]=floor+.0025-finger_lo[2]
    return base+box@desired,dict(exposed_pad_strip_overlap_m=float(strip_high-strip_low),
        target_tcp_box_local_m=desired.tolist(),floor_m=floor,bay_y_m=[low,high])


def run_segment(author,segment,parameters):
    boundaries={'e17_a_grasp_green_floor_edge_57':(57,5702,40),
                'e17_a_grasp_green_base_18':(18,1802,60)}
    if segment not in boundaries or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit native A57 floor-edge entry with empty parameters required')
    steps,tick,budget=boundaries[segment]
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='A'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('condition')!='I'or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick):
        raise ToolExecutionError('Actual native E17A57 floor-edge checkpoint required')
    p=ExecutionDesignAuthor(author)
    if p.objects[NAME].get('source_asset',{}).get('sha256')!=TRIANGLE_SHA:raise ToolExecutionError('Original green triangle mesh required')
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if not actual or actual.get('measured')is not True or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']:
        raise ToolExecutionError('Actual original stand geometry required')
    state,contacts=p.snapshot()
    if any(row['grasp'][1]for row in state.values())or frozenset((NAME,'packing_box'))not in contacts:
        raise ToolExecutionError('A57 must begin empty with actual triangle box support')
    base,rot=p.frame({'actor':'stand'});base=base.copy();rot=rot.copy();row=state['green_square']
    anchor=(rot.T@(row['pos']-base),rot.T@row['mat']);before=p.c.steps
    def guard():
        state,contacts=p.snapshot();pos,r=p.frame({'actor':'stand'});row=state['green_square']
        if np.linalg.norm(pos-base)>.001 or np.linalg.norm(r-rot)>STAND_ROTATION_MATRIX_LIMIT:raise ToolExecutionError('Actual stand moved during A57 edge pinch')
        if (any(row['grasp'])or frozenset(('green_square','stand'))not in contacts
                or np.linalg.norm(r.T@(row['pos']-pos)-anchor[0])>.002 or np.linalg.norm(r.T@row['mat']-anchor[1])>.02):
            raise ToolExecutionError('Previously placed green square changed during A57 edge pinch')
        if any(row['grasp'][0]for row in state.values())or state['packing_box']['grasp'][1]:raise ToolExecutionError('Actual A57 wrong-object or idle-hand grip')
    guard();old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=budget:raise ToolExecutionError('A edge pinch exhausted'+str(budget)+' public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        p.stage('local-e17a57-expose-open-fingers');p.move('right',p.tip('right')+[0,0,.040 if steps==18 else .030]);p.act('right','RELEASE')
        _,box=_frame(p);axis=p.frame({'actor':NAME})[1][:,0]if steps==18 else box[:,0];p.align_empty_chip_axis('right',axis)
        if steps==18:
            from .execution_design_e17_base_grasp import planned_target
            target,evidence=planned_target(p)
        else:target,evidence=edge_target(p)
        p.operations.append(dict(operation='actual_floor_edge_grasp_target',**evidence))
        p.stage('local-e17a57-direct-exposed-base-pinch');p.move('right',[*target[:2],p.tip('right')[2]]);p.move('right',target)
        from .execution_design_e20_reference import finish_chip_grip
        from .execution_design_segments_e17_e20 import _held_with_contacts
        finish_chip_grip(p,p.ref(NAME),'right');_held_with_contacts(p,NAME,'right');guard()
        initial=np.asarray(p.snapshot()[0][NAME]['pos']).copy();p.stage('local-e17a57-real-green-lift');p.act('right','UP',mm=10.)
        _held_with_contacts(p,NAME,'right');guard();state,_=p.snapshot()
        if float(state[NAME]['pos'][2]-initial[2])<.005 or p.contact(NAME,'packing_box'):
            raise ToolExecutionError('Actual A57 green triangle did not lift clear of box')
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
