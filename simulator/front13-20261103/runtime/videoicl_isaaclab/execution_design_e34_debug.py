"""Local E34C acquisition repair from a reconstructed engineering state.

Motor targets and public actions only. This stage is never fixed36 acceptance.
"""
import json,math
from pathlib import Path
import numpy as np

from .execution_design_e34_reference import scope, pad_capture


def boxes_overlap(a_lo, a_hi, b_lo, b_hi, margin=.001):
    return bool(np.all(np.asarray(a_hi)+margin >= np.asarray(b_lo))
                and np.all(np.asarray(a_lo)-margin <= np.asarray(b_hi)))


def preview_clearance(meshes, translation, obstacles, margin=.001):
    """Check separate native collision pieces; a utensil AABB is not material."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    delta=np.asarray(translation,float)
    for mesh in meshes:
        moved=np.asarray(mesh,float)+delta
        if not np.isfinite(moved).all():raise ValueError('Finite native hand mesh required')
        lo,hi=moved.min(0),moved.max(0)
        hand_hull=None
        for name,parts in obstacles.items():
            for part in parts:
                part=np.asarray(part,float)
                if part.ndim!=2 or part.shape[1]!=3 or len(part)<4 or not np.isfinite(part).all():
                    raise ValueError('Complete native obstacle collision piece required')
                if not boxes_overlap(lo,hi,part.min(0),part.max(0),margin=2*margin):continue
                if hand_hull is None:hand_hull=ConvexHull(moved,qhull_options='QJ')
                hull=ConvexHull(part,qhull_options='QJ')
                equations=np.r_[hand_hull.equations,hull.equations]
                separated=linprog([0.,0.,0.],A_ub=equations[:,:3],
                    b_ub=-equations[:,3]+margin,bounds=[(None,None)]*3,method='highs')
                if separated.success:return False,name
                if separated.status!=2:raise RuntimeError('Native cutlery collision separation unresolved')
    return True,None


def deep_capture(point,meshes,floor,depth=.003):
    if not pad_capture(point,meshes,floor):return False
    z=float(np.asarray(point)[2])
    return all(z-float(np.asarray(m)[:,2].min())>=depth for m in meshes)


def run(author,payload):
    a=author;scope(a);spec=a.scene.spec
    if spec.get('variant')!='C' or spec['execution_design'].get('condition')!='I':
        raise ValueError('Local debug is confined to E34C I')
    stage=payload.get('stage','acquire')
    if stage=='balanced_acquire':
        from .execution_design_e34_balanced_grasp import run_debug
        return run_debug(a,payload)
    if stage=='release':return release_only(a,payload)
    if stage=='verify_final':return verify_final(a,payload)
    if stage=='yaw_departure_probe':
        from .execution_design_e34_departure_debug import run as departure_probe
        return departure_probe(a,payload)
    if stage=='from_grasp':
        from .execution_design_e34_tail import finish_from_grasp
        return finish_from_grasp(a,a.scene.spec['semantic']['selected'],payload.get('side','left'))
    if stage in ('carry_place','level_place','place_only'):return carry_place(a,payload)
    if stage not in ('acquire','lift'):raise ValueError('Unknown E34C local stage')
    side=payload.get('side','left');assert side in ('left','right')
    target='fork';side_index=0 if side=='left'else 1
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_cutlery_grasp import sectional_target
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_branch_geometry import collision_parts_task
    from types import SimpleNamespace
    floor=float(table_bounds_task(a.scene)['top'])
    objects={o['id']:o for o in spec['objects']};obj=objects[target]
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    signs=getattr(a,'generated_axis_signs',{}).get(side,{})
    fingers=(f'{side}_finger1',f'{side}_finger2')
    trace=[];out=Path(a.out)/'e34-local-acquire.private.json'
    report=dict(local_debug_only=True,fixed36_positive=False,stage=stage,side=side,
        initial_state=payload.get('source',payload.get('origin')),trace=trace,passed=False)

    def snapshot():return a.c.snapshot()
    def write():out.write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n')
    def force(one,two):return float(getattr(a.c,'contact_forces',{}).get(frozenset((one,two)),0.))
    def pulse(token,mm=5.):
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm)
    def move(goal,tolerance=.0015):
        goal=np.asarray(goal,float);errors=[]
        for _ in range(96):
            e=goal-np.asarray(a.tip(side));err=float(np.max(abs(e)))
            if err<=tolerance:return
            errors.append(float(np.linalg.norm(e)))
            if len(errors)>=24 and min(errors[-24:-16])-min(errors[-8:])<.0004:
                raise RuntimeError('E34 local acquisition waypoint stalled')
            axis=int(np.argmax(abs(e)));direction=1 if e[axis]>0 else -1
            token=labels[axis][0 if direction==signs.get(axis,1)else 1]
            pulse(token,min(15.,max(3.,abs(e[axis])*1000)))
            if baseline is not None:untouched()
        raise RuntimeError('E34 local acquisition motion bound exhausted')
    baseline=None
    geometry_policy=SimpleNamespace(a=a,frame=lambda binding:(
        np.asarray(snapshot()[0][binding['actor']]['pos']),
        np.asarray(snapshot()[0][binding['actor']]['mat'])))
    def untouched():
        state,_=snapshot()
        for name,old in baseline.items():
            body=state[name]
            if any(body['grasp']) or np.linalg.norm(np.asarray(body['pos'])-old['pos'])>.002 or np.linalg.norm(np.asarray(body['mat'])-old['mat'])>.03:
                raise RuntimeError('E34 local debug moved unselected object: '+name)
            if any(force(name,f)>.001 for f in fingers):
                raise RuntimeError('E34 local debug hand contacted unselected object: '+name)
    try:
        state,_=snapshot()
        if stage=='lift':
            if not state[target]['grasp'][side_index]:raise RuntimeError('Lift checkpoint did not retain actual fork grasp')
            if any(any(body['grasp'])for name,body in state.items()if name!=target):raise RuntimeError('Unexpected held object in lift checkpoint')
            baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=target}
            untouched()
        else:
            if any(any(b['grasp'])for b in state.values()):raise RuntimeError('Acquisition reconstruction must start empty-handed')
            a.carried_payload=None;a.stage='debug-e34c-clear-neighbor'
            meshes=[actual_mesh(a,side,n)for n in ['panda_hand',*a.scene.embodiment.fingers]]
            tcp=np.asarray(a.tip(side));radius=max(float(np.linalg.norm(m-tcp,axis=1).max())for m in meshes)
            tops=[floor]
            for name,body in state.items():
                o=objects[name];center=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(o.get('local_bounds_center',[0,0,0]))
                extent=np.abs(body['mat'])@np.asarray(o.get('bounds_half_extent',o['size']));tops.append(float(center[2]+extent[2]))
            safe_z=max(float(tcp[2])+.065,max(tops)+radius+.020)
            move([*tcp[:2],safe_z],tolerance=.003)
            for _ in range(2):a.act()
            state,_=snapshot()
            if any(force(name,f)>.001 for name in objects if name!=target for f in fingers):
                raise RuntimeError('E34 local empty hand has not cleared neighboring material')
            baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=target}
            chosen=None
            for opening in (.015,.018):
                a.stage='debug-e34c-narrow-preopening';a.c.grips[side]=opening
                trace.append(dict(step=a.c.steps,control='private_pre_grasp_opening',per_finger_motor_target_m=opening,joint_state_written=False))
                for _ in range(2):a.act()
                state,_=snapshot();untouched();body=state[target]
                point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
                tcp=np.asarray(a.tip(side));rotation=np.asarray(a.tcp_rotation_task(side));palm=actual_mesh(a,side,'panda_hand');pad_meshes=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
                pose=sectional_target(point,tcp,rotation,rotation,palm,pad_meshes,floor)
                obstacles={name:collision_parts_task(geometry_policy,name)for name in state if name!=target}
                clear,blocker=preview_clearance([palm,*pad_meshes],pose-tcp,obstacles)
                trace.append(dict(step=a.c.steps,opening_m=opening,proposed_tcp=pose,actual_material_point=point,
                    native_piece_clear=clear,blocker=blocker,collision_piece_counts={n:len(v)for n,v in obstacles.items()},
                    geometry_source='native_enabled_collision_parts_convex_hull_1mm_margin'))
                if clear:chosen=pose;break
            if chosen is None:raise RuntimeError('Narrowed actual hand cannot clear neighboring cutlery')
            a.stage='debug-e34c-precise-fork-approach'
            move([chosen[0],chosen[1],max(safe_z,float(a.tip(side)[2]))],tolerance=.002)
            move(chosen,tolerance=.0015)
            untouched();state,_=snapshot();body=state[target];point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local']);pads=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
            if not deep_capture(point,pads,floor):raise RuntimeError('Fork material not deeply inside both actual pad sections')
            a.stage='debug-e34c-real-grasp'
            for _ in range(3):pulse('GRASP');untouched()
            state,_=snapshot()
            if not state[target]['grasp'][side_index]:raise RuntimeError('Fork not physically grasped in local debug')
        a.carried_payload=(target,side);initial_z=float(state[target]['pos'][2]);a.stage='debug-e34c-small-real-lift'
        for _ in range(12):
            token=labels[2][0 if signs.get(2,1)==1 else 1];pulse(token,5.);untouched();state,contacts=snapshot()
            if not state[target]['grasp'][side_index] or not all(force(target,f)>.001 for f in fingers):
                raise RuntimeError('Fork grip lost during local small lift')
            trace.append(dict(step=a.c.steps,actual_fork_z=float(state[target]['pos'][2]),
                table_contact=frozenset((target,'table'))in contacts,
                actual_finger_forces_n=[force(target,f)for f in fingers]))
            if float(state[target]['pos'][2])-initial_z>=.004 and frozenset((target,'table'))not in contacts:break
        lift=float(state[target]['pos'][2]-initial_z)
        if lift<.004 or frozenset((target,'table'))in contacts:
            raise RuntimeError('Local fork lift did not establish actual unsupported pickup')
        report.update(passed=True,segment_passed=True,final_step=a.c.steps,actual_lift_m=lift,
            final_fork_state=state[target],final_tcp=np.asarray(a.tip(side)),actual_two_finger_contacts=True,
            object_velocity_limit='Reconstruction may derive missing velocities; local debug only')
        write();return report
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),final_step=a.c.steps)
        write();raise


def carry_place(a,payload):
    """Held-fork checkpoint to real tray support; no pickup or restored history."""
    scope(a)
    from .engineering_checkpoint import capture
    from .execution_design_branch_geometry import HeldGeometry,collision_parts_task
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_e34_reference import level_handle,placement,retreat
    from types import SimpleNamespace
    side=payload.get('side','left');name='fork';ix=('left','right').index(side)
    spec=a.scene.spec;semantic=spec['semantic'];tray_name=semantic['container']
    if spec.get('variant')!='C' or spec['execution_design'].get('condition')!='I':raise ValueError('E34C I local carry required')
    report=dict(local_debug_only=True,fixed36_positive=False,stage='carry_place',side=side,passed=False,trace=[])
    out=Path(a.out)/'e34-local-carry-place.private.json';original=a.act;released=False;support_allowed=False
    state,_=a.c.snapshot();baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    fingers=[side+'_finger1',side+'_finger2'];a.carried_payload=(name,side)
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    def held(ref=None,requested_side=None):
        b=a.c.snapshot()[0][name]
        if not b['grasp'][ix]or not all(force(name,f)>.001 for f in fingers):raise RuntimeError('E34 carry lost actual two-pad fork grasp')
    policy=SimpleNamespace(a=a,c=a.c,frame=frame,snapshot=a.c.snapshot,tip=a.tip,require_held=held)
    geometry=HeldGeometry(policy,name,side)
    def untouched():
        values,_=a.c.snapshot()
        for n,old in baseline.items():
            body=values[n]
            if any(body['grasp'])or np.linalg.norm(np.asarray(body['pos'])-old['pos'])>.002 or np.linalg.norm(np.asarray(body['mat'])-old['mat'])>.03:
                raise RuntimeError('E34 carry moved unselected body: '+n)
            if any(force(n,f)>.001 for f in fingers):raise RuntimeError('E34 carry hand contacted unselected body: '+n)
    def guard():
        untouched()
        if not released:
            held();geometry.allowed=(tray_name,)if support_allowed else ();geometry.check()
    def act(left='STILL',right='STILL',mm=20.,rotation_deg=10.):
        guard();original(left,right,mm,rotation_deg=rotation_deg);guard()
    def pulse(token,mm=5.):act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm)
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'));signs=a.generated_axis_signs[side]
    def move(target,tolerance=.002):
        goal=np.asarray(target,float);history=[]
        for _ in range(100):
            error=goal-np.asarray(a.tip(side));distance=float(np.max(abs(error)))
            if distance<=tolerance:return
            history.append(float(np.linalg.norm(error)))
            if len(history)>=24 and min(history[-24:-16])-min(history[-8:])<.0005:raise RuntimeError('E34 held route stalled')
            axis=int(np.argmax(abs(error)));positive=1 if error[axis]>0 else -1
            token=labels[axis][0 if signs[axis]==positive else 1]
            pulse(token,min(15.,max(3.,abs(error[axis])*1000)))
        raise RuntimeError('E34 held route action bound exhausted')
    def save(stage):
        checkpoint=capture(a.c,stage,context=dict(carried_payload=None if released else[name,side],local_debug_only=True))
        path=Path(a.out)/('e34-'+stage+'.checkpoint.private.json');path.write_text(json.dumps(checkpoint,indent=2)+'\n')
        report['trace'].append(dict(stage=stage,step=a.c.steps,checkpoint=str(path)))
    try:
        a.act=act;guard();save('held-before-carry')
        if payload.get('stage')not in ('level_place','place_only'):
            hand=[actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)]
            fork=material_collision_points_task(policy,dict(actor=name));tip=np.asarray(a.tip(side));floor=table_bounds_task(a.scene)['top']
            obstacle_top=max(float(part[:,2].max())for n in baseline for part in collision_parts_task(policy,n))
            offset=min(float(m[:,2].min()-tip[2])for m in [*hand,fork]);clear_z=max(float(tip[2]),obstacle_top+.04-offset)
            a.stage='debug-e34c-held-clearance';move([*tip[:2],clear_z]);save('held-above-source')
            values,_=a.c.snapshot();tray=values[tray_name];body=values[name]
            bounds=semantic['compartment_bounds_local'];local=(np.asarray(bounds['lower'])+np.asarray(bounds['upper']))/2
            handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name])
            wanted=np.asarray(tray['pos'])+np.asarray(tray['mat'])@local;xy=wanted[:2]+(np.asarray(a.tip(side))-handle)[:2]
            a.stage='debug-e34c-held-carry-over-tray';move([*xy,clear_z],tolerance=.012);save('held-before-level')
        else:
            clear_z=float(a.tip(side)[2]);save('held-before-level')
        if payload.get('stage')!='place_only':
            # Screen a small free-space yaw against both the actual held pose and
            # the final receiving pose. The rule constrains the handle cell, not yaw.
            from .execution_design_drawer_ik_probe import inspect
            from .execution_design_e34b_place import yaw_target
            from .author_orientation import _axis_angle
            values,_=a.c.snapshot();body=values[name];tray=values[tray_name];tip=np.asarray(a.tip(side));rotation=np.asarray(a.tcp_rotation_task(side))
            bounds=semantic['compartment_bounds_local'];local=(np.asarray(bounds['lower'])+np.asarray(bounds['upper']))/2
            handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name]);obj=next(o for o in spec['objects']if o['id']==name)
            probes=[];yaw_candidates=[]
            for degrees in (10.,20.,-10.,-20.,30.,-30.):
                proposed=yaw_target(rotation,degrees);delta=proposed@rotation.T
                fork_rotation=delta@np.asarray(body['mat']);offset=delta@(tip-handle)
                new_handle_offset=fork_rotation@np.asarray(semantic['handle_points'][name]);half=float((np.abs(fork_rotation)@np.asarray(obj['size']))[2])
                desired=np.asarray(tray['pos'])+np.asarray(tray['mat'])@local
                desired[2]=float(tray['pos'][2])+half+float(new_handle_offset[2])+.003
                yaw_candidates.append((degrees,proposed));probes.extend([dict(position=tip,rotation=proposed),dict(position=desired+offset,rotation=proposed)])
            measured=inspect(a,a.c,side,probes);chosen=None
            for index,(degrees,proposed)in enumerate(yaw_candidates):
                pair=measured[2*index:2*index+2]
                if len(pair)==2 and all(v['kinematically_reachable']and v['minimum_joint_margin_rad']>=.04 and v['position_error_m']<.001 and v['orientation_error_rad']<math.radians(1.5)for v in pair):chosen=(degrees,proposed,pair);break
            report['yaw_screen']=dict(candidates=[dict(degrees=d,current=measured[2*i],low=measured[2*i+1])for i,(d,_)in enumerate(yaw_candidates)],native_route_verified=False)
            if chosen is None:raise RuntimeError('No measured yaw with actual held and receiving-pose joint margin')
            degrees,wanted_rotation,pair=chosen;report['chosen_yaw_degrees']=degrees
            a.stage='debug-e34c-safe-yaw-reconfigure';rotations=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'));errors=[]
            for _ in range(85):
                axis,angle=_axis_angle(wanted_rotation@np.asarray(a.tcp_rotation_task(side)).T)
                if angle<math.radians(.7):break
                errors.append(float(angle))
                if len(errors)>=20 and min(errors[-20:-12])-min(errors[-8:])<math.radians(.2):raise RuntimeError('E34C actual safe yaw stalled')
                vector=axis*angle;i=int(np.argmax(abs(vector)));direction=1 if vector[i]>0 else-1;turn=min(8.,max(.5,abs(math.degrees(vector[i]))))
                geometry.rotate(np.eye(3)[i],direction*math.radians(turn))
                act(rotations[i][0 if direction>0 else 1]if side=='left'else'STILL',rotations[i][0 if direction>0 else 1]if side=='right'else'STILL',5.,rotation_deg=turn)
            else:raise RuntimeError('E34C safe yaw action bound exhausted')
            # Clear an unfinished promised orientation with a legal small real yaw.
            act('ROTATE_CCW'if side=='left'else'STILL','ROTATE_CCW'if side=='right'else'STILL',5.,rotation_deg=.5)
            save('held-reconfigured-over-tray')
            a.stage='debug-e34c-destination-level';level_handle(a,name,side);save('held-level-over-tray')
        target=placement(a,name,side,next(z for z in spec['zones']if z['id']==spec['goals'][0]['target']))
        # Align during the real descent; the last high waypoint can hit joint3
        # even when the lower receiving pose remains physically reachable.
        save('held-before-lower')
        support_allowed=True;a.stage='debug-e34c-lower-into-tray';move(target,tolerance=.0015);save('held-before-release')
        guard()
        from .execution_design_e34_release import release_supported
        a.act=original
        try:report['release']=release_supported(a,side,name)
        finally:a.act=act
        released=True;a.carried_payload=None;untouched();save('released-in-tray')
        a.stage='debug-e34c-empty-raise';move([*a.tip(side)[:2],max(clear_z,float(a.tip(side)[2])+.06)])
        a.stage='debug-e34c-short-retreat';retreat(a,side)
        for _ in range(5):act()
        values,contacts=a.c.snapshot();body=values[name];tray=values[tray_name]
        handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name]);local=(handle-np.asarray(tray['pos']))@np.asarray(tray['mat'])
        bounds=semantic['compartment_bounds_local'];lower=np.asarray(bounds['lower']);upper=np.asarray(bounds['upper']);result=a.c.evaluator.result()
        checks=dict(released=not any(body['grasp']),actual_tray_contact=frozenset((name,tray_name))in contacts,
            handle_xyz_in_cell=bool(np.all(local>=lower-.003)and np.all(local<=upper+.003)),actual_handle_tray_local_xyz=local.tolist(),native_result=result)
        if not checks['released']or not checks['actual_tray_contact']or not checks['handle_xyz_in_cell']or not result['success']:
            raise RuntimeError('E34 local placement physical checks failed: '+json.dumps(checks,default=str))
        report.update(passed=True,segment_passed=True,final_step=a.c.steps,physical_checks=checks);save('completed-carry-place')
        out.write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n');return report
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),final_step=a.c.steps)
        out.write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n');raise
    finally:a.act=original


def release_only(a,payload):
    scope(a)
    from .execution_design_e34_release import release_supported
    from .execution_design_e34_reference import retreat
    from .engineering_checkpoint import capture
    side=payload.get('side','left');name='fork';a.carried_payload=(name,side)
    report=dict(local_debug_only=True,fixed36_positive=False,stage='release',passed=False)
    out=Path(a.out)/'e34-local-release.private.json'
    try:
        report['release']=release_supported(a,side,name)
        retreat(a,side)
        for _ in range(5):a.act()
        values,contacts=a.c.snapshot();b=values[name];s=a.scene.spec['semantic'];tray=values[s['container']]
        point=np.asarray(b['pos'])+np.asarray(b['mat'])@np.asarray(s['handle_points'][name]);local=(point-tray['pos'])@np.asarray(tray['mat']);bounds=s['compartment_bounds_local'];result=a.c.evaluator.result()
        checks=dict(actual_handle_tray_local_xyz=local.tolist(),actual_tray_contact=frozenset((name,s['container']))in contacts,
            released=not any(b['grasp']),handle_xyz_in_cell=bool(np.all(local>=np.asarray(bounds['lower'])-.003)and np.all(local<=np.asarray(bounds['upper'])+.003)),native_result=result)
        report['physical_checks']=checks
        if not checks['actual_tray_contact']or not checks['released']or not checks['handle_xyz_in_cell']or not result['success']:
            raise RuntimeError('E34 narrow release final physical checks failed')
        cp=capture(a.c,'completed-real-narrow-release',context=dict(carried_payload=None,local_debug_only=True));(Path(a.out)/'e34-release-completed.checkpoint.private.json').write_text(json.dumps(cp,indent=2)+'\n')
        report.update(passed=True,segment_passed=True,final_step=a.c.steps);out.write_text(json.dumps(report,indent=2));return report
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),final_step=a.c.steps);out.write_text(json.dumps(report,indent=2));raise


def verify_final(a,payload):
    scope(a)
    if a.scene.spec.get('variant')!='C':raise ValueError('E34C local final verifier required')
    a.carried_payload=None;a.stage='e34-local-verify-final'
    for _ in range(2):a.act()
    values,contacts=a.c.snapshot();s=a.scene.spec['semantic'];b=values['fork'];tray=values[s['container']]
    point=np.asarray(b['pos'])+np.asarray(b['mat'])@np.asarray(s['handle_points']['fork']);local=(point-tray['pos'])@np.asarray(tray['mat']);bounds=s['compartment_bounds_local'];result=a.c.evaluator.result()
    force=getattr(a.c,'contact_forces',{})
    checks=dict(released=not any(b['grasp']),actual_tray_contact=frozenset(('fork',s['container']))in contacts,
        bilateral_fork_finger_forces_n=[float(force.get(frozenset(('fork','left_finger'+str(i))),0.))for i in (1,2)],
        handle_xyz_in_cell=bool(np.all(local>=np.asarray(bounds['lower'])-.003)and np.all(local<=np.asarray(bounds['upper'])+.003)),actual_handle_tray_local_xyz=local.tolist(),native_result=result)
    if not checks['released']or not checks['actual_tray_contact']or max(checks['bilateral_fork_finger_forces_n'])>.001 or not checks['handle_xyz_in_cell']or not result['success']:
        raise RuntimeError('E34 local final-state physics verification failed: '+json.dumps(checks,default=str))
    report=dict(local_debug_only=True,fixed36_positive=False,passed=True,segment_passed=True,stage='verify_final',physical_checks=checks,final_step=a.c.steps)
    (Path(a.out)/'e34-local-final-verification.private.json').write_text(json.dumps(report,indent=2));return report
