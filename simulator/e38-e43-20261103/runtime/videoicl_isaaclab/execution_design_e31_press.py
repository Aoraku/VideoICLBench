"""Private E31 real fingertip support while the original hand lets go.

The second hand presses from above; no synthetic grasp, weld or state update.
Only public motion and the existing physical gripper motor target are used.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np


def support_and_release(a,parameters=None):
    parameters=parameters or {};spec=a.scene.spec
    if not(getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
           and spec['variant']in('B','C')and spec['seed']==4201
           and spec.get('execution_design',{}).get('condition')=='I'):
        raise ValueError('Explicit I E31 held-plate engineering support required')
    from .engineering_checkpoint import capture
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_e31_release import check_actual_limits
    name=spec['semantic']['plate'];bowl=spec['semantic']['bowl'];left='left';right='right'
    report=dict(diagnostic_only=True,source_initial_positive_claimed=False,trace=[])
    out=Path(a.out);floor=float(table_bounds_task(a.scene)['top']);right_free=False
    def write():
        (out/'e31-real-press-support.private.json').write_text(json.dumps(report,indent=2,
            default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n')
    def force(actor,body):return float(a.c.contact_forces.get(frozenset((actor,body)),0.))
    def pads(side):return [force(name,side+'_finger'+str(i))for i in(1,2)]
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    view=SimpleNamespace(a=a,frame=frame)
    state,_=a.c.snapshot();bowl_initial=np.asarray(state[bowl]['pos']).copy()
    def guard(require_right=True):
        state,contacts=a.c.snapshot();plate=state[name]
        reader=getattr(a,'_e31_native_contact_reader',None)
        if reader is not None:
            hits={key:value for key,value in reader['current_forces_n'].items()
                  if value is not None and value>1. and(key.startswith('robot_table/')or key.startswith('bowl/'))}
            if hits:raise RuntimeError('Real top support contacted robot/table or receiving bowl: '+str(hits))
        if require_right and (not plate['grasp'][1]or min(pads(right))<=.001):
            raise RuntimeError('Real original right pinch required until supported release')
        if float(plate['mat'][2,2])>-.20:raise RuntimeError('Physical lid face left the down hemisphere during support')
        if np.linalg.norm(np.asarray(state[bowl]['pos'])-bowl_initial)>.005:
            raise RuntimeError('Receiving bowl moved during real press support')
        if any(force(bowl,s+'_finger'+str(i))>.001 for s in(left,right)for i in(1,2)):
            raise RuntimeError('Support fingers contacted receiving bowl')
        for s in(left,right):check_actual_limits(a,s)
        return state,contacts
    def meshes(side):return {n:actual_mesh(a,side,n)for n in('panda_hand',*a.scene.embodiment.fingers)}
    def geometry(side,target):
        tip=np.asarray(a.tip(side));own=meshes(side);peer=right if side==left else left
        obstacles={bowl:collision_parts_task(view,bowl)}
        for body in a.scene.robots[peer].body_names:
            try:obstacles[peer+'_'+body]=[actual_mesh(a,peer,body)]
            except ValueError:continue
        swept_pose_clearance(own,tip,target,np.eye(3),obstacles,floor,margin=.001)
        swept_pose_clearance({'palm':own['panda_hand']},tip,target,np.eye(3),
            {name:collision_parts_task(view,name)},floor,margin=.0005)
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    def pulse(side,axis,distance,require_right=True):
        guard(require_right);tip=np.asarray(a.tip(side));mm=float(np.clip(abs(distance)*1000,.5,8.))
        proposed=tip.copy();proposed[axis]+=np.sign(distance)*mm/1000;geometry(side,proposed)
        token=labels[axis][0 if np.sign(distance)==a.generated_axis_signs[side][axis]else 1]
        a.act(token if side==left else'STILL',token if side==right else'STILL',mm)
        guard(require_right)
    def move(side,target,require_right=True,tol=.004):
        history=[]
        for _ in range(200):
            target=np.asarray(target()if callable(target)else target,float);delta=target-a.tip(side)
            if np.max(abs(delta))<=tol:return
            history.append(float(np.linalg.norm(delta)))
            if len(history)>20 and min(history[-20:-10])-min(history[-10:])<.001:
                raise RuntimeError('Actual support waypoint did not progress')
            axis=int(np.argmax(abs(delta)));pulse(side,axis,float(delta[axis]),require_right)
        raise RuntimeError('Actual support public waypoint bound')
    def save(stage):
        cp=capture(a.c,stage,context=dict(local_debug_only=True,carried_payload=[name,right]if not right_free else None))
        path=out/('e31-press-'+stage+'.checkpoint.private.json');path.write_text(json.dumps(cp,indent=2)+'\n')
        report['trace'].append(dict(stage=stage,steps=a.c.steps,checkpoint=str(path)));write()
    def point_clouds():
        return dict(plate=material_collision_points_task(view,{'actor':name}),
            bowl=material_collision_points_task(view,{'actor':bowl}),left=meshes(left),right=meshes(right))
    try:
        guard();save('start');report['source_actual_meshes']=point_clouds();write()
        if parameters.get('existing_real_support') is True:
            if max(pads(left))<=.01:raise RuntimeError('Existing native left material contact required')
            geometry(left,np.asarray(a.tip(left)))
        else:
            if parameters.get('resume_stage')!='top_contact':
                a.stage='e31-left-support-clear-above';move(left,[*a.tip(left)[:2],1.08])
                a.act('GRASP','STILL');guard()
                a.stage='e31-left-support-over-back'
                move(left,lambda:np.r_[a.c.snapshot()[0][name]['pos'][:2],1.08])
            a.stage='e31-left-support-real-top-contact'
            for _ in range(100):
                state,_=guard();plate=state[name]
                if max(pads(left))>.01:break
                xy=np.asarray(plate['pos'])[:2]-np.asarray(a.tip(left))[:2]
                if np.max(abs(xy))>.005:
                    axis=int(np.argmax(abs(xy)));pulse(left,axis,float(xy[axis]));continue
                finger=np.concatenate([actual_mesh(a,left,n)for n in a.scene.embodiment.fingers])
                pp=material_collision_points_task(view,{'actor':name})
                local_xy=np.linalg.norm(pp[:,:2]-np.asarray(plate['pos'])[:2],axis=1)<.030
                if not local_xy.any():raise RuntimeError('Actual central back material required')
                gap=float(finger[:,2].min()-pp[local_xy,2].max())
                # Different XY extrema are not a material intersection. The
                # real contact sensor is the stop; exact palm/peer/bowl swept
                # geometry is checked before every further public descent.
                pulse(left,2,-(.002 if gap<0 else min(.004,max(.0005,gap))))
            else:raise RuntimeError('Actual plate back contact not reached')
        report['press_contact']=dict(steps=a.c.steps,left_forces_n=pads(left),plate=guard()[0][name],meshes=point_clouds());save('top-supported-before-right-release')
        if parameters.get('stop_after_top_contact')is True:
            report.update(diagnostic_only=True,source_initial_positive_claimed=False,
                segment='actual-left-top-material-contact',segment_passed=max(pads(left))>.01,
                not_task_acceptance=True)
            write();return report
        if parameters.get('short_supported_release')is True:
            from .execution_design_e31_supported_separate import run as separate
            report['right_separation']=separate(a,{'left_top_support':True})
            right_free=True;a.carried_payload=None;save('actual-right-separated-left-supported')
            a.stage='e31-top-support-left-empty-lift'
            for _ in range(12):
                reader=getattr(a,'_e31_native_contact_reader',None)
                values={key:value for key,value in reader['current_forces_n'].items()if key.startswith(name+'/left/')}
                if values and all(value is not None and value<=.001 for value in values.values()):break
                pulse(left,2,.004,require_right=False)
            else:raise RuntimeError('Actual left top finger did not separate on short upward withdrawal')
            for _ in range(2):a.act();guard(False)
            report.update(segment_complete=True,final_plate=a.c.snapshot()[0][name],
                final_pad_forces_n={s:pads(s)for s in(left,right)},
                actual_bowl_plate_contact=frozenset((name,bowl))in a.c.snapshot()[1])
            save('complete');return report
        a.stage='e31-supported-real-right-release'
        robot=a.scene.robots[right];ids=a.c.ids[right][1]
        raw=robot.data.joint_pos[0,ids];initial_open=float(np.asarray(raw.detach().cpu().numpy()).max())
        for extra in(.001,.002,.003,.005,.008,.012,.020,.040):
            a.c.grips[right]=min(.04,initial_open+extra)
            for _ in range(2):a.act();guard(require_right=False)
            if not a.c.snapshot()[0][name]['grasp'][1]and max(pads(right))<=.001:
                right_free=True;a.carried_payload=None;break
        if not right_free:raise RuntimeError('Supported plate did not physically leave original right pinch')
        save('right-released-left-contact')
        a.stage='e31-supported-right-retreat'
        state,_=guard(False);direction=np.asarray(a.tip(right))-np.asarray(state[name]['pos']);direction/=np.linalg.norm(direction)
        direction[2]=max(0.,direction[2]);direction/=np.linalg.norm(direction)
        move(right,np.asarray(a.tip(right))+.12*direction,False)
        a.act('STILL','RELEASE');guard(False);save('right-clear')
        a.stage='e31-left-support-lower-to-real-bowl'
        for _ in range(100):
            state,contacts=guard(False)
            if frozenset((name,bowl))in contacts:break
            xy=np.asarray(state[bowl]['pos'])[:2]-np.asarray(state[name]['pos'])[:2]
            if np.max(abs(xy))>.012:
                axis=int(np.argmax(abs(xy)));pulse(left,axis,float(xy[axis]),False)
            else:pulse(left,2,-.003,False)
        else:raise RuntimeError('Actual supported plate did not reach bowl')
        save('real-bowl-contact-before-left-retreat');a.stage='e31-left-support-empty-retreat'
        move(left,np.asarray(a.tip(left))+[0,0,.12],False)
        a.act('RELEASE','STILL');a.act();a.act();guard(False)
        state,contacts=a.c.snapshot();report.update(segment_complete=True,
            final_plate=state[name],final_pad_forces_n={s:pads(s)for s in(left,right)},
            actual_bowl_plate_contact=frozenset((name,bowl))in contacts)
        save('complete');return report
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc);write();raise
