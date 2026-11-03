"""E44 engineering-only crease actuation by actual supported edge contact."""
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_unit
from .execution_design import REVISION_V3,source_sha256
from .execution_design_thin_edge import (table_bounds_task,mechanism_collision_points_task,
    actual_finger_points_task,trailing_edge_push_pose,seek_actual_contact)


def compress_fold(p):
    a=p.a;design=p.spec.get('execution_design',{})
    if p.task!='E44'or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)or not a.control_report.get('engineering_reference_only'):
        raise ValueError('E44 independent physical engineering required')
    s=p.s['crease'];g=s['expert']
    base=dict(mechanism=s['mechanism'],**g['base_press']);fold=dict(mechanism=s['mechanism'],**g['fold_grasp'])
    bounds=table_bounds_task(a.scene);desired=180.-(90.,120.,45.)[p.index]
    def log(phase,**values):
        row=dict(phase=phase,step=p.c.steps,measured_fold_deg=measured(),**values)
        with (a.out/'fold-compress-public.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
    def measured():
        bn=p.frame(base)[1]@_unit(s['base']['normal_local']);fn=p.frame(fold)[1]@_unit(s['fold']['normal_local'])
        return math.degrees(math.acos(float(np.clip(bn@fn,-1,1))))
    def held_base():return p.contact(base['contact_body'],'table')and any(p.contact(base['contact_body'],f'left_finger{i}')for i in(1,2))
    def guard():
        if not held_base():raise ToolExecutionError('Compression crease lost actual supported base contact')
    def leaf_contact():return any(p.contact(fold['contact_body'],f'right_finger{i}')for i in(1,2))
    p.stage('E44-compression-base-contact');p.act('left','GRASP')
    point=p.point(base);height=max(bounds['top']+.14,float(p.tip('left')[2]));p.move('left',[*p.tip('left')[:2],height]);p.move('left',[*point[:2],height])
    target=p.tip('left').copy();target[2]+=point[2]+.0006-float(a.finger_geometry('left')['lowest_z_task_m'])+.004
    p.move('left',target)
    if seek_actual_contact(held_base,lambda:p.act('left','DOWN',mm=.5),16)is None:
        raise ToolExecutionError('Compression crease could not physically hold base')
    p.stage('E44-compression-leaf-edge');p.act('right','GRASP')
    material=mechanism_collision_points_task(p,fold)
    # The toe starts above the crease axis but below the actual panel top.
    # Horizontal inward force then has an upward folding moment; no joint drive.
    start,receipt=trailing_edge_push_pose(material,actual_finger_points_task(a,'right'),p.tip('right'),[-1.,0.,0.],bounds['top'],clearance=.0008,center_leading_toe=True)
    log('measured-compression-edge',**receipt)
    # Keep the empty hand only140mm above the actual table; the old1.1m
    # detour consumed the available far-reach workspace before contact.
    from .execution_design_drawer_ik_probe import inspect
    height=max(bounds['top']+.14,float(p.tip('right')[2]))
    approach=np.array([*start[:2],height]);current=a.tcp_rotation_task('right')
    reach=inspect(a,p.c,'right',[dict(position=approach.tolist(),rotation=current.tolist()),dict(position=start.tolist(),rotation=current.tolist())])
    log('compression-approach-native-ik',ik=reach)
    if not all(row['kinematically_reachable']for row in reach):
        raise ToolExecutionError('Actual compression contact/low approach is outside native arm workspace')
    p.move('right',[*p.tip('right')[:2],height],guard);p.move('right',approach,guard);p.move('right',start,guard,tolerance=.0002)
    if seek_actual_contact(leaf_contact,lambda:p.act('right','BACK',mm=.5),12)is None:
        raise ToolExecutionError('Compression crease no actual outer-edge contact')
    history=[]
    for _ in range(300):
        guard();angle=measured()
        if angle>=desired-1.:break
        # Keep the real toe alongside the rising physical outer panel edge.
        edge=p.point(fold);low=float(a.finger_geometry('right')['lowest_z_task_m'])
        desired_low=max(bounds['top']+.0008,float(edge[2])-.0003)
        dz=desired_low-low
        if abs(dz)>.0004:
            p.act('right','UP'if dz>0 else'DOWN',mm=min(2.,abs(dz)*1000))
        if not leaf_contact():
            if seek_actual_contact(leaf_contact,lambda:p.act('right','BACK',mm=.5),4)is None:
                raise ToolExecutionError('Compression crease lost real moving-leaf contact')
        p.act('right','BACK',mm=.5 if desired-angle<5. else 1.)
        after=measured();history.append(after)
        log('contact-driven-compression',base_supported=held_base(),leaf_contact=leaf_contact(),leaf_point=p.point(fold).tolist())
        if len(history)>=12 and max(history[-12:])-min(history[-12:])<.5:
            raise ToolExecutionError('Real compression contact did not raise leaf angle')
    else:raise ToolExecutionError('Bounded real compression fold did not reach angle')
    if abs(measured()-desired)>3.:raise ToolExecutionError('Compression overshot source fold angle')
    p.act('right','FWD',mm=8.);p.move('right',p.tip('right')+[0,0,.04]);p.move('left',p.tip('left')+[0,0,.04]);p.wait(8)
    log('released-compression-final',base_table=p.contact(base['contact_body'],'table'))
