"""Short measured finger separation at real bowl support; no projection rule."""
import json
import numpy as np


def support_target_z_shift(initial_position,initial_rotation,initial_tip,position,rotation):
    """Track measured material height; keep the supporting hand's XY fixed."""
    origin=np.asarray(initial_position,float);basis=np.asarray(initial_rotation,float)
    tip=np.asarray(initial_tip,float);local=basis.T@(tip-origin)
    current=np.asarray(rotation,float);target=np.asarray(position,float)+current@local
    normal=current[:,2]
    if not np.isfinite(np.r_[target,normal]).all()or abs(normal[2])<.5:
        raise ValueError('Finite down-hemisphere plate plane required for upper support')
    # A laterally dragged tilted plate changes the surface height at fixed
    # hand XY. Follow that plane intersection, rather than a moving point's Z.
    desired_z=target[2]-float(normal[:2]@(tip[:2]-target[:2]))/float(normal[2])
    return float(np.clip(desired_z-tip[2],-.040,.004))


def run(a,parameters=None):
    parameters=parameters or {};left_support=parameters.get('left_top_support')is True
    from .engineering_native_tick import diagnostic_tick_scope
    from .engineering_checkpoint import capture
    from .execution_design_e31_arm_clearance import capture_native_meshes,LiveTableGuard
    from .execution_design_thin_edge import table_bounds_task
    spec=a.scene.spec;name=spec['semantic']['plate'];bowl=spec['semantic']['bowl'];side='right'
    if not(spec['id']=='E31'and spec['seed']==4201 and getattr(a.c,'_engineering_diagnostic_only',False)):
        raise ValueError('Explicit supported E31 checkpoint required')
    reader=getattr(a,'_e31_native_contact_reader',None)
    if reader is None:raise ValueError('Actual native all-link contact reader required')
    state,contacts=a.c.snapshot()
    if not state[name]['grasp'][1]or frozenset((name,bowl))not in contacts:
        raise RuntimeError('Real held plate and real bowl support required')
    if left_support and max(float(a.c.contact_forces.get(frozenset((name,'left_finger'+str(i))),0.))for i in(1,2))<=.01:
        raise RuntimeError('Measured real left top contact required')
    robot=a.scene.robots[side];ids=a.c.ids[side][1]
    initial=float(robot.data.joint_pos[0,ids].detach().cpu().numpy().max())
    opening=initial+.005
    if opening>.018:raise RuntimeError('Measured narrow opening exceeds engineering limit')
    meshes,_=capture_native_meshes(a,side);table=LiveTableGuard(a,side,meshes,float(table_bounds_task(a.scene)['top']))
    trace=[];quiet_since=[None];support_servo=[]
    if left_support:
        source_plate=dict(pos=np.asarray(state[name]['pos']).copy(),mat=np.asarray(state[name]['mat']).copy())
        source_left_tip=np.asarray(a.tip('left')).copy()
        source_left_target=(a.c.targets['left'][0].clone(),a.c.targets['left'][1].clone())
    def forces():
        prefix=name+'/right/'if left_support else name+'/'
        return {key:value for key,value in reader['current_forces_n'].items()if key.startswith(prefix)}
    def separated():
        values=forces()
        return bool(values and all(value is not None and value<=.001 for value in values.values())
                    and not(a.c.snapshot()[0][name]['grasp'][1]if left_support else any(a.c.snapshot()[0][name]['grasp'])))
    def supported_quiet():
        state,contacts=a.c.snapshot()
        good=(separated()and frozenset((name,bowl))in contacts
              and float(state[name]['mat'][2,2])<-.85)
        if not good:quiet_since[0]=None;return False
        now=a.c.physics_ticks*a.c.dt
        if quiet_since[0]is None:quiet_since[0]=now
        return now-quiet_since[0]>=.5
    def guard():
        if left_support:
            # Actual body fall/rotation can otherwise leave a fixed upper
            # finger in the air. Follow only measured Z through ordinary arm
            # motor targets; XY stays anchored against lateral dish dragging.
            import torch
            from isaaclab.utils.math import quat_apply_inverse
            body=a.c.snapshot()[0][name]
            dz=support_target_z_shift(source_plate['pos'],source_plate['mat'],source_left_tip,body['pos'],body['mat'])
            world=np.asarray(a.scene.layout.task_rotation)@np.array([0.,0.,dz])
            tensor=torch.as_tensor(world,device=a.c.device,dtype=source_left_target[0].dtype)[None]
            base=quat_apply_inverse(a.scene.robots['left'].data.root_quat_w,tensor)
            a.c.targets['left']=(source_left_target[0]+base,source_left_target[1])
            if not support_servo or abs(dz-support_servo[-1]['target_z_shift_m'])>.0005:
                support_servo.append(dict(tick=a.c.physics_ticks,target_z_shift_m=dz))
        table.check();values=reader['current_forces_n']
        hits={key:value for key,value in values.items()if value is not None and value>1.
              and (key.startswith('robot_table/')or key.startswith('bowl/'))}
        if hits:raise RuntimeError('Supported separation contacted robot/table or recipient: '+str(hits))
    a.carried_payload=None;a.c.grips[side]=opening
    a.stage='e31-supported-real-narrow-diagonal-separation'
    try:
        # CPU warm-start and full native per-link mesh checks retained a real
        # table margin on this short down/out escape. No large full opening.
        start=np.asarray(a.tip(side),float)
        for delta in([- .016,-.008,-.004],[-.032,-.016,-.004]):
            target=start+np.asarray(delta,float);guard()
            with diagnostic_tick_scope(a):
                receipt=a.c.author_move({side:target.tolist()},max_speed=.02,max_acceleration=.08,
                    guard=guard,done=supported_quiet)
            trace.append(dict(target=target.tolist(),receipt=receipt,actual_plate=a.c.snapshot()[0][name],forces=forces()))
            if supported_quiet():break
        if not separated():raise RuntimeError('Short supported escape did not establish real all-link separation')
        label='right-separated-left-supported'if left_support else'all-link-separated'
        cp=capture(a.c,'e31-actual-'+label+'-no-projection')
        (a.out/('e31-'+label+'.checkpoint.private.json')).write_text(json.dumps(cp,indent=2)+'\n')
        a.stage='e31-separated-native-half-second-settle'
        for _ in range(2):a.act()
        report=dict(actual_selected_hand_separation=separated(),selected_hand_scope='right'if left_support else'both',motor_opening_m=opening,trace=trace,
            no_direct_state_assignment=True,no_whole_hand_projection_requirement=True)
        return report
    finally:
        (a.out/'e31-supported-short-separation.private.json').write_text(json.dumps(dict(trace=trace,left_measured_z_motor_targets=support_servo,actual_plate=a.c.snapshot()[0][name],forces=forces()),indent=2,default=lambda value:value.tolist())+'\n')
