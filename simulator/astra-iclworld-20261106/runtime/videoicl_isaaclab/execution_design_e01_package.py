"""E01 original carton: reachable loading station and real rim-height release."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def _state(p):
    if p.task!='E01'or not p.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E01 independent physical packaging reference required')
    state=getattr(p,'_e01_package_progress',None)
    if state is None:
        side=p.hand_for('meal_box');destination=p.d['staging']['meal_box']['xy']
        from .execution_design_e01_balance import _coarse
        xy=np.array([-.24 if _coarse(p)else-.30,float(destination[1])]);actual=p.frame({'actor':'meal_box'})[0]
        ready=bool(p.contact('meal_box','table')and max(abs(actual[:2]-xy))<.015)
        state=dict(phase='load_tray'if ready else'stage_box',side=side,station_xy=xy.tolist())
        p._e01_package_progress=state
    return state


def stage_meal_box_for_loading(p):
    """Move the actual empty original carton over the unused food to near X."""
    state=_state(p)
    if state['phase']!='stage_box':
        return dict(local_completed=True,phase=state['phase'],whole_task_score=None)
    if not p.contact('tray','table'):
        p.stage('near-carton-public-contact-rebuild');p.act()
    if not p.contact('tray','table'):
        raise ToolExecutionError('E01 loaded tray needs actual table support before carton move')
    p.stage('near-loading-carton-source-acquire');previous=p.clearance;p.clearance=.99
    try:
        from .execution_design_e01_balance import _coarse
        held=[s for i,s in enumerate(('left','right'))if p.snapshot()[0]['meal_box']['grasp'][i]]
        if _coarse(p)and len(held)==1:
            ref,side=p.ref('meal_box'),held[0];state['side']=side
        else:ref,side=p.pickup('meal_box')
        p.raise_payload_bottom('meal_box',ref,side,.96)
        p.stage('near-loading-carton-carry')
        p.translate_cleared_meal_box('meal_box',ref,side,0,state['station_xy'][0],.95)
        p.translate_cleared_meal_box('meal_box',ref,side,1,state['station_xy'][1],.95)
        control=dict(actor='meal_box',local=p.bottom_local('meal_box').tolist())
        p.stage('near-carton-actual-table-lower')
        for _ in range(60):
            p.require_held(ref,side)
            if p.contact('meal_box','table'):break
            height=float(p.point(control)[2]);p.act(side,'DOWN',mm=min(10.,max(2.5,(height-.801)*1000)))
        else:raise ToolExecutionError('E01 near carton did not find actual table support')
        return settle_loading_carton(p)
    finally:p.clearance=previous


def settle_loading_carton(p):
    """Release the already supported original carton, ignoring a private XYZ goal."""
    state=_state(p);side=state['side']
    if state['phase']=='load_tray':return dict(local_completed=True,phase='load_tray',whole_task_score=None)
    p.stage('release-actual-supported-loading-carton');p.act(side,'RELEASE')
    if any(p.snapshot()[0]['meal_box']['grasp']):raise ToolExecutionError('E01 near carton did not physically release')
    p.move(side,p.tip(side)+[0,0,.07])
    if not p.contact('meal_box','table'):
        raise ToolExecutionError('E01 near loading carton lacks actual table support')
    state['phase']='load_tray'
    p.a.control_report['e01_near_loading_carton']=dict(position_task_m=p.frame({'actor':'meal_box'})[0].tolist(),
        original_source_geometry=True,private_far_x_station_required=False,
        private_two_mm_xyz_goal_required=False)
    return dict(local_completed=True,phase=state['phase'],whole_task_score=None)


def _meal_on_tray(p,require_contact=False):
    state,_=p.snapshot();base,r=p.frame({'actor':'tray'})
    region=p.d['local_regions'][0]
    for name in p.d['target_members']:
        value=state[name];center=value['pos']+value['mat']@np.asarray(p.objects[name].get('local_bounds_center',[0,0,0]))
        local=r.T@(center-base);half=np.abs(r.T@value['mat'])@np.asarray(p.objects[name]['size'])
        from .execution_design_e01_balance import _coarse
        if _coarse(p):
            if value['pos'][2]<.78 or (p.contact(name,'table')and not p.contact(name,'tray')and not p.contact(name,'meal_box')):
                raise ToolExecutionError('E01 selected meal actually fell from its carried tray: '+name)
            continue
        if not require_contact:
            tray=p.objects['tray'];mid=np.asarray(tray.get('local_bounds_center',[0,0,0]))
            outer=np.asarray(tray['size'])
            if (np.any(abs(local[:2]-mid[:2])>outer[:2])
                    or local[2]-half[2]<float(region['lower'][2])-.01
                    or p.contact(name,'table')and not p.contact('tray','table')):
                raise ToolExecutionError('E01 actual meal left its physical tray: '+name)
            continue
        if ((require_contact and not p.contact(name,'tray'))
                or local[2]-half[2]<float(region['lower'][2])-.01
                or np.any(local[:2]-half[:2]<np.asarray(region['lower'])[:2]-.003)
                or np.any(local[:2]+half[:2]>np.asarray(region['upper'])[:2]+.003)):
            raise ToolExecutionError('E01 selected meal lost actual tray support/containment: '+name)


def escape_lid_arm(p):
    """Use two public translations to leave the measured right-arm/lid contact."""
    if p.task!='E01' or not p.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E01 engineering carton escape required')
    p.stage('loaded-tray-right-arm-lid-escape')
    # The first intended UP also reconstructs contacts.  A startup STILL would
    # continue the failed downward target rather than leave the observed contact.
    for token in ('UP','BACK'):
        p.act('right',token,mm=10.)
        p.require_held({'actor':'tray'},'left')
        _meal_on_tray(p)
    state,_=p.snapshot()
    p.a.control_report['e01_lid_arm_escape']=dict(
        public_actions=['UP 10mm','BACK 10mm'],
        actual_left_tray_held=bool(state['tray']['grasp'][0]),
        tray_table_contact=p.contact('tray','table'),
        meal_box_position_task_m=p.frame({'actor':'meal_box'})[0].tolist(),
        lid_position_task_m=p.frame({'actor':'meal_box_lid'})[0].tolist())
    return dict(local_completed=True,whole_task_score=None)


def load_meal_tray_left(p):
    """Use the measured existing left rim hold; the real meal must stay aboard."""
    from .execution_design_e13_release import actual_opening_bodies
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_thin_edge import table_bounds_task
    state=_state(p)
    if state['phase']=='loaded':return dict(local_completed=True,phase='loaded',whole_task_score=None)
    if state['phase']!='load_tray':raise ToolExecutionError('E01 single rim carry needs its supported loading carton')
    p.stage('loaded-tray-single-left-actual-liftoff')
    # The original parked right hand is already outside this route.  Keep it
    # there; retracting its folded arm adds an unnecessary reachability demand.
    # The first intended lift also reconstructs the real left grip contacts.
    p.act('left','UP',mm=4.)
    def guard():
        p.require_held({'actor':'tray'},'left');_meal_on_tray(p)
    guard()
    if not p.contact('meal_box','table'):raise ToolExecutionError('E01 loading carton lacks actual table support')
    control=dict(actor='tray',local=p.bottom_local('tray').tolist())
    point=p.point(control);base,r=p.frame({'actor':'meal_box'});box=p.objects['meal_box']
    rim=float((base+r@np.asarray(box.get('local_bounds_center',[0,0,0])))[2]+abs(r[2])@np.asarray(box['size']))
    top=table_bounds_task(p.a.scene)['top']
    obstacle_names=['meal_box']+[package['lid']for package in p.d['packages']if package.get('lid')]
    obstacles={name:collision_parts_task(p,name)for name in obstacle_names}
    meal={name:collision_parts_task(p,name)for name in p.d['target_members']}
    tip=p.tip('left');opening=actual_opening_bodies(p,'left')
    swept_pose_clearance(opening,tip,tip,np.eye(3),meal,top,margin=.0003)
    shift=np.r_[base[:2]-point[:2],0.];goal=None
    for bottom in np.arange(rim+.006,rim+.102,.002):
        delta=shift+[0,0,float(bottom-point[2])]
        try:
            swept_pose_clearance({k:x+delta for k,x in opening.items()},tip+delta,tip+delta,
                                 np.eye(3),obstacles,top,margin=.0003)
        except ToolExecutionError:continue
        goal=np.r_[base[:2],bottom];break
    if goal is None:raise ToolExecutionError('E01 left rim opening has no actual clearance above original carton')
    p.a.control_report['e01_loaded_tray_single_rim_plan']=dict(side='left',
        actual_existing_hold=True,box_rim_task_z=rim,release_bottom_task_z=float(goal[2]),
        private_dual_hand_requirement=False)
    # The negative-Y carton has its hinge beyond the destination.  A carton
    # on the positive side requires an explicitly reviewed over-lid route.
    if base[1]>point[1]:raise ToolExecutionError('E01 positive-side loaded route needs its actual lid clearance plan')
    for label,target in [('lift',np.r_[point[:2],goal[2]+.008]),
                         ('carry-y',np.array([point[0],goal[1],goal[2]+.008])),
                         ('carry-x',goal+[0,0,.008]),('release-height',goal)]:
        p.stage('loaded-tray-single-left-'+label)
        for _ in range(300):
            guard();error=target-p.point(control)
            if max(abs(error))<=.003:break
            axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            p.act('left',token,mm=min(4.,max(p.min_mm,abs(float(error[axis]))*1000)))
        else:raise ToolExecutionError('E01 actual left-held meal did not reach '+label)
    guard();tip=p.tip('left')
    obstacles={name:collision_parts_task(p,name)for name in obstacle_names+list(p.d['target_members'])}
    swept_pose_clearance(actual_opening_bodies(p,'left'),tip,tip,np.eye(3),obstacles,top,margin=.0003)
    p.stage('loaded-tray-single-left-release');p.act('left','RELEASE')
    if any(p.snapshot()[0]['tray']['grasp']):raise ToolExecutionError('E01 original tray did not actually release')
    p.move('left',p.tip('left')+[0,0,.07]);_meal_on_tray(p,require_contact=True)
    if not p.contact('tray','meal_box'):raise ToolExecutionError('E01 actual released meal tray lacks carton contact')
    state['phase']='loaded'
    return dict(local_completed=True,phase='loaded',actual_original_box_contact=True,whole_task_score=None)


def load_meal_tray(p):
    """Carry the real loaded tray above the box; fingers never enter its walls."""
    from .execution_design_e01_tray_reference import reviewed_forward_grips,require_finger_floor_clearance
    from .execution_design_e13_release import actual_opening_bodies
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_thin_edge import table_bounds_task
    state=_state(p)
    if state['phase']=='stage_box':raise ToolExecutionError('E01 near loading carton must be physical first')
    if state['phase']=='loaded':return dict(local_completed=True,phase='loaded',whole_task_score=None)
    if not p.contact('meal_box','table'):
        p.stage('loaded-tray-public-contact-rebuild');p.act()
    if not p.contact('meal_box','table'):raise ToolExecutionError('E01 loading box lacks actual table support')
    refs=reviewed_forward_grips(p,.055);top=table_bounds_task(p.a.scene)['top']
    for side in('left','right'):
        from .execution_design_e01_balance import _coarse,complete_balanced_load
        if _coarse(p)and side=='right':return complete_balanced_load(p)
        if p.held({'actor':'tray'},side):continue
        other='right'if side=='left'else'left';ref=refs[side]
        def support_guard():
            _meal_on_tray(p)
            if not p.contact('tray','table')and not any(p.snapshot()[0]['tray']['grasp']):
                raise ToolExecutionError('E01 rim approach lost both table and real grasp support')
            require_finger_floor_clearance(p,side)
        p.stage('loaded-tray-rim-'+side);p.act(side,'RELEASE')
        height=max(1.0,float(p.tip(side)[2]));p.move(side,[*p.tip(side)[:2],height],support_guard)
        _,rotation=p.frame(ref);p.a.align_gripper_axis(side,rotation@np.asarray(ref['jaw_axis_local']))
        p.move(side,[*p.point(ref)[:2],height],support_guard);p.move(side,p.point(ref),support_guard)
        for _ in range(5):
            p.act(side,'GRASP');support_guard()
            if p.held(ref,side):break
        else:raise ToolExecutionError('E01 loaded original rim lacks actual '+side+' hold')
    def guard():
        p.require_held({'actor':'tray'},'left');p.require_held({'actor':'tray'},'right');_meal_on_tray(p)
    control=dict(actor='tray',local=p.bottom_local('tray').tolist());base,r=p.frame({'actor':'meal_box'})
    box=p.objects['meal_box'];rim=float((base+r@np.asarray(box.get('local_bounds_center',[0,0,0])))[2]+abs(r[2])@np.asarray(box['size']))
    # Both actual closed-to-open hands must clear the tall original carton.
    # Plan at the real boxXY using the present measured loaded tray frame.
    point=p.point(control);shift=np.r_[base[:2]-point[:2],0.]
    obstacle_names=['meal_box']+[package['lid']for package in p.d['packages']if package.get('lid')]
    obstacles={name:collision_parts_task(p,name)for name in obstacle_names}
    meal_obstacles={name:collision_parts_task(p,name)for name in p.d['target_members']}
    for side in('left','right'):
        tip=p.tip(side);swept_pose_clearance(actual_opening_bodies(p,side),tip,tip,np.eye(3),meal_obstacles,top,margin=.0003)
    goal=None
    for bottom in np.arange(rim+.006,rim+.102,.002):
        delta=shift+[0,0,float(bottom-point[2])]
        try:
            for side in('left','right'):
                bodies={k:points+delta for k,points in actual_opening_bodies(p,side).items()}
                tip=p.tip(side)+delta;swept_pose_clearance(bodies,tip,tip,np.eye(3),obstacles,top,margin=.0003)
        except ToolExecutionError:continue
        goal=np.r_[base[:2],bottom];break
    if goal is None:raise ToolExecutionError('E01 loaded tray has no actual open-finger clearance above original rim')
    p.a.control_report['e01_loaded_tray_release_plan']=dict(box_rim_task_z=rim,actual_tray_bottom_release_z=float(goal[2]),
        fingers_enter_original_box=False,actual_gravity_landing_required=True)
    for stage,target in [('lift',np.r_[point[:2],goal[2]+.008]),('carry-y',np.array([point[0],goal[1],goal[2]+.008])),
                         ('carry-x',goal+[0,0,.008]),('release-height',goal)]:
        p.stage('loaded-tray-'+stage)
        for _ in range(300):
            guard();error=target-p.point(control)
            if max(abs(error))<=.003:break
            axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            p.act('left',token,mm=min(4.,max(p.min_mm,abs(float(error[axis]))*1000)),follower='right')
        else:raise ToolExecutionError('E01 loaded tray actual transport did not reach '+stage)
    guard()
    obstacles={name:collision_parts_task(p,name)for name in obstacle_names}
    obstacles.update({name:collision_parts_task(p,name)for name in p.d['target_members']})
    for side in('left','right'):
        tip=p.tip(side);swept_pose_clearance(actual_opening_bodies(p,side),tip,tip,np.eye(3),obstacles,top,margin=.0003)
    p.stage('loaded-tray-real-gravity-release');p.act('left','RELEASE',follower='right')
    if any(p.snapshot()[0]['tray']['grasp']):raise ToolExecutionError('E01 loaded tray did not actually release')
    p.move('left',p.tip('left')+[0,0,.07],follower='right')
    _meal_on_tray(p,require_contact=True)
    if not p.contact('tray','meal_box'):raise ToolExecutionError('E01 gravity-released tray lacks original box contact')
    state['phase']='loaded'
    return dict(local_completed=True,phase='loaded',actual_original_box_contact=True,whole_task_score=None)


def package_stage(p):
    stage_meal_box_for_loading(p);load_meal_tray(p)
    from .execution_design_e01_lid import close_loading_lid
    return close_loading_lid(p)


def deliver_supported_box(p):
    """Translate the closed original carton on its real table support."""
    from .execution_design_e01_balance import _coarse
    if _coarse(p):
        from .execution_design_e01_functional import deliver
        return deliver(p)
    from .execution_design_e01_food import park_empty_other
    state=_state(p)
    if state['phase']!='loaded':raise ToolExecutionError('E01 delivery requires its real loaded carton')
    side=p.hand_for('meal_box');park_empty_other(p,side,{},None)
    previous=p.clearance;p.clearance=.99
    try:
        p.stage('delivery-supported-carton-acquire');ref,side=p.pickup('meal_box')
        zone=next(z for z in p.spec['zones']if z['id']==p.d['destination_zone'])
        control=dict(actor='meal_box',local=p.bottom_local('meal_box').tolist())
        target=np.asarray(zone['xy'],float)
        p.stage('delivery-actual-table-supported-carton')
        for _ in range(180):
            p.require_held(ref,side);_meal_on_tray(p)
            point=p.point(control);error=target-point[:2]
            if max(abs(error))<.002:break
            axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)]
            p.act(side,token,mm=min(8.,max(p.min_mm,abs(float(error[axis]))*1000)))
        else:raise ToolExecutionError('E01 actual supported delivery did not reach original zone')
        p.release(ref,side);p.move(side,p.tip(side)+[0,0,.07])
    finally:p.clearance=previous
    if not p.contact('meal_box','table'):raise ToolExecutionError('E01 delivered original carton lacks actual table support')
    state['phase']='delivered'
    return dict(local_completed=True,actual_table_supported_delivery=True,whole_task_score=None)
