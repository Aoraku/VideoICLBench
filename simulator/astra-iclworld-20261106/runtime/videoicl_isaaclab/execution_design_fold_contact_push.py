"""Engineering E44 continuation from an actual raised-leaf finger contact."""
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation

def complete(p,reuse_grip=False):
    from .engineering_thin_suffix import save_stage
    s=p.s['crease'];g=s['expert'];base=dict(mechanism=s['mechanism'],**g['base_press']);fold=dict(mechanism=s['mechanism'],**g['fold_grasp'])
    target=180.-(90.,120.,45.)[p.index]
    def angle():return math.degrees(math.acos(float(np.clip(p.frame(base)[1][:,2]@p.frame(fold)[1][:,2],-1,1))))
    def contact():return any(p.contact(fold['contact_body'],f'right_finger{i}')for i in(1,2))
    def supported():
        if not p.contact(base['contact_body'],'table'):raise ToolExecutionError('Contact fold lost base table support')
        if not any(p.contact(base['contact_body'],f'left_finger{i}')for i in(1,2)):raise ToolExecutionError('Contact fold lost left base pressure')
    p.stage('E44-contact-fold-reseat-left-pressure')
    for _ in range(6):
        if any(p.contact(base['contact_body'],f'left_finger{i}')for i in(1,2)):break
        if not p.contact(base['contact_body'],'table'):raise ToolExecutionError('Contact fold reseat lost table support')
        p.act('left','DOWN',mm=.5)
    if not reuse_grip:
        p.stage('E44-contact-fold-direct-grasp')
        for _ in range(10):
            if contact():break
            p.act('right','DOWN',mm=.5);supported()
        if not contact():raise ToolExecutionError('Direct fold grip could not regain leaf contact')
        p.act('right','GRASP')
        for _ in range(4):
            if p.held(fold,'right'):break
            p.act('right','STILL')
        if not p.held(fold,'right'):raise ToolExecutionError('Direct leaf GRASP lacked actual bilateral grip')
    save_stage(p.a,'actual-direct-leaf-grip',dict(angle_deg=angle()))
    from .execution_design_cutlery_grasp import orient
    bp,br=p.frame(base);hinge=bp+br@np.asarray(g['hinge_point_local']);axis=br@np.asarray(g['axis_local']);ref=dict(fold,local=[.1,-.05,0.]);vector=p.point(ref)-hinge;start=angle();initial=p.a.tcp_rotation_task('right').copy()
    def held():p.require_held(fold,'right');supported()
    p.stage('E44-contact-grip-real-fold')
    for desired in np.arange(start+1.,target+1.,1.):
        held();delta=math.radians(min(float(desired),target)-start)*float(g['direction']);turn=_axis_rotation(axis,delta)
        p.move_point('right',ref,hinge+turn@vector,held,tolerance=.0007);held();orient(p.a,'right',turn@initial);held()
        if abs(angle()-target)<10.:break
    save_stage(p.a,'actual-direct-grip-fold-target',dict(angle_deg=angle()))
    p.release(fold,'right');p.act('right','UP',mm=15.);p.act('left','UP',mm=30.);p.wait(2)
    save_stage(p.a,'actual-direct-grip-fold-released',dict(angle_deg=angle()))
    return dict(physical_fold_route_finished=True,measured_angle_deg=angle(),diagnostic_only=True)


def complete_passive_guide(p,raised_result=None):
    from .execution_design_fold_rails import raise_onto_rails
    from .engineering_thin_suffix import save_stage
    target=(82.,60.,82.)[p.index]
    result=raised_result if raised_result is not None else raise_onto_rails(p,counterpress_override=not p.s['execution_design_fold_fixture'].get('single_pusher',False),avoid_cross_arm=not p.s['execution_design_fold_fixture'].get('single_pusher',False),presser_y_local=-.095,presser_x_local=-.01,minimum_raise_deg=target,minimum_edge_z=.84)
    save_stage(p.a,'actual-tall-guide-angle',result)
    if p.index==2:
        from .execution_design_fold_normal_grasp import complete as normal_fold
        return normal_fold(p,grasp_side='left',face_normal_only=True)
    s=p.s['crease'];g=s['expert'];base=dict(mechanism=s['mechanism'],**g['base_press']);fold=dict(mechanism=s['mechanism'],**g['fold_grasp'])
    def angle():return math.degrees(math.acos(float(np.clip(p.frame(base)[1][:,2]@p.frame(fold)[1][:,2],-1,1))))
    def on_rail():
        _,pairs=p.snapshot();names=p.s['execution_design_fold_fixture']['fixture_contact_ids']
        return any(any(body in pair for body in(base['contact_body'],fold['contact_body']))and any(n in pair for n in names)for pair in pairs)
    from .execution_design_thin_edge import mechanism_collision_points_task,actual_finger_points_task,trailing_edge_push_pose,table_bounds_task
    from .execution_design_thin_motion import checked_move
    floor=table_bounds_task(p.a.scene)['top']
    def table_guard():
        guide=p.s['execution_design_fold_fixture']
        supported=p.contact(base['contact_body'],'table')or(guide.get('single_pusher',False)and any(p.contact(base['contact_body'],n)for n in guide.get('base_guide_contact_ids',[])))
        if not supported:raise ToolExecutionError('Guide release lost real base table or sliding-guide support')
    def pushing():return any(p.contact(base['contact_body'],f'left_finger{i}')for i in(1,2))
    p.stage('E44-guide-actual-side-edge-release')
    p.act('left','BACK',mm=8.);p.act('left','UP',mm=30.)
    target_pose,receipt=trailing_edge_push_pose(mechanism_collision_points_task(p,base),actual_finger_points_task(p.a,'left'),p.tip('left'),[0.,-1.,0.],floor,center_leading_toe=True)
    high=max(float(p.tip('left')[2]),float(target_pose[2])+.03)
    checked_move(p,'left',[float(p.tip('left')[0]),float(target_pose[1]),high],table_guard,tolerance=.005)
    checked_move(p,'left',[*target_pose[:2],high],table_guard,tolerance=.005)
    checked_move(p,'left',target_pose,table_guard,tolerance=.001)
    for _ in range(10):
        if pushing():break
        p.act('left','RIGHT',mm=.5);table_guard()
    if not pushing():raise ToolExecutionError('Guide side-edge release lacks actual base edge contact')
    save_stage(p.a,'actual-guide-side-pusher-contact',receipt)
    if not p.s['execution_design_fold_fixture'].get('single_pusher',False):
        p.act('right','UP',mm=25.)
        checked_move(p,'right',p.tip('right')+[0.,-.12,0.],table_guard,tolerance=.005)
    for _ in range(46):
        if not on_rail():break
        if not pushing():
            for _ in range(6):
                p.act('left','RIGHT',mm=.5);table_guard()
                if pushing():break
            if not pushing():raise ToolExecutionError('Guide side-edge pusher lost real base contact')
        p.act('left','RIGHT',mm=5.);table_guard()
    else:raise ToolExecutionError('Guide release did not physically leave rails')
    p.act('left','UP',mm=30.);p.wait(2)
    if on_rail():raise ToolExecutionError('Released leaf still depends on passive guide')
    if not p.contact(base['contact_body'],'table'):raise ToolExecutionError('Fully released base did not return to actual tabletop')
    save_stage(p.a,'actual-guide-released-fold',dict(angle_deg=angle()))
    return dict(physical_fold_route_finished=True,measured_angle_deg=angle(),diagnostic_only=True)
