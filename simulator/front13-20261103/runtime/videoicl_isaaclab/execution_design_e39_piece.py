"""Release an E39 T above the real tray walls before opening the fingers.

The source-C middle blue cell wedged a fully commanded open hand against both
tray walls. Empty-hand UP then lifted the tray. This reference uses the actual
closed and predicted fully open collision meshes to choose a clear release
height. The T falls onto its real support; no body or joint state is changed.
"""
from itertools import product
import json
import numpy as np

from .realworld_tool_expert import ToolExecutionError


def tray_parts(policy, actor):
    state=policy.snapshot()[0][actor]
    p=np.asarray(state['pos']);r=np.asarray(state['mat']);parts=[]
    for shape in policy.objects[actor]['collision_shapes']:
        if shape.get('type')!='box':raise ToolExecutionError('E39 tray release needs reviewed box collision parts')
        q=np.asarray(shape.get('quat',[1,0,0,0]),float);w,x,y,z=q/np.linalg.norm(q)
        sr=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        h=np.asarray(shape['size']);c=np.asarray(shape.get('pos',[0,0,0]))
        points=(np.asarray(list(product(*zip(-h,h))))@sr.T+c)@r.T+p
        parts.append(points)
    return parts


def release_lift(meshes, parts, current_point, target, margin=.004, maximum=.060):
    """Pure geometry: all relevant mesh bottoms clear intersecting real parts."""
    delta=np.asarray(target,float)-np.asarray(current_point,float);lift=0.
    for mesh in meshes:
        points=np.asarray(mesh,float)+delta;lo=points.min(0);hi=points.max(0)
        for part in parts:
            bounds=np.asarray(part,float);pl=bounds.min(0);ph=bounds.max(0)
            if np.all(hi[:2]>=pl[:2]-margin) and np.all(lo[:2]<=ph[:2]+margin):
                lift=max(lift,float(ph[2]+margin-lo[2]))
    lift=max(0.,lift)
    if not np.isfinite(lift)or lift>maximum:
        raise ToolExecutionError('E39 T release would require an unreviewed fall distance')
    return lift


def cradle_mass_offset(local_com,desired_rotation_in_tray):
    # Native T COM is 6.5mm off its authored root; the source cradle has an
    # 8mm-wide top. A yaw-zero T placed by root alone tips despite true contact.
    offset=-float((np.asarray(desired_rotation_in_tray)@np.asarray(local_com))[0])
    if not np.isfinite(offset)or abs(offset)>.015:
        raise ToolExecutionError('E39 mass-centred placement exceeds native preserved-position tolerance')
    return offset


def place_held_piece(policy, name, ref, side, local_point, target, rotation, support='work_tray',*,release_at_current_if_clear=False):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_e39_delivery import open_mesh_preview, _actual_open, _static_obstacles
    from .execution_design_e39_package import _native_route, body_bounds
    from .execution_design_clip_handover import public_rotation_poses, rotation_clear
    from .execution_design_thin_edge import table_bounds_task
    if policy.task!='E39' or not policy.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E39 piece placement requires private engineering authorization')
    if support!='work_tray' or name not in policy.d['target_members']:
        raise ToolExecutionError('E39 piece release is restricted to the actual work tray')
    control=dict(actor=name,local=np.asarray(local_point,float).tolist())
    target=np.asarray(target,float)
    from .engineering_checkpoint import _plain
    view=policy.a.scene.objects[name].root_physx_view
    local_com=np.asarray(_plain(view.get_coms())).reshape(-1,7)[0,:3]
    carrier_r=np.asarray(policy.frame(dict(actor=support))[1])
    desired_body=np.asarray(rotation)if rotation is not None else np.asarray(policy.frame(dict(actor=name))[1])
    offset=cradle_mass_offset(local_com,carrier_r.T@desired_body)
    target=target+carrier_r@np.array([offset,0,0])
    guard=lambda:policy.require_held(ref,side)
    if release_at_current_if_clear:
        point=policy.point(control);tcp=policy.tip(side);r=np.asarray(policy.a.tcp_rotation_task(side))
        opened=open_mesh_preview(policy,side)
        closed=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        opened_world=[mesh@r.T+tcp for mesh in opened]
        lift=release_lift(closed+opened_world,tray_parts(policy,support),point,target)
        release=target+[0,0,lift]
        if not actual_release_ready(policy,name,control,target,release,closed+opened_world,support):
            raise ToolExecutionError('Restored E39 held T is not in a measured clear functional release band')
        _native_route(policy,side,r,[tcp,tcp+[0,0,.06]],'restored-functional-clear-release-withdraw')
        with (policy.a.out/'e39-piece-release.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(stage='release-at-measured-functional-band',actor=name,side=side,
                actual_bottom_point=point.tolist(),nominal_release=release.tolist(),
                resumed_without_repeating_transport=True,actual_native_local_com=local_com.tolist()))+'\n')
        policy.stage('e39-functional-clear-release-'+name)
        finish_release(policy,name,ref,side,opened,rotation,support)
        return
    height=max(policy.clearance,float(target[2])+.07)
    policy.move_point(side,control,[*policy.point(control)[:2],height],guard)
    if rotation is not None:
        # Use the same actual world Jacobian and complete public rotation arc
        # as the other E39 routes before the first turn with this held T.
        tcp=policy.tip(side);current=np.asarray(policy.a.tcp_rotation_task(side))
        body=np.asarray(policy.snapshot()[0][name]['mat'])
        desired=np.asarray(rotation)@body.T@current
        meshes=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        lo,hi=body_bounds(policy,name);meshes.append(np.asarray(list(product(*zip(lo,hi)))))
        local=[(mesh-tcp)@current for mesh in meshes]
        obstacles=_static_obstacles(policy,{name})
        other='right'if side=='left'else'left'
        obstacles.extend(actual_mesh(policy.a,other,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers))
        poses=public_rotation_poses(tcp,current,desired)
        if not rotation_clear(local,tcp,current,poses,obstacles,table_bounds_task(policy.a.scene)['top']):
            raise ToolExecutionError('E39 held T turn lacks actual mesh clearance')
        _native_route(policy,side,desired,[tcp],'held-T-turn-before-tray-release')
        policy.rotate_actor(name,side,rotation)
    policy.move_point(side,control,[*target[:2],height],guard)
    point=policy.point(control);tcp=policy.tip(side);r=np.asarray(policy.a.tcp_rotation_task(side))
    opened=open_mesh_preview(policy,side)
    closed=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    opened_world=[mesh@r.T+tcp for mesh in opened]
    lift=release_lift(closed+opened_world,tray_parts(policy,support),point,target)
    release=target+[0,0,lift]
    hover_tcp=tcp+release-point
    _native_route(policy,side,r,[hover_tcp,hover_tcp+[0,0,.06]],'held-T-clear-release-and-withdraw')
    def clear_tray():
        guard();_,contacts=policy.snapshot()
        if any(frozenset((support,side+'_finger'+str(i)))in contacts for i in (1,2)):
            raise ToolExecutionError('E39 T approach touched a tray wall before release')
    with (policy.a.out/'e39-piece-release.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(stage='before-clear-release',actor=name,side=side,
            actual_bottom_point=point.tolist(),target=target.tolist(),release=release.tolist(),
            physical_fall_m=lift,actual_native_local_com=local_com.tolist(),cradle_x_offset_m=offset,
            all_closed_and_open_meshes_screened=True))+'\n')
    policy.stage('e39-clear-release-'+name)
    from .execution_design_e39_reference import move_payload_point
    def ready():
        now_tcp=policy.tip(side);now_r=np.asarray(policy.a.tcp_rotation_task(side))
        actual=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        opening=[mesh@now_r.T+now_tcp for mesh in opened]
        return actual_release_ready(policy,name,control,target,release,actual+opening,support)
    move_payload_point(policy,side,control,release,clear_tray,done=ready)
    clear_tray();finish_release(policy,name,ref,side,opened,rotation,support)


def actual_release_ready(policy,name,control,target,release,meshes,support):
    """Functional release band from actual hand mesh and physical mass support."""
    from .engineering_checkpoint import _plain
    point=policy.point(control)
    if np.max(np.abs(point[:2]-np.asarray(target)[:2]))>.015:return False
    if point[2]>float(release[2])+float(policy.d.get('geometry_tolerance_m',.003)):return False
    if not 0.<float(point[2]-target[2])<=.060:return False
    if release_lift(meshes,tray_parts(policy,support),point,point)>1e-7:return False
    base,carrier=policy.frame(dict(actor=support));p,body=policy.frame(dict(actor=name))
    com=np.asarray(_plain(policy.a.scene.objects[name].root_physx_view.get_coms())).reshape(-1,7)[0,:3]
    mass_point=carrier.T@(p+body@com-base);desired=carrier.T@(np.asarray(target)-base)
    size=np.asarray(policy.objects[name]['size']);candidates=[]
    for shape in policy.objects[support]['collision_shapes']:
        half=np.asarray(shape['size']);center=np.asarray(shape.get('pos',[0,0,0]))
        if np.all(half[:2]<size[:2])and half[2]>.004:
            candidates.append((np.linalg.norm(center[:2]-desired[:2]),center,half))
    if not candidates:raise ToolExecutionError('No reviewed real E39 cradle surface')
    _,center,half=min(candidates,key=lambda x:x[0])
    return bool(np.all(abs(mass_point[:2]-center[:2])<=half[:2]))


def finish_release(policy,name,ref,side,opened,rotation,support):
    from .execution_design_e39_delivery import _actual_open
    policy.release(ref,side)
    if not policy.contact(name,support):raise ToolExecutionError('E39 naturally released T lacks actual tray support')
    # The opening preview is only a plan until the native finger meshes agree.
    _actual_open(policy,side,opened)
    policy.move(side,policy.tip(side)+[0,0,.06])
    policy.wait(1)
    if not policy.contact(name,support):raise ToolExecutionError('E39 T lost tray support after empty-hand withdrawal')
    if rotation is not None:
        actual=np.asarray(policy.frame(dict(actor=name))[1]);error=actual@np.asarray(rotation).T
        if np.arccos(np.clip((np.trace(error)-1)/2,-1,1))>np.deg2rad(12.):
            raise ToolExecutionError('E39 released T exceeds the unchanged native 12-degree orientation limit')



def require_local_piece_poses(policy):
    """Immediate unchanged native orientation/support check, with no wait."""
    from .realworld_tool_expert import _axis_rotation
    state,contacts=policy.snapshot();carrier=policy.d['local_order']['actor']
    rotation=np.asarray(state[carrier]['mat'])
    for name,yaw in policy.d['local_order']['expected_yaws'].items():
        if any(state[name]['grasp'])or frozenset((name,carrier))not in contacts:
            raise ToolExecutionError('E39 placed T lost actual released tray support: '+name)
        relative=rotation.T@np.asarray(state[name]['mat'])
        error=relative@_axis_rotation([0,0,1],yaw).T
        if np.arccos(np.clip((np.trace(error)-1)/2,-1,1))>np.deg2rad(12.):
            raise ToolExecutionError('E39 placed T exceeds unchanged native orientation: '+name)

def complete_blue_suffix(policy, options):
    """Continue the measured pre-blue-place checkpoint through every stage."""
    from .realworld_tool_expert import _axis_rotation
    targets=options['local_targets'];yaws=options['expected_yaws']
    if policy.variant not in ('A','B','C'):raise ToolExecutionError('This measured E39 placement suffix requires a source variant')
    if set(targets)!=set(policy.d['target_members']):raise ToolExecutionError('Missing original measured T targets')
    policy._e39_home={s:np.asarray(p,float)for s,p in options['home_tips'].items()}
    name=options.get('held_actor','blue_active');side=options.get('held_hand','right')
    if name not in policy.d['target_members']or side not in ('left','right'):raise ToolExecutionError('Unknown measured E39 held piece')
    ref=policy.ref(name);policy.require_held(ref,side)
    base,r=policy.frame(dict(actor='work_tray'));target=base+r@np.asarray(targets[name])
    previous=policy.clearance;policy.clearance=policy.measured_transport_clearance(name,side,target)
    try:place_held_piece(policy,name,ref,side,policy.bottom_local(name),target,r@_axis_rotation([0,0,1],yaws[name]),release_at_current_if_clear=bool(options.get('release_at_current_if_clear',False)))
    finally:policy.clearance=previous
    for name in options.get('remaining_after_blue',['black_active']if policy.variant=='C'else[]):
        policy.place(name,'work_tray',targets[name],yaws[name])
    require_local_piece_poses(policy)
    policy.package_stage();require_local_piece_poses(policy);policy.deliver()

