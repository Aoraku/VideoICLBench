"""Private E34B/C held-utensil reference tail, shared by fixed primaries.

No model API, hidden physical-state mutation, or native acceptance override.
The caller must already hold the selected source utensil above the table.
"""
import json,math
from pathlib import Path
import numpy as np
from .execution_design_e34_reference import scope

def finish_held_cutlery(a,name,side):
    """Finish a genuine held B/C utensil through private physical controls."""
    payload=dict(side=side,stage="carry_place")
    scope(a)
    from .engineering_checkpoint import capture
    from .execution_design_branch_geometry import HeldGeometry,collision_parts_task
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_e34_reference import level_handle,placement,retreat
    from types import SimpleNamespace
    ix=('left','right').index(side)
    spec=a.scene.spec;semantic=spec['semantic'];tray_name=semantic['container']
    if spec.get('variant')not in ('B','C')or spec['execution_design'].get('condition')!='I'or name!=semantic['selected']or name!={'B':'spoon','C':'fork'}[spec['variant']]:raise ValueError('Private fixed I4201 E34B spoon/C fork reference tail required')
    if spec.get('seed')!=4201 or a.carried_payload!=(name,side):raise ValueError('Actually carried fixed primary utensil required')
    diagnostic=bool(getattr(a.c,'_engineering_diagnostic_only',False))
    report=dict(engineering_reference_only=True,local_debug_only=diagnostic,source_initial_tail=not diagnostic,fixed36_positive=False,independent_native_acceptance_required=True,stage='carry_place',side=side,object=name,passed=False,trace=[])
    out=Path(a.out)/'e34-private-reference-tail.private.json';original=a.act;released=False;support_allowed=False
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
        if spec.get('variant')=='B':
            from .execution_design_e34_acquire import check_pickup_neighbors
            check_pickup_neighbors(a,side,name,baseline)
            return
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
    def move(target,tolerance=.002,done=None):
        goal=np.asarray(target,float);history=[]
        for _ in range(100):
            if done is not None and done():return
            error=goal-np.asarray(a.tip(side));distance=float(np.max(abs(error)))
            if distance<=tolerance:return
            history.append(float(np.linalg.norm(error)))
            if len(history)>=24 and min(history[-24:-16])-min(history[-8:])<.0005:raise RuntimeError('E34 held route stalled')
            axis=int(np.argmax(abs(error)));positive=1 if error[axis]>0 else -1
            token=labels[axis][0 if signs[axis]==positive else 1]
            pulse(token,min(15.,max(3.,abs(error[axis])*1000)))
        raise RuntimeError('E34 held route action bound exhausted')
    def save(stage):
        checkpoint=capture(a.c,stage,context=dict(carried_payload=None if released else[name,side],local_debug_only=diagnostic))
        path=Path(a.out)/('e34-'+stage+'.checkpoint.private.json');path.write_text(json.dumps(checkpoint,indent=2)+'\n')
        report['trace'].append(dict(stage=stage,step=a.c.steps,checkpoint=str(path)))
    try:
        a.act=act;guard();save('held-before-carry')
        if payload.get('stage')not in ('level_place','place_only'):
            hand=[actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)]
            fork=material_collision_points_task(policy,dict(actor=name));tip=np.asarray(a.tip(side));floor=table_bounds_task(a.scene)['top']
            obstacle_top=max(float(part[:,2].max())for n in baseline for part in collision_parts_task(policy,n))
            offset=min(float(m[:,2].min()-tip[2])for m in [*hand,fork]);clear_z=max(float(tip[2]),obstacle_top+.04-offset)
            a.stage='e34-private-tail-held-clearance';move([*tip[:2],clear_z]);save('held-above-source')
            values,_=a.c.snapshot();tray=values[tray_name];body=values[name]
            bounds=semantic['compartment_bounds_local'];local=(np.asarray(bounds['lower'])+np.asarray(bounds['upper']))/2
            handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name])
            wanted=np.asarray(tray['pos'])+np.asarray(tray['mat'])@local;xy=wanted[:2]+(np.asarray(a.tip(side))-handle)[:2]
            a.stage='e34-private-tail-held-carry-over-tray';move([*xy,clear_z],tolerance=.012);save('held-before-level')
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
            a.stage='e34-private-tail-safe-yaw-reconfigure';rotations=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'));errors=[]
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
            a.stage='e34-private-tail-destination-level';level_handle(a,name,side)
            if spec.get('variant')=='B':
                # Source270 retained a measured 2.44deg unfinished PITCH goal.
                # A small real public rotation rebases from the actual pose,
                # matching the intended held orientation during XY/descent.
                act('ROTATE_CCW'if side=='left'else'STILL','ROTATE_CCW'if side=='right'else'STILL',5.,rotation_deg=.5)
            save('held-level-over-tray')
        target=placement(a,name,side,next(z for z in spec['zones']if z['id']==spec['goals'][0]['target']))
        if spec.get('variant')=='B':
            # A large Z error must not lower the spoon onto the outer wall
            # while its mass is still beyond the tray. Align the actual COM
            # corrected XY at real clearance before seeking floor support.
            a.stage='e34-private-tail-align-supported-com'
            move([target[0],target[1],float(a.tip(side)[2])],tolerance=.002)
            target=placement(a,name,side,next(z for z in spec['zones']if z['id']==spec['goals'][0]['target']))
        # Align during the real descent; the last high waypoint can hit joint3
        # even when the lower receiving pose remains physically reachable.
        save('held-before-lower')
        def supported_in_cell():
            values,contacts=a.c.snapshot();body=values[name];tray=values[tray_name]
            handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name])
            local=(handle-np.asarray(tray['pos']))@np.asarray(tray['mat']);bounds=semantic['compartment_bounds_local']
            raw=a.scene.objects[name].root_physx_view.get_coms()
            if hasattr(raw,'detach'):raw=raw.detach().cpu().numpy()
            com=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(raw,float).reshape(-1,7)[0,:3]
            mass_local=(com-np.asarray(tray['pos']))@np.asarray(tray['mat'])
            return bool(frozenset((name,tray_name))in contacts
                and np.all(local>=np.asarray(bounds['lower'])-.003)
                and np.all(local<=np.asarray(bounds['upper'])+.003)
                and np.all(mass_local[:2]>=np.asarray(bounds['lower'])[:2]-.003)
                and np.all(mass_local[:2]<=np.asarray(bounds['upper'])[:2]+.003))
        support_allowed=True;a.stage='e34-private-tail-lower-into-tray'
        move(target,tolerance=.0015,done=supported_in_cell if spec.get('variant')=='B'else None)
        save('held-before-release')
        guard()
        from .execution_design_e34_release import release_supported
        a.act=original
        try:report['release']=release_supported(a,side,name)
        finally:a.act=act
        released=True;a.carried_payload=None;untouched();save('released-in-tray')
        a.stage='e34-private-tail-empty-raise';move([*a.tip(side)[:2],max(clear_z,float(a.tip(side)[2])+.06)])
        a.stage='e34-private-tail-short-retreat';retreat(a,side)
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



def finish_held(author,name,side):
    """Demo hook: genuine held source utensil through final native checks."""
    return finish_held_cutlery(author,name,side)


def finish_from_grasp(a,name,side):
    """Legal near-pose rebase and bounded real lift, then the B/C tail."""
    scope(a);spec=a.scene.spec;ix=('left','right').index(side)
    if spec.get('variant')not in ('B','C')or name!={'B':'spoon','C':'fork'}[spec['variant']]or spec['execution_design'].get('condition')!='I':
        raise ValueError('Fixed private E34 B/C selected source grasp required')
    state,contacts=a.c.snapshot();initial_z=float(state[name]['pos'][2]);fingers=[side+'_finger1',side+'_finger2']
    if a.carried_payload!=(name,side)or not state[name]['grasp'][ix]:raise RuntimeError('E34 tail entry requires native source grasp')
    baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name};trace=[]
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def guard():
        values,contacts=a.c.snapshot()
        if not values[name]['grasp'][ix]or not all(force(name,f)>.001 for f in fingers):raise RuntimeError('E34 real departure lost opposing utensil grip')
        for n,old in baseline.items():
            b=values[n]
            if any(b['grasp'])or np.linalg.norm(np.asarray(b['pos'])-old['pos'])>.002 or np.linalg.norm(np.asarray(b['mat'])-old['mat'])>.03:
                raise RuntimeError('E34 real departure moved unselected body: '+n)
            if any(force(n,f)>.001 for f in fingers)or frozenset((name,n))in contacts:
                raise RuntimeError('E34 real departure contacted unselected body: '+n)
        return values,contacts
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from types import SimpleNamespace
    def frame(ref):
        body=a.c.snapshot()[0][ref['actor']];return np.asarray(body['pos']),np.asarray(body['mat'])
    policy=SimpleNamespace(a=a,frame=frame);floor=float(table_bounds_task(a.scene)['top'])
    def material_clearance():
        meshes=[actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)]
        meshes.append(material_collision_points_task(policy,dict(actor=name)))
        return min(float(mesh[:,2].min())for mesh in meshes)-floor
    token='UP'if a.generated_axis_signs[side][2]==1 else'DOWN'
    try:
        guard();a.stage='e34-private-real-near-pose-rebase'
        a.act('ROTATE_CCW'if side=='left'else'STILL','ROTATE_CCW'if side=='right'else'STILL',5.,rotation_deg=.5);guard()
        a.stage='e34-private-actual-table-departure'
        for _ in range(24):
            values,contacts=guard()
            if float(values[name]['pos'][2])-initial_z>=.004 and frozenset((name,'table'))not in contacts and material_clearance()>=.0015:break
            a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',5.)
            values,contacts=guard();trace.append(dict(step=a.c.steps,actual_tcp=np.asarray(a.tip(side)).tolist(),actual_center_z=float(values[name]['pos'][2]),actual_mesh_table_clearance_m=material_clearance(),table_contact=frozenset((name,'table'))in contacts,actual_pad_forces_n=[force(name,f)for f in fingers]))
            if len(trace)>=8 and trace[-1]['actual_center_z']-trace[-8]['actual_center_z']<.0005 and trace[-1]['actual_tcp'][2]-trace[-8]['actual_tcp'][2]<.001:raise RuntimeError('E34 real departure stopped making measured physical progress')
        values,contacts=guard();lift=float(values[name]['pos'][2])-initial_z
        if lift<.004 or frozenset((name,'table'))in contacts or material_clearance()<.0015:raise RuntimeError('E34 actual source departure failed physical lift, unsupported or native mesh-clearance checks')
        report=dict(object=name,side=side,actual_lift_m=lift,actual_unsupported_pickup=True,actual_mesh_table_clearance_m=material_clearance(),public_near_pose_yaw_degrees=.5,maximum_private_up_count=24,trace=trace,source_rule_unchanged=True)
        (Path(a.out)/'e34-private-source-departure.private.json').write_text(json.dumps(report,indent=2)+'\n')
        return finish_held_cutlery(a,name,side)
    except Exception as exc:
        (Path(a.out)/'e34-private-source-departure-failure.private.json').write_text(json.dumps(dict(object=name,side=side,trace=trace,error=type(exc).__name__+': '+str(exc)),indent=2)+'\n');raise
