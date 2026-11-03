"""Physical same-hand regrasp on the unchanged E42 source handle.

The rear grip can require an unreachable wrist position when pushing left.
Place the real tool on the table, release it, and pinch a forward material
section of its handle. No object/robot state or evaluator history is assigned.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def forward_handle_reference(obj,source_reference,x=.030):
    from scipy.spatial import ConvexHull
    from .execution_design_spatula_clearance import SUPPORT_VERTICES,SOURCE_SHA,HALF_SIZE
    if (obj.get('id')!='spatula'or obj.get('source_asset',{}).get('sha256')!=SOURCE_SHA
            or not np.allclose(obj.get('size',[]),HALF_SIZE,atol=1e-9,rtol=0)
            or not np.isfinite(x)or not .0<=x<=.040):
        raise ToolExecutionError('Reviewed unchanged E42 source handle section required')
    # The declared blade starts at local X=.070018m. Stay at least30mm
    # behind it, on the real handle centreline rather than a virtual TCP.
    y=float(source_reference['local'][1]);low=-np.inf;high=np.inf
    for nx,ny,nz,b in ConvexHull(SUPPORT_VERTICES).equations:
        fixed=nx*x+ny*y+b
        if abs(nz)<1e-10:
            if fixed>1e-8:raise ToolExecutionError('Forward grip centreline lies outside actual source handle')
        elif nz>0:high=min(high,-fixed/nz)
        else:low=max(low,-fixed/nz)
    if not np.isfinite([low,high]).all()or high-low<.001:
        raise ToolExecutionError('Actual source handle material thickness required')
    return dict(source_reference,local=[float(x),y,float((low+high)/2)],
                engineering_forward_handle_grip=True)


def regrasp(policy,tool,old_ref,side):
    from .execution_design_spatula_clearance import SUPPORT_VERTICES
    from .execution_design_thin_edge import table_bounds_task
    from .engineering_checkpoint import capture
    if (policy.task!='E42'or not policy.a.control_report.get('engineering_reference_only')
            or policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or side not in('left','right')):
        raise ToolExecutionError('Explicit E42 engineering same-hand handle regrasp required')
    actor=tool['actor'];obj=next(o for o in policy.spec['objects']if o['id']==actor)
    ref=forward_handle_reference(obj,old_ref)
    floor=table_bounds_task(policy.a.scene)['top'];balls=policy.spec['semantic']['groups']['balls']
    def no_ball_hand():
        if any(policy.contact(ball,f'{hand}_finger{i}')for ball in balls for hand in('left','right')for i in(1,2)):
            raise ToolExecutionError('Handle regrasp touched a source ball by hand')
    def held():
        no_ball_hand();policy.require_held(old_ref,side)
    state,_=policy.snapshot();body=state[actor]
    local_tip=np.asarray(body['mat']).T@(policy.tip(side)-body['pos'])
    already_forward=policy.held(ref,side)and np.linalg.norm(local_tip-np.asarray(ref['local']))<.025
    if not already_forward:
        if policy.held(old_ref,side):
            policy.stage('place-source-tool-on-clear-table-for-forward-grip')
            lowest=float((SUPPORT_VERTICES@body['mat'].T)[:,2].min())
            highest_ball=max(float(state[n]['pos'][2]+max(next(o for o in policy.spec['objects']if o['id']==n)['size']))for n in balls)
            height=max(float(body['pos'][2]),highest_ball+.012-lowest)
            origin=dict(actor=actor,local=[0.,0.,0.])
            policy.move_point(side,origin,[*body['pos'][:2],height],held)
            policy.move_point(side,origin,[-.13,-.25,height],held)
            # Re-read the actual source orientation after the transport.
            body=policy.snapshot()[0][actor]
            lowest=float((SUPPORT_VERTICES@body['mat'].T)[:,2].min())
            policy.move_point(side,origin,[-.13,-.25,floor-lowest+.001],held)
            for _ in range(8):
                held()
                if policy.contact(actor,'table'):break
                policy.act(side,'DOWN',mm=.5)
            if not policy.contact(actor,'table'):
                raise ToolExecutionError('Source tool lacks actual table support before release')
            policy.act(side,'RELEASE');no_ball_hand()
            if policy.held(old_ref,side)or not policy.contact(actor,'table'):
                raise ToolExecutionError('Actual supported source tool did not release')
            policy.move(side,policy.tip(side)+[0,0,.08],no_ball_hand)
        elif any(body['grasp'])or not policy.contact(actor,'table'):
            raise ToolExecutionError('Forward regrasp requires this hand holding or an actually rested source tool')
        policy.stage('acquire-real-forward-source-handle')
        policy.acquire(ref,side);no_ball_hand();policy.require_held(ref,side)
    # Preserve the real acquired state before subsequent push planning.
    measured=capture(policy.c,'e42-forward-handle-acquired',context=dict(
        engineering_forward_handle_grip=True,grasp_local=ref['local'],tool_side=side))
    (policy.a.out/'e42-forward-handle-acquired.checkpoint.private.json').write_text(json.dumps(measured))
    body=policy.snapshot()[0][actor]
    (policy.a.out/'e42-forward-handle-grasp.private.json').write_text(json.dumps(dict(
        local=ref['local'],actual_tip_source_local=(np.asarray(body['mat']).T@(policy.tip(side)-body['pos'])).tolist(),
        bilateral_native_grip=policy.held(ref,side),same_source_geometry=True,body_position=body['pos'].tolist(),
        no_hand_ball_contact=True,source_initial_positive=False)))
    updated=dict(tool,grasp_local=ref['local']);policy.s['tools']['main']=updated
    return updated,ref,side
