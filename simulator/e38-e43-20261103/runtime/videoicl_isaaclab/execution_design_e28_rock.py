"""Short public-action rock of a table-supported food against an open stop.

The source blade first presses higher than the measured far-side contact,
creating a real tipping couple. The tool then feeds down/forward into the gap.
Food and robot states are never assigned; every point is read from native pose.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e28_brace import near_bottom
from .execution_design_e28_backstop import center_over_blade


def prepare(policy,tool,grip,side,food,edge,direction,*,raise_mm=8.,entry_height_task=None,feed_only=False):
    actor=tool['actor'];other='left'if side=='right'else'right'
    start=np.asarray(policy.snapshot()[0][food]['pos']).copy();current=float(policy.point(edge)[2])
    base=current if entry_height_task is None else float(entry_height_task)
    raise_mm=float(raise_mm)
    if not np.isfinite([base,raise_mm]).all()or not 1. <= raise_mm <= 12. or abs(base-current)>.03:
        raise ValueError('Rock requires a measured nearby entry level and bounded public raise')
    obj=next(o for o in policy.spec['objects']if o['id']==food);state=policy.snapshot()[0][food]
    floor=float(state['pos'][2]-(np.abs(state['mat'])@np.asarray(obj['size']))[2])
    def check(label):
        policy.require_held(grip,side);all_state=policy.snapshot()[0];body=all_state[food]
        if any(body['grasp']):raise ToolExecutionError('Food acquired by a hand during blade rock')
        if np.linalg.norm(np.asarray(body['pos'])[:2]-start[:2])>.015:
            raise ToolExecutionError('Food slid15mm without a real blade entry during rock')
        loaded,local=center_over_blade(tool,all_state[actor],body['pos'])
        table=policy.contact(food,'table');near=near_bottom(policy,food,direction)
        row=dict(stage=label,actions=policy.c.steps,food_task=np.asarray(body['pos']).tolist(),
            edge_task=policy.point(edge).tolist(),near_bottom_task=near.tolist(),
            near_gap_above_initial_table_m=float(near[2]-floor),actual_table_contact=table,
            center_over_blade_patch=loaded,food_center_tool_local=local.tolist(),
            actual_food_grasp=body['grasp'],actual_tool_held=True,
            contact_forces_n=[dict(bodies=sorted(pair),force_n=force)for pair,force in policy.c.contact_forces.items()if food in pair and force>0])
        with(policy.a.out/'E28-public-blade-rock.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        if not table and not loaded:raise ToolExecutionError('Rock lost real table support before food entered blade patch')
        return row
    component=int(np.argmax(abs(direction[:2])));forward=(('FWD','BACK'),('LEFT','RIGHT'))[component][int(direction[component]<0)]
    if feed_only:
        row=check('restored-measured-open-gap')
    else:
        if not any(policy.contact(food,f'{other}_finger{i}')for i in (1,2)):
            raise ToolExecutionError('Blade rock requires the actual existing open far-side stop')
        policy.stage('e28-public-measured-pose-before-rock')
        policy.a.act('ROTATE_CCW','ROTATE_CCW',mm=1.,rotation_deg=.5);check('achieved-pose-rebase')
        policy.stage('e28-public-near-upper-edge-couple')
        policy.act(side,'UP',mm=raise_mm);row=check(f'tool-up{raise_mm:g}mm')
        # Check the achieved gap before another contact action. Native v27
        # opened4.19mm on UP, then two needless pushes closed it again.
        for _ in range(2):
            if row['near_gap_above_initial_table_m']>=.004:break
            policy.act(side,forward,mm=5.);row=check('upper-edge-forward5mm')
    if row['near_gap_above_initial_table_m']<.004:
        raise ToolExecutionError('Actual upper-edge couple did not open4mm near-side gap')
    # Keep the physical stabilizer at its achieved location while feeding the
    # lowered tip, through ordinary public moves, into the measured opening.
    policy.stage('e28-public-rock-down-and-feed')
    for _ in range(24):
        if row['center_over_blade_patch']:return
        height=float(policy.point(edge)[2]-base)
        if height<=.0008:return
        policy.act(side,'DOWN',mm=min(1.,height*1000.));row=check('rock-down1mm-toward-source-table-level')
        policy.act(side,forward,mm=3.);row=check('rock-feed3mm')
    raise ToolExecutionError('Actual rocked blade did not return to the measured entry level')
