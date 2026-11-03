"""Optional engineering thin-card surface slide using ordinary public actions.

This route has no dispatch hook and no native success claim. It preserves all
source contact coefficients; native material friction and actual displacement,
rather than a GRASP contact bit, decide whether surface sliding is feasible.
"""
import json
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .realworld_tool_expert import ToolExecutionError


def slide(p,ref,side,outward,distance_m):
    from .execution_design_public_precision_orientation import orient
    from .execution_design_thin_motion import checked_move
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
    from .execution_design_e33_grasp import actual_mesh
    a=p.a;design=p.spec.get('execution_design',{})
    if p.task not in ('E47','E48','E49','E50')or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)or not a.control_report.get('engineering_reference_only'):
        raise ValueError('Explicit source-checked thin-card engineering required')
    direction=np.asarray(outward,float);distance=float(distance_m)
    if direction.shape!=(3,)or not np.isfinite(direction).all()or abs(direction[2])>1e-9 or abs(direction[0])!=1 or abs(direction[1])>1e-9 or not .005<=distance<=.3:
        raise ValueError('Bounded task-X card surface slide required')
    floor=table_bounds_task(a.scene)['top'];initial=p.frame(ref)[0].copy()
    preserved={name:p.frame(dict(actor=name))for name in p.s.get('preserve_unrevealed',())}
    def guard():
        if not p.contact(ref['actor'],'table'):raise ToolExecutionError('Surface-slide card lost real table support')
        for name,(pos,rotation)in preserved.items():
            actual,mat=p.frame(dict(actor=name))
            if np.linalg.norm(actual-pos)>.004 or np.linalg.norm(mat-rotation)>.08:
                raise ToolExecutionError('Surface slide disturbed an unrevealed card')
    def forces():
        p.snapshot()
        return {str(i):float(p.c.contact_forces.get(frozenset((ref['actor'],side+'_finger'+str(i))),0.))for i in(1,2)}
    def log(phase,**values):
        with(a.out/'card-surface-slide.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(phase=phase,step=p.c.steps,card_position=p.frame(ref)[0].tolist(),tcp=p.tip(side).tolist(),actual_card_finger_forces_n=forces(),**values))+'\n')
    p.stage('card-surface-empty-clear')
    checked_move(p,side,p.tip(side)+[0.,0.,.025],guard,tolerance=.002)
    orient(a,side,np.diag([1.,-1.,-1.]))
    p.act(side,'GRASP')
    for _ in range(12):
        q=a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
        if float(np.max(q))<.001:break
        p.act()
    else:raise ToolExecutionError('Empty surface-pusher fingers did not actually close')
    fingers=np.concatenate([actual_mesh(a,side,n)for n in a.scene.embodiment.fingers])
    low=fingers[fingers[:,2]<=fingers[:,2].min()+.0003].mean(0)
    card=p.frame(ref)[0];material=material_collision_points_task(p,ref)
    target=p.tip(side)+(card-low);target[2]+=float(material[:,2].max()-card[2])+.001
    height=max(float(p.tip(side)[2]),floor+.08)
    p.stage('card-surface-center-approach')
    checked_move(p,side,[*p.tip(side)[:2],height],guard,tolerance=.002)
    checked_move(p,side,[*target[:2],height],guard,tolerance=.001)
    checked_move(p,side,target,guard,tolerance=.0002)
    p.stage('card-surface-real-top-contact')
    for _ in range(8):
        if all(value>.001 for value in forces().values()):break
        lowest=float(a.finger_geometry(side)['lowest_z_task_m'])
        if lowest-.0005<floor+.00002:
            raise ToolExecutionError('No actual top contact before source table-clearance boundary')
        p.act(side,'DOWN',mm=.5);guard();log('seek-symmetric-top-contact')
    else:raise ToolExecutionError('No symmetric native card top contact')
    log('actual-top-contact',note='Contact is a pushing state; not a lifted grasp')
    history=[];token='FWD'if direction[0]>0 else'BACK'
    for _ in range(80):
        guard();advance=float((p.frame(ref)[0]-initial)@direction)
        if advance>=distance:
            log('actual-slide-distance',actual_displacement_m=advance);return advance
        if not any(value>.001 for value in forces().values()):
            raise ToolExecutionError('Surface pusher lost actual card contact')
        p.stage('card-surface-real-horizontal-push')
        p.act(side,token,mm=min(p.max_mm,max(p.min_mm,(distance-advance)*1000.)))
        guard();advance=float((p.frame(ref)[0]-initial)@direction);history.append(advance);log('real-surface-slide',actual_displacement_m=advance)
        if len(history)>=4 and history[-1]-history[-4]<.0005:
            raise ToolExecutionError('Actual card did not slide under surface friction')
    raise ToolExecutionError('Bounded real card surface slide did not reach requested distance')
