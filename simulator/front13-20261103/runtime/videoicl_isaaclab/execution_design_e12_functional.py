"""Explicit coarse engineering workflow; native scores remain untouched."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .author_orientation import _axis_angle


def move_point(p,side,ref,target,guard=None,follower=None,tolerance=.008):
    target=np.asarray(target,float);history=[]
    while True:
        if guard:guard()
        point=p.point(ref);error=target-point
        if max(abs(error))<=max(.006,tolerance):return
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        p.act(side,token,mm=min(10.,max(3.,abs(float(error[axis]))*1000)),follower=follower)
        history.append(p.point(ref))
        if len(history)>=8 and max(np.linalg.norm(q-history[-1])for q in history[-8:])<.001:
            raise ToolExecutionError('E12 functional payload waypoint has no actual progress')


def insert(p,name,ref,side,slot_id,rotation,depth,*,resume=False):
    from .execution_design_e12_reference import pin_aperture_diagnostics
    from .realworld_structural_evidence import _basis
    slot=p.s['slots'][str(slot_id)];pin=p.s['pins'][name][0];hole=slot['holes'][0]
    ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);matrix=p.frame(slot['ref'])[1]
    ha,hu,hv=(matrix@x for x in(ha,hu,hv));center=p.body_point(slot['ref'],hole['center_local'])
    control=dict(actor=name,local=pin['tip_local']);guard=lambda:p.require_held(ref,side)
    if not resume:
        high=max(float(p.clearance),float(center[2])+.10)
        p.stage('functional-clear-and-orient-'+name)
        move_point(p,side,control,[*p.point(control)[:2],high],guard)
        p.rotate_actor(name,side,rotation)
        move_point(p,side,control,[*center[:2],high],guard)
        move_point(p,side,control,center+ha*.025,guard)
    p.stage('functional-real-insertion-slot-'+str(slot_id));stalled=0;recoveries=0
    while True:
        guard();rows=pin_aperture_diagnostics(p,name,slot_id)
        guided=min(-row['axial_m']for row in rows)
        if guided>=.0035:break
        lateral=np.mean([row['lateral_m']for row in rows],axis=0)
        correction=-(hu*lateral[0]+hv*lateral[1]);_,current=p.frame({'actor':name})
        axis,angle=_axis_angle(np.asarray(rotation)@current.T)
        before=np.asarray(p.frame({'actor':name})[0]).copy()
        if angle>math.radians(1.5)and min(row['axial_m']for row in rows)>.006:
            i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
            p.act(side,token,degrees=min(10.,max(2.,abs(math.degrees(angle*axis[i])))))
        elif max(abs(correction[:2]))>.00025:
            if guided>0 and recoveries<3:
                p.act(side,'UP',mm=2.);recoveries+=1
            else:
                i=int(np.argmax(abs(correction[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[i][int(correction[i]<0)]
                p.act(side,token,mm=.5)
        else:p.act(side,'DOWN',mm=2. if min(row['axial_m']for row in rows)>.006 else .5)
        guard();after=np.asarray(p.frame({'actor':name})[0])
        stalled=stalled+1 if np.linalg.norm(after-before)<.0001 else 0
        if stalled>=3:
            if recoveries>=3:raise ToolExecutionError('E12 functional insertion has no real material progress')
            p.act(side,'UP',mm=2.);recoveries+=1;stalled=0
    p.a.control_report.setdefault('e12_functional_guides',[]).append(dict(actor=name,slot=slot_id,
        measured_two_pin_depths_m=[-row['axial_m']for row in rows],native_score_unchanged=True))
    if name=='charger_2':
        from .execution_design_e12_reference import release_toe_charger
        release_toe_charger(p,name,ref,side,slot_id)
    else:
        p.act(side,'RELEASE');p.move(side,p.tip(side)+[0,0,.06],tolerance=.006)
    if p.held(ref,side):raise ToolExecutionError('E12 functional charger did not actually release')


def record_result(p):
    from .execution_design_e12_reference import pin_aperture_diagnostics
    state,_=p.snapshot();rows=[]
    for name,slot in zip(p.s['groups']['chargers'],((1,2),(3,4),(1,4))[p.index]):
        pins=pin_aperture_diagnostics(p,name,slot);released=not any(state[name]['grasp'])
        supported=p.contact(name,'strip');inserted=min(-pin['axial_m']for pin in pins)>.001
        rows.append(dict(actor=name,slot=slot,actual_released=released,actual_strip_contact=supported,
            measured_pin_depths_m=[-pin['axial_m']for pin in pins],functional_inserted=inserted,
            functional_pass=bool(released and supported and inserted)))
    result=dict(scope='independent_engineering_only',functional_pass=all(row['functional_pass']for row in rows),
        coarse_workflow=True,native_score_unchanged=True,chargers=rows,
        native_current_conditions=list(getattr(p.c.evaluator,'current_conditions',[])))
    p.a.control_report['front13_functional_acceptance']=result
    return result
