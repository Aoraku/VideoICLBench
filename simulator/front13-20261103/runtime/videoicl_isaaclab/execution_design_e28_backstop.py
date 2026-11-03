"""A single open finger stops table-supported food sliding during real scoop.

No hand grasps or lifts the food. The open finger withdraws after shallow
blade entry, before the independent hand-free blade lift.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def finger_target(food_pos, food_half, direction, finger):
    direction=np.asarray(direction,float);direction=direction/np.linalg.norm(direction)
    low=np.asarray(finger['aabb_min_task_m'],float);high=np.asarray(finger['aabb_max_task_m'],float)
    center=(low+high)/2;half=(high-low)/2
    desired=np.asarray(food_pos,float).copy()
    desired[:2]+=direction[:2]*(float(np.abs(direction)@np.asarray(food_half))+float(np.abs(direction)@half)+.002)
    desired[2]=float(food_pos[2]-food_half[2]+.0005+center[2]-low[2])
    return center,desired


def align_open_fingers(a,side,direction,guard):
    # Put both open fingers beside one another, not one above the destination
    # plate. The positive-X finger becomes the food backstop; the other stays
    # on the empty outside edge of this source layout.
    desired=np.array([-direction[1],direction[0]],float);desired/=np.linalg.norm(desired)
    a.move(side,[*a.tip(side)[:2],max(1.08,float(a.tip(side)[2]))],guard)
    for _ in range(50):
        guard();geometry=a.a.finger_geometry(side)
        centers=[np.asarray(f['aabb_center_task_m'])for f in geometry['fingers']]
        axis=(centers[1]-centers[0])[:2];axis/=np.linalg.norm(axis)
        if axis@desired<0:axis=-axis
        angle=float(np.arctan2(axis[0]*desired[1]-axis[1]*desired[0],axis@desired))
        if abs(angle)<np.radians(4):return
        if geometry['lowest_z_task_m']<.93:
            raise ToolExecutionError('E28 empty fingers lost real table clearance while aligning')
        # Native evidence measured only2.25degrees of finger-axis rotation
        # per8-degree public command. Keep that command above the settling
        # band until the measured axis is within the unchanged4-degree goal.
        a.act(side,'ROTATE_CCW'if angle>0 else'ROTATE_CW',
              degrees=8.)
    raise ToolExecutionError('E28 actual open-finger lateral alignment stalled')


def require_finger_clearance(a,food,side,translation):
    state=a.snapshot()[0]
    for finger in a.a.finger_geometry(side)['fingers']:
        low=np.asarray(finger['aabb_min_task_m'])+translation
        high=np.asarray(finger['aabb_max_task_m'])+translation
        for obj in a.spec['objects']:
            name=obj['id']
            if name==food or name==a.s['tools']['main']['actor']:continue
            body=state[name];half=np.abs(body['mat'])@np.asarray(obj['size'],float)
            lo=np.asarray(body['pos'])-half;hi=np.asarray(body['pos'])+half
            if np.all(high>=lo-.002)and np.all(low<=hi+.002):
                raise ToolExecutionError('E28 open finger approach would collide with '+name)


def choose_backstop_finger(a,food,side,direction,food_pos,food_half,fingers):
    """Select the open finger whose whole-hand contact pose clears other food."""
    for finger in sorted(fingers,key=lambda f:f['aabb_center_task_m'][0],reverse=True):
        center,target=finger_target(food_pos,food_half,direction,finger)
        try:require_finger_clearance(a,food,side,target-center)
        except ToolExecutionError:continue
        return finger['name']
    raise ToolExecutionError('E28 neither open-finger backstop clears actual neighbouring objects')


def place(a, food, direction, guard):
    if a.s.get('auxiliary_loading_hand_allowed') is not True:
        raise ToolExecutionError('E28 source does not allow an auxiliary stabilizing hand')
    side='left';a._e28_backstop_park=np.asarray(a.tip(side),float).copy()
    a.stage('open-finger-backstop-'+food);a.act(side,'RELEASE')
    align_open_fingers(a,side,direction,guard)
    guard();state=a.snapshot()[0];obj=next(o for o in a.spec['objects']if o['id']==food)
    half=np.abs(state[food]['mat'])@np.asarray(obj['size'],float)
    fingers=a.a.finger_geometry(side)['fingers']
    selected=choose_backstop_finger(a,food,side,direction,
        state[food]['pos'],half,fingers)
    a.move(side,[*a.tip(side)[:2],max(1.08,float(a.tip(side)[2]))],guard)
    for index in range(10):
        guard();state=a.snapshot()[0]
        if any(state[food]['grasp']):raise ToolExecutionError('E28 auxiliary hand must not grasp food')
        finger=next(f for f in a.a.finger_geometry(side)['fingers']if f['name']==selected)
        center,target=finger_target(state[food]['pos'],half,direction,finger)
        error=target-center
        if np.max(abs(error))<=.0015:break
        # Keep the empty finger high until its lateral outside-food target is reached.
        if np.max(abs(error[:2]))>.0015:error[2]=0.
        require_finger_clearance(a,food,side,error)
        a.move(side,a.tip(side)+error,guard,tolerance=.001)
    else:raise ToolExecutionError('E28 actual open-finger backstop did not converge')
    with (a.a.out/'E28-backstop.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(step=a.c.steps,food=food,finger=selected,actual=finger,target=target.tolist(),grasp_requested=False))+'\n')
    return side


def clear_loaded_column(a,food,side):
    state=a.snapshot()[0][food];obj=next(o for o in a.spec['objects']if o['id']==food)
    half=np.abs(state['mat'])@np.asarray(obj['size'],float)
    food_low=np.asarray(state['pos'])-half;food_high=np.asarray(state['pos'])+half
    for finger in a.a.finger_geometry(side)['fingers']:
        lo=np.asarray(finger['aabb_min_task_m']);hi=np.asarray(finger['aabb_max_task_m'])
        if np.all(hi[:2]>=food_low[:2]-.02) and np.all(lo[:2]<=food_high[:2]+.02):
            raise ToolExecutionError('E28 withdrawn finger still intersects loaded vertical path')


def withdraw(a,food,side,direction,guard):
    """Move away laterally before lifting the empty finger out of the route.

    The old UP-only retreat parked the open finger 80mm above the food; the
    later real blade lift then collided with it and rolled the spatula in the
    other hand. No food pose or grasp state is written here.
    """
    a.stage('withdraw-open-finger-before-blade-lift-'+food)
    direction=np.asarray(direction,float).copy();direction[2]=0
    direction/=np.linalg.norm(direction)
    # Release the actual side-contact normal before a tangential retreat.
    # v14's -X-only motion dragged the bread 57mm with ~6N side friction.
    # These are genuine public empty-hand motions; no food state is set.
    start=np.asarray(a.snapshot()[0][food]['pos']).copy()
    original_guard=guard;normal_released=[False]
    def guard():
        original_guard()
        # Displacement can evidence hand drag only while that contact is not
        # yet physically separated. Later the actual load-contact guard stays
        # authoritative; small motion on the blade is not hand dragging.
        if not normal_released[0]and np.linalg.norm(np.asarray(a.snapshot()[0][food]['pos'])[:2]-start[:2])>.005:
            raise ToolExecutionError('E28 backstop withdrawal dragged food more than5mm')
    def touching():
        contacts=a.snapshot()[1]
        return any(frozenset((food,f'{side}_finger{i}'))in contacts for i in (1,2))
    def normal_clear():
        state=a.snapshot()[0][food];obj=next(o for o in a.spec['objects']if o['id']==food)
        center=np.asarray(state['pos']);half=np.abs(state['mat'])@np.asarray(obj['size'])
        lateral=np.array([-direction[1],direction[0],0.])
        for finger in a.a.finger_geometry(side)['fingers']:
            lo=np.asarray(finger['aabb_min_task_m']);hi=np.asarray(finger['aabb_max_task_m'])
            # An already detached high hand can be safely translated sideways
            # even when its XY shadow overlaps food. Requiring a2D normal gap
            # in this case adds needless motions above a genuinely clear load.
            if lo[2]>=center[2]+half[2]+.010:continue
            fc=(lo+hi)/2;fh=(hi-lo)/2
            if abs(float((fc-center)@lateral))>float(np.abs(lateral)@(fh+half))+.002:continue
            gap=float((fc-center)@direction-np.abs(direction)@(fh+half))
            if gap<.005:return False
        return True
    for _ in range(10):
        guard()
        if not touching()and normal_clear():break
        require_finger_clearance(a,food,side,direction*.003)
        a.move(side,a.tip(side)+direction*.003,guard,tolerance=.0007)
        if np.linalg.norm(np.asarray(a.snapshot()[0][food]['pos'])[:2]-start[:2])>.005:
            raise ToolExecutionError('E28 backstop normal separation dragged food more than5mm')
    else:raise ToolExecutionError('E28 backstop did not release actual side contact')
    if touching()or not normal_clear():raise ToolExecutionError('E28 backstop remained near food before lateral withdrawal')
    normal_released[0]=True
    # Escape sideways toward the source's clear negative-X edge; advancing
    # the other open finger toward +Y sweeps it into the destination plate.
    away=np.array([-direction[1],direction[0],0.]);away*=1 if away[0]<=0 else -1
    require_finger_clearance(a,food,side,away*.10)
    a.move(side,a.tip(side)+away*.10,guard)
    # The empty hand is now outside the food's vertical lift column.
    clear_loaded_column(a,food,side)
    if getattr(a,'_e28_short_backstop_retreat',False):
        a.move(side,a.tip(side)+[0.,0.,.04],guard)
        clear_loaded_column(a,food,side)
        return
    park=np.asarray(a._e28_backstop_park,float)
    high=max(1.02,float(park[2]),float(a.tip(side)[2])+.08)
    a.move(side,np.r_[a.tip(side)[:2],high],guard)
    a.move(side,np.r_[park[:2],high],guard)
    clear_loaded_column(a,food,side)
    with (a.a.out/'E28-backstop-retreat.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(step=a.c.steps,food=food,side=side,
            actual_tcp=a.tip(side).tolist(),public_actions_only=True,
            lateral_before_up=True,parked_outside_loaded_vertical_path=True))+'\n')


def center_over_blade(tool,tool_state,food_position,margin=.005):
    """Require the measured food centre inside the source blade support patch."""
    local=np.asarray(tool_state['mat']).T@(np.asarray(food_position)-tool_state['pos'])
    box=tool['support_bounds'];lo=np.asarray(box['lower']);hi=np.asarray(box['upper'])
    return bool(np.all(local[:2]>=lo[:2]+margin)and np.all(local[:2]<=hi[:2]-margin)),local


def insert(a, food, edge, side, direction, height, guard, *, backstop_side=None,pulse_mm=3.,backstop_already_withdrawn=False):
    """Track actual edge relative to food; a pushed food is never entry."""
    if not 1.<=float(pulse_mm)<=12.:raise ValueError('Insertion pulse must fit the reviewed public action range')
    if backstop_side is None:backstop=place(a,food,direction,guard)
    else:
        if backstop_side not in ('left','right')or not hasattr(a,'_e28_backstop_park'):
            raise ToolExecutionError('E28 insertion resume requires actual backstop side and original parking pose')
        if a.c.grips[backstop_side]<.035 or any(a.snapshot()[0][food]['grasp']):
            raise ToolExecutionError('E28 insertion resume requires genuinely open, non-grasping backstop')
        backstop=backstop_side
    withdrawn=bool(backstop_already_withdrawn);history=[];motion=[]
    obj=next(o for o in a.spec['objects']if o['id']==food)
    initial_state=a.snapshot()[0][food]
    initial=np.asarray(initial_state['pos'],float).copy()
    initial_bottom=float(initial[2]-(np.abs(initial_state['mat'])@np.asarray(obj['size'],float))[2])
    for iteration in range(70):
        guard();all_state=a.snapshot()[0];state=all_state[food]
        if any(state['grasp']):raise ToolExecutionError('E28 food was grasped during physical insertion')
        center=np.asarray(state['pos']);half=np.abs(state['mat'])@np.asarray(obj['size'],float)
        extent=float(np.abs(np.asarray(state['mat']).T@direction)@np.asarray(obj['size'],float))
        point=a.point(edge);relative=float((point-center)@direction)
        tool=a.s['tools']['main'];loaded_geometry,local=center_over_blade(tool,all_state[tool['actor']],center)
        bounds=tool['support_bounds']
        if not bounds['lower'][1]+.005<=local[1]<=bounds['upper'][1]-.005:
            raise ToolExecutionError('E28 food moved laterally outside the real blade load corridor')
        table_supported=a.contact(food,'table')
        row=dict(step=a.c.steps,food_id=food,relative_edge=relative,food=center.tolist(),blade=point.tolist(),backstop_withdrawn=withdrawn,food_grasp=state['grasp'],food_center_tool_local=local.tolist(),center_over_blade_patch=loaded_geometry,actual_table_support=table_supported)
        history.append(row)
        if len(history)>=8 and max(h['relative_edge']for h in history[-7:])-history[-8]['relative_edge']<.001:
            raise ToolExecutionError('E28 actual edge made no progress relative to food in8actions')
        with (a.a.out/'E28-relative-insertion.private.jsonl').open('a')as stream:
            stream.write(json.dumps(row)+'\n')
        if not withdrawn and (loaded_geometry or not table_supported):
            hold=getattr(a,'_e28_contact_hold',None)
            if hold is not None:
                hold()
                # A real achieved-pose hold can resolve a transient contact
                # dropout. Require the fresh table force before more entry.
                table_supported=a.contact(food,'table')
            if loaded_geometry or not table_supported:
                withdraw(a,food,backstop,direction,guard)
                withdrawn=True
        # The tip extends beyond the load-bearing patch. Native v15 still had
        # the food centre at localX=.131m,6mm beyond the patch's .125m end,
        # despite the tip advancing past it. Do not lift that shallow load.
        # Assistance ends immediately if actual table support disappears.
        if withdrawn and loaded_geometry:break
        if np.linalg.norm(center[:2]-initial[:2])>.035:
            raise ToolExecutionError('E28 food slid ahead without actual blade entry')
        a.stage('actual-relative-blade-insertion-'+food)
        # One public pulse, then remeasure the actual blade. A nested point
        # tracker reduces a3mm command to a weak sub-mm residual against static
        # friction; it is not a meaningful requirement for this contact stroke.
        error=direction*(float(pulse_mm)/1000.);error[2]=height-point[2]
        if abs(error[2])<.0015:error[2]=0.
        axis=int(np.argmax(abs(error)))
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        a.act(side,token,mm=min(float(pulse_mm),abs(float(error[axis]))*1000))
        actual=a.point(edge);motion.append(actual.copy())
        if len(motion)>=8 and max(float((p-motion[-8])@direction)for p in motion[-7:])<.001:
            raise ToolExecutionError('E28 blade made no actual insertion progress in8public actions')
        if not initial_bottom-.006<=actual[2]<=initial_bottom+.004:
            raise ToolExecutionError('E28 blade left the real food underside height band')
    else:raise ToolExecutionError('E28 actual blade entry action bound exhausted')
    if not withdrawn:withdraw(a,food,backstop,direction,guard)
    with (a.a.out/'E28-relative-insertion.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(food=food,history=history,hand_grasped=False))+'\n')
