"""Actual supported card push into the measured free gap between existing plates."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def clear_plate_rim(p,ref,side='left',resume_pusher=False):
    from .author_clearance import prepare_single_hand
    from .execution_design_cutlery_grasp import orient,plane_section
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_thin_motion import checked_move
    from .engineering_thin_suffix import save_stage
    if p.task!='E50'or not p.spec['semantic'].get('engineering_card_approximation'):
        raise ValueError('Explicit practical E50 engineering required')
    plates={o['id']:p.frame(dict(actor=o['id']))for o in p.spec['objects']if o.get('source_asset',{}).get('relative_path')=='plate.usda'}
    xs=sorted(float(pos[0])for pos,rot in plates.values());initial=p.frame(ref)[0].copy()
    pairs=[(a,b)for a,b in zip(xs,xs[1:])if a<initial[0]<b]
    if not pairs:raise ToolExecutionError('Existing plates do not provide a measured side gap')
    source_x=float(next(o for o in p.spec['objects']if o['id']==ref['actor'])['xy'][0])
    desired=max(sum(pairs[0])/2+.001,source_x+.026)
    if not -.001<=desired-initial[0]<=.035:raise ToolExecutionError('E50 clearance must be the supported25mm gap move')
    floor=table_bounds_task(p.a.scene)['top']
    def guarded():
        if not p.contact(ref['actor'],'table'):raise ToolExecutionError('Card lost table support during actual plate clearance')
        for name,(pos,rot)in plates.items():
            actual,r=p.frame(dict(actor=name))
            if np.linalg.norm(actual-pos)>.004 or np.linalg.norm(r-rot)>.08:raise ToolExecutionError('Plate moved during card clearance')
    gap_x=sum(pairs[0])/2
    def cleared():
        pos=p.frame(ref)[0]
        return (abs(float(pos[0])-gap_x)<=.002 and float(pos[0])-source_x>=.020
                and not any(p.contact(ref['actor'],name)for name in plates))
    old_max_mm=p.max_mm;p.max_mm=min(25.,float(p.a.scene.embodiment.config['control']['step_mm'][1]))
    if cleared():
        # An achieved free gap is the purpose of this waypoint. Preserve the
        # measured24.4mm prefix rather than chasing a nominal25/26mm number.
        p.stage('e50-plate-gap-achieved-empty-retreat');guarded()
        tcp=p.tip(side);material=material_collision_points_task(p,ref)
        meshes=[actual_mesh(p.a,side,n)for n in p.a.scene.embodiment.fingers]
        safe_x=float(material[:,0].min())-.004-max(float(m[:,0].max()-tcp[0])for m in meshes)
        checked_move(p,side,[safe_x,tcp[1],tcp[2]],guarded,tolerance=.001)
        checked_move(p,side,p.tip(side)+[0.,0.,.06],guarded,tolerance=.004)
        p.act(side,'RELEASE');guarded()
        total=float(p.frame(ref)[0][0]-source_x)
        save_stage(p.a,'e50-card-cleared-plate-rim',dict(actual_x_displacement_from_task_initial_m=total,measured_plate_gap_error_m=float(p.frame(ref)[0][0])-gap_x,plates_preserved=True))
        p.max_mm=old_max_mm;return 0.
    if not resume_pusher:
        p.stage('e50-clear-plate-closed-pusher');prepare_single_hand(p.a,side,.98)
        # prepare_single_hand is intentionally opt-in and may be a no-op. This
        # actual empty-space retreat must precede closing near an old grasp pose.
        checked_move(p,side,[*p.tip(side)[:2],.98],guarded,tolerance=.004)
        orient(p.a,side,np.diag([1.,-1.,-1.]));p.act(side,'GRASP')
        for _ in range(14):
            if float(p.a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].max())<.001:break
            p.act()
        else:raise ToolExecutionError('E50 empty pusher did not physically close')
        tcp=p.tip(side);meshes=[actual_mesh(p.a,side,n)for n in p.a.scene.embodiment.fingers]
        dz=floor+.00025-min(float(m[:,2].min())for m in meshes)
        material=material_collision_points_task(p,ref);z=float(material[:,2].mean());sections=[]
        for mesh in meshes:
            try:sections.append(plane_section(mesh+[0.,0.,dz],z))
            except ValueError:pass
        if not sections:raise ToolExecutionError('Actual closed finger has no card-height edge')
        section=np.concatenate(sections);target=tcp.copy()
        target[0]+=float(material[:,0].min())-.0015-float(section[:,0].max())
        target[1]+=initial[1]-.005-float(section[:,1].mean());target[2]+=dz
        p.stage('e50-clear-plate-left-side-approach')
        checked_move(p,side,[*tcp[:2],.98],guarded,tolerance=.004)
        checked_move(p,side,[*target[:2],.98],guarded,tolerance=.004)
        checked_move(p,side,target,guarded,tolerance=.0006)
    elif float(p.a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].max())>.001 or p.held(ref,side):
        raise ToolExecutionError('Pusher resume requires actual empty closed fingers')
    # The public macro target can retain a submillimetre tracking residual.
    # Retire left of the whole finger, enter the measured1mm side band, then
    # recompute the real finite pushing section at the achieved pose.
    p.stage('e50-clear-plate-actual-side-band')
    tcp=p.tip(side);meshes=[actual_mesh(p.a,side,n)for n in p.a.scene.embodiment.fingers]
    material=material_collision_points_task(p,ref)
    safe_x=float(material[:,0].min())-.004-max(float(m[:,0].max()-tcp[0])for m in meshes)
    checked_move(p,side,[safe_x,tcp[1],tcp[2]],guarded,tolerance=.001)
    for _ in range(3):
        lowest=float(p.a.finger_geometry(side)['lowest_z_task_m'])
        contact_z=float(material_collision_points_task(p,ref)[:,2].mean())
        if lowest<=contact_z-.00015:break
        p.act(side,'DOWN',mm=max(.5,(lowest-floor-.00025)*1000));guarded()
    else:raise ToolExecutionError('Actual pusher remained above the1mm card side')
    material=material_collision_points_task(p,ref);z=float(material[:,2].mean());sections=[]
    for name in p.a.scene.embodiment.fingers:
        try:sections.append(plane_section(actual_mesh(p.a,side,name),z))
        except ValueError:pass
    if not sections:raise ToolExecutionError('Actual closed finger has no achieved card-height section')
    section=np.concatenate(sections);tcp=p.tip(side);target=tcp.copy()
    target[0]+=float(material[:,0].min())-.0015-float(section[:,0].max())
    target[1]+=p.frame(ref)[0][1]-.005-float(section[:,1].mean())
    checked_move(p,side,target,guarded,tolerance=.0006)
    save_stage(p.a,'e50-actual-pusher-side-ready',dict(lowest_z_m=float(p.a.finger_geometry(side)['lowest_z_task_m'])))
    history=[];p.stage('e50-clear-plate-actual-push')
    for _ in range(32):
        guarded();x=float(p.frame(ref)[0][0])
        if cleared():break
        low=float(p.a.finger_geometry(side)['lowest_z_task_m'])
        if low>floor+.00035:
            p.act(side,'DOWN',mm=max(.5,(low-floor-.00025)*1000));guarded()
        touching=any(p.contact(ref['actor'],f'{side}_finger{i}')for i in(1,2))
        p.act(side,'FWD',mm=min(4.,max(1.,(desired-x)*1000))if touching else 1.)
        guarded();history.append(float(p.frame(ref)[0][0]))
        if len(history)>=6 and max(history[-6:])-min(history[-6:])<.001:raise ToolExecutionError('Actual E50 card did not advance under edge push')
    else:raise ToolExecutionError('Supported E50 plate clearance exceeded bounded travel')
    checked_move(p,side,p.tip(side)+[0.,0.,.06],guarded,tolerance=.004)
    p.act(side,'RELEASE');guarded()
    moved=float(p.frame(ref)[0][0]-initial[0])
    total_moved=float(p.frame(ref)[0][0]-source_x)
    if not cleared():raise ToolExecutionError('Card has not actually cleared existing plate rim')
    save_stage(p.a,'e50-card-cleared-plate-rim',dict(actual_x_displacement_m=moved,actual_x_displacement_from_task_initial_m=total_moved,plates_preserved=True))
    p.max_mm=old_max_mm
    return moved
