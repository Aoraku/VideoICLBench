"""Independent E44 passive-rail preparation diagnostic through public actions.

A partial raised edge is never an accepted whole-task positive. Both panels
remain dynamic source bodies and the rails exert ordinary passive contact.
"""
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_thin_edge import (table_bounds_task,mechanism_collision_points_task,
    actual_finger_points_task,trailing_edge_push_pose,seek_actual_contact)


def raise_onto_rails(p,*,resume=False,counterpress_override=None,left_clear_already_raised=False,left_clear_already_high=False,avoid_cross_arm=False,left_low_side_lane=False,presser_y_local=-.040,presser_x_local=-.025,relocate_presser=False,retain_existing_push_setup=False,minimum_raise_deg=20.,minimum_edge_z=.835):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_cutlery_grasp import orient
    from .execution_design_drawer_ik_probe import inspect
    from .execution_design_thin_motion import checked_move
    a=p.a;s=p.s['crease'];g=s['expert'];base=dict(mechanism=s['mechanism'],**g['base_press']);fold=dict(mechanism=s['mechanism'],**g['fold_grasp'])
    marker=p.s.get('execution_design_fold_fixture',{})
    if marker.get('schema')not in('e44-passive-folding-rails-v1','e44-passive-folding-rails-v2','e44-passive-folding-rails-v3','e44-passive-folding-rails-v4')or(p.c.steps!=0 and not resume):
        raise ValueError('Fresh or restored source-required rail preparation diagnostic only')
    bounds=table_bounds_task(a.scene);bp,br=p.frame(base);start=bp.copy();outward=np.array([1.,0.,0.])
    def contact():return any(p.contact(base['contact_body'],f'left_finger{i}')for i in(1,2))
    def angle():
        bn=p.frame(base)[1]@np.array(s['base']['normal_local']);fn=p.frame(fold)[1]@np.array(s['fold']['normal_local'])
        return math.degrees(math.acos(float(np.clip(bn@fn,-1,1))))
    def log(phase,**values):
        _,contacts=p.snapshot();row=dict(phase=phase,steps=p.c.steps,base_origin=p.frame(base)[0].tolist(),fold_point=p.point(fold).tolist(),fold_angle_deg=angle(),
            rail_contacts=[sorted(pair)for pair in contacts if any(x in pair for x in marker['fixture_contact_ids'])],
            actual_contact_forces=[dict(pair=sorted(pair),force_n=float(force))for pair,force in p.c.contact_forces.items()if any('cardboard/'in name for name in pair)and float(force)>.001],**values)
        with(a.out/'e44-rail-raise.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    def guard():
        guided=marker.get('single_pusher',False) and any(p.contact(base['contact_body'],n)for n in marker.get('base_guide_contact_ids',[]))
        if not p.contact(base['contact_body'],'table')and not guided:raise ToolExecutionError('Rail preparation lost real table or sliding-guide base support')
        if abs(p.frame(base)[1][2,2])<.995:raise ToolExecutionError('Rail preparation base tilted away from table')
    height=max(bounds['top']+.14,float(p.tip('left')[2]))
    if not resume:
        p.stage('E44-rails-pusher-orient');p.act('left','GRASP')
        rotation=a.tcp_rotation_task('left');candidate=_axis_rotation([0,1,0],math.radians(10))@rotation
        tips=actual_finger_points_task(a,'left');tcp=p.tip('left');future=(tips-tcp)@rotation@candidate.T+tcp
        planned,_=trailing_edge_push_pose(mechanism_collision_points_task(p,base),future,tcp,outward,bounds['top'])
        palm=(actual_mesh(a,'left','panda_hand')-tcp)@rotation@candidate.T+planned
        if palm[:,2].min()<bounds['top']+.0002:raise ToolExecutionError('Rail pusher palm below actual tabletop')
        height=max(bounds['top']+.14,float(tcp[2]));waypoints=[tcp.tolist(),[*tcp[:2],height],[*planned[:2],height],planned.tolist()]
        probes=[inspect(a,p.c,'left',[dict(position=point,rotation=candidate.tolist())])[0]for point in waypoints]
        log('empty-pusher-native-screen',ik=probes)
        if not all(r['kinematically_reachable']and r['minimum_joint_margin_rad']>.02 for r in probes):
            raise ToolExecutionError('Rail pusher approach lacks native IK margin')
        orient(a,'left',candidate)
    seated_once=[bool(resume and retain_existing_push_setup)]
    def seat():
        guard();target,geometry=trailing_edge_push_pose(mechanism_collision_points_task(p,base),actual_finger_points_task(a,'left'),p.tip('left'),outward,bounds['top'])
        # Pass above the supporting right wrist before returning to the
        # trailing edge. The old 8mm lift left both forearms in one low lane.
        if seated_once[0]:h=max(float(p.tip('left')[2])+.008,float(target[2])+.012)
        elif left_low_side_lane:h=max(float(p.tip('left')[2]),float(target[2])+.02)
        elif left_clear_already_high:
            h=float(p.tip('left')[2])
            if h<bounds['top']+.10:raise ToolExecutionError('Restored hand is not actually above the high-clearance band')
        else:h=max(bounds['top']+.14,float(p.tip('left')[2])+.008,float(target[2])+.012)
        p.stage('E44-rails-pusher-seat')
        checked_move(p,'left',[*p.tip('left')[:2],h],guard,tolerance=.006)
        if avoid_cross_arm and not seated_once[0]:
            lane=max(.15,float(p.tip('left')[1]))
            checked_move(p,'left',[float(target[0]),lane,h],guard,tolerance=.006)
            checked_move(p,'left',[float(target[0]),lane,float(target[2])+.02],guard,tolerance=.006)
            checked_move(p,'left',[*target[:2],float(target[2])+.02],guard,tolerance=.004)
        else:checked_move(p,'left',[*target[:2],h],guard,tolerance=.006)
        checked_move(p,'left',target,guard,tolerance=.0003)
        if seek_actual_contact(contact,lambda:p.act('left','FWD',mm=.5),12)is None:
            raise ToolExecutionError('Rail preparation lacks actual trailing-panel contact')
        seated_once[0]=True
        log('actual-trailing-contact',geometry=geometry)
    counterpress=(__import__('os').environ.get('VIC_E44_COUNTERPRESS')=='1')if counterpress_override is None else bool(counterpress_override)
    def press_force():
        return sum(float(force)for pair,force in p.c.contact_forces.items()if base['contact_body']in pair and any(f'right_finger{i}'in pair for i in(1,2)))
    def seat_presser(initial=False):
        from .execution_design_clip_grasp import convex_meshes_clear
        from .execution_design_local_pose_path import inspect_local_pose_path
        if press_force()>=.2 and p.contact(base['contact_body'],'table'):
            log('retained-actual-base-counterpress',actual_force_n=press_force());return
        if initial:p.act('right','GRASP')
        if not -.095<=float(presser_y_local)<=-.04:raise ValueError('Source interior base pressing point required')
        position,mat=p.frame(base);point=position+mat@np.array([float(presser_x_local),float(presser_y_local),.0006])
        finger=actual_finger_points_task(a,'right');low=float(finger[:,2].min());pad=finger[finger[:,2]<=low+.0001].mean(0)
        target=p.tip('right')+(point-pad);target[2]+=.004 if initial else-.0002
        rotation=a.tcp_rotation_task('right');r_tcp=p.tip('right')
        right_mesh=[actual_mesh(a,'right',n)for n in('panda_hand',*a.scene.embodiment.fingers)]
        left_mesh=[actual_mesh(a,'left',n)for n in('panda_hand',*a.scene.embodiment.fingers)]
        if not all(convex_meshes_clear(m-r_tcp+target,obstacle)for m in right_mesh for obstacle in left_mesh):
            raise ToolExecutionError('Actual base counterpress overlaps supporting pusher')
        if initial:
            h=max(bounds['top']+.14,float(r_tcp[2]));poses=[dict(position=[*r_tcp[:2],h],rotation=rotation.tolist()),dict(position=[*target[:2],h],rotation=rotation.tolist()),dict(position=target.tolist(),rotation=rotation.tolist())]
            path=inspect_local_pose_path(a,p.c,'right',poses,minimum_joint_margin_rad=.04)
            log('counterpress-native-route',continuous_path=path,target=target.tolist())
            if not path['feasible']:raise ToolExecutionError('Actual counterpress approach lacks continuous native IK')
            checked_move(p,'right',[*r_tcp[:2],h],guard,tolerance=.006);checked_move(p,'right',[*target[:2],h],guard,tolerance=.006)
        p.stage('E44-rails-base-counterpress');checked_move(p,'right',target,guard,tolerance=.004)
        for _ in range(20):
            if press_force()>=.2 and p.contact(base['contact_body'],'table'):
                log('actual-base-counterpress',actual_force_n=press_force(),base_point=point.tolist())
                from .engineering_thin_suffix import save_stage
                save_stage(a,'actual-base-counterpress',dict(actual_force_n=press_force()))
                return
            p.act('right','DOWN',mm=.5)
        raise ToolExecutionError('No actual supported base counterpress force')
    if not resume and not counterpress:p.move('left',[*p.tip('left')[:2],height]);seat()
    elif not contact()and not counterpress:
        if seek_actual_contact(contact,lambda:p.act('left','FWD',mm=.5),4)is None:
            raise ToolExecutionError('Restored rail pusher lacks actual base contact')
    if counterpress and not retain_existing_push_setup:
        # Clear the unladen left wrist/forearm while the right hand passes
        # through its high approach. Its old hold was both near the right
        # palm and continuously pushing the board during the long approach.
        p.stage('E44-counterpress-clear-left')
        if avoid_cross_arm:
            checked_move(p,'left',[float(p.tip('left')[0]),.15,float(p.tip('left')[2])],guard,tolerance=.006)
        if relocate_presser:
            p.stage('E44-counterpress-side-relocation')
            checked_move(p,'right',p.tip('right')+[0.,0.,.025],guard,tolerance=.004)
        if not left_clear_already_high:
            if not left_clear_already_raised:checked_move(p,'left',p.tip('left')+[0.,0.,.03],guard,tolerance=.006)
            checked_move(p,'left',p.tip('left')+[0.,.06,0.],guard,tolerance=.006)
        # A jaw axis alone preserves the default7.3degree pitched palm.
        if not(avoid_cross_arm and press_force()>=.2):
            p.stage('E44-counterpress-full-down');orient(a,'right',np.diag([1.,-1.,-1.]))
        seat_presser(initial=not left_clear_already_high)
        seat()
    elif counterpress:
        guard()
        if press_force()<.2:seat_presser()
        if not contact():seat()
    history=[]
    for _ in range(250):
        guard();_,contacts=p.snapshot();rail=any(any(n in pair for n in marker['fixture_contact_ids'])and fold['contact_body']in pair for pair in contacts)
        if p.point(fold)[2]>float(minimum_edge_z) and angle()>float(minimum_raise_deg) and rail:
            log('actual-rail-raised-edge',preparation_only=True,native_whole_task_success=False)
            return dict(raised_edge=True,angle_deg=angle(),actions=p.c.steps,whole_task_positive=False)
        advance=float(p.frame(base)[0][0]-start[0])
        if advance>.13:raise ToolExecutionError('Rail preparation exceeded130mm real base translation')
        material_top=float(mechanism_collision_points_task(p,base)[:,2].max());low=float(a.finger_geometry('left')['lowest_z_task_m'])
        if not contact()or low>=material_top-.00015:seat();low=float(a.finger_geometry('left')['lowest_z_task_m'])
        if low>bounds['top']+.0004:p.act('left','DOWN',mm=min(1.,(low-bounds['top']-.0002)*1000))
        if counterpress and press_force()<.2:seat_presser()
        p.stage('E44-rails-real-push');request=8. if rail and angle()<float(minimum_raise_deg) else 2.
        p.act('left','FWD',mm=request)
        if counterpress:seat_presser()
        history.append(float(p.frame(base)[0][0]));log('real-rail-push',requested_public_step_mm=request)
        if len(history)>=16 and float(np.mean(history[-6:])-np.mean(history[-12:-6]))<.0002:
            raise ToolExecutionError('Actual board failed to advance onto passive rails')
    raise ToolExecutionError('Bounded passive-rail preparation did not raise real leaf')
