"""E34B held-spoon suffix: public yaw, measured low route, real release.

The native rule only constrains the handle's tray-local cell and support. A
small yaw in empty space avoids a low wrist branch approaching its joint stop.
No joints, actor poses, source goals, or controller tolerances are changed.
"""
import json,math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from .execution_design_e34_reference import scope,placement,retreat,level_handle


def yaw_target(rotation,degrees):
    angle=math.radians(float(degrees));c,s=math.cos(angle),math.sin(angle)
    return np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])@np.asarray(rotation,float)


def place_held(a,payload):
    scope(a)
    spec=a.scene.spec;semantic=spec['semantic'];name=semantic['selected']
    if spec.get('variant')!='B' or name!='spoon' or spec['execution_design'].get('condition')!='I':
        raise ValueError('E34B I measured held-spoon route required')
    from .author_orientation import _axis_angle
    from .execution_design_branch_geometry import HeldGeometry
    from .execution_design_cutlery_transfer import screen_direct_translation
    from .engineering_checkpoint import capture
    side=payload.get('side','left');ix=('left','right').index(side);tray=semantic['container']
    original=a.act;released=False;support_allowed=False
    state,_=a.c.snapshot();baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    fingers=[side+'_finger1',side+'_finger2'];a.carried_payload=(name,side)
    out=Path(a.out)/'e34b-local-place.private.json'
    report=dict(local_debug_only=True,fixed36_positive=False,trace=[],passed=False,
                initial_step=a.c.steps,side=side,source_goals_unchanged=True)
    def write():out.write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n')
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def held(*args):
        b=a.c.snapshot()[0][name]
        if not b['grasp'][ix]or not all(force(name,f)>.001 for f in fingers):
            raise RuntimeError('E34B actual opposing spoon grip lost')
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    policy=SimpleNamespace(a=a,c=a.c,frame=frame,snapshot=a.c.snapshot,tip=a.tip,require_held=held)
    geometry=HeldGeometry(policy,name,side)
    def untouched():
        from .execution_design_e34_acquire import check_pickup_neighbors
        check_pickup_neighbors(a,side,name,baseline)
    def guard():
        untouched()
        if not released:
            held();geometry.allowed=(tray,)if support_allowed else ();geometry.check()
    def act(left='STILL',right='STILL',mm=15.,rotation_deg=8.):
        guard();original(left,right,mm,rotation_deg=rotation_deg);guard()
    def pulse(token,mm=15.,degrees=8.):
        act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm,rotation_deg=degrees)
    signs=a.generated_axis_signs[side];labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    def move(target,tolerance=.0015,done=None):
        goal=np.asarray(target,float);history=[]
        for _ in range(130):
            if done is not None and done():return
            error=goal-np.asarray(a.tip(side));distance=float(np.max(abs(error)))
            if distance<=tolerance:return
            history.append(float(np.linalg.norm(error)))
            if len(history)>=24 and min(history[-24:-16])-min(history[-8:])<.0004:
                raise RuntimeError('E34B held waypoint stopped progressing')
            axis=int(np.argmax(abs(error)));direction=1 if error[axis]>0 else-1
            token=labels[axis][0 if signs[axis]==direction else 1]
            pulse(token,min(15.,max(3.,abs(error[axis])*1000)))
        raise RuntimeError('E34B held waypoint action bound exhausted')
    def save(stage):
        cp=capture(a.c,stage,context=dict(carried_payload=None if released else[name,side],local_debug_only=True))
        path=Path(a.out)/('e34b-'+stage+'.checkpoint.private.json');path.write_text(json.dumps(cp,indent=2)+'\n')
        report['trace'].append(dict(stage=stage,step=a.c.steps,checkpoint=str(path)))
    try:
        a.act=act;guard();save('held-before-yaw')
        from .execution_design_author_rotation import command_degrees,update_loss
        target=(np.asarray(a.tcp_rotation_task(side)).copy()if payload.get('skip_yaw')
                else yaw_target(a.tcp_rotation_task(side),payload.get('yaw_degrees',20.)))
        rotations=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        errors=[];last_axis=2;last_sign=1;losses=[0.,0.,0.]
        a.stage='debug-e34b-empty-space-yaw'
        for _ in range(85):
            actual=np.asarray(a.tcp_rotation_task(side));axis,angle=_axis_angle(target@actual.T)
            if angle<math.radians(.6):break
            errors.append(float(angle))
            if len(errors)>=20 and min(errors[-20:-12])-min(errors[-8:])<math.radians(.2):
                raise RuntimeError('E34B measured yaw stopped progressing')
            vector=axis*angle;i=int(np.argmax(abs(vector)));direction=1 if vector[i]>0 else-1
            last_axis,last_sign=i,direction
            # The swept mesh is checked before the actual public rotation.
            degrees=command_degrees(vector[i],losses[i],maximum=8.)
            command_axis=np.eye(3)[i];geometry.rotate(command_axis,direction*math.radians(degrees))
            pulse(rotations[i][0 if direction>0 else 1],degrees=degrees)
            feedback=a.c.action_feedback()['control_feedback'][side]
            if not feedback.get('blocked')and not feedback.get('joint_limit')and feedback.get('status')!='blocked':
                losses[i],_=update_loss(actual,a.tcp_rotation_task(side),i,direction,degrees,losses[i])
        else:raise RuntimeError('E34B public yaw action bound exhausted')
        # Public rotation rebases from actual pose. A small final command avoids
        # carrying a several-degree unfinished promised orientation into DOWN.
        if errors:pulse(rotations[last_axis][0 if last_sign>0 else 1],degrees=.5)
        save('held-yawed-above-tray')
        if payload.get('level',True):
            a.stage='debug-e34b-level-actual-handle';level_handle(a,name,side)
            save('held-levelled-above-tray')
        goal=next(z for z in spec['zones']if z['id']==spec['goals'][0]['target'])
        target=placement(a,name,side,goal);clear=float(a.tip(side)[2])
        a.stage='debug-e34b-align-actual-handle';move([target[0],target[1],clear]);save('held-before-lower')
        target=placement(a,name,side,goal)
        # Same measured 0.04rad branch margin as source reference; no relaxation.
        screen_direct_translation(a,name,side,target)
        def supported_in_cell():
            values,contacts=a.c.snapshot();body=values[name];container=values[tray]
            handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name])
            local=(handle-np.asarray(container['pos']))@np.asarray(container['mat']);bounds=semantic['compartment_bounds_local']
            raw=a.scene.objects[name].root_physx_view.get_coms()
            if hasattr(raw,'detach'):raw=raw.detach().cpu().numpy()
            com=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(raw,float).reshape(-1,7)[0,:3]
            mass_local=(com-np.asarray(container['pos']))@np.asarray(container['mat'])
            return bool(frozenset((name,tray))in contacts
                and np.all(local>=np.asarray(bounds['lower'])-.003)
                and np.all(local<=np.asarray(bounds['upper'])+.003)
                and np.all(mass_local[:2]>=np.asarray(bounds['lower'])[:2]-.003)
                and np.all(mass_local[:2]<=np.asarray(bounds['upper'])[:2]+.003))
        support_allowed=True;a.stage='debug-e34b-actual-low-route';move(target,done=supported_in_cell);save('held-ready-to-release')
        if payload.get('narrow_release'):
            # A geometric support-plane proposal is not actual contact.
            for _ in range(8):
                values,contacts=a.c.snapshot()
                if frozenset((name,tray))in contacts:break
                pulse('DOWN'if signs[2]==1 else'UP',3.)
            else:raise RuntimeError('E34B held spoon failed to reach actual tray support')
            save('held-actually-supported-before-release')
            from .execution_design_e34_release import release_supported
            a.act=original
            try:report['release']=release_supported(a,side,name)
            finally:a.act=act
        else:
            guard();original('RELEASE'if side=='left'else'STILL','RELEASE'if side=='right'else'STILL',5.)
        released=True;a.carried_payload=None;untouched();save('released-in-cell')
        a.stage='debug-e34b-empty-hand-clear';move([*a.tip(side)[:2],max(clear,float(a.tip(side)[2])+.07)])
        retreat(a,side)
        for _ in range(5):act()
        values,contacts=a.c.snapshot();b=values[name];t=values[tray]
        handle=np.asarray(b['pos'])+np.asarray(b['mat'])@np.asarray(semantic['handle_points'][name])
        local=(handle-np.asarray(t['pos']))@np.asarray(t['mat']);bounds=semantic['compartment_bounds_local']
        result=a.c.evaluator.result();physical=result.get('conditions',{})
        checks=dict(released=not any(b['grasp']),actual_tray_contact=frozenset((name,tray))in contacts,
            handle_xyz_in_cell=bool(np.all(local>=np.asarray(bounds['lower'])-.003)and np.all(local<=np.asarray(bounds['upper'])+.003)),
            actual_handle_tray_local_xyz=local.tolist(),native_result=result)
        if not checks['released']or not checks['actual_tray_contact']or not checks['handle_xyz_in_cell']or not result['success']:
            raise RuntimeError('E34B physical placement failed: '+json.dumps(checks,default=str))
        report.update(passed=True,segment_passed=True,physical_checks=checks,final_step=a.c.steps)
        save('completed-place');write();return report
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),final_step=a.c.steps);write();raise
    finally:a.act=original


def run(author,parameters):
    if not getattr(author.c,'_engineering_diagnostic_only',False):
        raise ValueError('E34B local segment requires admitted checkpoint')
    if parameters.get('stage')=='settle':return settle_released(author,parameters)
    if parameters.get('stage')=='release':return release_held(author,parameters)
    return place_held(author,parameters)


def release_held(a,parameters):
    """Finish an already real-supported native checkpoint, without re-lowering."""
    scope(a)
    if a.scene.spec.get('variant')!='B':raise ValueError('Actual E34B checkpoint required')
    from .execution_design_e34_acquire import check_pickup_neighbors
    from .execution_design_e34_release import release_supported
    name=a.scene.spec['semantic']['selected'];side=parameters.get('side','left')
    state,_=a.c.snapshot()
    baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    original=a.act
    def act(*args,**kwargs):
        check_pickup_neighbors(a,side,name,baseline)
        value=original(*args,**kwargs)
        check_pickup_neighbors(a,side,name,baseline)
        return value
    a.act=act
    try:
        result=release_supported(a,side,name)
        a.stage='debug-e34b-released-short-retreat';retreat(a,side)
        report=settle_released(a,parameters)
        report['release']=result
        return report
    finally:a.act=original


def settle_released(a,parameters):
    """Observe a genuinely released supported spoon; no pickup or placement."""
    scope(a)
    if a.scene.spec['variant']!='B':raise ValueError('Original E34B identity required')
    semantic=a.scene.spec['semantic'];name=semantic['selected'];tray=semantic['container'];trace=[]
    for _ in range(31):
        values,contacts=a.c.snapshot();body=values[name];t=values[tray]
        handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(semantic['handle_points'][name])
        local=(handle-np.asarray(t['pos']))@np.asarray(t['mat']);bounds=semantic['compartment_bounds_local']
        if any(body['grasp'])or frozenset((name,tray))not in contacts or np.any(local<np.asarray(bounds['lower'])-.003)or np.any(local>np.asarray(bounds['upper'])+.003):
            raise RuntimeError('E34B settling lost real release, cell or support')
        if any(float(force)>.001 for pair,force in a.c.contact_forces.items()if name in pair and any('finger'in x for x in pair)):
            raise RuntimeError('E34B released spoon has hand contact')
        result=a.c.evaluator.result();trace.append(dict(step=a.c.steps,raw_native_success=bool(result['success']),conditions=result.get('conditions'),handle_tray_local=local.tolist()))
        if result['success']:
            report=dict(segment_passed=True,local_debug_only=True,fixed36_positive=False,trace=trace,native_result=result,final_step=a.c.steps)
            (Path(a.out)/'e34b-released-settle.private.json').write_text(json.dumps(report,indent=2)+'\n');return report
        if len(trace)>30:break
        a.stage='debug-e34b-genuine-released-settle';a.act()
    (Path(a.out)/'e34b-released-settle.private.json').write_text(json.dumps(dict(segment_passed=False,local_debug_only=True,trace=trace),indent=2)+'\n')
    raise RuntimeError('E34B real spoon did not meet unchanged native stability bound in 12s')
