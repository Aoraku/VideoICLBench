"""Feed the real blade along its measured support plane using public actions.

Contact strokes are partial motions. A nominal3:1 forward/down staircase does
not preserve a plane when only the forward stroke is blocked. Here the actual
plane height at one fixed source-food anchor determines whether to feed, lower,
or raise; commands never stand in for achieved insertion.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e28_backstop import center_over_blade


def plane_height(tool,state,anchor_xy):
    normal=np.asarray(state['mat'],float)@np.asarray(tool['support_normal_local'],float)
    if normal[2]<=.8:raise ToolExecutionError('E28 measured blade support face lost its upward orientation')
    return float((float(tool['support_plane_offset'])+normal@np.asarray(state['pos'])-normal[:2]@np.asarray(anchor_xy))/normal[2])


def run(policy,tool,grip,side,food,edge,direction):
    actor=tool['actor'];state=policy.snapshot()[0];anchor=np.asarray(state[food]['pos'])[:2].copy()
    target=plane_height(tool,state[actor],anchor);history=[];forward_history=[]
    component=int(np.argmax(abs(direction[:2])));forward=(('FWD','BACK'),('LEFT','RIGHT'))[component][int(direction[component]<0)]
    policy.stage('e28-public-measured-support-plane-feed')
    for _ in range(140):
        policy.require_held(grip,side);state=policy.snapshot()[0];body=state[food]
        if any(body['grasp']):raise ToolExecutionError('E28 plane feed acquired food with a hand')
        loaded,local=center_over_blade(tool,state[actor],body['pos']);table=policy.contact(food,'table')
        if not table and not loaded:raise ToolExecutionError('E28 plane feed lost table support before real blade loading')
        if np.linalg.norm(np.asarray(body['pos'])[:2]-anchor)>.015:
            raise ToolExecutionError('E28 plane feed pushed food15mm without loading')
        actual=plane_height(tool,state[actor],anchor);error=actual-target
        relative=float((policy.point(edge)-np.asarray(body['pos']))@direction)
        row=dict(actions=policy.c.steps,anchor_xy_task=anchor.tolist(),target_plane_height_task=target,
            actual_plane_height_task=actual,plane_height_error_m=error,relative_edge_m=relative,
            food_task=np.asarray(body['pos']).tolist(),edge_task=policy.point(edge).tolist(),
            actual_food_grasp=body['grasp'],actual_table_contact=table,
            center_over_blade_patch=loaded,food_center_tool_local=local.tolist())
        with(policy.a.out/'E28-measured-plane-feed.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        if loaded:return
        history.append(row)
        if error>.0006:
            policy.act(side,'DOWN',mm=min(2.,max(.5,error*1000.)))
        elif error<-.0006:
            policy.act(side,'UP',mm=min(2.,max(.5,-error*1000.)))
        else:
            forward_history.append(relative)
            if len(forward_history)>=8 and max(forward_history[-7:])-forward_history[-8]<.001:
                raise ToolExecutionError('E28 measured-plane blade made no1mm relative progress in8forward pulses')
            policy.act(side,forward,mm=6.)
        if len(history)>=12 and max(r['relative_edge_m']for r in history[-11:])-history[-12]['relative_edge_m']<.001:
            raise ToolExecutionError('E28 actual plane feed made no1mm relative progress in12actions')
    raise ToolExecutionError('E28 measured support-plane feed action bound exhausted')
