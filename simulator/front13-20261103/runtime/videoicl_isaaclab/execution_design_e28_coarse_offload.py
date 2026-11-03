"""Practical plate offload: lift clear, tip the real blade, retract it.

No floor-level precision target is chased and no body pose is assigned. The
food must actually leave the blade and land on the plate; native scores remain
separate from this engineering intent check.
"""
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def run(p,tool,grip,side,food,destination=None):
    from .execution_design_e28_source import _scope
    _scope(p);actor=tool['actor'];plate_name=p.s['containers']['plate']['object'];events=[]
    def guard():
        p.require_held(grip,side);body=p.snapshot()[0][food]
        if any(body['grasp'])or any(p.contact(food,f'{hand}_finger{i}')for hand in('left','right')for i in(1,2)):
            raise ToolExecutionError('Plate offload touched food with a robot hand')
    def log(stage):
        state=p.snapshot()[0];row=dict(stage=stage,actions=p.c.steps,
            food_task=np.asarray(state[food]['pos']).tolist(),tool_task=np.asarray(state[actor]['pos']).tolist(),
            food_blade_contact=p.contact(food,actor),food_plate_contact=p.contact(food,plate_name),
            blade_plate_contact=p.contact(actor,plate_name),tool_held=p.held(grip,side))
        events.append(row)
        with(p.a.out/'E28-coarse-offload.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        return row
    def centre_in_plate():
        state=p.snapshot()[0];container=p.s['containers']['plate'];body=state[plate_name]
        local=np.asarray(body['mat']).T@(np.asarray(state[food]['pos'])-body['pos'])
        return bool(np.all(local[:2]>=np.asarray(container['lower'])[:2])and np.all(local[:2]<=np.asarray(container['upper'])[:2]))
    def on_plate():return bool(p.contact(food,plate_name)and centre_in_plate())
    guard();log('start-held-food-above-plate')
    p.stage('e28-coarse-lift-clear-of-plate')
    lift=p.tip(side).copy();lift[2]=max(.95,float(lift[2]));p.move(side,lift,guard,tolerance=.005)
    state=p.snapshot()[0];forward=np.asarray(state[actor]['mat'])[:,0].copy();forward[2]=0.;forward/=np.linalg.norm(forward)
    centre=np.asarray(state[plate_name]['pos'])if destination is None else np.asarray(destination,float)
    target=p.tip(side).copy();target[:2]+=centre[:2]-forward[:2]*.04-np.asarray(state[food]['pos'])[:2]
    p.stage('e28-coarse-food-over-receiving-plate');p.move(side,target,guard,tolerance=.005);log('positioned-over-plate')
    pitch=30.;extra_clearances=0
    p.stage('e28-coarse-tip-food-off-real-blade')
    for index in range(45):
        guard();row=log('tip-readback')
        if on_plate():break
        if p.contact(actor,plate_name)and extra_clearances<2:
            p.move(side,p.tip(side)+[0.,0.,.04],guard,tolerance=.005);extra_clearances+=1;continue
        current=np.asarray(p.snapshot()[0][actor]['mat']);yaw=math.atan2(current[1,0],current[0,0]);cy,sy=math.cos(yaw),math.sin(yaw);cp,sp=math.cos(math.radians(pitch)),math.sin(math.radians(pitch))
        desired=np.array([[cy,-sy,0.],[sy,cy,0.],[0.,0.,1.]])@np.array([[cp,0.,sp],[0.,1.,0.],[-sp,0.,cp]])
        delta=desired@current.T;angle=math.acos(float(np.clip((np.trace(delta)-1)/2,-1.,1.)))
        if angle<math.radians(5):
            p.wait(3);log('real-gravity-release-wait')
            if on_plate():break
            if pitch==30.:
                p.move(side,p.tip(side)+[0.,0.,.04],guard,tolerance=.005);pitch=40.;continue
            raise ToolExecutionError('Food did not actually slide from tipped blade into plate')
        axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle));component=int(np.argmax(abs(axis)))
        token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[component][int(axis[component]<0)]
        p.act(side,token,degrees=10.)
    else:raise ToolExecutionError('Practical blade-tip release action bound reached')
    p.stage('e28-coarse-retract-empty-blade')
    actual=np.asarray(p.snapshot()[0][actor]['mat']);away=actual@np.asarray(tool['withdraw_local']);target=p.tip(side)+away*.10;target[2]=max(float(target[2]),float(p.tip(side)[2])+.06)
    p.move(side,target,guard,tolerance=.005)
    for _ in range(3):p.act();log('released-food-settling-on-plate')
    final=log('complete-offload');observed_plate=any(e['food_plate_contact']for e in events)
    if not observed_plate or not centre_in_plate()or p.contact(food,actor):raise ToolExecutionError('Food was not actually released from blade onto plate')
    result=dict(segment='coarse-real-blade-tip-offload',segment_passed=True,segment_finished=True,
        task_intent_completed=True,source_initial_episode=False,native_task_acceptance=False,
        actual_food_released_from_blade=True,actual_plate_contact_observed=True,actual_blade_retracted=True,
        final_plate_contact=p.contact(food,plate_name),actual_food_hand_contact=False,
        final_food_task=final['food_task'],native_score_not_overridden=True,actions=p.c.steps-p.start)
    (p.a.out/'E28-coarse-offload-result.private.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def offload(policy,name,tool,grip,side,slot=0,total=1):
    """Shared source/debug call; C gets separate plate destinations."""
    from .execution_design_e28_source import plate_destination
    target=plate_destination(policy,name,slot,total)
    result=run(policy,tool,grip,side,name,destination=target)
    if slot+1<total:
        from .execution_design_e28_reference import level_handle
        policy.stage('e28-coarse-high-empty-blade-for-next-food')
        guard=lambda:policy.require_held(grip,side)
        tip=policy.tip(side);policy.move(side,[*tip[:2],max(1.02,float(tip[2]))],guard,tolerance=.005)
        direction=level_handle(policy,tool['actor'],side,guard,tolerance_degrees=4.,minimum_rotation_degrees=8.)
        result['next_insertion_direction_task']=np.asarray(direction).tolist()
    return result


def resume_insert_and_deliver(p,tool,grip,side,food,*,insertion_pulse_already_completed=False,
                             additional_insertion_pulses=0,tip_down_entry_degrees=0.,
                             retract_and_reseat_source_blade=False,entry_already_retracted_high=False):
    """One real insertion pulse from an existing source boundary, then deliver.

    This diagnostic never repeats tool acquisition or replaces native history.
    Actual hand-free lift and actual blade support must occur before carry.
    """
    from .execution_design_e28_source import _scope
    from .execution_design_e28_contact_guard import ensure_contact
    _scope(p);actor=tool['actor'];other='left'if side=='right'else'right'
    obj=next(o for o in p.spec['objects']if o['id']==food)
    def bottom():
        body=p.snapshot()[0][food]
        return float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size']))[2])
    initial_bottom=bottom()
    def guard(allow_open_backstop=False):
        p.require_held(grip,side);body=p.snapshot()[0][food]
        hands=(side,)if allow_open_backstop else('left','right')
        if any(body['grasp'])or any(p.contact(food,f'{hand}_finger{i}')for hand in hands for i in(1,2)):
            raise ToolExecutionError('Coarse insertion/lift touched food with a hand')
    guard(True);direction=np.asarray(p.snapshot()[0][actor]['mat'])[:,0]
    axis=int(np.argmax(abs(direction[:2])))
    token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(direction[axis]<0)]
    edge=dict(actor=actor,local=np.asarray(tool['edge_segment']).mean(axis=0))
    if retract_and_reseat_source_blade or tip_down_entry_degrees:
        if not 0<=float(tip_down_entry_degrees)<=10.:raise ValueError('Coarse shallow entry only')
        p.stage('e28-coarse-retract-before-lower-tip-entry')
        horizontal=direction.copy();horizontal[2]=0.;horizontal/=np.linalg.norm(horizontal)
        if not entry_already_retracted_high:
            p.move(side,p.tip(side)-horizontal*.04,lambda:guard(True),tolerance=.005)
            p.move(side,p.tip(side)+[0.,0.,.08],lambda:guard(True),tolerance=.005)
        yaw=math.atan2(horizontal[1],horizontal[0]);cy,sy=math.cos(yaw),math.sin(yaw)
        angle=math.radians(float(tip_down_entry_degrees));ct,st=math.cos(angle),math.sin(angle)
        desired=np.array([[cy,-sy,0.],[sy,cy,0.],[0.,0.,1.]])@np.array([[ct,0.,st],[0.,1.,0.],[-st,0.,ct]])
        p.stage('e28-coarse-actual-shallow-tip-down')
        for _ in range(24):
            guard(True);current=np.asarray(p.snapshot()[0][actor]['mat']);delta=desired@current.T
            error=math.acos(float(np.clip((np.trace(delta)-1)/2,-1.,1.)))
            if error<=math.radians(3.):break
            vector=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])
            component=int(np.argmax(abs(vector)))
            rotate=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[component][int(vector[component]<0)]
            p.act(side,rotate,degrees=8.)
        else:raise ToolExecutionError('Coarse actual shallow entry orientation stalled')
        body=p.snapshot()[0][food];half=np.abs(body['mat'])@np.asarray(obj['size'])
        target=np.asarray(body['pos'])-horizontal*(float(np.abs(body['mat'].T@horizontal)@np.asarray(obj['size']))+.012)
        offset=target-p.point(edge);offset[2]=0.
        p.stage('e28-coarse-real-tip-before-food');p.move(side,p.tip(side)+offset,lambda:guard(True),tolerance=.005)
        from .execution_design_e28_reference import actual_leading_surfaces
        p.stage('e28-coarse-lower-real-tip-to-table')
        lower_history=[]
        for _ in range(30):
            guard(True);surface=actual_leading_surfaces(p,actor)
            if p.contact(actor,'table'):
                if surface['bottom_z']>initial_bottom+.004:
                    raise ToolExecutionError('Another tool material reached table before usable blade tip')
                break
            if surface['bottom_z']<=initial_bottom+.001:break
            lower_history.append(surface['bottom_z'])
            if len(lower_history)>=4 and lower_history[-4]-lower_history[-1]<.0003:
                raise ToolExecutionError('Actual blade tip cannot descend to table before food contact')
            p.act(side,'DOWN',mm=5.)
        else:raise ToolExecutionError('Coarse real tip could not reach food underside')
        (p.a.out/'E28-real-tip-reset-before-contact.private.json').write_text(json.dumps(dict(
            actual_source_surface=surface,food_declared_bottom_task=initial_bottom,
            actual_tool_table_contact=p.contact(actor,'table'),actual_food_tool_contact=p.contact(food,actor),
            actual_body=np.asarray(p.snapshot()[0][actor]['mat']).tolist(),
            public_down_actions=len(lower_history),tool_pose_or_contact_assigned=False),indent=2)+'\n')
        direction=np.asarray(p.snapshot()[0][actor]['mat'])[:,0];direction[2]=0.;direction/=np.linalg.norm(direction)
        axis=int(np.argmax(abs(direction[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(direction[axis]<0)]
    if not insertion_pulse_already_completed:
        p.stage('e28-coarse-single-real-forward-pulse');p.act(side,token,mm=6.);guard(True)
    if type(additional_insertion_pulses)is not int or not 0<=additional_insertion_pulses<=12:
        raise ValueError('Bounded actual insertion pulse count required')
    for index in range(additional_insertion_pulses):
        guard(True);body=p.snapshot()[0][food]
        relative=float((p.point(edge)-np.asarray(body['pos']))@direction)
        with(p.a.out/'E28-coarse-insertion-pulses.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(action=p.c.steps,relative_edge_m=relative,
                actual_tool_food_contact=p.contact(food,actor),table_support=p.contact(food,'table')))+'\n')
        if relative>=.002:break
        p.stage('e28-coarse-additional-real-forward-pulse');p.act(side,token,mm=6.)
    p.stage('e28-coarse-empty-open-hand-clear')
    p.move(other,p.tip(other)+[0.,0.,.10],lambda:guard(True),tolerance=.005)
    p.stage('e28-coarse-real-independent-lift')
    # Establish the actual independent load before moving the parked open
    # hand sideways. A single long lift reaches that hand's old vertical
    # column; the measured source prefix already proved this failure mode.
    p.move(side,p.tip(side)+[0.,0.,.012],guard,tolerance=.003);guard()
    if bottom()-initial_bottom>=.006 and not p.contact(food,'table'):
        from .execution_design_e28_proven_entry import withdraw
        withdraw(p,food,other,direction,guard)
    p.move(side,p.tip(side)+[0.,0.,.065],guard,tolerance=.005);guard()
    independent_lift=bottom()-initial_bottom
    if p.contact(food,'table')or independent_lift<.006 or not p.contact(food,actor):
        raise ToolExecutionError('Single insertion pulse did not physically produce hand-free blade lift')
    def loaded():
        guard();ensure_contact(p,food,tool,lambda:p.require_held(grip,side))
    work=dict(actor=actor,local=tool['working_local']);dest=p.destination(food,0)
    p.stage('e28-coarse-real-loaded-carry')
    for target in ([*p.point(work)[:2],.92],[*dest[:2],.92]):
        delta=np.asarray(target)-p.point(work)
        p.move(side,p.tip(side)+delta,loaded,tolerance=.005)
    result=offload(p,food,tool,grip,side)
    result['resumed_source_insertion_boundary']=True
    result['actual_independent_food_lift_m']=independent_lift
    return result
