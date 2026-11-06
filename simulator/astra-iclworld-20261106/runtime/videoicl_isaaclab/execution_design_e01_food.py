"""Original food placements, resumed after the empty tray's actual release."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def park_empty_other(policy,active,state,held_ref):
    if state.get('parked_for')==active:return
    other='left'if active=='right'else'right';snapshot,_=policy.snapshot()
    if any(row['grasp'][0 if other=='left'else 1]for row in snapshot.values()):
        raise ToolExecutionError('E01 inactive food arm must actually be empty')
    def guard():
        if held_ref is not None:policy.require_held(held_ref,active)
    robot=policy.a.scene.robots[other]
    base=policy.a.scene.world_to_task(robot.data.root_pos_w[0].detach().cpu().numpy())
    policy.stage('food-park-empty-'+other);guard()
    robot=policy.a.scene.robots[other]
    ids,_=robot.find_joints(policy.a.scene.embodiment.finger_joints,preserve_order=True)
    current=robot.data.joint_pos[0,ids].detach().cpu().numpy()
    if not np.all(current>=np.asarray(policy.a.scene.embodiment.gripper_values(1.))-.0001):
        policy.act(other,'RELEASE')
    # Move laterally first: the measured1091 left wrist overlaps the active
    # right palm. Raising it in place would retain that crossed-arm obstacle.
    tip=policy.tip(other)
    policy.move(other,[tip[0],base[1],tip[2]],guard)
    policy.move(other,[*policy.tip(other)[:2],max(1.02,float(policy.tip(other)[2]))],guard)
    policy.move(other,[base[0]+.45,base[1],max(1.02,float(policy.tip(other)[2]))],guard)
    state['parked_for']=active


def pickup_food(policy,name,side):
    ref=policy.ref(name);robot=policy.a.scene.robots[side]
    if name=='fries':
        if policy.objects[name].get('source_asset',{}).get('sha256')!='80885424fb976c87ab6fd971fbbe22318078bb1794c65a692fe04b6ab514a6b0':
            raise ToolExecutionError('Reviewed original fries carton source required')
        # Original+40mm Z point pinched the thin fry ends and lost its real
        # hold on the first UP. The source carton section below those ends
        # supplies broad opposing faces; the raised body-Y clears the palm.
        ref=dict(ref,local=[0.,.022,-.015],jaw_axis_local=[1,0,0])
        policy.a.control_report['e01_original_fries_carton_grip']=dict(local=ref['local'],
            source_sha256=policy.objects[name]['source_asset']['sha256'],source_geometry_changed=False)
    ids=robot.find_joints('panda_joint7')[0]
    if len(ids)!=1:raise ToolExecutionError('E01 actual Panda wrist joint required')
    index=ids[0];policy.stage('food-empty-equivalent-pinch-'+name)
    finger_ids,_=robot.find_joints(policy.a.scene.embodiment.finger_joints,preserve_order=True)
    opened=np.asarray(policy.a.scene.embodiment.gripper_values(1.),float)
    current=robot.data.joint_pos[0,finger_ids].detach().cpu().numpy()
    if not np.all(current>=opened-.0001):policy.act(side,'RELEASE')
    if any(row['grasp'][0 if side=='left'else 1]for row in policy.snapshot()[0].values()):
        raise ToolExecutionError('E01 food jaw alignment requires actual empty hand')
    from .execution_design_e33_grasp import actual_mesh
    body=policy.snapshot()[0][name];obj=policy.objects[name];tip=policy.tip(side)
    center=body['pos']+body['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    top=float(center[2]+abs(body['mat'][2])@np.asarray(obj['size']))
    hand_low=min(float(actual_mesh(policy.a,side,part)[:,2].min()-tip[2])
        for part in('panda_hand',*policy.a.scene.embodiment.fingers))
    height=max(float(tip[2]),top+.015-hand_low)
    policy.move(side,[*tip[:2],height])
    # Native1397 reached q7's upper limit using the canonical signed axis.
    # Antipodal finger axes pinch the same original source faces.
    for _ in range(3):
        q=float(robot.data.joint_pos[0,index]);limits=np.asarray(robot.data.joint_pos_limits[0,index].cpu(),float)
        if min(q-limits[0],limits[1]-q)>.10:break
        policy.act(side,'ROTATE_CCW'if q>float(np.mean(limits))else'ROTATE_CW',degrees=10.)
        stalled=0
        while True:
            feedback=policy.c.action_feedback()['control_feedback'][side]
            error=float(feedback['orientation_error_rad'])
            if error<=float(feedback.get('orientation_tolerance_rad',np.deg2rad(1.))):break
            policy.act(side,'STILL')
            remaining=float(policy.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])
            stalled=stalled+1 if remaining>=error-.0005 else 0
            if stalled>=3:raise ToolExecutionError('E01 accepted empty wrist escape has no actual progress')
    else:raise ToolExecutionError('E01 empty wrist did not leave its measured hard limit')
    _,rotation=policy.frame(ref);desired=rotation@np.asarray(ref['jaw_axis_local'],float)
    from .execution_design_e01_balance import _coarse
    if _coarse(policy):
        # The tray extraction can leave a genuinely tilted empty finger axis.
        # Use the existing full3D public alignment rather than the chip-only
        # horizontal-yaw precondition, retaining the same real food grasp axis.
        fingers=policy.a.finger_geometry(side)['fingers']
        current=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
        if current@desired<0:desired=-desired
        policy.a.align_gripper_axis(side,desired)
    else:policy.align_empty_chip_axis(side,desired)
    fingers=policy.a.finger_geometry(side)['fingers']
    axis=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
    if axis@desired<0:ref=dict(ref,jaw_axis_local=(-np.asarray(ref['jaw_axis_local'],float)).tolist())
    # The hand is already physically open and aligned. A redundant RELEASE
    # after the accepted yaw caused1621's zero-motion IK rejection.
    point=policy.point(ref);height=max(policy.clearance,float(point[2])+.07,float(policy.tip(side)[2]))
    policy.stage('food-prealigned-acquire-'+name)
    policy.move(side,[*policy.tip(side)[:2],height])
    policy.move(side,[*point[:2],height]);policy.move(side,policy.point(ref))
    for _ in range(5):
        policy.act(side,'GRASP')
        if policy.held(ref,side):break
    else:raise ToolExecutionError('E01 actual source carton lacks a real bilateral grip')
    policy.move(side,policy.tip(side)+[0,0,.07],lambda:policy.require_held(ref,side))
    return ref,side


def _food_local(policy):
    if policy.task!='E01':raise ToolExecutionError('E01 food branch required')
    selected=(['burger','fries'],['burger','drink'],['fries','drink'])[policy.index]
    state=getattr(policy,'_e01_food_progress',None)
    if state is None:
        state=dict(selected=selected,completed=[],current=None)
        policy._e01_food_progress=state
    if state['selected']!=selected:raise ToolExecutionError('Original food selection differs')
    container=policy.s['containers']['plate']
    support=container['ref'].get('actor',container['ref'].get('contact_body'))
    for label in selected:
        if label in state['completed']:continue
        name=policy.identity[label];ref=policy.ref(name)
        actual=policy.snapshot()[0][name]['grasp']
        holding=[hand for i,hand in enumerate(('left','right'))if actual[i]]
        if len(holding)>1:raise ToolExecutionError('Food branch requires one actual working hand')
        sides=state.setdefault('working_sides',{})
        side=holding[0]if holding else sides.get(label,policy.hand_for(name));sides[label]=side
        park_empty_other(policy,side,state,ref if policy.held(ref,side)else None)
        state['current']=label;policy.stage('food-to-plate-'+label)
        if not policy.held(ref,side):ref,side=pickup_food(policy,name,side)
        target=policy.body_point(container['ref'],policy.geometry['plate_positions'][name])
        policy.lower_place(name,ref,side,policy.bottom_local(name),target,support=support)
        state['completed'].append(label);state['current']=None
    return dict(local_completed=True,selected=selected,completed=state['completed'],
        native_current_conditions=list(getattr(policy.c.evaluator,'current_conditions',[])),whole_task_score=None)


def food_local(policy):
    # This reviewed corridor stays in front of the rack (all foods and tray
    # x<=-0.10m). Its98cm working height clears their real upper surfaces.
    previous=policy.clearance;policy.clearance=.98
    try:return _food_local(policy)
    finally:policy.clearance=previous
