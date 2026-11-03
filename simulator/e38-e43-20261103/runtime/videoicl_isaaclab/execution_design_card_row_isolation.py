"""Move one actual1mm card out of its row before opening a wide gripper."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def isolate(p,ref,side):
    from .author_clearance import prepare_single_hand
    from .execution_design_cutlery_grasp import orient,plane_section
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_thin_motion import checked_move
    from .engineering_thin_suffix import save_stage
    obj=next(o for o in p.spec['objects']if o['id']==ref['actor'])
    if p.task not in ('E47','E48','E49')or obj.get('engineering_practical_card',{}).get('approximate_thickness_m')!=.001:
        raise ValueError('Explicit practical1mm card row required')
    ramp=p.task=='E47';direction=1. if ramp else -1.;distance=.026 if ramp else .105
    p.stage('card-row-isolation-closed-pusher')
    prepare_single_hand(p.a,side,.98)
    checked_move(p,side,[*p.tip(side)[:2],.94],tolerance=.004)
    orient(p.a,side,np.diag([1.,-1.,-1.]))
    p.act(side,'GRASP')
    for _ in range(14):
        q=p.a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
        if float(np.max(q))<.001:break
        p.act()
    else:raise ToolExecutionError('Row-isolation empty fingers did not physically close')
    initial=p.frame(ref)[0].copy();floor=table_bounds_task(p.a.scene)['top']
    source_x=float(obj['xy'][0]);desired_x=source_x+direction*distance
    bounds=table_bounds_task(p.a.scene)
    if desired_x-float(obj['size'][0])<float(bounds['lower'][0])+.005 or desired_x+float(obj['size'][0])>float(bounds['upper'][0])-.005:
        raise ToolExecutionError('Card row has no supported near-side isolation space')
    original={name:p.frame(dict(actor=name))for name in p.contract['untouched']}
    def guarded():
        rails=p.s.get('execution_design_flip_fixture',{}).get('card_slot_fixtures',{}).get(ref['actor'],[])if ramp else[]
        if not(p.contact(ref['actor'],'table')or any(p.contact(ref['actor'],name)for name in rails)):
            raise ToolExecutionError('Isolated card lost real table/flip-device support')
        for name,(position,rotation)in original.items():
            pos,rot=p.frame(dict(actor=name))
            if np.linalg.norm(pos-position)>.004 or np.linalg.norm(rot-rotation)>.08:
                raise ToolExecutionError('Row isolation moved an unrevealed card')
    tcp=p.tip(side);meshes=[actual_mesh(p.a,side,n)for n in p.a.scene.embodiment.fingers]
    delta_z=floor+.00025-min(float(m[:,2].min())for m in meshes)
    material=material_collision_points_task(p,ref);contact_z=float(material[:,2].mean())
    sections=[]
    for mesh in meshes:
        try:sections.append(plane_section(mesh+[0.,0.,delta_z],contact_z))
        except ValueError:pass
    if not sections:raise ToolExecutionError('Closed finger has no finite card-height push section')
    section=np.concatenate(sections);target=tcp.copy()
    target[0]+=(float(material[:,0].min())-.0015-float(section[:,0].max())if direction>0
                else float(material[:,0].max())+.0015-float(section[:,0].min()))
    target[1]+=initial[1]-float(section[:,1].mean());target[2]+=delta_z
    p.stage('card-row-isolation-side-approach')
    checked_move(p,side,[*tcp[:2],.90],guarded,tolerance=.004)
    checked_move(p,side,[*target[:2],.90],guarded,tolerance=.0008)
    checked_move(p,side,target,guarded,tolerance=.0006)
    # Macro approach residuals can leave the toe above the whole card. Use
    # the measured finite1mm contact band, without a micrometre setpoint.
    def seat_band():
        for _ in range(5):
            lowest=float(p.a.finger_geometry(side)['lowest_z_task_m'])
            if lowest<=floor+.0004:return
            amount=lowest-(floor+.0002)
            if amount<float(p.min_mm)/1000.:
                p.act(side,'UP',mm=p.min_mm);guarded();continue
            p.act(side,'DOWN',mm=amount*1000.);guarded()
        raise ToolExecutionError('Actual pusher toe remained above finite card contact band')
    seat_band()
    def touching():return any(p.contact(ref['actor'],side+'_finger'+str(i))for i in(1,2))
    p.stage('card-row-isolation-contact-push')
    history=[]
    for _ in range(48):
        guarded();pos=p.frame(ref)[0]
        if direction*(pos[0]-source_x)>=distance-.002:break
        seat_band()
        p.act(side,'FWD'if direction>0 else'BACK',mm=4. if touching() else 1.)
        guarded();history.append(float(p.frame(ref)[0][0]))
        if len(history)>=6 and min(history[-6:])>=max(history[-6:])-.001:
            raise ToolExecutionError('Real card did not advance under closed-finger edge push')
    else:raise ToolExecutionError('Actual supported row isolation exceeded bounded travel')
    p.stage('card-row-isolation-empty-retreat')
    checked_move(p,side,p.tip(side)+[0.,0.,.06],guarded,tolerance=.004)
    p.act(side,'RELEASE');guarded()
    save_stage(p.a,'card-row-isolated-'+ref['actor'],dict(actual_displacement_m=(p.frame(ref)[0]-initial).tolist()))
