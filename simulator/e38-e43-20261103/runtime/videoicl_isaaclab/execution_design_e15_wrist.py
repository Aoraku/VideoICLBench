"""E15 v3 engineering empty-hand finger assignment before half-turns.

Native IK is a rejection filter, never a joint command or collision certificate.
The only physical changes below are recorded public empty-hand actions. Original
object poses, source goals, native scoring and the positive A route stay intact.
"""
import json
import math
import numpy as np
from .execution_design import REVISION_V3, source_sha256
from .realworld_tool_expert import _axis_rotation


def _numpy(value):
    if hasattr(value, 'detach'):value=value.detach()
    if hasattr(value, 'cpu'):value=value.cpu()
    return np.asarray(value, float)


def _wrap(value):return float((value+math.pi)%(2*math.pi)-math.pi)


def _wrist(author, side):
    robot=author.scene.robots[side];ids,_=robot.find_joints('panda_joint7')
    if len(ids)!=1:raise RuntimeError('Actual E15 Panda wrist joint required')
    j=ids[0]
    return float(_numpy(robot.data.joint_pos)[0,j]), _numpy(robot.data.soft_joint_pos_limits)[0,j]


def _guard_public_step(author,side,token,degrees):
    """The normal controller runs local IK at every physics tick; inspect its
    refusal receipt and all measured joints after each accepted public action.
    No unbounded retry of an unsafe intermediate wrist pose is allowed.
    """
    author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
    robot=author.scene.robots[side];ids,names=robot.find_joints('panda_joint[1-7]')
    if len(ids)!=7:raise RuntimeError('All seven measured E15 arm joints required')
    q=_numpy(robot.data.joint_pos)[0,ids];limits=_numpy(robot.data.soft_joint_pos_limits)[0,ids]
    if not np.isfinite(q).all() or np.any(q<=limits[:,0]+.005) or np.any(q>=limits[:,1]-.005):
        raise RuntimeError('E15 measured intermediate arm joint reached its limit')
    feedback=author.c.action_feedback()['control_feedback'][side]
    row=dict(stage=author.stage,side=side,token=token,joint_names=list(names),q=q.tolist(),
             limits=limits.tolist(),public_local_ik_feedback=feedback)
    with (author.out/'e15-wrist-public-steps.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    if feedback.get('status')=='blocked' or feedback.get('joint_limit_names') or feedback.get('consecutive_ik_refusals',0)>0:
        raise RuntimeError('E15 public local IK rejected an intermediate wrist step')


def _scope(author):
    s=author.scene.spec;d=s.get('execution_design',{})
    if (s.get('id')!='E15' or d.get('revision')!=REVISION_V3
            or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or author.scene.embodiment.name!='franka'
            or not getattr(author,'_execution_design_reference_authorized',False)
            or not getattr(author,'control_report',{}).get('engineering_reference_only')
            or getattr(author,'smooth',False)):
        raise ValueError('Checksum-pinned E15 v3 public engineering wrist control required')


def prepare_empty(author, side, name, goal, clearance, ik_probe=None):
    """Swap opposed fingers before a required near-180-degree object rotation.

    Call after normal empty gripper-axis alignment and before source descent.
    Returns without actions for ordinary A goals. The caller keeps original
    clearance, final object orientation, public transfer and scoring unchanged.
    """
    _scope(author)
    if 'roll'in goal or 'pitch'in goal or 'yaw'not in goal:
        raise ValueError('E15 source yaw-only goal required')
    state,contacts=author.c.snapshot();body=state[name]
    yaw=math.atan2(body['mat'][1,0],body['mat'][0,0])
    wanted=_wrap(float(goal['yaw'])-yaw)
    if abs(wanted)<math.radians(150):return None
    if any(any(b.get('grasp',[]))for b in state.values()):
        raise RuntimeError('E15 equivalent finger assignment requires both hands empty')
    if frozenset((name,'table'))not in contacts:
        raise RuntimeError('E15 source must remain genuinely supported before finger swap')
    if ik_probe is None:
        from .execution_design_e15_path import inspect_path
        ik_probe=inspect_path
    q,limits=_wrist(author,side)
    turn=math.copysign(math.pi,q if abs(q)>.001 else -wanted)
    if not limits[0]+.08<q-turn<limits[1]-.08:
        raise RuntimeError('No conservative empty E15 wrist half-turn within actual limits')
    current=np.asarray(author.tcp_rotation_task(side),float)
    if float(current[2,2])>-.95:
        raise RuntimeError('E15 wrist half-turn requires a measured downward palm')
    chosen=_axis_rotation([0,0,1],turn)@current
    obj=next(o for o in author.scene.spec['objects']if o['id']==name)
    offset=np.asarray(body['mat'])@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
    pickup=np.asarray(body['pos'])+offset
    target=next(z for z in author.scene.spec['zones']if z['id']==goal['target'])
    goal_rotation=_axis_rotation([0,0,1],float(goal['yaw']))
    final_offset=goal_rotation@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
    final_xy=np.asarray(goal.get('placement_xy',target['xy']))+final_offset[:2]
    # Source and loaded endpoints are checked using the actual native Jacobian.
    # Check the physically intended half-turn arc, not only its final SO(3) pose.
    # After swapping opposed fingers the object turns opposite the empty turn.
    loaded_turn=wanted
    if loaded_turn*turn>0:loaded_turn-=math.copysign(2*math.pi,loaded_turn)
    final_hand=goal_rotation@np.asarray(body['mat']).T@chosen
    floor=float(author.floor_clear_tcp(side))
    source_z=max(float(pickup[2]),floor)
    final_z=max(float(target.get('surface_z',.8))+float(obj['size'][2])+float(final_offset[2])+.004,floor)
    tip=np.asarray(author.tip(side),float);empty_height=max(.96,float(tip[2]))
    points=[dict(position=[*tip[:2],empty_height],rotation=(_axis_rotation([0,0,1],turn*fraction)@current).tolist())
            for fraction in np.linspace(0.,1.,7)]
    if author.scene.spec.get('variant')=='B':
        points.append(dict(position=[*pickup[:2],empty_height],rotation=chosen.tolist()))
    points.append(dict(position=[*pickup[:2],source_z],rotation=chosen.tolist()))
    for fraction in np.linspace(0.,1.,7):
        r=_axis_rotation([0,0,1],loaded_turn*fraction)@chosen
        points.append(dict(position=[*pickup[:2],float(clearance)],rotation=r.tolist()))
    points.extend([dict(position=[*final_xy,float(clearance)],rotation=final_hand.tolist()),
                   dict(position=[*final_xy,final_z],rotation=final_hand.tolist())])
    candidates=ik_probe(author,author.c,side,points)
    row=dict(object=name,side=side,requested_object_yaw_delta_rad=wanted,
        empty_turn_rad=turn,planned_loaded_turn_rad=loaded_turn,before_joint7_rad=q,
        limits_rad=limits.tolist(),candidate_targets=points,candidates=candidates,
        source_state_written=False,collision_verified=False,native_route_passed=False)
    def record():
        with (author.out/'e15-empty-wrist.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    if (len(candidates)!=len(points) or not all(r.get('kinematically_reachable')
            and r.get('minimum_joint_margin_rad',-1)>.02 for r in candidates)):
        row['rejected']='native_ik_endpoint_or_joint_margin';record()
        raise RuntimeError('E15 empty-finger branch has unverified native endpoints')
    author.stage='e15-empty-finger-assignment-'+name
    author.move_generated({side:[*tip[:2],empty_height]})
    # Public yaw commands follow the selected direction and measured incremental
    # hand yaw. No robot joint-state or controller-target writes are used.
    initial=np.asarray(author.tip(side),float);previous=np.asarray(author.tcp_rotation_task(side),float)
    # Raising the empty hand can finish the prior controller's angular goal.
    # Rebase the remaining turn on the measured post-raise pose, preserving the
    # selected winding and the originally checked final orientation.
    yaw_residual=math.atan2((chosen@previous.T)[1,0],(chosen@previous.T)[0,0])
    remaining=turn+_wrap(yaw_residual-turn)
    row['after_raise_remaining_turn_rad']=remaining
    for _ in range(160):
        actual,actual_contacts=author.c.snapshot()
        if (any(any(b.get('grasp',[]))for b in actual.values())
                or frozenset((name,'table'))not in actual_contacts):
            raise RuntimeError('E15 source support/empty-hand invariant changed during swap')
        geometry=author.finger_geometry(side)
        if (geometry.get('source')!='actual_collision_mesh_current_body_pose'
                or geometry['lowest_z_task_m']<.85
                or np.linalg.norm(np.asarray(author.tip(side))-initial)>.025):
            raise RuntimeError('E15 empty rotation lost measured geometric clearance')
        q_now,_=_wrist(author,side)
        if not limits[0]+.02<q_now<limits[1]-.02:
            raise RuntimeError('E15 empty wrist approached actual joint limit')
        if abs(remaining)<math.radians(1):
            error=math.acos(float(np.clip((np.trace(chosen@previous.T)-1)/2,-1,1)))
            if error>math.radians(2):raise RuntimeError('E15 measured equivalent hand pose failed')
            row.update(after_joint7_rad=q_now,actual_pose_error_rad=error,public_actions_only=True)
            record();author.control_report.setdefault('e15_empty_wrist',[]).append(row)
            author._e15_wrist_branch=dict(object=name,side=side,goal_yaw=float(goal['yaw']),loaded_turn=loaded_turn)
            if author.scene.spec.get('variant')=='B':
                author._e15_wrist_branch['empty_height']=empty_height
            return row
        token='ROTATE_CCW'if remaining>0 else'ROTATE_CW'
        _guard_public_step(author,side,token,min(4.,max(.5,abs(math.degrees(remaining)))))
        current=np.asarray(author.tcp_rotation_task(side),float)
        delta=current@previous.T;advanced=math.atan2(delta[1,0],delta[0,0])
        if advanced*turn<-.002:raise RuntimeError('E15 actual wrist moved opposite the selected branch')
        remaining-=advanced;previous=current
    raise RuntimeError('E15 public empty wrist half-turn did not converge')



def prepared_empty_height(author, side, name, goal, fallback):
    """B's caller follows the exact empty approach plane checked before swap.

    Loaded carry and all C/A callers retain their original clearance.
    """
    if author.scene.spec.get('id')!='E15' or author.scene.spec.get('variant')!='B':
        return float(fallback)
    branch=getattr(author,'_e15_wrist_branch',None)
    if not branch:return float(fallback)
    _scope(author)
    if (branch.get('object')!=name or branch.get('side')!=side
            or abs(_wrap(float(goal.get('yaw',float('nan')))-branch['goal_yaw']))>1e-6):
        raise RuntimeError('E15 B prepared empty height belongs to another source/goal')
    height=branch.get('empty_height')
    if type(height)not in(float,int) or not math.isfinite(height) or height<.96:
        raise RuntimeError('E15 B actual screened empty height is unavailable')
    return float(height)


def rotate_prepared_payload(author, name, side, goal):
    """Follow the selected winding through real held-body yaw feedback.

    Returns False without actions unless prepare_empty measured and recorded a
    successful swap for exactly this object/side/goal. This companion is needed
    because a generic SO(3) logarithm is ambiguous at a 180-degree rotation.
    """
    branch=getattr(author,'_e15_wrist_branch',None)
    if not branch:return False
    _scope(author)
    if (branch['object']!=name or branch['side']!=side
            or abs(_wrap(float(goal.get('yaw',float('nan')))-branch['goal_yaw']))>1e-6):
        raise RuntimeError('E15 prepared wrist branch does not match the original held goal')
    author.__dict__.pop('_e15_wrist_branch',None)
    state,_=author.c.snapshot();body=state[name]
    initial_yaw=math.atan2(body['mat'][1,0],body['mat'][0,0])
    turn=_wrap(branch['goal_yaw']-initial_yaw)
    if turn*branch['loaded_turn']<0:turn+=math.copysign(2*math.pi,branch['loaded_turn'])
    remaining=turn;previous=initial_yaw;tip=np.asarray(author.tip(side),float)
    _,limits=_wrist(author,side);idx=0 if side=='left'else 1
    desired=_axis_rotation([0,0,1],branch['goal_yaw'])
    for _ in range(160):
        state,contacts=author.c.snapshot();body=state[name]
        if (not body['grasp'][idx] or not all(frozenset((name,f'{side}_finger{i}'))in contacts for i in (1,2))):
            raise RuntimeError('E15 actual bilateral held contact lost during selected turn')
        q,_=_wrist(author,side)
        if not limits[0]+.015<q<limits[1]-.015:
            raise RuntimeError('E15 loaded selected turn approached actual wrist limit')
        if np.linalg.norm(np.asarray(author.tip(side))-tip)>.03:
            raise RuntimeError('E15 loaded turn left measured TCP envelope')
        error=math.acos(float(np.clip((np.trace(desired@np.asarray(body['mat']).T)-1)/2,-1,1)))
        if abs(remaining)<math.radians(3) and error<math.radians(6):
            author.control_report.setdefault('e15_loaded_wrist',[]).append(dict(object=name,side=side,
                selected_turn_rad=turn,remaining_yaw_rad=remaining,actual_orientation_error_rad=error,
                final_joint7_rad=q,public_actions_only=True,native_route_passed=False))
            return True
        token='ROTATE_CCW'if remaining>0 else'ROTATE_CW'
        _guard_public_step(author,side,token,min(4.,max(.5,abs(math.degrees(remaining)))))
        state,_=author.c.snapshot();rotation=state[name]['mat']
        current=math.atan2(rotation[1,0],rotation[0,0]);advanced=_wrap(current-previous)
        if advanced*turn<-.002:raise RuntimeError('E15 payload yaw moved opposite the selected branch')
        remaining-=advanced;previous=current
    raise RuntimeError('E15 actual selected payload turn did not converge')
