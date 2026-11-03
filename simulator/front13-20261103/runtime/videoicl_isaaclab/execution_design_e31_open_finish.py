"""Finish actual anchored single-finger release through real native motors."""
import json
import numpy as np


def support_force_z_bias(force_n,bias_m,dt):
    """Bounded ordinary motor target feedback, never a synthetic force."""
    if not np.isfinite([force_n,bias_m,dt]).all()or force_n<0 or not 0<dt<=.02:
        raise ValueError('Finite actual support force and native tick required')
    speed=-.025 if force_n<.35 else .010 if force_n>1.2 else 0.
    return float(np.clip(bias_m+speed*dt,-.040,.004))


def run(a,parameters=None):
    parameters=parameters or {}
    from .engineering_native_tick import diagnostic_tick_scope
    from .engineering_checkpoint import capture
    spec=a.scene.spec;name=spec['semantic']['plate'];bowl=spec['semantic']['bowl']
    diagnostic=bool(getattr(a.c,'_engineering_diagnostic_only',False))
    source_c=(spec.get('variant')=='C'and spec.get('execution_design',{}).get('condition')=='I'
        and spec['execution_design'].get('revision')=='embodied50-execution-v3-20261102'
        and a.control_report.get('engineering_reference_only')is True
        and getattr(a,'_execution_design_reference_authorized',False)
        and getattr(a,'_engineering_e31_verified_path',False)is True)
    if not(spec['id']=='E31'and spec['seed']==4201 and(diagnostic or source_c)):
        raise ValueError('Explicit anchored E31 diagnostic required')
    def motion_scope():return diagnostic_tick_scope(a,reference_authorization=not diagnostic)
    reader=getattr(a,'_e31_native_contact_reader',None)
    if reader is None:raise ValueError('Actual all-link contact reader required')
    trace=[];support_trace=[]
    def hand_forces(side):
        values={key:value for key,value in reader['current_forces_n'].items()if key.startswith(name+'/'+side+'/')}
        if not values or any(value is None for value in values.values()):raise RuntimeError('Incomplete actual hand contact readback')
        return values
    def pad_force(side):
        return max(float(a.c.contact_forces.get(frozenset((name,side+'_finger'+str(i))),0.))for i in(1,2))
    def base_guard():
        hits={key:value for key,value in reader['current_forces_n'].items()if value is not None and value>1.
              and(key.startswith('robot_table/')or key.startswith('bowl/'))}
        if hits:raise RuntimeError('Anchored opening contacted robot/table or receiving bowl: '+str(hits))
    def right_clear():return max(hand_forces('right').values())<=.001 and not a.c.snapshot()[0][name]['grasp'][1]
    state,contacts=a.c.snapshot()
    if frozenset((name,bowl))not in contacts:
        if parameters.get('allow_gravity_drop')is not True:
            raise RuntimeError('Actual plate/bowl support required before anchored opening')
        from types import SimpleNamespace
        from .execution_design_branch_geometry import collision_parts_task
        def frame(ref):
            body=a.c.snapshot()[0][ref['actor']]
            return np.asarray(body['pos']),np.asarray(body['mat'])
        view=SimpleNamespace(a=a,frame=frame)
        plate=np.concatenate(collision_parts_task(view,name));support=np.concatenate(collision_parts_task(view,bowl))
        gap=float(plate[:,2].min()-support[:,2].max())
        if not 0<=gap<=.09:raise RuntimeError('Ordinary gravity release is outside the measured height bound')
    # Rebuild cached contact using cumulative real motor targets below; do
    # not repeat submillimetre targets relative to a barely moving actual tip.
    left_target=(a.c.targets['left'][0].clone(),a.c.targets['left'][1].clone());bias=[0.];last_tick=[None]
    def guard():
        import torch
        from isaaclab.utils.math import quat_apply_inverse
        if last_tick[0]!=a.c.physics_ticks:
            force=pad_force('left');bias[0]=support_force_z_bias(force,bias[0],a.c.dt);last_tick[0]=a.c.physics_ticks
            if not support_trace or abs(bias[0]-support_trace[-1]['z_bias_m'])>.0005:
                support_trace.append(dict(tick=a.c.physics_ticks,z_bias_m=bias[0],actual_top_force_n=force))
        dz=bias[0]
        delta=np.asarray(a.scene.layout.task_rotation)@np.array([0.,0.,dz])
        tensor=torch.as_tensor(delta,device=a.c.device,dtype=left_target[0].dtype)[None]
        base=quat_apply_inverse(a.scene.robots['left'].data.root_quat_w,tensor)
        a.c.targets['left']=(left_target[0]+base,left_target[1]);base_guard()
    try:
        a.stage='e31-actual-force-supported-contact'
        for _ in range(3):
            with motion_scope():
                a.c.author_move({'right':np.asarray(a.tip('right')).tolist()},max_speed=.02,max_acceleration=.08,guard=guard)
            if pad_force('left')>.05:break
        if pad_force('left')<=.05:raise RuntimeError('Actual force-supported top contact not established')
        for opening in(()if parameters.get('resume_full_open')is True else(.040,)):
            a.c.grips['right']=opening;a.stage='e31-real-anchored-right-opening'
            for _ in range(3):
                with motion_scope():
                    receipt=a.c.author_move({'right':np.asarray(a.tip('right')).tolist()},
                        max_speed=.02,max_acceleration=.08,guard=guard)
                trace.append(dict(step=a.c.steps,opening_m=opening,receipt=receipt,
                    right_forces=hand_forces('right'),left_force_n=pad_force('left'),plate=a.c.snapshot()[0][name]))
            if right_clear():break
        if not right_clear():
            # The remaining pad is below the dish. Separate downward before
            # dragging an open finger sideways through the real rim.
            start=np.asarray(a.tip('right')).copy()
            for down in(.008,.020):
                a.stage='e31-fully-open-real-downward-separation'
                with motion_scope():
                    receipt=a.c.author_move({'right':(start+[0,0,-down]).tolist()},
                        max_speed=.02,max_acceleration=.08,guard=guard,done=right_clear)
                trace.append(dict(step=a.c.steps,opening_m=.040,receipt=receipt,
                    right_forces=hand_forces('right'),left_force_n=pad_force('left'),plate=a.c.snapshot()[0][name]))
                if right_clear():break
        if not right_clear():
            # Ordinary empty-hand retreat after full RELEASE. Stop on actual
            # separation; no full-hand footprint or cosmetic centring target.
            start=np.asarray(a.tip('right')).copy()
            for back in(.020,.040):
                a.stage='e31-fully-open-real-empty-retreat'
                with motion_scope():
                    receipt=a.c.author_move({'right':(start+[-back,0,0]).tolist()},
                        max_speed=.025,max_acceleration=.08,guard=guard,done=right_clear)
                trace.append(dict(step=a.c.steps,opening_m=.040,receipt=receipt,
                    right_forces=hand_forces('right'),left_force_n=pad_force('left'),plate=a.c.snapshot()[0][name]))
                if right_clear():break
        if not right_clear():raise RuntimeError('Actual fully open retreat retained right contact')
        cp=capture(a.c,'e31-right-actually-free-left-supported')
        (a.out/'e31-right-actually-free.checkpoint.private.json').write_text(json.dumps(cp,indent=2)+'\n')
        a.carried_payload=None;a.stage='e31-left-real-upward-separation'
        for _ in range(12):
            if max(hand_forces('left').values())<=.001:break
            a.act('UP','STILL',4.);base_guard()
        else:raise RuntimeError('Actual upper support did not separate on short upward withdrawal')
        for _ in range(2):a.act();base_guard()
        return dict(actual_right_contact_free=right_clear(),actual_left_contact_free=max(hand_forces('left').values())<=.001,
            trace=trace,real_gripper_and_arm_motor_targets_only=True)
    finally:
        report=dict(trace=trace,actual_top_force_motor_feedback=support_trace,final_plate=a.c.snapshot()[0][name],right_forces=hand_forces('right'),left_forces=hand_forces('left'))
        (a.out/'e31-anchored-opening.private.json').write_text(json.dumps(report,indent=2,default=lambda value:value.tolist())+'\n')
