"""Engineering E37: real second-hand support while the driving wrist unwinds.

Adapted from the earlier physical E37 regrip author, with explicit active and
support sides. No object, joint state, thread history or physical coefficient
is assigned. Planning certificates and every motor receipt remain separate.
"""
from contextlib import contextmanager
import json
import math
import numpy as np


def _scope(p):
    s=p.spec
    if not (p.a.control_report.get('engineering_reference_only') is True
            and s.get('id')=='E37' and s.get('seed')==4201
            and s.get('execution_design',{}).get('condition')=='R'
            and s['execution_design'].get('revision')=='embodied50-execution-v3-20261102'):
        raise ValueError('Explicit E37 R4201 engineering author required')


def _record(p,name,row):
    with (p.a.out/name).open('a') as f:
        f.write(json.dumps(dict(stage=p.a.stage,step=p.c.steps,**row),
                           default=lambda x:x.tolist())+'\n')


@contextmanager
def hold_measured_arm(p,side):
    """Command the measured q through the existing motor override, not state IO."""
    _scope(p)
    robot=p.a.scene.robots[side];ids=p.c.ids[side][0]
    q=robot.data.joint_pos[:,ids].clone()
    overrides=p.c._author_joint_override;previous=overrides.get(side)
    checkpointing=getattr(p.a,'_engineering_stage_checkpoints',False)
    p.a._engineering_stage_checkpoints=False
    overrides[side]=(q,q*0.)
    try:yield
    finally:
        if previous is None:overrides.pop(side,None)
        else:overrides[side]=previous
        pos,quat=p.c.pose(side);p.c.targets[side]=(pos.clone(),quat.clone())
        p.a._engineering_stage_checkpoints=checkpointing


def _boundary(p,stage,main_side,support_side,driver):
    from .engineering_checkpoint import capture
    checkpoint=capture(p.c,stage,context=dict(main_side=main_side,
        support_side=support_side,carried_payload=[driver,main_side],
        phase=stage,real_motor_hold_released_before_capture=True))
    folder=p.a.out/'checkpoints';folder.mkdir(exist_ok=True)
    (folder/(stage+'.private.json')).write_text(json.dumps(checkpoint,indent=2)+'\n')


def winding_room(q,limits,hand_rotation,axis,unscrew_direction):
    """Signed original-limit wrist reserve; other joints retain .12 rad."""
    q=np.asarray(q,float);limits=np.asarray(limits,float)
    hand_rotation=np.asarray(hand_rotation,float);axis=np.asarray(axis,float)
    if q.shape!=(7,) or limits.shape!=(7,2) or hand_rotation.shape!=(3,3) or axis.shape!=(3,):
        raise ValueError('Measured Panda q/limits/hand/axis dimensions required')
    if not all(np.isfinite(x).all()for x in(q,limits,hand_rotation,axis)):
        raise ValueError('Finite native kinematics required')
    if np.any(limits[:,0]>=limits[:,1]) or np.any(q<limits[:,0]) or np.any(q>limits[:,1]):
        raise ValueError('Measured joints must remain in original limits')
    if unscrew_direction not in(-1.,1.):raise ValueError('Original screw direction must be signed unit')
    if np.linalg.norm(axis)<1e-12:raise ValueError('Nonzero actual screw axis required')
    axis=axis/np.linalg.norm(axis)
    margins=np.minimum(q-limits[:,0],limits[:,1]-q)
    sign=float((axis*unscrew_direction)@hand_rotation[:,2])
    room=float(q[-1]-limits[-1,0] if sign<-.5 else
               limits[-1,1]-q[-1] if sign>.5 else margins[-1])
    other=float(np.min(margins[:-1]))
    return dict(wrist_room_rad=room,other_joint_margin_rad=other,
                admissible=room>=.7 and other>=.12,
                score=room+.25*other)


def predicted_turn_room(jacobian,q,limits,twist,damping,*,reserve=.03):
    """Instantaneous signed DLS prediction; never a finite path certificate."""
    j=np.asarray(jacobian,float);q=np.asarray(q,float)
    limits=np.asarray(limits,float);twist=np.asarray(twist,float)
    if j.shape!=(6,7) or q.shape!=(7,) or limits.shape!=(7,2) or twist.shape!=(6,):
        raise ValueError('Measured TCP Jacobian, original q/limits and world twist required')
    if not all(np.isfinite(x).all()for x in(j,q,limits,twist)):
        raise ValueError('Finite measured kinematics required')
    if not np.isfinite(damping) or damping<=0 or not 0<=reserve<=.03:
        raise ValueError('Original positive damping and bounded author reserve required')
    if np.any(limits[:,0]>=limits[:,1]) or np.any(q<limits[:,0]) or np.any(q>limits[:,1]):
        raise ValueError('Measured joints must remain in original limits')
    dq=j.T@np.linalg.solve(j@j.T+damping*damping*np.eye(6),twist)
    moving=np.abs(dq)>1e-12
    distance=np.where(dq>0,limits[:,1]-q,q-limits[:,0])
    room=np.full(7,np.inf)
    room[moving]=np.maximum(0.,distance[moving]-reserve)/np.abs(dq[moving])
    return dict(safe_angle_rad=float(np.min(room)),dq_dtheta=dq.tolist(),
                limiting_joint=int(np.argmin(room)) if moving.any() else None,
                reserve_rad=float(reserve),prediction_only=True)


def measured_turn_room(p,side,pivot,axis,pitch,unscrew_direction):
    """Predict impending stops from the current native hand Jacobian/TCP."""
    _scope(p)
    from .execution_design_jacobian_reference import capture
    if not np.isfinite(pitch) or pitch<=0 or unscrew_direction not in(-1.,1.):
        raise ValueError('Unchanged positive pitch and original signed turn required')
    measured=capture(p.a,p.c,side)
    tcp=np.asarray(measured['position']);axis=np.asarray(axis,float)
    if axis.shape!=(3,) or not np.isfinite(axis).all() or np.linalg.norm(axis)<1e-12:
        raise ValueError('Measured finite screw axis required')
    axis=axis/np.linalg.norm(axis);omega=axis*unscrew_direction
    twist=np.r_[np.cross(omega,tcp-np.asarray(pivot,float))+axis*pitch/(2*math.pi),omega]
    # Isaac's native hand Jacobian is at the rigid-body COM. The shared
    # capture routine verifies that COM against the native body witnesses
    # before shifting it to the measured TCP in the task frame.
    result=predicted_turn_room(measured['jacobian'],measured['q'],measured['limits'],twist,
        float(p.c.ik[side].cfg.ik_params['lambda_val']))
    _record(p,'E37-current-directional-turn-room.private.jsonl',dict(side=side,
        jacobian_reference=measured['reference'],**result))
    return result


def helical_turn(p,ref,head,axis,degrees,pitch,unscrew_direction,*,
                 side='left',extra_guard=None):
    """One real short rotation with the unchanged thread's axial pitch feed."""
    _scope(p)
    from .author_orientation import native_rotate
    from .realworld_tool_expert import ToolExecutionError,_axis_rotation
    from .engineering_native_tick import diagnostic_tick_scope
    if not 0<float(degrees)<=30. or not np.isfinite(pitch) or pitch<=0:
        raise ValueError('Short positive turn and original positive thread pitch required')
    if unscrew_direction not in(-1.,1.):raise ValueError('Original signed turn direction required')
    axis=np.asarray(axis,float)
    if axis.shape!=(3,) or not np.isfinite(axis).all() or np.linalg.norm(axis)<1e-12:
        raise ValueError('Measured finite screw axis required')
    axis=axis/np.linalg.norm(axis)
    if p.c.steps>=p.spec.get('expert_action_budget',3000):
        raise ToolExecutionError('E37 engineering motor-action budget exhausted')
    def guard():
        p.require_held(ref,side)
        if extra_guard is not None:extra_guard()
    pivot=np.asarray(head()if callable(head)else head,float)
    feed=axis*pitch*float(degrees)/360.
    delta=_axis_rotation(axis,math.radians(float(degrees)*unscrew_direction))
    tick_before=p.c.physics_ticks;step_before=p.c.steps
    _record(p,'E37-helical-motor-commands.private.jsonl',dict(side=side,
        pivot_task=pivot,axis_task=axis,degrees=float(degrees),pitch_m=float(pitch),
        unscrew_direction=unscrew_direction,axial_translation_task=feed,
        native_physics_tick_before=tick_before,public_gui_action=False))
    previous=getattr(p.a,'_engineering_e37_verified_path',False)
    p.a._engineering_e37_verified_path=True
    try:
        with diagnostic_tick_scope(p.a,reference_authorization=not bool(
                getattr(p.c,'_engineering_diagnostic_only',False))):
            result=native_rotate(p.c,side,delta,guard=guard,pivot_task=pivot,
                                 axial_translation_task=feed)
    except Exception as exc:
        _record(p,'E37-helical-motor-failures.private.jsonl',dict(side=side,
            step_before=step_before,native_physics_tick_before=tick_before,
            native_physics_tick_after=p.c.physics_ticks,error=repr(exc)))
        raise
    finally:p.a._engineering_e37_verified_path=previous
    _record(p,'E37-helical-motor-receipts.private.jsonl',dict(side=side,
        native_physics_tick_before=tick_before,native_physics_tick_after=p.c.physics_ticks,
        native_motor_receipt=result,public_gui_action=False))
    if not result['target_reached']:
        raise ToolExecutionError('Actual helical motor segment did not reach its tracking envelope')
    return result


def _hand(p,side):
    return np.asarray(p.a.tcp_rotation_task(side),float)


def _execute(p,side,proposal,guard):
    from .engineering_native_tick import diagnostic_tick_scope
    from .realworld_tool_expert import ToolExecutionError
    if proposal.get('status')!='Success' or proposal.get('verified') is not True:
        raise ToolExecutionError('Real regrip has no verified full-world path')
    previous=getattr(p.a,'_engineering_e37_verified_path',False)
    p.a._engineering_e37_verified_path=True
    try:
        with diagnostic_tick_scope(p.a,reference_authorization=not bool(
                getattr(p.c,'_engineering_diagnostic_only',False))):
            return p.a.execute_joint_path(side,proposal,guard=guard)
    finally:p.a._engineering_e37_verified_path=previous


def _plan(p,side,point,rotation,*,driver=None,screw=None):
    from .author_mplib_planner import plan,_quat
    request=dict(position=np.asarray(point,float).tolist())
    if screw is not None:
        if driver is None:raise ValueError('A reviewed held-driver contact identity is required')
        request['allowed_contact_pairs']=[[driver,screw]]
    proposed=plan(p.a.scene,p.c,side,request,
                  task_tcp_quaternion=_quat(rotation).tolist())
    _record(p,'E37-actual-regrip-plans.private.jsonl',dict(side=side,
        target_task=request,hand_rotation=rotation,status=proposed.get('status'),
        verified=proposed.get('verified'),diagnostics=proposed.get('diagnostics')))
    return proposed


def _opposed_close(p,ref,side,guard,*,start=.024,minimum=.001):
    from .realworld_tool_expert import ToolExecutionError
    count=0
    for _ in range(6):
        guard();p.act(side,'GRASP');guard()
        sensor,labels=p.a.scene.contacts[ref['actor']]
        matrix=sensor.data.force_matrix_w[0].sum(axis=0).detach().cpu().numpy()
        forces=[np.asarray(matrix[labels.index(side+'_finger'+str(i))],float)for i in(1,2)]
        norms=[float(np.linalg.norm(f))for f in forces]
        opposition=float(-forces[0]@forces[1]/max(norms[0]*norms[1],1e-12))
        valid=bool(p.held(ref,side)and min(norms)>.7 and opposition>.7)
        count=count+1 if valid else 0
        _record(p,'E37-actual-support-grips.private.jsonl',dict(side=side,
            command='GRASP',normal_forces_n=forces,opposition=opposition,
            actual_two_pad_grip=valid,fast_standard_close=True))
        if count>=2:return
    # A partly settled real grasp must not be reopened by the fallback.
    # Continue closing from its actual native opening instead.
    robot=p.a.scene.robots[side]
    finger_ids=p.c.ids[side][1]
    actual=robot.data.joint_pos[0,finger_ids].detach().cpu().numpy()
    count=0;opening=min(start,float(np.mean(actual)))
    for _ in range(60):
        guard();p.c.grips[side]=opening;p.act();guard()
        sensor,labels=p.a.scene.contacts[ref['actor']]
        matrix=sensor.data.force_matrix_w[0].sum(axis=0).detach().cpu().numpy()
        forces=[np.asarray(matrix[labels.index(side+'_finger'+str(i))],float) for i in(1,2)]
        norms=[float(np.linalg.norm(f))for f in forces]
        opposition=float(-forces[0]@forces[1]/max(norms[0]*norms[1],1e-12))
        valid=bool(p.held(ref,side) and min(norms)>.7 and opposition>.7)
        count=count+1 if valid else 0
        _record(p,'E37-actual-support-grips.private.jsonl',dict(side=side,
            commanded_half_opening_m=opening,normal_forces_n=forces,
            opposition=opposition,actual_two_pad_grip=valid))
        if count>=3:return
        if not valid:opening=max(minimum,opening-.0005)
    raise ToolExecutionError('Real regrip never established opposed native pad forces')


def regrip(p,ref,tip,axis,socket_geometry,*,main_side='left',
           support_local=None,screw=None,unscrew_direction=1.,extra_guard=None,resume_stage=None):
    """Physically support, open/reset/regrasp, then withdraw the other hand.

    Caller supplies the unchanged socket predicate and the current screw ID.
    A tool/screw planning contact must also be explicitly reviewed in the
    job's planner profile. A loss of socket/grip ends this suffix immediately.
    """
    _scope(p)
    from .realworld_tool_expert import ToolExecutionError,_axis_rotation
    if main_side not in('left','right'):raise ValueError('Explicit driving hand required')
    if resume_stage not in(None,'main_release'):raise ValueError('Explicit already-double-held regrip boundary required')
    support_side='right'if main_side=='left'else'left';name=ref['actor']
    axis=np.asarray(axis,float);axis/=np.linalg.norm(axis)
    # Original wood-handle station, spatially separated from the source
    # primary grasp at local X=-.05926. No new collision geometry is created.
    support=dict(actor=name,local=(list(support_local) if support_local is not None
                                  else[-.025,-.00010791,-.00007562]))

    def base_guard():
        if extra_guard is not None:extra_guard()
        if not socket_geometry():
            raise ToolExecutionError('Actual driver left original socket during physical wrist reset')

    def main_held():base_guard();p.require_held(ref,main_side)
    def support_held():base_guard();p.require_held(support,support_side)

    if resume_stage=='main_release':
        main_held();support_held();support_hand=_hand(p,support_side)
    else:
        p.stage('e37-real-'+support_side+'-wood-handle-support')
        with hold_measured_arm(p,main_side):
            p.act(support_side,'RELEASE');main_held();accepted=None;support_hand=None
            for yaw in(0.,math.pi/2,-math.pi/2,math.pi):
                z=np.array([math.cos(yaw),math.sin(yaw),0.]);y=np.array([-z[1],z[0],0.])
                for sign in(1.,-1.):
                    hand=np.column_stack((np.cross(sign*y,z),sign*y,z))
                    proposal=_plan(p,support_side,p.point(support),hand)
                    if proposal.get('status')=='Success'and proposal.get('verified')is True:
                        accepted=proposal;support_hand=hand;break
                if accepted is not None:break
            if accepted is None:raise ToolExecutionError('No verified original-handle support approach')
            _execute(p,support_side,accepted,main_held)
            _opposed_close(p,support,support_side,main_held)
            support_held()
    _boundary(p,'e37-both-held-before-main-release',main_side,support_side,name)

    p.stage('e37-real-'+main_side+'-empty-wrist-reset')
    with hold_measured_arm(p,support_side):
        old=_hand(p,main_side);p.act(main_side,'RELEASE');support_held()
        if p.held(ref,main_side):raise ToolExecutionError('Driving hand did not actually release')
        clearance=p.tip(main_side)+axis*.07
        proposal=_plan(p,main_side,clearance,old)
        _execute(p,main_side,proposal,support_held)
        robot=p.a.scene.robots[main_side];ids=p.c.ids[main_side][0]
        limits=robot.data.soft_joint_pos_limits[0,ids].detach().cpu().numpy()
        accepted=None
        # Stop at the first complete verified winding with useful reserve.
        # Do not spend physical attempts on other equivalent empty headings.
        for angle in(-unscrew_direction*math.pi/2,math.pi,unscrew_direction*math.pi/2,0.,2*math.pi/3,-2*math.pi/3):
            desired=_axis_rotation(axis,angle)@old
            proposal=_plan(p,main_side,p.point(ref),desired)
            if proposal.get('status')!='Success'or proposal.get('verified')is not True:continue
            room=winding_room(proposal['position'][-1],limits,desired,axis,unscrew_direction)
            _record(p,'E37-actual-reset-reserve.private.jsonl',dict(side=main_side,
                angle_rad=angle,**room))
            if room['admissible']:accepted=proposal;break
        if accepted is None:raise ToolExecutionError('No verified handle regrasp with original-limit reserve')
        _execute(p,main_side,accepted,support_held)
        _opposed_close(p,ref,main_side,support_held)
        main_held()
    _boundary(p,'e37-main-regrasped-before-support-release',main_side,support_side,name)

    p.stage('e37-real-'+support_side+'-support-withdrawal')
    with hold_measured_arm(p,main_side):
        p.act(support_side,'RELEASE');main_held()
        if p.held(support,support_side):raise ToolExecutionError('Supporting hand did not actually release')
        target=p.tip(support_side)-support_hand[:,2]*.09
        proposal=_plan(p,support_side,target,_hand(p,support_side))
        _execute(p,support_side,proposal,main_held)
    main_held()
    _record(p,'E37-real-regrip-completed.private.jsonl',dict(main_side=main_side,
        support_side=support_side,driver=name,screw=screw,caller_reset_geometry_condition_verified=True,
        state_written=False,thread_history_restored=False))
