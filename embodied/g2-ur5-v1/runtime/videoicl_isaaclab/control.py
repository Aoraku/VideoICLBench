"""Bounded Cartesian actions using Isaac Lab's native Jacobian IK controller."""
import math
import torch
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
from isaaclab.utils.math import apply_delta_pose, subtract_frame_transforms, matrix_from_quat, quat_apply, skew_symmetric_matrix
try:
    from isaaclab.utils.math import quat_apply_inverse
except ImportError:
    # Isaac Lab 2.1 / Isaac Sim 4.5 uses this name for the same wxyz
    # quaternion inverse rotation. Preserve the actual coordinate transform.
    from isaaclab.utils.math import quat_rotate_inverse as quat_apply_inverse
from .evaluator import Evaluator

MOTION={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1),'ROTATE_CCW':(5,1),'ROTATE_CW':(5,-1)}
MOTION.update(PITCH_UP=(4,1),PITCH_DOWN=(4,-1),ROLL_LEFT=(3,1),ROLL_RIGHT=(3,-1))
TOKENS={'STILL','GRASP','RELEASE',*MOTION,*('MV_'+x for x in MOTION if not x.startswith('ROTATE'))}

def pose_residual(position, quaternion, target_position, target_quaternion):
    """Base-frame position and shortest-axis orientation residual (wxyz)."""
    a=target_quaternion; b=quaternion.clone(); b[...,1:]=-b[...,1:]
    w=a[...,:1]*b[...,:1]-(a[...,1:]*b[...,1:]).sum(-1,keepdim=True)
    v=a[...,:1]*b[...,1:]+b[...,:1]*a[...,1:]+torch.cross(a[...,1:],b[...,1:],dim=-1)
    v=torch.where(w<0,-v,v); w=w.abs()
    length=v.norm(dim=-1,keepdim=True)
    angle=2*torch.atan2(length,w.clamp_min(1e-12))
    rotation=v*torch.where(length>1e-8,angle/length.clamp_min(1e-12),torch.full_like(length,2.))
    return torch.cat((target_position-position,rotation),dim=-1)


def bounded_cartesian_delta(jacobian, residual, lower, upper, damping=.01):
    """Conservative active-set damped IK; joint bounds participate in every solve.

    Bound variables remain fixed during this small solve. This is deliberately
    conservative (not an optimality claim); the caller rejects unsafe Cartesian
    directions instead of post-clipping a nominally valid unconstrained solution.
    All loops stay on the tensor device; no per-tick CPU transfer is needed.
    """
    lower=lower.to(jacobian);upper=upper.to(jacobian)
    n=jacobian.shape[-1]; fixed=torch.zeros_like(lower,dtype=torch.bool)
    value=torch.zeros_like(lower); eye=torch.eye(n,device=jacobian.device,dtype=jacobian.dtype)
    for _ in range(n+1):
        free=(~fixed).to(jacobian.dtype)
        J=jacobian*free.unsqueeze(-2)
        rhs=residual-(jacobian@value.unsqueeze(-1)).squeeze(-1)
        h=J.transpose(-1,-2)@J+damping*damping*eye
        step=torch.linalg.solve(h,(J.transpose(-1,-2)@rhs.unsqueeze(-1))).squeeze(-1)*free
        candidate=value+step
        violation=(candidate<lower)|(candidate>upper)
        newly=violation&(~fixed)
        value=torch.where(newly,torch.maximum(lower,torch.minimum(upper,candidate)),value)
        fixed=fixed|newly
    result=value+step* (~fixed).to(step.dtype)
    # Numerical guard only; a violation is refused, never independently clipped.
    feasible=((result>=lower-1e-7)&(result<=upper+1e-7)).all(-1)
    return torch.where(feasible.unsqueeze(-1),result,torch.zeros_like(result)),feasible


def public_motion_guard(residual,predicted,feasible,rotation_command=False):
    """Direction/progress checks including sub-millimeter and small-angle moves.

    Does not claim nonlinear collision safety. A zero requested residual permits
    a zero prediction; a nonzero explicit command requires positive progress.
    """
    import math
    finite=torch.isfinite(residual).all(-1)&torch.isfinite(predicted).all(-1)
    position=residual[...,:3];distance=position.norm(dim=-1)
    axis=position/distance.clamp_min(1e-12).unsqueeze(-1)
    forward=(predicted[...,:3]*axis).sum(-1)
    lateral=(predicted[...,:3]-forward.unsqueeze(-1)*axis).norm(dim=-1)
    # Explicit rotation holds position within the existing 2 mm envelope.
    # Micrometer FK/drive drift must not compete with angular progress; actual
    # translation commands retain their strict positive direction requirement.
    rotation_hold=rotation_command&(distance<=.002)
    translating=(distance>1e-7)&(~rotation_hold)
    wrong_direction=translating&((forward<=1e-10)|(forward>distance+1e-6)|
        (lateral>torch.maximum(torch.full_like(distance,.0005),forward*.25)))
    unwanted_translation=(~translating)&(predicted[...,:3].norm(dim=-1)>.001)
    unwanted_translation=unwanted_translation|(rotation_hold&
        ((position-predicted[...,:3]).norm(dim=-1)>.002))
    rotation=residual[...,3:];angle=rotation.norm(dim=-1)
    angular_axis=rotation/angle.clamp_min(1e-12).unsqueeze(-1)
    angular_forward=(predicted[...,3:]*angular_axis).sum(-1)
    angular_lateral=(predicted[...,3:]-angular_forward.unsqueeze(-1)*angular_axis).norm(dim=-1)
    rotating=angle>1e-7
    wrong_rotation=rotation_command&rotating&((angular_forward<=1e-10)|
        (angular_forward>angle+1e-6)|
        (angular_lateral>torch.maximum(torch.full_like(angle,1e-4),angular_forward*.25)))
    unwanted_rotation=rotation_command&(~rotating)&(predicted[...,3:].norm(dim=-1)>1e-6)
    old_orientation=angle>math.radians(20.)
    return feasible&finite&(~wrong_direction)&(~unwanted_translation)&(~wrong_rotation)&(~unwanted_rotation)&((~old_orientation)|rotation_command)

def releasing_bounded_delta(jacobian, residual, lower, upper, damping=.01):
    """Feasible active-set box QP with constraint release (batched on device).

    Unlike clamping all violated joints permanently, advance to the first bound
    and release a bound when its gradient violates KKT. Finite iteration budget:
    returned validity means finite/bounded, not certified optimality/convergence.
    """
    lower, upper = lower.to(jacobian), upper.to(jacobian)
    n = jacobian.shape[-1]
    finite = (torch.isfinite(jacobian).all(dim=(-2,-1)) & torch.isfinite(residual).all(-1)
              & torch.isfinite(lower).all(-1) & torch.isfinite(upper).all(-1)
              & (lower <= upper).all(-1))
    J = torch.where(finite[...,None,None],jacobian,torch.zeros_like(jacobian))
    e = torch.where(finite[...,None],residual,torch.zeros_like(residual))
    lo = torch.where(finite[...,None],lower,torch.zeros_like(lower))
    hi = torch.where(finite[...,None],upper,torch.zeros_like(upper))
    eye = torch.eye(n,dtype=J.dtype,device=J.device)
    H = J.transpose(-1,-2) @ J + damping*damping*eye
    b = (J.transpose(-1,-2) @ e.unsqueeze(-1)).squeeze(-1)
    x = torch.maximum(lo,torch.minimum(hi,torch.zeros_like(lo)))
    fixed = (x <= lo) | (x >= hi)
    equal = hi == lo
    tiny = 1e-10 if J.dtype == torch.float64 else 1e-7
    for _ in range(4*n+4):
        gradient = (H @ x.unsqueeze(-1)).squeeze(-1)-b
        free = (~fixed).to(J.dtype)
        system = H * free.unsqueeze(-1)*free.unsqueeze(-2) + torch.diag_embed(fixed.to(J.dtype))
        step = torch.linalg.solve(system,(-gradient*free).unsqueeze(-1)).squeeze(-1)*free
        positive,negative = step>tiny,step<-tiny
        denominator = torch.where(positive|negative,step,torch.ones_like(step))
        ratios = torch.where(positive,(hi-x)/denominator,
                    torch.where(negative,(lo-x)/denominator,torch.full_like(step,float('inf'))))
        alpha = ratios.amin(-1).clamp(0.,1.)
        x = x+alpha.unsqueeze(-1)*step
        # Roundoff projection only; line search already respected every bound.
        x = torch.maximum(lo,torch.minimum(hi,x))
        hit = (ratios <= alpha.unsqueeze(-1)+tiny) & (positive|negative)
        fixed = fixed | hit | equal
        # At a free minimizer, free at most one incorrectly active constraint.
        gradient = (H @ x.unsqueeze(-1)).squeeze(-1)-b
        bad = torch.where(x<=lo+tiny,(-gradient).clamp_min(0),
                 torch.where(x>=hi-tiny,gradient.clamp_min(0),torch.zeros_like(gradient)))
        bad = torch.where(fixed & (~equal),bad,torch.zeros_like(bad))
        maximum,index = bad.max(-1)
        release = (alpha>=1.-tiny) & (maximum>tiny)
        chosen = torch.arange(n,device=J.device)==index.unsqueeze(-1)
        fixed = fixed & (~(chosen & release.unsqueeze(-1)))
    feasible = finite & torch.isfinite(x).all(-1) & ((x>=lower-1e-7)&(x<=upper+1e-7)).all(-1)
    return torch.where(feasible.unsqueeze(-1),x,torch.zeros_like(x)),feasible

def scaled_bounded_fallback(jacobian,residual,lower,upper,guard,rotation_command=False,damping=.01):
    """Try smaller task residuals in one batched solve; never change the goal.

    Scaling is an internal reference segment, not completion of the original
    command. The native controller must continue checking its measured endpoint.
    """
    scales=jacobian.new_tensor([1.,.5,.25,.125,.0625,.03125,.015625])
    count=len(scales)
    J=jacobian.unsqueeze(-3).expand(*jacobian.shape[:-2],count,*jacobian.shape[-2:])
    r=residual.unsqueeze(-2)*scales.unsqueeze(-1)
    lo=lower.unsqueeze(-2).expand_as(r[...,:1].expand(*r.shape[:-1],lower.shape[-1]))
    hi=upper.unsqueeze(-2).expand_as(lo)
    delta,valid=releasing_bounded_delta(J,r,lo,hi,damping)
    predicted=(J@delta.unsqueeze(-1)).squeeze(-1)
    original=residual.unsqueeze(-2).expand_as(r)
    safe=guard(original,predicted,valid,rotation_command)
    # Prefer the largest tried segment that passes the unchanged safety guard.
    choice=safe.to(torch.int64).argmax(-1)
    selected=delta.gather(-2,choice[...,None,None].expand(*choice.shape,1,delta.shape[-1])).squeeze(-2)
    allowed=safe.any(-1)
    return torch.where(allowed.unsqueeze(-1),selected,torch.zeros_like(selected)),allowed

def guarded_cartesian_delta(jacobian,residual,lower,upper,rotation_command=False,damping=.01):
    """Advance a large command by a direction-preserving feasible segment.

    Solving the full Cartesian displacement against one-tick velocity bounds
    can saturate several joints independently and destroy Cartesian direction.
    First search along the damped IK direction for the largest common scalar
    step satisfying *all* joint/velocity bounds. The unscaled original residual
    remains the safety reference, including stale orientation. If this line is
    blocked, the bounded re-solve may find a different safe direction; neither
    candidate is accepted without the unchanged Cartesian safety guard.
    """
    lower=lower.to(jacobian);upper=upper.to(jacobian)
    valid_input=(torch.isfinite(jacobian).all(dim=(-2,-1)) & torch.isfinite(residual).all(-1)
                 & torch.isfinite(lower).all(-1) & torch.isfinite(upper).all(-1) & (lower<=upper).all(-1))
    # Reject malformed samples independently before any dense solve. A bad
    # sample must not poison another arm or rely on backend NaN behaviour.
    jacobian=torch.where(valid_input[...,None,None],jacobian,torch.zeros_like(jacobian))
    residual=torch.where(valid_input[...,None],residual,torch.zeros_like(residual))
    lower=torch.where(valid_input[...,None],lower,torch.zeros_like(lower))
    upper=torch.where(valid_input[...,None],upper,torch.zeros_like(upper))
    rows=jacobian.shape[-2]
    eye=torch.eye(rows,device=jacobian.device,dtype=jacobian.dtype)
    direction=(jacobian.transpose(-1,-2)@torch.linalg.solve(
        jacobian@jacobian.transpose(-1,-2)+damping*damping*eye,
        residual.unsqueeze(-1))).squeeze(-1)
    moving=direction.abs()>1e-12
    denominator=torch.where(moving,direction,torch.ones_like(direction))
    a=lower/denominator;b=upper/denominator
    alpha_lower=torch.where(moving,torch.minimum(a,b),torch.zeros_like(a)).amax(-1).clamp_min(0.)
    alpha_upper=torch.where(moving,torch.maximum(a,b),torch.ones_like(b)).amin(-1).clamp_max(1.)
    stationary_ok=(moving|((lower<=0)&(upper>=0))).all(-1)
    line_valid=(alpha_upper>=alpha_lower)&stationary_ok&(lower<=upper).all(-1)
    segment=direction*alpha_upper.clamp_min(0.).unsqueeze(-1)
    line_valid=line_valid&((segment>=lower-1e-7)&(segment<=upper+1e-7)).all(-1)
    predicted=(jacobian@segment.unsqueeze(-1)).squeeze(-1)
    line_safe=public_motion_guard(residual,predicted,line_valid,rotation_command)
    bounded,bounded_valid=bounded_cartesian_delta(jacobian,residual,lower,upper,damping)
    bounded_prediction=(jacobian@bounded.unsqueeze(-1)).squeeze(-1)
    bounded_safe=public_motion_guard(residual,bounded_prediction,
        bounded_valid&(lower<=upper).all(-1),rotation_command)
    allowed=line_safe|bounded_safe
    delta=torch.where(line_safe.unsqueeze(-1),segment,bounded)
    # Exceptional fallback only: one host predicate avoids dozens of solves
    # on every normal tick. Preserve the original accepted candidate per arm.
    if not bool(allowed.all()):
        fallback,fallback_allowed=scaled_bounded_fallback(jacobian,residual,lower,upper,
            public_motion_guard,rotation_command,damping)
        delta=torch.where(allowed.unsqueeze(-1),delta,fallback)
        allowed=allowed|fallback_allowed
    allowed=allowed&valid_input
    return torch.where(allowed.unsqueeze(-1),delta,torch.zeros_like(delta)),allowed


def rolling_reference_bounds(current,reference,limits,velocity,dt,maximum_lead):
    """Limit trajectory reference rate and measured tracking error separately."""
    travel=velocity*dt
    lower=torch.maximum(reference-travel-current,torch.full_like(current,-maximum_lead))
    upper=torch.minimum(reference+travel-current,torch.full_like(current,maximum_lead))
    return (torch.maximum(lower,limits[...,0]+1e-4-current),
            torch.minimum(upper,limits[...,1]-1e-4-current))


def accelerated_reference_bounds(current,reference,previous_velocity,lower,upper,dt,acceleration,goal=None):
    """Acceleration of the commanded reference, not measured joint velocity.

    Position/rate/tracking bounds take priority when their intersection with
    acceleration bounds is empty. The caller reports this safety override.
    """
    braking_override=torch.zeros_like(lower[...,0],dtype=torch.bool)
    if goal is not None:
        # Brake against remaining REFERENCE travel, not measured tracking error.
        # Reserve one full tick before the continuous stopping-distance bound.
        # Brake moving joints against their own remaining travel. Stationary
        # zero-nominal joints retain compensation space for the bounded solve.
        distance=(goal-reference).abs()
        free_compensation=(distance<1e-9)&(previous_velocity.abs()<1e-9)
        distance=torch.where(free_compensation,(goal-reference).norm(dim=-1,keepdim=True),distance)
        braking_speed=torch.sqrt((acceleration*dt)**2+2*acceleration*distance)-acceleration*dt
        braked_lower=torch.maximum(lower,reference-braking_speed*dt-current)
        braked_upper=torch.minimum(upper,reference+braking_speed*dt-current)
        braking_override=(braked_lower>braked_upper).any(-1)
        lower=torch.where(braking_override.unsqueeze(-1),lower,braked_lower)
        upper=torch.where(braking_override.unsqueeze(-1),upper,braked_upper)
    travel_lower=(previous_velocity-acceleration*dt)*dt
    travel_upper=(previous_velocity+acceleration*dt)*dt
    lo=torch.maximum(lower,reference+travel_lower-current)
    hi=torch.minimum(upper,reference+travel_upper-current)
    override=(lo>hi).any(-1)
    return (torch.where(override.unsqueeze(-1),lower,lo),
            torch.where(override.unsqueeze(-1),upper,hi),override|braking_override)


def public_refusal_state(blocked,failures,allowed,hard_refusal,retry_ticks):
    """Only hard faults or consecutive failed solves latch this command."""
    failures=torch.where(allowed,torch.zeros_like(failures),failures+1)
    return blocked|hard_refusal|(failures>=retry_ticks),failures


class Controller:
    def __init__(self,scene,simulation):
        self.scene=scene;self.sim=simulation;self.device=simulation.device;self.dt=simulation.get_physics_dt()
        self.ik={};self.ids={};self.targets={};self.grips=dict(left=.04,right=.04)
        initial_grips=scene.embodiment.config.get('author_recording',{}).get('initial_gripper_commands_m',{})
        for side,value in initial_grips.items():
            if side not in self.grips or not isinstance(value,(int,float)) or not 0<=value<=.04:
                raise ValueError('Invalid reviewed initial gripper command')
            self.grips[side]=float(value)
        self.evaluator=Evaluator(scene.spec);self.steps=0;self.started=False;self.tick_hooks=[]
        self.physics_ticks=0
        ff=scene.embodiment.config.get('author_recording',{}).get('joint_velocity_feedforward',False)
        if type(ff) is not bool:raise ValueError('Private joint_velocity_feedforward must be explicitly boolean')
        self.author_joint_velocity_feedforward=ff and bool(scene.spec.get('author_smooth_recording',False))
        self._author_ff_twists={}
        self._author_joint_override={}
        self._public_action=None;self._public_blocked={};self._public_hold_q={};self._public_limit_seen={};self._public_reference={}
        self._public_reference_velocity={}
        control=scene.embodiment.config.get('control',{})
        acceleration=control.get('public_reference_acceleration_rad_s2')
        if acceleration is not None and (type(acceleration) not in (int,float) or not math.isfinite(acceleration) or acceleration<=0):
            raise ValueError('Public reference acceleration must be finite and positive')
        retries=control.get('public_ik_retry_ticks',6)
        if type(retries) is not int or not 1<=retries<=25:
            raise ValueError('Public IK retries must be an integer from 1 to 25 ticks')
        for side,robot in scene.robots.items():
            profile=scene.embodiment
            arm,_=robot.find_joints(profile.arm_joints,preserve_order=True);fingers,_=robot.find_joints(profile.finger_joints,preserve_order=True);body,_=robot.find_bodies(profile.hand)
            self.ids[side]=(arm,fingers,body[0])
            self.ik[side]=DifferentialIKController(DifferentialIKControllerCfg(command_type='pose',use_relative_mode=False,ik_method=profile.config['control']['ik_method']),num_envs=1,device=self.device)
            self.targets[side]=self.pose(side)
            if self.author_joint_velocity_feedforward and not callable(getattr(robot,'set_joint_velocity_target',None)):
                raise RuntimeError('Native articulation does not expose joint velocity targets')

    def pose(self,side):
        robot=self.scene.robots[side];_,_,bid=self.ids[side]
        pos,quat=robot.data.body_pos_w[:,bid],robot.data.body_quat_w[:,bid]
        pos=pos+quat_apply(quat,torch.tensor([self.scene.embodiment.tcp],device=self.device))
        return subtract_frame_transforms(robot.data.root_pos_w,robot.data.root_quat_w,pos,quat)

    def public_feedback(self):
        """Measured robot state in the room task frame; no object/evaluator state."""
        import numpy as np
        from .layout import rotation_matrix, multiply_quaternions
        scene = self.scene
        arms = {}
        for side, robot in scene.robots.items():
            position, quaternion = self.pose(side)
            base_position = robot.data.root_pos_w[0].cpu().numpy()
            base_quaternion = robot.data.root_quat_w[0].cpu().numpy()
            world_position = position[0].cpu().numpy() @ rotation_matrix(base_quaternion).T + base_position
            world_quaternion = multiply_quaternions(base_quaternion, quaternion[0].cpu().numpy())
            q = scene.layout.task_quat
            task_quaternion = multiply_quaternions((q[0], -q[1], -q[2], -q[3]), world_quaternion)
            arm_ids, finger_ids, _ = self.ids[side]
            finger = robot.data.joint_pos[0, finger_ids].cpu().numpy()
            opened = np.asarray(scene.embodiment.config['gripper']['open'])
            closed = np.asarray(scene.embodiment.config['gripper']['closed'])
            moving = np.abs(opened - closed) > 1e-9
            fraction = float(np.clip(((finger - closed)[moving] / (opened - closed)[moving]).mean(), 0., 1.)) if moving.any() else None
            arms[side] = dict(tcp_position=scene.world_to_task(world_position).tolist(),
                tcp_quaternion_wxyz=list(map(float, task_quaternion)),
                joint_names=list(scene.embodiment.arm_joints),
                joint_positions_rad=robot.data.joint_pos[0, arm_ids].cpu().tolist(),
                gripper_open_fraction=fraction,
                tcp_position_world_m=world_position.tolist(),
                tcp_quaternion_world_wxyz=list(map(float, world_quaternion)),
                finger_joint_positions= finger.tolist(),
                finger_joint_position_units='m',
                holding_status='not_measured', contact_status='not_measured')
            # Robot-local proprioception only; never consult scene contact pairs.
            optional = {}
            for key, attr, ids in (
                ('joint_velocities_rad_s', 'joint_vel', arm_ids),
                ('finger_joint_velocities_m_s', 'joint_vel', finger_ids),
                ('joint_soft_limits_rad', 'soft_joint_pos_limits', arm_ids)):
                value = getattr(robot.data, attr, None)
                if value is None:
                    optional[key] = dict(available=False, reason='sensor_unavailable')
                    continue
                measured = value[0, ids].detach().cpu().numpy()
                optional[key] = dict(available=bool(np.isfinite(measured).all()),
                    value=measured.tolist() if np.isfinite(measured).all() else None)
            velocity = getattr(robot.data, 'body_vel_w', None)
            if velocity is not None:
                _, _, body_id = self.ids[side]
                v = velocity[0, body_id].detach().cpu().numpy()
                offset = world_position - robot.data.body_pos_w[0, body_id].detach().cpu().numpy()
                tcp_velocity = v[:3] + np.cross(v[3:], offset)
                optional['tcp_linear_velocity_task_m_s'] = dict(available=bool(np.isfinite(tcp_velocity).all()),
                    value=(scene.layout.task_rotation.T @ tcp_velocity).tolist() if np.isfinite(tcp_velocity).all() else None)
            else:
                optional['tcp_linear_velocity_task_m_s'] = dict(available=False, reason='sensor_unavailable')
            arms[side]['measured_sensors'] = optional
        return dict(coordinate_frame='room-local task frame: +X forward, +Y left, +Z up',
                    units=dict(position='m', orientation='quaternion wxyz', joints='rad'), arms=arms)

    def snapshot(self):
        contacts=set()
        groups=[];vectors=[]
        for name,(sensor,filters) in self.scene.contacts.items():
            matrix=sensor.data.force_matrix_w
            if matrix is None:raise RuntimeError('Missing PhysX contact matrix; evaluator must not approximate contacts')
            forces=matrix.norm(dim=-1).amax(dim=1)[0]
            groups.append((name,filters,len(forces)));vectors.append(forces)
        # One GPU-to-CPU read for the complete contact panel. Per-pair .item()
        # incurred hundreds of device synchronizations on the 14-chip scenes.
        values=torch.cat(vectors).cpu().tolist() if vectors else []
        offset=0;self.contact_forces={}
        for name,filters,count in groups:
            for i,f in enumerate(filters):
                force=float(values[offset+i]);pair=frozenset((name,f))
                self.contact_forces[pair]=max(force,self.contact_forces.get(pair,0.))
                if force>.001:contacts.add(pair)
            offset+=count
        state={}
        names=list(self.scene.objects)
        if names:
            positions=torch.stack([self.scene.objects[n].data.root_pos_w[0] for n in names])
            rotations=matrix_from_quat(torch.stack([self.scene.objects[n].data.root_quat_w[0] for n in names]))
            poses=torch.cat((positions,rotations.reshape(len(names),9)),dim=1).cpu().numpy()
        for i,name in enumerate(names):
            grasp=[all(frozenset((name,f'{side}_finger{i}')) in contacts for i in (1,2)) and self.grips[side]<.01 for side in ('left','right')]
            state[name]=dict(pos=self.scene.world_to_task(poses[i,:3]),
                mat=self.scene.layout.task_rotation.T@poses[i,3:].reshape(3,3),grasp=grasp)
        return state,contacts

    def snapshot_mechanisms(self):
        result={}
        for name,asset in getattr(self.scene,'mechanisms',{}).items():
            positions=asset.data.body_pos_w[0].cpu().numpy()
            matrices=matrix_from_quat(asset.data.body_quat_w[0]).cpu().numpy()
            result[name]=dict(joint_names=list(asset.joint_names),joint_pos=asset.data.joint_pos[0].cpu().tolist(),
                              joint_vel=asset.data.joint_vel[0].cpu().tolist(),body_names=list(asset.body_names),
                              body_pos_task={body:self.scene.world_to_task(positions[i]).tolist() for i,body in enumerate(asset.body_names)},
                              body_mat_task={body:(self.scene.layout.task_rotation.T@matrices[i]).tolist() for i,body in enumerate(asset.body_names)})
        return result

    def tick(self,render=False,*,phase='full'):
        # A pool writes every room before advancing the shared world once,
        # then reads every room. Ordinary single-room callers retain full ticks.
        if phase not in ('full','write','read'):
            raise ValueError('Unknown physics tick phase')
        if phase!='full' and render:
            raise ValueError('Pool rendering belongs to the shared world')
        if phase=='full' and getattr(self,'_room_pool',None) is not None:
            raise RuntimeError('Advance this controller through its RoomPool')
        if phase!='read':
            for side,robot in self.scene.robots.items():
                arm,fingers,bid=self.ids[side]
                override=getattr(self,'_author_joint_override',{}).get(side)
                if override is None:
                    pos,quat=self.pose(side)
                    self.ik[side].set_command(torch.cat(self.targets[side],dim=-1))
                    jacobian=robot.root_physx_view.get_jacobians()[:,bid-1 if robot.is_fixed_base else bid,:,arm].clone()
                    offset=quat_apply(robot.data.body_quat_w[:,bid],torch.tensor([self.scene.embodiment.tcp],device=self.device))
                    # The UI translates/rotates the grasp center, not the wrist origin.
                    jacobian[:,:3,:]-=torch.bmm(skew_symmetric_matrix(offset),jacobian[:,3:,:])
                    # PhysX returns world Jacobians; IK poses/targets are base-relative.
                    inverse_rotation=matrix_from_quat(robot.data.root_quat_w).transpose(1,2)
                    jacobian[:,:3,:]=torch.bmm(inverse_rotation,jacobian[:,:3,:])
                    jacobian[:,3:,:]=torch.bmm(inverse_rotation,jacobian[:,3:,:])
                    if getattr(self,'_public_action',None) is not None:
                        current=robot.data.joint_pos[:,arm]
                        if not bool(torch.isfinite(current).all()):
                            raise RuntimeError('Nonfinite measured joints; no actuator target issued')
                        bounds=robot.data.joint_pos_limits[:,arm]
                        velocity=torch.minimum(robot.data.joint_vel_limits[:,arm],torch.full_like(current,float(self.scene.embodiment.config['actuators']['arm']['velocity_limit'])))
                        maximum=torch.minimum(velocity*self.dt,torch.full_like(current,float(self.scene.embodiment.config['physics']['max_joint_delta'])))
                        lower=torch.maximum(-maximum,bounds[...,0]+1e-4-current)
                        upper=torch.minimum(maximum,bounds[...,1]-1e-4-current)
                        rolling=self.scene.embodiment.config.get('control',{}).get('rolling_joint_reference',False)
                        if rolling:
                            reference=self._public_reference.get(side,current)
                            lower,upper=rolling_reference_bounds(current,reference,bounds,velocity,self.dt,
                                float(self.scene.embodiment.config['physics']['max_joint_delta']))
                            acceleration=self.scene.embodiment.config['control'].get('public_reference_acceleration_rad_s2')
                            if acceleration is not None:
                                residual=pose_residual(pos,quat,*self.targets[side])
                                # Local endpoint estimate only; every resulting
                                # step still passes the original Cartesian guard.
                                finite=torch.isfinite(jacobian).all(dim=(-2,-1))&torch.isfinite(residual).all(-1)
                                J=torch.where(finite[:,None,None],jacobian,torch.zeros_like(jacobian))
                                e=torch.where(finite[:,None],residual,torch.zeros_like(residual))
                                eye=torch.eye(J.shape[-2],device=J.device,dtype=J.dtype)
                                nominal=(J.transpose(-1,-2)@torch.linalg.solve(J@J.transpose(-1,-2)+.0001*eye,e.unsqueeze(-1))).squeeze(-1)
                                previous_velocity=getattr(self,'_public_reference_velocity',{}).get(side,torch.zeros_like(current))
                                lower,upper,acceleration_override=accelerated_reference_bounds(current,reference,previous_velocity,
                                    lower,upper,self.dt,acceleration,goal=current+nominal)
                                self._public_acceleration_override[side]=self._public_acceleration_override.get(side,torch.zeros_like(acceleration_override))|acceleration_override
                        residual=pose_residual(pos,quat,*self.targets[side])
                        token=self._public_action[side]
                        rotation_command=token in MOTION and MOTION[token][0]>=3
                        delta,allowed=guarded_cartesian_delta(jacobian,residual,lower,upper,rotation_command)
                        hard=((residual[...,3:].norm(dim=-1)>math.radians(20.))&(~torch.full_like(allowed,rotation_command)))|(~(lower<=upper).all(-1))|(~torch.isfinite(lower).all(-1))|(~torch.isfinite(upper).all(-1))|(~torch.isfinite(residual).all(-1))|(~torch.isfinite(jacobian).all(dim=(-2,-1)))
                        if not hasattr(self,'_public_failures'):self._public_failures={}
                        failures=self._public_failures.get(side,torch.zeros_like(allowed,dtype=torch.long))
                        blocked,failures=public_refusal_state(self._public_blocked.get(side,torch.zeros_like(allowed)),
                            failures,allowed,hard,self.scene.embodiment.config.get('control',{}).get('public_ik_retry_ticks',6))
                        self._public_failures[side]=failures
                        self._public_blocked[side]=blocked
                        # Latch reached joint pose on refusal. Keep Cartesian goal
                        # intact for error reporting and an explicit next command.
                        held=self._public_hold_q.get(side,current.clone())
                        was=self._public_blocked_before.get(side,torch.zeros_like(blocked))
                        held=torch.where((blocked&(~was)).unsqueeze(-1),current,held)
                        self._public_hold_q[side]=held;self._public_blocked_before[side]=blocked
                        near=((current-bounds[...,0]).abs()<.002)|((bounds[...,1]-current).abs()<.002)
                        self._public_limit_seen[side]=self._public_limit_seen.get(side,torch.zeros_like(near))|near
                        target=torch.where(blocked.unsqueeze(-1),held,
                            torch.where(allowed.unsqueeze(-1),current+delta,current))
                        if rolling:
                            if not hasattr(self,'_public_reference_velocity'):self._public_reference_velocity={}
                            reference_velocity=(target-reference)/self.dt
                            # Refusal holds measured q immediately. This safety stop
                            # takes precedence over normal reference acceleration.
                            if acceleration is not None:
                                interrupted=(~allowed)|blocked
                                self._public_acceleration_override[side]=self._public_acceleration_override.get(side,torch.zeros_like(allowed))|interrupted
                            self._public_reference_velocity[side]=torch.where(
                                ((~allowed)|blocked).unsqueeze(-1),torch.zeros_like(reference_velocity),reference_velocity)
                            self._public_reference[side]=target.clone()
                    else:
                        target=self.ik[side].compute(pos,quat,jacobian,robot.data.joint_pos[:,arm])
                else:
                    target,velocity=override
                # Do not send discontinuous IK updates or targets beyond physical joint limits.
                current=robot.data.joint_pos[:,arm]
                if getattr(self,'_public_action',None) is None or override is not None:
                    target=current+(target-current).clamp(-self.scene.embodiment.config['physics']['max_joint_delta'],self.scene.embodiment.config['physics']['max_joint_delta'])
                    bounds=robot.data.joint_pos_limits[:,arm]
                    target=target.clamp(bounds[...,0]+1e-4,bounds[...,1]-1e-4)
                robot.set_joint_position_target(target,joint_ids=arm)
                if override is not None or side in self._author_ff_twists:
                    native_limits=robot.data.joint_vel_limits[:,arm]
                    configured_limit=float(self.scene.embodiment.config['actuators']['arm']['velocity_limit'])
                    if not math.isfinite(configured_limit) or configured_limit<=0:
                        raise ValueError('Finite positive native profile arm velocity limit required')
                    limits=torch.minimum(native_limits,torch.full_like(native_limits,configured_limit))
                    if override is None:
                        from .author_feedforward import damped_joint_velocity
                        velocity=damped_joint_velocity(jacobian,self._author_ff_twists[side],limits,
                            float(self.ik[side].cfg.ik_params['lambda_val']),array_module=torch)
                    else:velocity=velocity.clamp(-limits,limits)
                    robot.set_joint_velocity_target(velocity,joint_ids=arm)
                profile=self.scene.embodiment
                values=torch.tensor([profile.gripper_values(self.grips[side]/.04)],device=self.device)
                bounds=robot.data.joint_pos_limits[:,fingers]
                values=values.clamp(bounds[...,0],bounds[...,1])
                robot.set_joint_position_target(values,joint_ids=fingers)
                robot.write_data_to_sim()
            self.scene.apply_passive_efforts()
        if phase=='write':return
        if phase=='full':
            self.sim.step(render=False)
        physics_update=getattr(self.scene,'update_physics',None)
        if physics_update is None:
            self.scene.update(self.dt)
        else:
            physics_update(self.dt)
        if render:
            if physics_update is not None:self.scene.prepare_render()
            self.sim.render()
            if physics_update is None:self.scene.update(0.)
            else:self.scene.update_render_cameras()
        state,contacts=self.snapshot()
        mechanism_update=getattr(self.evaluator,'update_mechanisms',None)
        if mechanism_update is not None:mechanism_update(self.snapshot_mechanisms())
        force_update=getattr(self.evaluator,'update_contact_forces',None)
        if force_update is not None:force_update(self.contact_forces)
        self.evaluator.update(state,contacts,self.dt)
        self.physics_ticks+=1
        if phase!='read':
            for hook in self.tick_hooks:hook(self,render)

    def clear_author_velocity_feedforward(self,sides):
        """Flush zero native arm velocity for only this private move's hands."""
        for side in sides:
            self._author_ff_twists.pop(side,None)
            robot=self.scene.robots[side];arm=self.ids[side][0]
            robot.set_joint_velocity_target(torch.zeros_like(robot.data.joint_pos[:,arm]),joint_ids=arm)
            # Lab 2.1 setters only fill buffers. Flush without advancing physics,
            # including when a guard raises and there will be no following tick.
            robot.write_data_to_sim()

    def author_joint_path(self,side,position,velocity,dt,guard=None,done=None,metadata=None,
                          tracking_tolerance=.001,minimum_settle_seconds=.12,maximum_settle_seconds=.8):
        """Execute a caller-verified private arm path through native targets.

        Samples include the measured t=0 configuration. Each following sample
        advances exactly one real 4ms physics tick, with the ordinary source
        position clamp, contacts/evaluator updates and render clock. Only the
        selected arm receives the joint override; joint/object states are never
        assigned directly. Normal completion holds the final q for .12--.8s
        until its measured L2 error is <=1e-3rad; these engineering hold bounds
        can be explicitly set to zero and never replace the task evaluator.
        """
        from copy import deepcopy
        from .recording_trajectory import frame_due
        if side not in self.scene.robots:raise ValueError('Unknown private joint-path hand')
        if (not math.isfinite(float(dt)) or not math.isclose(float(dt),self.dt,rel_tol=0.,abs_tol=1e-9)
                or not math.isclose(self.dt,.004,rel_tol=0.,abs_tol=1e-9)):
            raise ValueError('Private joint path dt must equal the actual 4ms physics step')
        if metadata is not None and not isinstance(metadata,dict):raise ValueError('Joint-path metadata must be a mapping')
        metadata=deepcopy(metadata or {})
        if metadata.get('requires_native_grasp_guard') is True and not callable(guard):
            raise ValueError('Held-geometry plan requires a callable native grasp guard')
        if (not all(math.isfinite(float(v)) for v in
                    (tracking_tolerance,minimum_settle_seconds,maximum_settle_seconds))
                or not 0<tracking_tolerance<=.05
                or not 0<=minimum_settle_seconds<=maximum_settle_seconds<=.8):
            raise ValueError('Invalid private joint-path engineering settle bounds')
        if (side in getattr(self,'_author_joint_override',{}) or side in self._author_ff_twists):
            raise RuntimeError('Selected hand already has a private motion override')
        robot=self.scene.robots[side];arm=self.ids[side][0]
        if len(arm)!=7:raise ValueError('Private joint-path execution requires exactly seven native arm joints')
        if not callable(getattr(robot,'set_joint_velocity_target',None)):
            raise RuntimeError('Native articulation does not expose joint velocity targets')
        q=torch.as_tensor(position,device=self.device,dtype=robot.data.joint_pos.dtype).clone()
        qd=torch.as_tensor(velocity,device=self.device,dtype=robot.data.joint_pos.dtype).clone()
        if q.ndim!=2 or q.shape[1]!=7 or len(q)<2 or qd.shape!=q.shape:
            raise ValueError('Joint path position/velocity must have matching (T,7) shape with T>=2')
        if not torch.isfinite(q).all() or not torch.isfinite(qd).all():
            raise ValueError('Nonfinite private joint path')
        planned_ticks=len(q)-1
        if planned_ticks*self.dt>30.+1e-9:
            raise ValueError(f'Private joint path exceeds 30s physical plan: samples={len(q)}, ticks={planned_ticks}')
        current=robot.data.joint_pos[:,arm].clone()
        bounds=robot.data.joint_pos_limits[:,arm]
        if ((q<bounds[...,0]-1e-6).any() or (q>bounds[...,1]+1e-6).any()):
            raise ValueError('Private joint path exceeds native position limits')
        configured_limit=float(self.scene.embodiment.config['actuators']['arm']['velocity_limit'])
        native_limits=robot.data.joint_vel_limits[:,arm]
        if (not math.isfinite(configured_limit) or configured_limit<=0
                or not torch.isfinite(native_limits).all() or (native_limits<0).any()):
            raise ValueError('Valid native/profile velocity limits are required')
        limits=torch.minimum(native_limits,torch.full_like(native_limits,configured_limit))
        if (qd>limits+1e-6).any() or (qd<-limits-1e-6).any():
            raise ValueError('Private joint path exceeds native/profile velocity limits')
        delta=q[1:]-q[:-1]
        if (delta>limits*self.dt+1e-6).any() or (delta<-limits*self.dt-1e-6).any():
            raise ValueError('Private joint path sample positions exceed native/profile velocity limits')
        start_error=q[0:1]-current
        if (start_error>1e-4).any() or (start_error<-1e-4).any():
            raise ValueError('Private joint path first sample must connect to measured native joints within 1e-4rad')
        other_guard=None
        if metadata.get('frozen_other_arm') is True:
            other='right' if side=='left' else 'left'
            if metadata.get('other_arm_side',other)!=other:raise ValueError('Frozen other-arm identity mismatch')
            names=metadata.get('other_arm_joint_names');captured=metadata.get('other_arm_qpos')
            if not isinstance(names,list) or not names or len(names)!=len(set(names)):
                raise ValueError('Frozen other-arm plan must include every captured native joint name')
            other_robot=self.scene.robots[other]
            if names!=list(other_robot.joint_names):raise ValueError('Frozen other-arm snapshot must cover the complete native joint ordering')
            other_ids,found=other_robot.find_joints(names,preserve_order=True)
            if found!=names:raise ValueError('Frozen other-arm joint identities differ from native joints')
            reference=torch.as_tensor(captured,device=self.device,dtype=other_robot.data.joint_pos.dtype)
            if reference.shape!=(len(names),) or not torch.isfinite(reference).all():
                raise ValueError('Invalid captured other-arm joint positions')
            reference=reference[None].clone()
            tolerances=torch.as_tensor([[1e-4 if n.startswith('panda_finger_joint') else 1e-3 for n in names]],
                device=self.device,dtype=other_robot.data.joint_pos.dtype)
            peak=torch.zeros_like(reference)
            def check_other():
                nonlocal peak
                delta=other_robot.data.joint_pos[:,other_ids]-reference
                peak=torch.maximum(peak,torch.maximum(delta,-delta))
                if (delta>tolerances).any() or (delta<-tolerances).any():
                    raise RuntimeError('Frozen other-arm collision snapshot drifted beyond its native joint guard')
            check_other()
            other_guard=dict(side=other,joint_names=names,tolerances=tolerances,peak=lambda:peak)
        else:
            def check_other():pass
        def checked_guard():
            check_other()
            if guard is not None:guard()
        if not hasattr(self,'_author_joint_override'):self._author_joint_override={}
        self._public_action=None;self._public_blocked={};self._public_hold_q={};self._public_limit_seen={}
        self._public_action=None  # Private author trajectory retains its separate controller.
        before=float(self.sim.current_time);tick_before=self.physics_ticks
        fps=self.scene.embodiment.config['physics']['render_hz']
        executed=0;frames=0;settle_ticks=0;done_reached=False;last_target=current
        max_error=0.;self.evaluator.event_enabled=True
        try:
            for index in range(1,len(q)):
                checked_guard()
                if done is not None and done():done_reached=True;break
                last_target=q[index:index+1]
                self._author_joint_override[side]=(last_target,qd[index:index+1])
                render=frame_due(self.physics_ticks+1,self.dt,fps)
                self.tick(render=render)
                executed+=1;frames+=int(render)
                max_error=max(max_error,float((last_target-robot.data.joint_pos[:,arm]).norm()))
                checked_guard()
                if done is not None and done():done_reached=True;break
            if not done_reached and executed==planned_ticks:
                # Keep the final native q target while the actual servos close
                # their measured error. Holds always command zero velocity.
                last_target=q[-1:]
                self._author_joint_override[side]=(last_target,torch.zeros_like(qd[-1:]))
                self.clear_author_velocity_feedforward([side])
                for _ in range(round(maximum_settle_seconds/self.dt)):
                    checked_guard()
                    if done is not None and done():done_reached=True;break
                    render=frame_due(self.physics_ticks+1,self.dt,fps)
                    self.tick(render=render);settle_ticks+=1;frames+=int(render)
                    error=float((last_target-robot.data.joint_pos[:,arm]).norm())
                    max_error=max(max_error,error)
                    checked_guard()
                    if done is not None and done():done_reached=True;break
                    if settle_ticks>=round(minimum_settle_seconds/self.dt) and error<=tracking_tolerance:break
            self.steps+=1
            return dict(step_before=self.steps-1,step_after=self.steps,side=side,
                control='private_native_joint_position_velocity_path',
                joint_velocity_feedforward=True,physics_dt=self.dt,
                planned_samples=len(q),planned_ticks=planned_ticks,trajectory_ticks=planned_ticks,
                executed_trajectory_ticks=executed,settle_ticks=settle_ticks,
                executed_physics_ticks=self.physics_ticks-tick_before,
                executed_path_samples=executed,path_completed=executed==planned_ticks,done_reached=done_reached,
                simulation_seconds=float(self.sim.current_time)-before,frames_rendered=frames,fps=fps,
                tracking_error_rad=float((last_target-robot.data.joint_pos[:,arm]).norm()),
                maximum_tracking_error_rad=max_error,
                requested_endpoint_error_rad=float((q[-1:]-robot.data.joint_pos[:,arm]).norm()),
                engineering_tracking_tolerance_rad=tracking_tolerance,
                endpoint_tracking_converged=float((q[-1:]-robot.data.joint_pos[:,arm]).norm())<=tracking_tolerance,
                planner_metadata=metadata,collision_geometry_validated_by_controller=False,
                frozen_other_arm_guard=(None if other_guard is None else dict(side=other_guard['side'],
                    joint_names=other_guard['joint_names'],
                    maximum_deviations=other_guard['peak']()[0].cpu().tolist(),
                    tolerances=other_guard['tolerances'][0].cpu().tolist())),
                joint_state_written=False,object_state_written=False)
        finally:
            self._author_joint_override.pop(side,None)
            try:
                actual_pos,actual_quat=self.pose(side)
                self.targets[side]=(actual_pos.clone(),actual_quat.clone())
                robot.set_joint_position_target(robot.data.joint_pos[:,arm].clone(),joint_ids=arm)
            finally:
                self.clear_author_velocity_feedforward([side])

    def author_move(self,goals,*,max_speed=.18,max_acceleration=.6,guard=None,done=None,tracking_tolerance=None):
        """Private recording controller: interpolate real TCP actuator targets.

        Physics, contact sensing and evidence run at every tick. Only robot
        joint targets are sent through the native IK path; object state is
        never assigned. This API is separate from policy observations/actions.
        """
        from .recording_trajectory import minimum_jerk,trajectory_ticks,frame_due
        from .author_feedforward import minimum_jerk_phase_rate
        if tracking_tolerance is not None and not 0<tracking_tolerance<=.05:
            raise ValueError('Invalid private actuator tracking tolerance')
        if not goals or any(side not in self.robots_for_author for side in goals):
            raise ValueError('Expected one or two named robot TCP targets')
        starts={};ends={}
        for side,value in goals.items():
            position=torch.as_tensor(value,device=self.device,dtype=torch.float32)
            if position.shape!=(3,) or not torch.isfinite(position).all():
                raise ValueError('Author TCP target must be a finite three-vector')
            world=torch.as_tensor(self.scene.task_to_world(position.cpu().numpy()),device=self.device,dtype=torch.float32)[None]
            robot=self.scene.robots[side]
            ends[side]=quat_apply_inverse(robot.data.root_quat_w,world-robot.data.root_pos_w)
            starts[side]=self.pose(side)[0].clone()
        distance=max(float((ends[s]-starts[s]).norm()) for s in goals)
        ticks=trajectory_ticks(distance,self.dt,max_speed,max_acceleration)
        if ticks*self.dt>30.+1e-9:
            raise ValueError(f'Private author trajectory exceeds 30s physical plan: distance={distance:.9g}m, '
                             f'planned_ticks={ticks}, planned_duration={ticks*self.dt:.9g}s, goals={goals!r}')
        self._public_action=None  # Private author trajectory retains its separate controller.
        before=float(self.sim.current_time);self.evaluator.event_enabled=True
        fps=self.scene.embodiment.config['physics']['render_hz']
        feedforward=bool(getattr(self,'author_joint_velocity_feedforward',False))
        done_reached=False
        try:
            for index in range(1,ticks+1):
                if guard is not None:guard()
                if done is not None and done():
                    done_reached=True;break
                phase=index/ticks;alpha=minimum_jerk(phase)
                for side in goals:
                    delta=ends[side]-starts[side]
                    self.targets[side]=(starts[side]+alpha*delta,self.targets[side][1])
                    if feedforward:
                        linear=delta*minimum_jerk_phase_rate(phase,ticks*self.dt)
                        self._author_ff_twists[side]=torch.cat((linear,torch.zeros_like(linear)),dim=-1)
                self.tick(render=frame_due(self.physics_ticks+1,self.dt,fps))
                if guard is not None:guard()
                if done is not None and done():
                    done_reached=True;break
            if done_reached:
                # Freeze the measured TCP on an early contact/joint stop.
                for side in goals:
                    self.targets[side]=(self.pose(side)[0].clone(),self.targets[side][1])
            if feedforward:self.clear_author_velocity_feedforward(goals)
            # Position-only hold: no residual velocity target during settling.
            settle_ticks=0
            minimum_settle=round(.12/self.dt)
            maximum_settle=round((.8 if tracking_tolerance is not None else .12)/self.dt)
            for _ in range(maximum_settle):
                if guard is not None:guard()
                self.tick(render=frame_due(self.physics_ticks+1,self.dt,fps))
                if guard is not None:guard()
                settle_ticks+=1
                if (tracking_tolerance is not None and settle_ticks>=minimum_settle
                        and all(float((self.targets[s][0]-self.pose(s)[0]).norm())<=tracking_tolerance for s in goals)):
                    break
            self.steps+=1
            return dict(step_before=self.steps-1,step_after=self.steps,
                        simulation_seconds=float(self.sim.current_time)-before,
                        joint_velocity_feedforward=feedforward,
                        planned_ticks=ticks,settle_ticks=settle_ticks,done_reached=done_reached,max_speed_m_s=max_speed,max_acceleration_m_s2=max_acceleration,
                        tracking_error_m={s:float((self.targets[s][0]-self.pose(s)[0]).norm()) for s in goals})
        finally:
            if feedforward:self.clear_author_velocity_feedforward(goals)

    @property
    def robots_for_author(self):
        return self.scene.robots

    def validate_action(self,left='STILL',right='STILL',step_mm=20.,rotation_deg=10.):
        if left not in TOKENS or right not in TOKENS:raise ValueError('Unknown action')
        limits=self.scene.embodiment.config['control']
        if type(step_mm) not in (int,float) or not math.isfinite(step_mm) or not limits['step_mm'][0]<=step_mm<=limits['step_mm'][1]:raise ValueError('Step out of range')
        if type(rotation_deg) not in (int,float) or not math.isfinite(rotation_deg) or not limits['rotation_deg'][0]<=rotation_deg<=limits['rotation_deg'][1]:raise ValueError('Angle out of range')

    def begin_action(self,left='STILL',right='STILL',step_mm=20.,rotation_deg=10.):
        """Set one public pair's targets, without advancing shared physics."""
        self.validate_action(left,right,step_mm,rotation_deg)
        self.evaluator.event_enabled=True
        continuing=getattr(self,'_public_action',None) is not None
        self._public_action=dict(left=left.removeprefix('MV_'),right=right.removeprefix('MV_'))
        self._public_blocked={};self._public_blocked_before={};self._public_hold_q={};self._public_limit_seen={}
        self._public_failures={};self._public_acceleration_override={};self._public_superseded_orientation={}
        self._public_tolerances={}
        self._public_start={side:self.pose(side)[0].clone() for side in getattr(self.scene,'robots',{})}
        if not continuing:
            self._public_reference={};self._public_reference_velocity={}
        left=left.removeprefix('MV_');right=right.removeprefix('MV_')
        # Relative commands start from the achieved pose, preventing unreachable
        # requests from building up a hidden target far outside the workspace.
        for side,token in [('left',left),('right',right)]:
            if token=='GRASP':self.grips[side]=0.
            elif token=='RELEASE':self.grips[side]=.04
            elif token in MOTION:
                axis,sign=MOTION[token];delta=torch.zeros((1,6),device=self.device)
                # A sub-mm/degree request must not count as reached before it
                # moves merely because the generic settling tolerance is larger.
                self._public_tolerances[side]=(min(.002,step_mm/1000*.1) if axis<3 else .002,
                    min(.05,math.radians(rotation_deg)*.1) if axis>=3 else .05)
                measured_position,measured_quaternion=self.pose(side)
                # Translation preserves the promised orientation. An explicit
                # relative rotation supersedes the old angular goal and starts
                # at the measured orientation; report the superseded error.
                if axis>=3:
                    self._public_superseded_orientation[side]=pose_residual(
                        measured_position,measured_quaternion,*self.targets[side])[...,3:].norm(dim=-1)
                    target_quaternion=measured_quaternion.clone()
                else:target_quaternion=self.targets[side][1]
                self.targets[side]=(measured_position.clone(),target_quaternion)
                delta[0,axis]=sign*(step_mm/1000 if axis<3 else math.radians(rotation_deg))
                # Public actions keep the audited task axes even with rotated
                # robot bases. Both linear and angular increments use that frame.
                rotation=torch.as_tensor(self.scene.layout.task_rotation,device=self.device,dtype=delta.dtype)
                delta[:,:3]=quat_apply_inverse(self.scene.robots[side].data.root_quat_w,delta[:,:3]@rotation.T)
                delta[:,3:]=quat_apply_inverse(self.scene.robots[side].data.root_quat_w,delta[:,3:]@rotation.T)
                self.targets[side]=apply_delta_pose(*self.targets[side],delta)
        return dict(step_before=self.steps)

    def action_feedback(self):
        """Public robot-only diagnostics, identical for pooled and isolated calls."""
        errors={};orientation={};details={}
        for side,robot in self.scene.robots.items():
            position,quaternion=self.pose(side)
            residual=pose_residual(position,quaternion,*self.targets[side])
            errors[side]=float(residual[0,:3].norm());orientation[side]=float(residual[0,3:].norm())
            blocked=bool(self._public_blocked.get(side,torch.tensor([False]))[0])
            def task_delta(delta):
                world=quat_apply(robot.data.root_quat_w,delta)
                rotation=torch.as_tensor(self.scene.layout.task_rotation,device=world.device,dtype=world.dtype)
                return (world@rotation)[0].cpu().tolist()
            start=self._public_start.get(side,position)
            limits=self._public_limit_seen.get(side,torch.zeros((1,len(self.scene.embodiment.arm_joints)),dtype=torch.bool))
            position_tolerance,orientation_tolerance=getattr(self,'_public_tolerances',{}).get(side,(.002,.05))
            retrying=int(getattr(self,'_public_failures',{}).get(side,torch.tensor([0]))[0])>0
            details[side]=dict(status='blocked' if blocked else ('partial' if retrying or errors[side]>position_tolerance or orientation[side]>orientation_tolerance else 'reached'),
                reason=('unresolved_orientation_target' if blocked and orientation[side]>math.radians(20.) and
                    self._public_action[side] not in {k for k,v in MOTION.items() if v[0]>=3} else
                    ('no_safe_ik_step' if blocked else ('ik_retry_pending' if
                        int(getattr(self,'_public_failures',{}).get(side,torch.tensor([0]))[0]) else None))),
                requested_delta_m=task_delta(self.targets[side][0]-start),actual_delta_m=task_delta(position-start),
                position_error_m=errors[side],orientation_error_rad=orientation[side],
                position_tolerance_m=position_tolerance,orientation_tolerance_rad=orientation_tolerance,
                joint_limit_names=[name for name,hit in zip(self.scene.embodiment.arm_joints,limits[0].cpu().tolist()) if hit],
                consecutive_ik_refusals=int(getattr(self,'_public_failures',{}).get(side,torch.tensor([0]))[0]),
                reference_acceleration_safety_override=bool(getattr(self,'_public_acceleration_override',{}).get(side,torch.tensor([False]))[0]),
                superseded_orientation_error_rad=float(getattr(self,'_public_superseded_orientation',{}).get(side,torch.tensor([0.]))[0]))
        return dict(tracking_error_m=errors,orientation_error_rad=orientation,control_feedback=details)

    def public_action_converged(self):
        """Stop settling only on measured convergence or a latched refusal.

        Controllers continue holding their unchanged Cartesian goals while
        other rooms settle. No receipt/image is captured at this intermediate
        check; the pool publishes every room at the same final shared tick.
        """
        for side in self.scene.robots:
            residual=pose_residual(*self.pose(side),*self.targets[side])
            if not bool(torch.isfinite(residual).all()):
                raise RuntimeError('Nonfinite measured robot pose during public action convergence check')
            if bool(self._public_blocked.get(side,torch.tensor([False]))[0]):continue
            if bool(getattr(self,'_public_failures',{}).get(side,torch.tensor([0]))[0]>0):return False
            position_tolerance,orientation_tolerance=getattr(self,'_public_tolerances',{}).get(side,(.002,.05))
            if bool((residual[...,:3].norm(dim=-1)>position_tolerance).any() or
                    (residual[...,3:].norm(dim=-1)>orientation_tolerance).any()):return False
        return True

    def action(self,left='STILL',right='STILL',step_mm=20.,rotation_deg=10.):
        if getattr(self,'_room_pool',None) is not None:
            raise RuntimeError('Advance this controller through its RoomPool')
        physics=self.scene.embodiment.config['physics']
        from .room_pool import action_tick_limits
        minimum_ticks,maximum_ticks,check_ticks=action_tick_limits(physics,self.dt)
        before=float(self.sim.current_time)
        self.begin_action(left,right,step_mm,rotation_deg)
        from .recording_trajectory import frame_due
        executed_ticks=0
        for index in range(maximum_ticks):
            self.tick(render=frame_due(self.physics_ticks+1,self.dt,physics['render_hz']))
            executed_ticks=index+1
            if executed_ticks>=minimum_ticks and (executed_ticks-minimum_ticks)%check_ticks==0:
                if maximum_ticks==minimum_ticks or self.public_action_converged():break
        self.steps+=1
        return dict(step_before=self.steps-1,step_after=self.steps,simulation_seconds=float(self.sim.current_time)-before,
            physics_ticks=executed_ticks,settle_ticks=max(0,executed_ticks-minimum_ticks),maximum_action_ticks=maximum_ticks,
            **self.action_feedback())
