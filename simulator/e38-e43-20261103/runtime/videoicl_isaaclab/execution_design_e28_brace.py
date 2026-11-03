"""Measured E28 contact diagnostic: open far-edge brace and real tool rock.

Robot actuators provide every motion. The food remains table-supported and is
never grasped, lifted by a hand, repositioned, or assigned a pose. This module
only tests a local geometry route and cannot certify a source-initial episode.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def near_bottom(policy,food,direction):
    body=policy.snapshot()[0][food];obj=next(o for o in policy.spec['objects']if o['id']==food)
    size=np.asarray(obj['size'],float);local=np.asarray(body['mat']).T@np.asarray(direction,float)
    flat=local[:2];flat/=np.linalg.norm(flat)
    radius=min(size[i]/abs(flat[i])for i in (0,1)if abs(flat[i])>1e-7)
    point=np.r_[-flat*radius,-size[2]]
    return np.asarray(body['pos'])+np.asarray(body['mat'])@point


def run(policy,tool,grip,side,food):
    from .engineering_checkpoint import capture
    from .engineering_native_tick import diagnostic_tick_scope
    from .execution_design_e28_backstop import require_finger_clearance
    other='left'if side=='right'else'right';actor=tool['actor']
    if policy.c.grips[other]<.035:raise ToolExecutionError('E28 top brace requires a genuinely open empty hand')
    state=policy.snapshot()[0];obj=next(o for o in policy.spec['objects']if o['id']==food)
    direction=np.asarray(state[actor]['mat'])[:,0].copy();direction[2]=0;direction/=np.linalg.norm(direction)
    if not policy.contact(food,'table'):raise ToolExecutionError('Top brace must start with real food table support')
    start=np.asarray(state[food]['pos']).copy();initial_near=near_bottom(policy,food,direction)
    def guard():
        policy.require_held(grip,side)
        current=policy.snapshot()[0][food]
        if any(current['grasp']):raise ToolExecutionError('Food acquired by a hand during brace diagnostic')
        if np.linalg.norm(np.asarray(current['pos'])[:2]-start[:2])>.010:
            raise ToolExecutionError('Food slid more than10mm during contact brace diagnostic')
    def boundary(name):
        policy.stage(name);folder=policy.a.out/'checkpoints';folder.mkdir(exist_ok=True)
        p=folder/f'native-{policy.c.steps:04d}-{name}.private.json'
        p.write_text(json.dumps(capture(policy.c,name),indent=2)+'\n')
    def move(side,target,label):
        boundary(label);guard()
        goals={s:policy.tip(s).copy()for s in ('left','right')};goals[side]=np.asarray(target,float)
        receipt=policy.c.author_move(goals,max_speed=.055,max_acceleration=.2,guard=guard,tracking_tolerance=.001)
        with(policy.a.out/'demo-actions.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(stage=policy.a.stage,control='private_continuous_empty_brace_approach',
                tips={s:policy.tip(s).tolist()for s in ('left','right')},
                task_targets={s:p.tolist()for s,p in goals.items()},**receipt))+'\n')
        if np.linalg.norm(policy.tip(side)-target)>.002:
            raise ToolExecutionError('Actual empty hand did not reach brace approach')
    def log(label):
        body=policy.snapshot()[0][food];contacts=policy.snapshot()[1]
        row=dict(stage=label,actions=policy.c.steps,food_task=np.asarray(body['pos']).tolist(),
            food_mat=np.asarray(body['mat']).tolist(),near_bottom_task=near_bottom(policy,food,direction).tolist(),
            near_bottom_rise_m=float(near_bottom(policy,food,direction)[2]-initial_near[2]),
            actual_food_table_contact=policy.contact(food,'table'),
            actual_food_tool_contact=policy.contact(food,actor),actual_food_grasp=body['grasp'],
            contact_forces_n=[dict(bodies=sorted(pair),force_n=force)for pair,force in policy.c.contact_forces.items()if food in pair and force>0],
            hand_contact=any(frozenset((food,f'{other}_finger{i}'))in contacts for i in (1,2)))
        with(policy.a.out/'E28-far-top-brace.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        return row
    with diagnostic_tick_scope(policy.a):
        # Supersede old contact goals using a genuine measured-pose motor hold.
        move(other,policy.tip(other),'e28-brace-achieved-pose-hold')
        if any(policy.contact(food,f'{other}_finger{i}')for i in (1,2)):
            require_finger_clearance(policy,food,other,direction*.020)
            move(other,policy.tip(other)+direction*.020,'e28-brace-detach-side-normal')
        move(other,policy.tip(other)+[0.,0.,.055],'e28-brace-empty-rise-before-top')
        fingers=policy.a.finger_geometry(other)['fingers']
        selected=min(fingers,key=lambda f:np.linalg.norm((np.asarray(f['lowest_point_task_m'])-start)[:2]))['name']
        # Put the real lower fingertip just inside the food's far top edge.
        for _ in range(3):
            body=policy.snapshot()[0][food];half=np.abs(body['mat'])@np.asarray(obj['size'])
            extent=float(np.abs(np.asarray(body['mat']).T@direction)@np.asarray(obj['size']))
            target=np.asarray(body['pos']).copy()+direction*(extent-.003);target[2]=float(body['pos'][2]+half[2]+.018)
            finger=next(f for f in policy.a.finger_geometry(other)['fingers']if f['name']==selected)
            point=np.asarray(finger['lowest_point_task_m']);delta=target-point
            require_finger_clearance(policy,food,other,delta)
            move(other,policy.tip(other)+delta,'e28-brace-measured-far-top-approach')
            if np.max(abs(delta))<.0015:break
        boundary('e28-brace-actual-top-contact')
        for _ in range(28):
            guard()
            if any(policy.contact(food,f'{other}_finger{i}')for i in (1,2)):break
            policy.act(other,'DOWN',mm=1.)
            if not policy.contact(food,'table'):raise ToolExecutionError('Empty top approach displaced food off table')
        else:raise ToolExecutionError('Actual empty fingertip did not touch far food top')
        log('actual-top-contact')
        boundary('e28-brace-tool-up-open-hand-down')
        for _ in range(5):
            guard()
            policy.a.act('DOWN'if other=='left'else'UP','UP'if side=='right'else'DOWN',mm=1.,rotation_deg=.5)
            row=log('opposed1mm-rock')
            if not row['actual_food_table_contact']:raise ToolExecutionError('Food lost table support before entry under downward brace')
            if row['near_bottom_rise_m']>=.003:
                return dict(segment='real-tool-rock-with-downward-brace',segment_finished=True,
                    segment_passed=True,diagnostic_only=True,source_initial_episode=False,native_task_acceptance=False,**row)
        raise ToolExecutionError('Actual food near edge did not open3mm under bounded tool rock')


def practical(policy,tool,grip,side,food):
    """Open fingertip presses the far top while the real blade levers in.

    This short physical suffix does not restore or invent scoop history. The
    hand completely detaches before the mandatory independent blade lift.
    """
    from .execution_design_e28_source import _scope
    from .execution_design_e28_contact_guard import support_geometry
    _scope(policy);actor=tool['actor'];other='left'if side=='right'else'right'
    obj=next(o for o in policy.spec['objects']if o['id']==food)
    direction=np.asarray(policy.snapshot()[0][actor]['mat'])[:,0].copy()
    direction[2]=0.;direction/=np.linalg.norm(direction)
    initial_near=near_bottom(policy,food,direction);history=[]
    def guard():
        policy.require_held(grip,side)
        if any(policy.snapshot()[0][food]['grasp']):raise ToolExecutionError('Open stabilizer grasped the food')
        if policy.c.grips[other]<.035:raise ToolExecutionError('Far top stabilizer is not actually open')
    def log(stage):
        body=policy.snapshot()[0][food];supported,local,gap=support_geometry(policy,tool,food)
        row=dict(stage=stage,actions=policy.c.steps,food_task=np.asarray(body['pos']).tolist(),
            near_edge_rise_m=float(near_bottom(policy,food,direction)[2]-initial_near[2]),
            food_tool_local=np.asarray(local).tolist(),blade_plane_gap_m=gap,
            native_supported_footprint=bool(supported),actual_food_table=policy.contact(food,'table'),
            actual_food_blade=policy.contact(food,actor),
            actual_open_hand_contact=any(policy.contact(food,f'{other}_finger{i}')for i in(1,2)),
            actual_food_grasp=body['grasp'],tool_held=policy.held(grip,side))
        history.append(row)
        with(policy.a.out/'E28-practical-far-top-brace.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        return row
    guard()
    if not policy.contact(food,'table'):raise ToolExecutionError('Brace needs actual food/table support')
    policy.stage('e28-practical-open-hand-clear-before-top')
    policy.move(other,policy.tip(other)+direction*.02,guard,tolerance=.005)
    policy.move(other,policy.tip(other)+[0.,0.,.07],guard,tolerance=.005)
    fingers=policy.a.finger_geometry(other)['fingers'];body=policy.snapshot()[0][food]
    selected=min(fingers,key=lambda f:np.linalg.norm((np.asarray(f['lowest_point_task_m'])-body['pos'])[:2]))['name']
    for _ in range(2):
        guard();body=policy.snapshot()[0][food];half=np.abs(body['mat'])@np.asarray(obj['size'])
        extent=float(np.abs(np.asarray(body['mat']).T@direction)@np.asarray(obj['size']))
        target=np.asarray(body['pos']).copy()+direction*(extent-.004);target[2]=body['pos'][2]+half[2]+.008
        finger=next(f for f in policy.a.finger_geometry(other)['fingers']if f['name']==selected)
        delta=target-np.asarray(finger['lowest_point_task_m'])
        policy.stage('e28-practical-open-fingertip-far-top')
        policy.move(other,policy.tip(other)+delta,guard,tolerance=.005)
    policy.stage('e28-practical-real-top-contact')
    for _ in range(8):
        guard()
        if any(policy.contact(food,f'{other}_finger{i}')for i in(1,2)):break
        policy.act(other,'DOWN',mm=2.)
    else:raise ToolExecutionError('Open stabilizer did not actually touch food top')
    log('actual-far-top-contact')
    policy.stage('e28-practical-small-real-opening-couple')
    for _ in range(8):
        guard()
        policy.a.act('DOWN'if other=='left'else'UP','UP'if side=='right'else'DOWN',mm=1.,rotation_deg=.5)
        row=log('real-up-tool-down-open-finger')
        if not row['actual_food_table']:raise ToolExecutionError('Food left table while still touching stabilizer')
        if row['near_edge_rise_m']>=.002:break
    else:raise ToolExecutionError('Real far-top/tool couple did not open the food near edge')
    axis=int(np.argmax(abs(direction[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(direction[axis]<0)]
    policy.stage('e28-practical-blade-enter-open-near-edge')
    for _ in range(6):
        guard();policy.act(side,token,mm=5.);row=log('actual-entry-under-open-near-edge')
        if row['native_supported_footprint']and abs(row['blade_plane_gap_m'])<=.004:break
    policy.stage('e28-practical-open-stabilizer-completely-away')
    policy.move(other,policy.tip(other)+direction*.025,guard,tolerance=.005)
    policy.move(other,policy.tip(other)+[0.,0.,.10],guard,tolerance=.005)
    if any(policy.contact(food,f'{other}_finger{i}')for i in(1,2)):
        raise ToolExecutionError('Open stabilizer did not detach before independent lift')
    log('open-hand-cleared-before-tool-only-lift')
    from .execution_design_e28_coarse_offload import resume_insert_and_deliver
    result=resume_insert_and_deliver(policy,tool,grip,side,food,insertion_pulse_already_completed=True)
    result['actual_far_top_stabilizer_released_before_lift']=True
    return result
