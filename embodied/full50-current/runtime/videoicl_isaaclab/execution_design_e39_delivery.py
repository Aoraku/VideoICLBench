"""E39 engineering contact suffixes; measured public motion only."""
import numpy as np
from itertools import product
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e39_package import (_authorized,_empty,_guard_closed_package,
    body_bounds,_log,preflight_empty_orientation,orient_empty,_native_route)


def station_axis_contains(policy,axis):
    zone=next(z for z in policy.spec['zones']if z['id']==policy.d['destination_zone'])
    lower=float(zone['xy'][axis]-zone['half_size'][axis]);upper=float(zone['xy'][axis]+zone['half_size'][axis])
    tolerance=float(policy.d.get('geometry_tolerance_m',.003))
    return all(float(body_bounds(policy,name)[0][axis])>=lower-tolerance and float(body_bounds(policy,name)[1][axis])<=upper+tolerance
               for name in ('protective_box','protective_box_lid'))


def clip_mesh_height(vertices,lower,upper):
    """Clip the actual convex finger collision hull against a wall-height slab."""
    from scipy.spatial import ConvexHull
    points=np.asarray(vertices,float)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all()or lower>=upper:
        raise ToolExecutionError('Invalid E39 actual contact hull')
    hull=ConvexHull(points);edges=set()
    for triangle in hull.simplices:
        for a,b in ((0,1),(1,2),(2,0)):edges.add(tuple(sorted((int(triangle[a]),int(triangle[b])))))
    clipped=[p for p in points if lower<=p[2]<=upper]
    for i,j in edges:
        a,b=points[i],points[j]
        if abs(b[2]-a[2])<1e-10:continue
        for z in (lower,upper):
            fraction=(z-a[2])/(b[2]-a[2])
            if 0<=fraction<=1:clipped.append(a+fraction*(b-a))
    if len(clipped)<3:raise ToolExecutionError('E39 actual finger misses wall-height slab')
    return np.asarray(clipped)


def open_mesh_preview(policy,side):
    """Predict an empty Panda RELEASE from actual q, then require native readback."""
    from .execution_design_e33_grasp import actual_mesh
    a=policy.a;tcp=policy.tip(side);current=np.asarray(a.tcp_rotation_task(side));robot=a.scene.robots[side]
    names=a.scene.embodiment.fingers;ids=[robot.find_joints(n)[0][0]for n in a.scene.embodiment.finger_joints]
    q=robot.data.joint_pos[0,ids].cpu().numpy()
    jaw=_native_finger_axis(policy,side)
    world=[actual_mesh(a,side,'panda_hand')-tcp]
    world.extend(actual_mesh(a,side,name)-tcp+sign*(.04-float(position))*jaw for name,position,sign in zip(names,q,(1.,-1.)))
    return [m@current for m in world]


def _native_finger_axis(policy,side):
    """The actual prismatic Jacobian remains defined with fully closed fingers."""
    robot=policy.a.scene.robots[side];body=robot.find_bodies(policy.a.scene.embodiment.fingers[0])[0][0]
    joint=policy.c.ids[side][1][0]
    jac=robot.root_physx_view.get_jacobians()[0,body-1 if robot.is_fixed_base else body,:3,joint].detach().cpu().numpy()
    axis=np.asarray(policy.a.scene.layout.task_rotation).T@jac
    if not np.isfinite(axis).all()or abs(np.linalg.norm(axis)-1.)>.002:raise ToolExecutionError('Invalid native E39 finger prismatic axis')
    return axis/np.linalg.norm(axis)


def _down_targets(policy,side):
    robot=policy.a.scene.robots[side];ids=[robot.find_bodies(n)[0][0]for n in policy.a.scene.embodiment.fingers];palm=policy.c.ids[side][2]
    points=robot.data.body_pos_w[0,ids].detach().cpu().numpy();p=robot.data.body_pos_w[0,palm].detach().cpu().numpy()
    jaw=_native_finger_axis(policy,side);forward=np.asarray(policy.a.scene.layout.task_rotation).T@(points.mean(0)-p);forward-=jaw*(forward@jaw);forward/=np.linalg.norm(forward)
    current=np.asarray(policy.a.tcp_rotation_task(side));basis=current.T@np.column_stack((jaw,forward,np.cross(jaw,forward)))
    return [np.column_stack(([sign,0.,0.],[0.,0.,-1.],np.cross([sign,0.,0.],[0.,0.,-1.])))@basis.T for sign in (1.,-1.)]


def _actual_open(policy,side,local):
    from .execution_design_e33_grasp import actual_mesh
    for _ in range(3):
        policy.act(side,'RELEASE');_empty(policy,side,contact_free=True)
        tcp=policy.tip(side);r=np.asarray(policy.a.tcp_rotation_task(side));actual=[(actual_mesh(policy.a,side,n)-tcp)@r for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        errors=[float(np.linalg.norm(a-b,axis=1).max())for a,b in zip(actual,local)]
        _log(policy,'actual-open-preview-confirmation',side=side,maximum_vertex_errors_m=errors)
        if max(errors)<=.001:return actual
    raise ToolExecutionError('Actual E39 open fingers disagree with measured prismatic preview')


def _static_obstacles(policy,excluded):
    result=[]
    for name in policy.objects:
        if name not in excluded:
            obj=policy.objects[name];p,r=policy.frame(dict(actor=name))
            shapes=obj.get('collision_shapes')
            if shapes:
                from .layout import rotation_matrix
                for shape in shapes:
                    if shape.get('type')!='box':raise ToolExecutionError('Unreviewed E39 compound collision shape')
                    h=np.asarray(shape['size']);center=np.asarray(shape.get('pos',[0,0,0]));sr=rotation_matrix(shape.get('quat',[1,0,0,0]))
                    local=np.asarray(list(product(*zip(-h,h))))@sr.T+center
                    result.append(local@r.T+p)
            else:
                lo,hi=body_bounds(policy,name);result.append(np.asarray(list(product(*zip(lo,hi)))))
    for f in policy.spec.get('fixtures',[]):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed E39 delivery fixture')
        c=np.asarray([*f['xy'],f['z']]);h=np.asarray(f['size']);result.append(np.asarray(list(product(*zip(c-h,c+h)))))
    return result


def _screen_translations(policy,side,local,rotation,positions,excluded,*,initial_escape_axis=None):
    from .execution_design_clip_grasp import convex_meshes_clear
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e33_grasp import actual_mesh
    world=[m@np.asarray(rotation).T for m in local];floor=table_bounds_task(policy.a.scene)['top'];obstacles=_static_obstacles(policy,excluded)
    other='right'if side=='left'else'left'
    obstacles.extend(actual_mesh(policy.a,other,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers))
    current=np.asarray(positions[0],float).copy();segments=[]
    for goal in positions[1:]:
        goal=np.asarray(goal,float)
        for _ in range(400):
            delta=goal-current
            if max(abs(delta))<=.002:break
            axis=int(np.argmax(abs(delta)));end=current.copy();end[axis]+=np.sign(delta[axis])*min(.010,abs(delta[axis]));segments.append((current.copy(),end.copy()));current=end
        else:raise ToolExecutionError('E39 delivery public sweep step bound exhausted')
    for segment_index,(start,end) in enumerate(segments):
        for mesh_index,mesh in enumerate(world):
            swept=np.vstack((mesh+start,mesh+end))
            if swept[:,2].min()<floor+.0002:raise ToolExecutionError('E39 delivery hand sweep intersects table')
            hits=[i for i,o in enumerate(obstacles)if not convex_meshes_clear(swept,o,clearance=.002)]
            if hits:
                anchor=policy.tip(side)
                normal_escape=(initial_escape_axis==1 and side=='left'
                    and np.max(abs(np.array([start[0],end[0]])-anchor[0]))<1e-7
                    and min(start[1],end[1])>=anchor[1]-1e-7
                    and max(start[1],end[1])<=anchor[1]+.0351
                    and min(start[2],end[2])>=anchor[2]-1e-7)
                normal_escape=normal_escape or (initial_escape_axis==2
                    and np.max(abs(np.array([start[:2],end[:2]])-anchor[:2]))<1e-7
                    and min(start[2],end[2])>=anchor[2]-1e-7
                    and max(start[2],end[2])<=anchor[2]+.0151)
                if normal_escape and all(convex_meshes_clear(swept,obstacles[i],clearance=0.)for i in hits):
                    _log(policy,'nonpenetrating-initial-normal-clearance-escape',side=side,start=start.tolist(),end=end.tolist(),mesh_index=mesh_index)
                    continue
                raise ToolExecutionError('E39 delivery hand sweep intersects protected body: '+str(dict(start=start.tolist(),end=end.tolist(),mesh_index=mesh_index,obstacle_indices=hits)))


def required_protected_vertical_clearance(meshes,obstacles,margin=.003):
    lift=0.
    for mesh in meshes:
        lo,hi=np.asarray(mesh).min(0),np.asarray(mesh).max(0)
        for obstacle in obstacles:
            low,high=np.asarray(obstacle).min(0),np.asarray(obstacle).max(0)
            if np.all(hi[:2]>=low[:2])and np.all(lo[:2]<=high[:2]):
                lift=max(lift,float(high[2]+margin-lo[2]))
    return max(0.,lift)


def lift_clear_of_protected_rim(policy,side='left',millimeters=8.):
    from .execution_design_e33_grasp import actual_mesh
    package=next(p for p in policy.d['packages']if p['container']=='protective_box')
    _empty(policy,side);_guard_closed_package(policy,package)
    anchors={n:policy.frame(dict(actor=n))for n in policy.d['reference_objects']}
    start=policy.tip(side);rotation=np.asarray(policy.a.tcp_rotation_task(side))
    goal=start+[0,0,float(millimeters)/1000]
    local=[(actual_mesh(policy.a,side,n)-start)@rotation for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    _native_route(policy,side,rotation,[start,goal],'up-only-before-reference-rim-contact')
    excluded={'protective_box','protective_box_lid','work_tray',*policy.d['target_members']}
    _screen_translations(policy,side,local,rotation,[start,goal],excluded,initial_escape_axis=2)
    policy.stage('e39-clear-protected-rim-before-wall-push')
    policy.act(side,'UP',mm=float(millimeters));_guard_closed_package(policy,package)
    for n,(p,r)in anchors.items():
        pp,rr=policy.frame(dict(actor=n))
        if np.linalg.norm(pp-p)>.003 or np.linalg.norm(rr-r)>.03:
            raise ToolExecutionError('E39 clearance lift disturbed native protected reference')


def wall_plan(policy,side,axis,target,rotation,local,*,contact_z=None,cross_offset=0.,force_envelope=0.,direction_override=None):
    package=next(p for p in policy.d['packages']if p['container']=='protective_box');box=package['container'];start=policy.frame(dict(actor=box))[0].copy();direction=(1 if target>start[axis]else-1)if direction_override is None else direction_override
    if direction not in(-1,1):raise ToolExecutionError('Invalid E39 intended wall face')
    world=[m@np.asarray(rotation).T for m in local];lo,hi=body_bounds(policy,box);lidtop=float(body_bounds(policy,package['lid'])[1][2]);z=max(.85 if contact_z is None else float(contact_z),lidtop+.004-world[0][:,2].min(),.802-min(m[:,2].min()for m in world))
    fingers=world[1:]
    vertices=max(fingers,key=lambda m:m[:,0].mean())if axis==1 else np.concatenate(fingers)
    clipped=clip_mesh_height(vertices,float(lo[2])-z,float(hi[2])-z)
    extreme=float(clipped[:,axis].max()if direction>0 else clipped[:,axis].min())
    leading=clipped[direction*(clipped[:,axis]-extreme)>-.0004].mean(0)
    cross=1-axis;contact=start.copy();offset=float(cross_offset)
    if abs(offset)>min(.1501,float(policy.objects[box]['size'][cross])-.012):raise ToolExecutionError('E39 wall contact exceeds reviewed face interior')
    contact[cross]+=offset-leading[cross];contact[2]=z
    # Intersect the actual rotated wall plane at this contact's transverse
    # coordinate. An AABB extreme can be 16mm in empty space at seven degrees.
    origin,body_rotation=policy.frame(dict(actor=box));obj=policy.objects[box]
    center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float);face=center.copy();face[axis]-=direction*obj['size'][axis]
    face=origin+body_rotation@face;normal=body_rotation[:,axis]
    if abs(float(normal[axis]))<.9:raise ToolExecutionError('E39 wall angle requires a separate physical orientation route')
    surface=contact+leading;surface[axis]=face[axis]-sum(normal[k]*(surface[k]-face[k])for k in range(3)if k!=axis)/normal[axis]
    inside=body_rotation.T@(surface-origin)-center
    if any(abs(float(inside[k]))>obj['size'][k]+.002 for k in range(3)if k!=axis):raise ToolExecutionError('E39 selected contact leaves the real wall')
    contact[axis]=surface[axis]-leading[axis]-direction*.004
    end=contact.copy();end[axis]+=target-start[axis]+direction*force_envelope;approach=contact.copy();approach[axis]-=direction*.010
    home=policy.tip(side).copy();park=np.array([-.19,.25,max(home[2],.920)])if side=='left'else home.copy()
    high=max(home[2],park[2],lidtop+.008-min(m[:,2].min()for m in world));retreat=end.copy();retreat[axis]-=direction*.035
    # At the right rear-wall approach the far-X/high-Z corner is needlessly
    # near full extension. Travel on the empty near-X side, descend outside
    # the rear wall, then approach at the measured wall-contact height.
    if side=='right'and axis==1:
        ingress=[np.array([home[0],approach[1],high]),np.array([home[0],approach[1],z]),approach,contact]
        retreat_goals=[retreat,np.array([retreat[0],retreat[1],high])]
    else:
        ingress=[np.array([*approach[:2],high]),approach,contact]
        retreat_goals=([retreat,np.array([park[0],retreat[1],z]),np.array([park[0],retreat[1],high]),park]
            if side=='left'else[retreat,np.array([retreat[0],retreat[1],high])])
    positions=[home,*ingress,end,*retreat_goals]
    return dict(positions=positions,ingress=ingress,end=end,retreat_goals=retreat_goals,contact=contact,home=home,high=high,approach=approach,start=start,direction=direction,z=z,leading=leading,cross_offset=offset)


def _resumed_wall_positions(policy,side,axis,plan):
    # Withdraw along the wall normal before lifting or shifting sideways.
    # The CP113 near finger is only 0.5mm above the protected tray rim;
    # shifting across that rim at the sagged contact height is unsafe.
    start=policy.tip(side).copy();withdraw=start.copy();withdraw[axis]-=plan['direction']*.035
    raised=withdraw.copy();raised[2]=max(float(raised[2]),plan['z'])
    aligned=raised.copy();aligned[1-axis]=plan['contact'][1-axis]
    contact=aligned.copy();contact[axis]=plan['contact'][axis]
    return [start,withdraw,raised,aligned,contact,plan['end'],*plan['retreat_goals']]


def move_clear_air(policy,side,goal,guard):
    """Use legal 25mm public requests only on preflighted high empty travel."""
    start=policy.tip(side);goal=np.asarray(goal,float)
    state,_=policy.snapshot();i=('left','right').index(side)
    fast=(min(float(start[2]),float(goal[2]))>=.900 and abs(float(goal[2]-start[2]))<=.002
        and float(np.linalg.norm(goal[:2]-start[:2]))>=.040 and not any(v['grasp'][i]for v in state.values())
        and policy.a.scene.embodiment.config['control']['step_mm'][1]>=25.)
    previous=policy.max_mm
    try:
        if fast:policy.max_mm=25.
        policy.move(side,goal,guard)
    finally:policy.max_mm=previous


def _validate_feedback_step(policy,side,goal,axis):
    from .execution_design_local_pose_path import inspect_local_pose_path
    from .execution_design_e33_grasp import actual_mesh
    rotation=np.asarray(policy.a.tcp_rotation_task(side));start=policy.tip(side).copy()
    path=inspect_local_pose_path(policy.a,policy.c,side,[dict(position=np.asarray(goal).tolist(),rotation=rotation.tolist())],minimum_joint_margin_rad=.02)
    if not path['feasible']:raise ToolExecutionError('E39 measured contact feedback step lacks actual native IK margin')
    local=[(actual_mesh(policy.a,side,n)-start)@rotation for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    _screen_translations(policy,side,local,rotation,[start,goal],{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']})


def reposition_wall_contact(policy,side,axis,target,offset,guard,*,direction=None):
    """Release wall pressure before moving the actual point of force."""
    from .execution_design_e33_grasp import actual_mesh
    start=policy.tip(side).copy();rotation=np.asarray(policy.a.tcp_rotation_task(side))
    local=[(actual_mesh(policy.a,side,n)-start)@rotation for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    fresh=wall_plan(policy,side,axis,target,rotation,local,cross_offset=offset,direction_override=direction)
    outside=start.copy();outside[axis]-=fresh['direction']*.012
    raised=outside.copy();raised[2]=max(raised[2],fresh['z'])
    aligned=raised.copy();aligned[1-axis]=fresh['contact'][1-axis]
    positions=[start,outside,raised,aligned,fresh['contact']]
    _native_route(policy,side,rotation,positions,'unload-before-measured-wall-contact-change')
    _screen_translations(policy,side,local,rotation,positions,{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']},initial_escape_axis=axis if side=='left'else None)
    for goal in positions[1:]:policy.move(side,goal,guard)
    return fresh


def push_wall(policy,side,axis,target,*,resume_contact=False,withdraw_at_handover=False,cross_offset=0.,yaw_feedback=False,yaw_correction=False):
    _authorized(policy);package=next(p for p in policy.d['packages']if p['container']=='protective_box');_guard_closed_package(policy,package);_empty(policy,side,contact_free=not resume_contact)
    if resume_contact:
        local=open_mesh_preview(policy,side);rotation=np.asarray(policy.a.tcp_rotation_task(side));plan=wall_plan(policy,side,axis,target,rotation,local,cross_offset=-.012 if side=='left'and axis==1 else cross_offset,force_envelope=.020 if yaw_correction else 0.)
        positions=_resumed_wall_positions(policy,side,axis,plan)
        _native_route(policy,side,rotation,positions,'resumed-actual-contact-wall-push')
        _screen_translations(policy,side,local,rotation,positions,{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']},initial_escape_axis=axis)
        chosen=(rotation,plan)
    else:chosen=None
    local=open_mesh_preview(policy,side)
    for rotation in ([]if resume_contact else _down_targets(policy,side)):
        try:
            plan=wall_plan(policy,side,axis,target,rotation,local,cross_offset=cross_offset)
            preflight_empty_orientation(policy,side,rotation)
            _native_route(policy,side,rotation,plan['positions'],'whole-open-finger-wall-push-before-first-action')
            _screen_translations(policy,side,local,rotation,plan['positions'],{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']})
            chosen=(rotation,plan);break
        except ToolExecutionError as error:_log(policy,'wall-route-candidate-rejected',error=str(error))
    if chosen is None:raise ToolExecutionError('No full actual-joint/mesh E39 open-finger wall push')
    rotation,plan=chosen
    anchors={n:policy.frame(dict(actor=n))for n in policy.d['reference_objects']}
    def guard():
        _guard_closed_package(policy,package)
        for name,(p,r)in anchors.items():
            pp,rr=policy.frame(dict(actor=name))
            if np.linalg.norm(pp-p)>.002 or np.linalg.norm(rr-r)>.02:raise ToolExecutionError('E39 wall push moved protected reference')
    policy.stage('e39-wall-push-'+side+'-'+str(axis))
    if not resume_contact:_actual_open(policy,side,local);orient_empty(policy,side,rotation)
    # Actual public turn can leave a small quantized residual. Recompute its
    # real wall-height contact surface and reject if the full route changed.
    actual=np.asarray(policy.a.tcp_rotation_task(side))
    from .execution_design_e33_grasp import actual_mesh
    local=[(actual_mesh(policy.a,side,n)-policy.tip(side))@actual for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    plan=wall_plan(policy,side,axis,target,actual,local,cross_offset=-.012 if resume_contact and side=='left'and axis==1 else cross_offset,force_envelope=.020 if yaw_correction else 0.)
    positions=plan['positions']
    if resume_contact:
        positions=_resumed_wall_positions(policy,side,axis,plan)
    _native_route(policy,side,actual,positions,'actual-oriented-open-wall-push')
    _screen_translations(policy,side,local,actual,positions,{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']},initial_escape_axis=axis if resume_contact else None)
    _log(policy,'open-finger-wall-contact-plan',side=side,axis=axis,target=float(target),contact=plan['contact'].tolist(),leading=plan['leading'].tolist(),z=plan['z'])
    if side=='right'and axis==0:
        _log(policy,'actual-final-X-contact-geometry',tcp=policy.tip(side).tolist(),
             rotation=actual.tolist(),meshes_local_tcp=[m.tolist()for m in local],
             box_position=policy.frame(dict(actor=package['container']))[0].tolist(),
             box_rotation=policy.frame(dict(actor=package['container']))[1].tolist())
    if not resume_contact:
        for goal in plan['ingress']:move_clear_air(policy,side,goal,guard)
    else:
        for goal in positions[1:5]:policy.move(side,goal,guard)
    history=[];yaw_errors=[];cross_errors=[];cross=1-axis;direction=plan['direction'];endpoint_tolerance=.008 if side=='left'and axis==1 else.005
    for _ in range(120):
        guard();position=policy.frame(dict(actor=package['container']))[0];remaining=direction*(target-position[axis])
        if (station_axis_contains(policy,axis)if side=='right'else remaining<=endpoint_tolerance):break
        if yaw_feedback and remaining<.010:
            zone=next(z for z in policy.spec['zones']if z['id']==policy.d['destination_zone'])
            if direction*(position[axis]-zone['xy'][axis])>.010:raise ToolExecutionError('E39 contact correction exhausted real station translation headroom')
        from .execution_design_e33_grasp import actual_mesh
        palm_low=float(actual_mesh(policy.a,side,'panda_hand')[:,2].min());lid_top=float(body_bounds(policy,package['lid'])[1][2])
        hand_low=min(float(actual_mesh(policy.a,side,n)[:,2].min())for n in ('panda_hand',*policy.a.scene.embodiment.fingers))
        if hand_low<.802:raise ToolExecutionError('E39 open-wall push hand reached table')
        obstacles=_static_obstacles(policy,{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']})
        meshes=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        required=required_protected_vertical_clearance(meshes,obstacles)
        if required>0.:
            lift_clear_of_protected_rim(policy,side,millimeters=min(10.,max(6.,required*1000+1.)))
            continue
        if palm_low<lid_top+.004:
            policy.act(side,'UP',mm=6.);continue
        # A force-limited wall push can drift sideways while still advancing
        # the package. Recenter the measured finger contact on the *actual*
        # wall instead of accumulating that drift until the push stalls.
        live_offset=wall_yaw_offset(policy,axis=axis,direction=direction)if yaw_feedback else plan['cross_offset']
        error=float(position[cross]+live_offset-plan['leading'][cross]-policy.tip(side)[cross])
        if abs(error)>.003:
            cross_errors.append(abs(error))
            if len(cross_errors)>=6 and min(cross_errors[-6:-3])-min(cross_errors[-3:])<.0003:
                raise ToolExecutionError('E39 wall contact cross alignment lacks actual progress')
            fresh=reposition_wall_contact(policy,side,axis,target,live_offset,guard,direction=direction)
            for key in ('leading','cross_offset','z'):plan[key]=fresh[key]
            continue
        cross_errors=[]
        history.append(float(remaining))
        import math
        body_rotation=policy.frame(dict(actor=package['container']))[1]
        yaw_errors.append(abs(math.atan2(float(body_rotation[1,0]),float(body_rotation[0,0]))))
        if len(history)>=9 and min(history[-9:-4])-min(history[-4:])<.0003:
            turning=yaw_feedback and min(yaw_errors[-9:-4])-min(yaw_errors[-4:])>math.radians(.3)
            if not turning:raise ToolExecutionError('E39 open-wall push lacks actual box translation or yaw progress')
        token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(direction<0)]
        # Native v4's 5mm relative request settled at only 3.6--3.9N and
        # stalled against the unchanged package/table static friction. Use
        # the existing public 10mm bound, with actual box progress feedback.
        finishing_yaw=yaw_correction or yaw_feedback and remaining<.010
        amount=7. if finishing_yaw else min(10.,max(1.,remaining*1000))
        if finishing_yaw:
            zone=next(z for z in policy.spec['zones']if z['id']==policy.d['destination_zone'])
            if direction*(position[axis]-zone['xy'][axis])>.010:raise ToolExecutionError('E39 yaw correction exhausted real station translation headroom')
            goal=policy.tip(side).copy();goal[axis]+=direction*amount/1000;_validate_feedback_step(policy,side,goal,axis)
        policy.act(side,token,mm=amount)
    else:raise ToolExecutionError('E39 open-wall push action bound exhausted')
    if side=='left'and axis==1 and not withdraw_at_handover:
        # This is a handover region, not a source-mandated exact point. The
        # opposite hand's later motion naturally leaves this empty finger.
        policy.stage('e39-left-wall-handover-region');policy.wait(1);guard()
        return abs(float(policy.frame(dict(actor=package['container']))[0][axis])-float(target))<=endpoint_tolerance
    retreat=policy.tip(side).copy();retreat[axis]-=direction*.035
    goals=[np.asarray(g).copy()for g in plan['retreat_goals']]
    # Public tracking can drift several millimeters; withdraw from the actual
    # last contact before following the preflighted empty retreat.
    correction=retreat-np.asarray(plan['retreat_goals'][0]);goals[0]=retreat
    if len(goals)>1:goals[1][:2]+=correction[:2]
    for goal in goals:move_clear_air(policy,side,goal,guard)
    policy.stage('e39-wall-push-released-stable');policy.wait(2);guard()
    return station_axis_contains(policy,axis)if side=='right'else abs(float(policy.frame(dict(actor=package['container']))[0][axis])-float(target))<=endpoint_tolerance


def cover_drag_plan(policy,side,target,rotation,local):
    package=next(p for p in policy.d['packages']if p['container']=='protective_box');box=package['container'];start=policy.frame(dict(actor=box))[0].copy()
    world=[m@np.asarray(rotation).T for m in local];far=max(world[1:],key=lambda m:m[:,0].mean())
    toe=far[far[:,2]<=far[:,2].min()+.002].mean(0);top=float(body_bounds(policy,package['lid'])[1][2]);home=policy.tip(side).copy()
    contact=start.copy()-toe;contact[2]=top-toe[2]
    # A controlled 0.5mm downward public request establishes real contact.
    # Penetrating geometry is not assumed by this pose calculation.
    end=contact.copy();end[1]+=target-start[1];raised=end+[0,0,.012]
    high=max(float(home[2]),top+.010-min(m[:,2].min()for m in world))
    positions=[home,np.array([*contact[:2],high]),contact,end,raised]
    return dict(positions=positions,home=home,contact=contact,start=start,toe=toe,high=high)


def drag_cover(policy,target=-.30,*,resume_contact=False):
    """Slide a closed supported box using genuine toe/cover friction.

    Force magnitudes are read from the native contact sensor. Neither contact
    force nor box/lid pose is assigned. A non-sliding surface fails promptly.
    """
    _authorized(policy);side='right';package=next(p for p in policy.d['packages']if p['container']=='protective_box')
    _guard_closed_package(policy,package);_empty(policy,side,contact_free=not resume_contact)
    start=policy.frame(dict(actor=package['container']))[0]
    if abs(float(start[1])+.10)>.008:raise ToolExecutionError('E39 cover drag requires the actual left-wall endpoint')
    local=open_mesh_preview(policy,side);chosen=np.asarray(policy.a.tcp_rotation_task(side))if resume_contact else None
    for rotation in ([]if resume_contact else _down_targets(policy,side)):
        try:
            plan=cover_drag_plan(policy,side,target,rotation,local)
            preflight_empty_orientation(policy,side,rotation)
            _native_route(policy,side,rotation,plan['positions'],'whole-toe-cover-drag-before-first-action')
            _screen_translations(policy,side,local,rotation,plan['positions'],{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']})
            chosen=rotation;break
        except ToolExecutionError as error:_log(policy,'cover-drag-candidate-rejected',error=str(error))
    if chosen is None:raise ToolExecutionError('No actual-joint/whole-hand E39 cover drag route')
    anchors={n:policy.frame(dict(actor=n))for n in policy.d['reference_objects']}
    def guard():
        _guard_closed_package(policy,package)
        for name,(p,r)in anchors.items():
            pp,rr=policy.frame(dict(actor=name))
            if np.linalg.norm(pp-p)>.002 or np.linalg.norm(rr-r)>.02:raise ToolExecutionError('E39 cover drag disturbed reference')
    def force():
        return sum(float(policy.c.contact_forces.get(frozenset((package['lid'],f'{side}_finger{i}')),0.))for i in (1,2))
    policy.stage('e39-right-toe-cover-drag')
    if not resume_contact:_actual_open(policy,side,local);orient_empty(policy,side,chosen)
    actual=np.asarray(policy.a.tcp_rotation_task(side))
    from .execution_design_e33_grasp import actual_mesh
    local=[(actual_mesh(policy.a,side,n)-policy.tip(side))@actual for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    plan=cover_drag_plan(policy,side,target,actual,local)
    if resume_contact:
        start=policy.tip(side).copy();end=start+[0,target-plan['start'][1],0]
        raised=end+[0,0,.015]
        plan['positions']=[start,end,raised]
    _native_route(policy,side,actual,plan['positions'],'actual-oriented-toe-cover-drag')
    _screen_translations(policy,side,local,actual,plan['positions'],{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']})
    if not resume_contact:
        for goal in plan['positions'][1:3]:policy.move(side,goal,guard)
    history=[];contact_attempts=0
    for _ in range(180):
        guard();box=policy.frame(dict(actor=package['container']))[0];remaining=float(box[1]-target)
        if station_axis_contains(policy,1):break
        measured=force()
        if measured>25.:raise ToolExecutionError('E39 toe drag excessive native contact force')
        if measured<.05:
            contact_attempts+=1
            if contact_attempts>8:raise ToolExecutionError('E39 toe drag failed to establish native cover contact')
            policy.act(side,'DOWN',mm=min(10.,.5+contact_attempts));continue
        if measured>18.:
            policy.act(side,'UP',mm=.5);continue
        contact_attempts=0;history.append(float(box[1]))
        if len(history)>=9 and min(history[-9:-4])-min(history[-4:])<.0003:
            raise ToolExecutionError('E39 toe/cover friction produced no actual box sliding')
        _log(policy,'actual-cover-drag-contact',contact_force_magnitude_n=measured,box_position=box.tolist(),tcp=policy.tip(side).tolist())
        policy.act(side,'RIGHT'if remaining>0 else'LEFT',mm=10.)
    else:raise ToolExecutionError('E39 toe drag public action bound exhausted')
    policy.stage('e39-cover-drag-retreat')
    tip=policy.tip(side).copy();policy.move(side,tip+[0,0,.015],guard)
    policy.stage('e39-cover-drag-released-stable');policy.wait(3);guard()
    return station_axis_contains(policy,1)


def deliver_supported_package(policy,*,from_cover=False,resume_left=False,resume_cover=False):
    """Keep one world alive across every already implemented delivery phase."""
    from .execution_design_probe import persist_engineering_checkpoint
    from .engineering_e39_suffix import verify_released_boxed_tray
    package=next(p for p in policy.d['packages']if p['container']=='protective_box')
    def save(stage):
        policy.stage(stage);persist_engineering_checkpoint(policy.a,policy.a.out.parent.name)
    if not from_cover:
        if not push_wall(policy,'left',1,-.10,resume_contact=resume_left):raise ToolExecutionError('E39 left push did not enter handover region')
        save('e39-left-push-passed-continue-cover')
    if not drag_cover(policy,resume_contact=resume_cover):raise ToolExecutionError('E39 right cover contact did not enter station Y')
    save('e39-cover-drag-passed-continue-final-X')
    if not push_wall(policy,'right',0,.225):raise ToolExecutionError('E39 right wall did not enter station X')
    save('e39-real-supported-delivery-complete')
    return verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)


def clear_left_wall_contact(policy):
    """Leave the measured low rear-wall contact before the other hand enters."""
    _authorized(policy);side='left';package=next(p for p in policy.d['packages']if p['container']=='protective_box')
    anchors={n:policy.frame(dict(actor=n))for n in policy.d['reference_objects']}
    def guard():
        _empty(policy,side);_guard_closed_package(policy,package)
        for name,(p,r)in anchors.items():
            pp,rr=policy.frame(dict(actor=name))
            if np.linalg.norm(pp-p)>.002 or np.linalg.norm(rr-r)>.02:raise ToolExecutionError('E39 handover escape moved protected reference')
    guard();start=policy.tip(side).copy();outside=start+[0,.035,0];near=outside.copy();near[0]=-.19
    high=near.copy();high[2]=max(.920,float(start[2]));park=high.copy();park[1]=.25
    positions=[start,outside,near,high,park];rotation=np.asarray(policy.a.tcp_rotation_task(side))
    from .execution_design_e33_grasp import actual_mesh
    local=[(actual_mesh(policy.a,side,n)-start)@rotation for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
    _native_route(policy,side,rotation,positions,'actual-left-low-back-before-up-handover')
    _screen_translations(policy,side,local,rotation,positions,{'protective_box','protective_box_lid','work_tray',*policy.d['target_members']})
    policy.stage('e39-clear-left-for-actual-right-handover')
    for goal in positions[1:]:move_clear_air(policy,side,goal,guard)


def wall_yaw_offset(policy,*,axis=0,direction=1,maximum=None):
    import math
    rotation=policy.frame(dict(actor='protective_box'))[1]
    yaw=math.atan2(float(rotation[1,0]),float(rotation[0,0]))
    if axis==1:return float(np.clip(-direction*.4*yaw,-.030,.030))
    # Native v5 slid 14.5mm with only .087deg yaw at a local Y about -60mm.
    # Use that measured neutral anchor, then adjust from the current yaw.
    limit=.120 if maximum is None else maximum
    local_y=float(np.clip(-.060+direction*.4*yaw,-limit,limit))
    local_x=-direction*float(policy.objects['protective_box']['size'][0])
    return float(rotation[1,0]*local_x+rotation[1,1]*local_y)


def record_loaded_package_com(policy):
    from .engineering_checkpoint import _plain
    rows=[];weighted=np.zeros(3);total=0.
    for name in ['protective_box','protective_box_lid','work_tray',*policy.d['target_members']]:
        view=policy.a.scene.objects[name].root_physx_view
        mass=float(np.asarray(_plain(view.get_masses())).reshape(-1)[0]);local=np.asarray(_plain(view.get_coms())).reshape(-1,7)[0,:3]
        p,r=policy.frame(dict(actor=name));world=p+r@local
        rows.append(dict(actor=name,mass_kg=mass,local_com=local.tolist(),world_com=world.tolist()));weighted+=mass*world;total+=mass
    p,r=policy.frame(dict(actor='protective_box'));combined=r.T@(weighted/total-p)
    _log(policy,'actual-loaded-package-mass-com',bodies=rows,total_mass_kg=total,combined_com_box_local=combined.tolist(),empirical_neutral_contact_y_m=-.060)
    return combined


def deliver_wall_package(policy,*,resume_left=False,from_right=False):
    """New source-neutral reset layout: actual wall contact for all three legs."""
    from .execution_design_probe import persist_engineering_checkpoint
    from .engineering_e39_suffix import verify_released_boxed_tray
    package=next(p for p in policy.d['packages']if p['container']=='protective_box')
    record_loaded_package_com(policy)
    if from_right:clear_left_wall_contact(policy)
    legs=([('left',1,-.21)]if not from_right else[])+[('right',1,-.30),('right',0,.225)]
    for side,axis,target in legs:
        offset=wall_yaw_offset(policy,axis=axis,direction=1 if axis==0 else-1)if side=='right'else 0.
        if not push_wall(policy,side,axis,target,resume_contact=resume_left and side=='left',withdraw_at_handover=side=='left',cross_offset=offset,yaw_feedback=side=='right'):
            raise ToolExecutionError('E39 actual wall leg did not reach its functional region')
        policy.stage('e39-wall-leg-passed-'+side+'-'+str(axis));persist_engineering_checkpoint(policy.a,policy.a.out.parent.name)
    return verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
