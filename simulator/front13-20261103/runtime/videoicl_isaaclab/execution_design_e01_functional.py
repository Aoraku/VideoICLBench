"""Coarse E01 lid and supported delivery through public robot actions."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def move_tool(p,side,target,guard=None,follower=None,tolerance=.006):
    target=np.asarray(target,float);history=[]
    while True:
        if guard:guard()
        error=target-p.tip(side);distance=float(np.linalg.norm(error))
        if max(abs(error))<=max(.006,tolerance):return
        history.append(distance)
        if len(history)>=9 and distance>=history[-9]-.001:
            raise ToolExecutionError('E01 functional waypoint has no real progress: '+p.a.stage)
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        p.act(side,token,mm=min(25.,max(3.,abs(float(error[axis]))*1000)),follower=follower)


def move_material(p,side,ref,target,guard=None,follower=None,tolerance=.006):
    target=np.asarray(target,float);history=[]
    while True:
        if guard:guard()
        error=target-p.point(ref);distance=float(np.linalg.norm(error))
        if max(abs(error))<=max(.006,tolerance):return
        history.append(distance)
        if len(history)>=9 and distance>=history[-9]-.001:
            raise ToolExecutionError('E01 functional material point has no real progress: '+p.a.stage)
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        p.act(side,token,mm=min(25.,max(3.,abs(float(error[axis]))*1000)),follower=follower)


def _lid_angle(p,package):
    r=p.frame({'actor':'meal_box'})[1].T@p.frame({'actor':package['lid']})[1]
    return math.atan2(float(r[2,1]-r[1,2])/2,float((np.trace(r)-1)/2))


def prestage_open_carton(p):
    """Drag the still-open real carton forward before its final lid closure."""
    from .execution_design_e01_package import _meal_on_tray
    from .execution_design_e01_food import park_empty_other
    if float(p.frame({'actor':'meal_box'})[0][0])>=-.11:return
    park_empty_other(p,'right',{},None);p.stage('functional-open-carton-forward-on-table')
    previous=p.clearance;p.clearance=max(1.12,float(p.tip('right')[2]))
    try:ref,side=p.pickup('meal_box')
    finally:p.clearance=previous
    stale=0
    while float(p.frame({'actor':'meal_box'})[0][0])<-.11:
        p.require_held(ref,side);_meal_on_tray(p);before=float(p.frame({'actor':'meal_box'})[0][0])
        p.act(side,'FWD',mm=25.)
        after=float(p.frame({'actor':'meal_box'})[0][0]);stale=stale+1 if after-before<.001 else 0
        if stale>=3:raise ToolExecutionError('E01 open carton supported drag has no actual progress')
    p.act(side,'RELEASE');p.move(side,p.tip(side)+[0,0,.07],tolerance=.008)
    if not p.contact('meal_box','table'):raise ToolExecutionError('E01 forward carton lacks actual table support')


def close_lid(p):
    from .execution_design_e01_package import _state
    from .execution_design_e01_food import park_empty_other
    state=_state(p);package=next(q for q in p.d['packages']if q['container']=='meal_box')
    side='right'if p.frame({'actor':'meal_box'})[0][1]<0 else'left'
    park_empty_other(p,side,{},None);p.max_mm=float(p.a.scene.embodiment.config['control']['step_mm'][1])
    name=package['lid'];ref=dict(actor=name,local=[0.,float(p.objects[name]['size'][1])-.010,0.],jaw_axis_local=[0,0,1])
    fingers=p.a.finger_geometry(side)['fingers'];axis=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
    normal=p.frame(ref)[1][:,2]
    if axis@normal<0:ref['jaw_axis_local']=[0,0,-1];normal=-normal
    p.stage('functional-original-lid-free-edge-acquire');p.act(side,'RELEASE')
    high=max(float(p.tip(side)[2]),float(p.point(ref)[2])+.06)
    p.move(side,np.r_[p.tip(side)[:2],high],tolerance=.008)
    p.a.align_gripper_axis(side,normal)
    p.move(side,np.r_[p.point(ref)[:2],high],tolerance=.008)
    p.move(side,p.point(ref),tolerance=.006)
    for _ in range(5):
        p.act(side,'GRASP')
        if p.held(ref,side):break
    else:raise ToolExecutionError('E01 functional lid free edge lacks a real hold')
    # The original lid leans outward at100°. Bring it just past vertical;
    # the unchanged passive hinge and gravity finish closure after release.
    joint=p.spec['joints'][package['hinge_joint_index']]
    p.stage('functional-lid-past-vertical')
    while _lid_angle(p,package)>math.radians(85):
        if not p.held(ref,side):break
        base,r=p.frame({'actor':'meal_box'});desired=r@_axis_rotation([1,0,0],math.radians(80))
        goal=base+r@np.asarray(joint['anchor0'])+desired@(np.asarray(ref['local'])-np.asarray(joint['anchor1']))
        error=goal-p.point(ref);i=int(np.argmax(abs(error)))
        if max(abs(error))<.010:break
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[i][int(error[i]<0)]
        p.act(side,token,mm=min(40.,max(5.,abs(float(error[i]))*1000)))
    p.act(side,'RELEASE');p.move(side,p.tip(side)+[0,0,.07],tolerance=.008)
    state['phase']='lid_released'
    p.a.control_report['e01_functional_lid']=dict(original_hinge=True,
        actual_angle_degrees=math.degrees(_lid_angle(p,package)),extra_stability_waits=0)
    return dict(local_completed=True,phase=state['phase'],whole_task_score=None)


def deliver(p):
    from .execution_design_e01_package import _state,_meal_on_tray
    from .execution_design_e01_food import park_empty_other
    from .execution_design_e33_grasp import actual_mesh
    state=_state(p)
    if state['phase']not in('loaded','lid_released','closed','delivered'):
        raise ToolExecutionError('E01 functional delivery needs its physical loaded carton')
    side='right'if p.frame({'actor':'meal_box'})[0][1]<0 else'left'
    park_empty_other(p,side,{},None);p.max_mm=float(p.a.scene.embodiment.config['control']['step_mm'][1])
    zone=next(z for z in p.spec['zones']if z['id']==p.d['destination_zone'])
    p.stage('functional-supported-carton-side-push');p.act(side,'GRASP')
    tip=p.tip(side);parts=[actual_mesh(p.a,side,name)for name in('panda_hand',*p.a.scene.embodiment.fingers)]
    cloud=np.concatenate(parts);offset=cloud-tip;fingers=np.concatenate(parts[1:])-tip
    base,r=p.frame({'actor':'meal_box'});box=p.objects['meal_box'];half=abs(r)@np.asarray(box['size'])
    high=max(float(tip[2]),float(base[2]+half[2])+.03-float(offset[:,2].min()))
    outside=float(base[0]-half[0]-offset[:,0].max()-.004)
    push_z=max(float(base[2])-.01-float(fingers[:,2].mean()),.806-float(offset[:,2].min()))
    p.move(side,np.r_[tip[:2],high],tolerance=.008)
    p.move(side,[outside,float(base[1]),high],tolerance=.008)
    p.move(side,[outside,float(base[1]),push_z],tolerance=.008)
    stale=0
    while float(p.frame({'actor':'meal_box'})[0][0])<float(zone['xy'][0])-.015:
        before=p.frame({'actor':'meal_box'})[0].copy();_meal_on_tray(p)
        if before[2]<.8:raise ToolExecutionError('E01 functional carton actually fell from table')
        p.act(side,'FWD',mm=20.)
        after=p.frame({'actor':'meal_box'})[0]
        stale=stale+1 if after[0]-before[0]<.001 else 0
        if stale>=4:raise ToolExecutionError('E01 functional carton push has no real progress')
    p.act(side,'RELEASE');p.move(side,p.tip(side)+[-.07,0,.05],tolerance=.008)
    state['phase']='delivered';snapshot,_=p.snapshot();base,r=p.frame({'actor':'meal_box'})
    cargo=[]
    for name in ['tray',*p.d['target_members']]:
        local=r.T@(np.asarray(snapshot[name]['pos'])-base)
        inside=bool(np.all(abs(local[:2])<np.asarray(box['size'])[:2]+.03)and local[2]>-float(box['size'][2])-.03)
        cargo.append(dict(actor=name,center_in_original_box=inside,actual_released=not any(snapshot[name]['grasp'])))
    package=next(q for q in p.d['packages']if q['container']=='meal_box')
    angle=abs(math.degrees(_lid_angle(p,package)));destination=bool(np.all(abs(base[:2]-np.asarray(zone['xy']))<np.asarray(zone['half_size'])))
    result=dict(scope='independent_engineering_only',coarse_workflow=True,native_score_unchanged=True,
        functional_pass=bool(all(q['center_in_original_box']and q['actual_released']for q in cargo)
            and p.contact('meal_box','table')and destination and angle<20),cargo=cargo,
        actual_table_contact=p.contact('meal_box','table'),requested_destination_center_reached=destination,
        actual_lid_angle_degrees=angle,native_current_conditions=list(getattr(p.c.evaluator,'current_conditions',[])))
    p.a.control_report['front13_functional_acceptance']=result
    if not result['functional_pass']:raise ToolExecutionError('E01 coarse shipment has not physically completed')
    return dict(local_completed=True,functional_pass=True,functional_acceptance=result,whole_task_score=None)


def complete_shipment(p):
    from .execution_design_e01_package import _state
    from .execution_design_e01_balance import _coarse,complete_balanced_load
    if not _coarse(p):raise ToolExecutionError('Explicit E01 functional engineering mode required')
    if _state(p)['phase']=='load_tray':complete_balanced_load(p)
    if _state(p)['phase']=='loaded':prestage_open_carton(p);close_lid(p)
    return deliver(p)
