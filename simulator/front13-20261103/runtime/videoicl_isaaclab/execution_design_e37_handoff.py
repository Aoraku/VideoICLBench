"""Diagnostic, real two-hand transfer of the source driver.

The incoming hand pinches a separate, source-mesh handle section. The outgoing
hand stays closed until three genuine incoming bilateral grasp observations.
No object pose, robot state or grip flag is written.
"""
import json
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError

SOURCE='a4a58fbf36b5d003c83df395c8de25d283620932605ac1210d1a35b396751077'
POINT=[.015,8.555000000000014e-05,5.856415515362675e-05]


def side_approach_frame(driver_matrix,current_jaw,jaw_sign=None):
    """Keep the empty palm on the +Y side of a vertical held shaft."""
    body=np.asarray(driver_matrix,float);jaw=body[:,2].copy()
    if jaw_sign is None:
        if jaw@np.asarray(current_jaw,float)<0:jaw=-jaw
    else:
        if jaw_sign not in (-1,1):raise ValueError('Equivalent actual driver jaw sign must be -1 or +1')
        jaw*=int(jaw_sign)
    approach=np.cross(body[:,0],jaw);approach/=np.linalg.norm(approach)
    if approach[1]>0:approach=-approach
    if abs(approach[1])<.7:raise ToolExecutionError('Driver side approach lacks measured lateral clearance')
    return np.column_stack((np.cross(jaw,approach),jaw,approach))


def screened_side_approach_frame(policy,actor,incoming,current,jaw_sign=None):
    """Choose a continuous bounded-joint branch and screen real hand meshes."""
    from types import SimpleNamespace
    from .execution_design_jacobian_reference import capture
    from .execution_design_e31_continuation import screen
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_thin_edge import table_bounds_task
    from .author_orientation import _axis_angle
    measured=capture(policy.a,policy.c,incoming);tcp=np.asarray(measured['position']);rotation=np.asarray(measured['rotation_task'])
    body=np.asarray(policy.snapshot()[0][actor]['mat']);state,_=policy.snapshot()
    if any(b['grasp'][('left','right').index(incoming)]for b in state.values()):
        raise ToolExecutionError('Equivalent wrist branch requires an actually empty incoming hand')
    def frame(ref):
        value=policy.snapshot()[0][ref['actor']];return np.asarray(value['pos']),np.asarray(value['mat'])
    geometry_policy=SimpleNamespace(a=policy.a,frame=frame)
    meshes={n:actual_mesh(policy.a,incoming,n)for n in('panda_hand',*policy.a.scene.embodiment.fingers)}
    obstacles={};obstacle_evidence={}
    for name in state:
        try:
            obstacles[name]=collision_parts_task(geometry_policy,name)
            obstacle_evidence[name]='actual_enabled_native_convex_pieces'
        except ToolExecutionError as exc:
            if 'No actual branch obstacle collision pieces'not in str(exc):raise
            # Socket fixtures use native analytic primitives rather than USD
            # Mesh. A full current-stage bound is conservative, not a guessed
            # mesh; convert its local bound by the measured actual actor pose.
            from itertools import product
            from pxr import Usd,UsdGeom
            import omni.usd
            stage=omni.usd.get_context().get_stage();prim=stage.GetPrimAtPath(f'{policy.a.scene.root_path}/Props/{name}')
            cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render,UsdGeom.Tokens.proxy,UsdGeom.Tokens.guide],useExtentsHint=False)
            box=cache.ComputeWorldBound(prim).ComputeAlignedRange();low=np.asarray(box.GetMin());high=np.asarray(box.GetMax())
            if not np.isfinite(np.r_[low,high]).all()or np.any(high<=low):raise ToolExecutionError('Actual primitive fixture bound is incomplete')
            corners=np.asarray(list(product(*zip(low,high))),float)
            inverse=np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(prim).GetInverse(),float)
            local=corners@inverse[:3,:3]+inverse[3,:3];pos,rot=frame(dict(actor=name))
            obstacles[name]=[local@rot.T+pos];obstacle_evidence[name]='conservative_current_USD_bound_of_nonmesh_native_fixture'
    peer='right'if incoming=='left'else'left'
    for name in policy.a.scene.robots[peer].body_names:
        try:obstacles[peer+'_'+name]=[actual_mesh(policy.a,peer,name)]
        except ValueError:continue
    if peer+'_panda_hand'not in obstacles:raise ToolExecutionError('Actual outgoing palm geometry is missing')
    floor=table_bounds_task(policy.a.scene)['top'];candidates=[];accepted=[]
    for sign in ((jaw_sign,)if jaw_sign is not None else(1,-1)):
        target=side_approach_frame(body,current[:,1],sign);tcp_target=target@current.T@rotation
        continuation=screen(measured,[dict(position=tcp,rotation=tcp_target)],margin=.04)
        row=dict(jaw_sign=int(sign),target_tool_frame=target.tolist(),target_tcp_rotation=tcp_target.tolist(),
            angle_rad=float(_axis_angle(tcp_target@rotation.T)[1]),continuation=continuation,
            actual_hand_mesh_clear=False)
        if continuation['passed']:
            previous_rotation=rotation;previous_meshes=meshes
            try:
                for sample in continuation['samples']:
                    next_rotation=np.asarray(sample['rotation']);delta=next_rotation@previous_rotation.T
                    swept_pose_clearance(previous_meshes,tcp,tcp,delta,obstacles,floor,margin=.001)
                    previous_meshes={n:(p-tcp)@delta.T+tcp for n,p in previous_meshes.items()};previous_rotation=next_rotation
                row['actual_hand_mesh_clear']=True
                accepted.append((row['angle_rad'],-continuation['minimum_joint_margin_rad'],len(candidates),target))
            except ToolExecutionError as exc:row['collision_rejection']=str(exc)
        candidates.append(row)
    report=dict(measured_native_reference=measured,candidates=candidates,kinematic_candidate_only=True,
        native_grasp_not_established=True,actual_mesh_scope='incoming palm/fingers against props, outgoing full robot and table',
        obstacle_geometry_sources=obstacle_evidence)
    if not accepted:
        (policy.a.out/'E37-equivalent-side-wrist-screen.private.json').write_text(json.dumps(report,indent=2)+'\n')
        raise ToolExecutionError('No continuous native-joint and actual-hand-mesh-safe equivalent side approach')
    _,_,index,target=min(accepted,key=lambda row:row[:2]);report['chosen_candidate']=index
    (policy.a.out/'E37-equivalent-side-wrist-screen.private.json').write_text(json.dumps(report,indent=2)+'\n')
    return target


def _native_boundary(policy,name):
    from .engineering_checkpoint import capture
    folder=policy.a.out/'checkpoints';folder.mkdir(exist_ok=True)
    checkpoint=capture(policy.c,name,context=dict(room=policy.c.room_id)if hasattr(policy.c,'room_id')else{})
    (folder/f'native-{policy.c.steps:04d}-{name}.private.json').write_text(json.dumps(checkpoint,indent=2)+'\n')


def move_tip(policy,side,tip,target,guard,tolerance=.002):
    target=np.asarray(target,float);history=[]
    for _ in range(240):
        guard();actual=np.asarray(policy.point(tip));error=target-actual;distance=float(np.linalg.norm(error))
        if np.max(abs(error))<=tolerance:return
        history.append(distance)
        required=min(.002,max(tolerance*.5,history[-20] *.1))if len(history)>=20 else None
        if len(history)>=20 and history[-20]-min(history[-5:])<required:
            raise ToolExecutionError('Actual driver target distance lacks effective 20-action progress')
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        policy.act(side,token,mm=min(policy.max_mm,abs(float(error[axis]))*1000.))
    raise ToolExecutionError('Actual driver target approach action bound exhausted')


def handoff(policy,old_ref,outgoing='right',incoming='left',*,native_motion=False,flip_empty_wrist=False,side_approach=False,side_approach_jaw_sign=None,incoming_already_at_safe_wrist=False,section='shaft'):
    if (outgoing,incoming)!=('right','left'):raise ToolExecutionError('Only reviewed right-to-left driver handoff is supported')
    actor=old_ref['actor'];obj=next(o for o in policy.spec['objects']if o['id']==actor)
    if obj['source_asset']['sha256']!=SOURCE:raise ToolExecutionError('Driver handoff source mesh identity changed')
    sections={'shaft':POINT,'handle0':[0.,-7.477380000000047e-05,1.04899999999776e-07]}
    if section not in sections:raise ValueError('Reviewed driver material section required')
    ref=dict(actor=actor,local=sections[section],jaw_axis_local=[0.,0.,1.])
    def outgoing_guard():
        policy.require_held(old_ref,outgoing)
        if policy.contact(actor,'table'):raise ToolExecutionError('Held driver touched table during real handoff')
    def move(side,target,guard=outgoing_guard):
        if native_motion:
            _native_boundary(policy,'before-transfer-translation')
            goals={s:policy.tip(s).copy()for s in(outgoing,incoming)};goals[side]=np.asarray(target)
            policy.a.move_smooth(goals,tolerance=.0015,guard=guard,max_speed=.06,max_acceleration=.25)
        else:policy.move(side,target,guard)
    outgoing_guard();policy.stage('checkpoint-e37-real-two-hand-driver-transfer')
    if not incoming_already_at_safe_wrist:policy.act(incoming,'RELEASE');outgoing_guard()
    elif any(b['grasp'][('left','right').index(incoming)]for b in policy.snapshot()[0].values()):
        raise ToolExecutionError('Safe-wrist resume requires an actual empty incoming hand')
    if native_motion:
        # Supersede an old, unfinished outgoing wrist goal through a real
        # guarded native hold before asking both arms to keep their positions.
        from .author_orientation import native_rotate
        policy.stage('checkpoint-e37-native-outgoing-achieved-pose-hold')
        receipt=native_rotate(policy.c,outgoing,np.eye(3),guard=outgoing_guard,
            position_tolerance=.002,orientation_tolerance=math.radians(1.))
        with (policy.a.out/'demo-actions.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(stage=policy.a.stage,control='private_continuous_outgoing_hold',side=outgoing,**receipt))+'\n')
        if not receipt['target_reached']:raise ToolExecutionError('Actual outgoing driver hold did not settle')
    target=policy.point(ref)
    # Arrive beside the held shaft, then descend in the empty lateral lane.
    # An overhead approach would traverse the outgoing palm/fingers.
    safe_y=float(target[1])+.14
    if not incoming_already_at_safe_wrist and policy.tip(incoming)[1]<safe_y:
        move(incoming,[policy.tip(incoming)[0],safe_y,policy.tip(incoming)[2]])
    height=max(float(target[2])+.065,float(policy.tip(incoming)[2]))
    if native_motion and not incoming_already_at_safe_wrist:
        # Rebend the empty arm before selecting its equivalent wrist branch.
        move(incoming,[min(-.25,float(policy.tip(incoming)[0])),max(.10,safe_y),height])
    elif not incoming_already_at_safe_wrist:move(incoming,[*policy.tip(incoming)[:2],height])
    history=[]
    if native_motion:
        from .author_orientation import native_rotate
        def rotate(delta):
            _native_boundary(policy,'before-transfer-rotation')
            outgoing_guard();receipt=native_rotate(policy.c,incoming,delta,guard=outgoing_guard,
                position_tolerance=.002,orientation_tolerance=math.radians(1.))
            with (policy.a.out/'demo-actions.private.jsonl').open('a')as stream:
                stream.write(json.dumps(dict(stage=policy.a.stage,control='private_continuous_empty_wrist',side=incoming,**receipt))+'\n')
            if not receipt['target_reached']:raise ToolExecutionError('Actual continuous empty-wrist target was not reached')
        if flip_empty_wrist:
            robot=policy.a.scene.robots[incoming];ids,_=robot.find_joints('panda_joint7')
            joint=float(robot.data.joint_pos[0,ids[0]]);home=float(policy.a.scene.embodiment.config['robots'][incoming]['initial_joints']['panda_joint7'])
            sense=-1. if home>=joint else 1.;a=sense*math.pi/2;c,s=math.cos(a),math.sin(a)
            half=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
            policy.stage('checkpoint-e37-real-empty-wrist-equivalent-half1');rotate(half)
            policy.stage('checkpoint-e37-real-empty-wrist-equivalent-half2');rotate(half)
        fingers=policy.a.finger_geometry(incoming)['fingers'];p=policy.tip(incoming)
        first=np.asarray(fingers[0]['body_origin_task_m']);second=np.asarray(fingers[1]['body_origin_task_m'])
        y=first-second;y/=np.linalg.norm(y);z=p-(first+second)/2;z-=y*float(z@y);z/=np.linalg.norm(z)
        x=np.cross(y,z);x/=np.linalg.norm(x);current=np.column_stack((x,y,np.cross(x,y)))
        desired=np.asarray(policy.snapshot()[0][actor]['mat'])[:,2].copy();desired[2]=0.;desired/=np.linalg.norm(desired)
        if desired@y<0:desired=-desired
        down=np.array([0.,0.,-1.]);target=(screened_side_approach_frame(policy,actor,incoming,current,side_approach_jaw_sign)
            if side_approach else np.column_stack((np.cross(desired,down),desired,down)))
        policy.stage('checkpoint-e37-actual-palm-side-before-transfer'if side_approach else'checkpoint-e37-actual-palm-down-before-transfer');rotate(target@current.T)
    for _ in range(0 if native_motion else 50):
        outgoing_guard();fingers=policy.a.finger_geometry(incoming)['fingers']
        actual=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m']);actual/=np.linalg.norm(actual)
        desired=np.asarray(policy.snapshot()[0][actor]['mat'])[:,2]
        if actual@desired<0:desired=-desired
        error=math.acos(float(np.clip(actual@desired,-1.,1.)));history.append(error)
        if error<=math.radians(4.):break
        if len(history)>=12 and history[-12]-min(history[-11:])<math.radians(1.):raise ToolExecutionError('Empty incoming fingers failed to align for driver handoff')
        axis=np.cross(actual,desired);component=int(np.argmax(abs(axis)))
        token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[component][int(axis[component]<0)]
        policy.act(incoming,token,degrees=8.)
    else:
        if not native_motion:raise ToolExecutionError('Incoming hand alignment bound exhausted')
    target=policy.point(ref);safe_y=float(target[1])+.14
    move(incoming,[target[0],safe_y,height])
    move(incoming,[target[0],safe_y,target[2]])
    # The target is measured from the outgoing-held object after every step.
    if native_motion:move(incoming,policy.point(ref))
    for _ in range(0 if native_motion else 90):
        outgoing_guard();error=policy.point(ref)-policy.tip(incoming)
        if np.max(abs(error))<=.0015:break
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        policy.act(incoming,token,mm=min(5.,abs(float(error[axis]))*1000.))
    else:
        if not native_motion:raise ToolExecutionError('Incoming hand failed to reach actual separate driver handle section')
    if np.max(abs(policy.point(ref)-policy.tip(incoming)))>.0015:raise ToolExecutionError('Incoming actual TCP missed the separate driver section')
    stable=0
    for _ in range(8):
        outgoing_guard();policy.act(incoming,'GRASP');outgoing_guard()
        stable=stable+1 if policy.held(ref,incoming)else 0
        if stable>=3:break
    else:raise ToolExecutionError('Incoming hand did not establish stable actual bilateral driver grip')
    policy.require_held(ref,incoming);policy.act(outgoing,'RELEASE');policy.require_held(ref,incoming)
    move(outgoing,policy.tip(outgoing)+[0.,0.,.065],lambda:policy.require_held(ref,incoming))
    policy.require_held(ref,incoming)
    (policy.a.out/'E37-real-handoff.private.json').write_text(json.dumps(dict(source_mesh_sha256=SOURCE,
        incoming=incoming,outgoing=outgoing,source_handle_section_local=ref['local'],
        actual_stable_incoming_grip_observations=stable,actual_grasps=policy.snapshot()[0][actor]['grasp'],
        source_initial_episode=False,diagnostic_only=True,no_native_state_written=True,native_continuous_motor_primitives=native_motion),indent=2)+'\n')
    return ref,incoming
