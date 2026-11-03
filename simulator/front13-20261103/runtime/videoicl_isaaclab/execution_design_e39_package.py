"""E39 private engineering package routes using public actions and native feedback.

No body/joint state, scoring rules, or task inputs are written. These routes
require independent physical verification and do not themselves assert success.
"""
import json
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def _authorized(author):
    if (author.task!='E39' or not getattr(author.a,'_execution_design_reference_authorized',False)
            or not author.a.control_report.get('engineering_reference_only')):
        raise ToolExecutionError('E39 package reference requires explicit engineering authorization')


def _empty(author,side,*,contact_free=False):
    state,contacts=author.snapshot();i=('left','right').index(side)
    if any(v['grasp'][i]for v in state.values()):
        raise ToolExecutionError('E39 pushing requires an empty hand')
    if contact_free and any(frozenset((n,f'{side}_finger{k}'))in contacts for n in state for k in (1,2)):
        raise ToolExecutionError('E39 approach requires a contact-free empty hand')


def _log(author,phase,**values):
    with (author.a.out/'e39-package-geometry.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(phase=phase,step=author.c.steps,**values))+'\n')


def body_bounds(author,name):
    p,r=author.frame(dict(actor=name));obj=author.objects[name]
    center=p+r@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    extent=np.abs(r)@np.asarray(obj['size'],float)
    return center-extent,center+extent


def palm_clear_contact(tcp,palm,fingers,obstacle_top,wall_lower,wall_upper,axis,direction,gap=.004):
    """Measure the TCP offset from the real closed finger leading surface.

    Returns a height that clears the *whole palm* by 4mm, while checking that
    actual finger geometry still overlaps the real target wall vertically.
    This is geometry only: native contacts, reachability and progress remain
    separate requirements.
    """
    tcp,palm=map(lambda x:np.asarray(x,float),(tcp,palm));fingers=np.concatenate(fingers)
    if (tcp.shape!=(3,)or palm.ndim!=2 or palm.shape[1]!=3 or fingers.ndim!=2 or fingers.shape[1]!=3
            or axis not in (0,1)or direction not in (-1,1)or not np.isfinite([*tcp,obstacle_top,wall_lower,wall_upper]).all()
            or not np.isfinite(palm).all()or not np.isfinite(fingers).all()):
        raise ToolExecutionError('Invalid actual E39 push geometry')
    rel=palm-tcp;f=fingers-tcp
    z=max(.866,float(obstacle_top)-float(rel[:,2].min())+.004)
    overlap=min(z+float(f[:,2].max()),wall_upper)-max(z+float(f[:,2].min()),wall_lower)
    if overlap<.006:raise ToolExecutionError('Palm-clear fingers do not overlap the package wall')
    leading=float(f[:,axis].max()if direction>0 else f[:,axis].min())
    return dict(tcp_z=z,leading_offset=leading,contact_gap=float(gap),wall_overlap_m=overlap,
                palm_clearance_m=z+float(rel[:,2].min())-float(obstacle_top))


def push_rotation(author,side,tilt_degrees=90.):
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    down=physical_grasp_targets(author.a,author.c,side,[0,0,1],[1,0,0])[0]
    local=np.asarray(down).T@np.column_stack(([1.,0,0],[0,0,-1.],[0,1.,0]))
    # Lid contact needs the 60 degree forward finger reach. The tall box wall
    # can instead be pushed with the downward fingers' side faces, avoiding
    # the far-Y reach failure of the forward-leaning 60 degree package route.
    if tilt_degrees not in (60.,90.):raise ToolExecutionError('Unreviewed E39 push tilt')
    tilt=math.radians(tilt_degrees)
    jaw=np.array([0.,-1.,0]);forward=np.array([math.cos(tilt),0.,-math.sin(tilt)])
    if tilt_degrees==90.:return down
    return np.column_stack((jaw,forward,np.cross(jaw,forward)))@local.T


def preflight_empty_orientation(author,side,target):
    """No actions: actual public turn path and whole collision-mesh arc."""
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_local_pose_path import inspect_local_pose_path
    from itertools import product
    _empty(author,side,contact_free=True);target=np.asarray(target,float);errors=[]
    tcp=author.tip(side);current=np.asarray(author.a.tcp_rotation_task(side))
    local=[(actual_mesh(author.a,side,n)-tcp)@current for n in ('panda_hand',*author.a.scene.embodiment.fingers)]
    obstacles=[]
    for name in author.objects:
        lo,hi=body_bounds(author,name)
        obstacles.append(np.asarray(list(product(*zip(lo,hi)))))
    other='right'if side=='left'else'left'
    obstacles.extend(actual_mesh(author.a,other,n)for n in ('panda_hand',*author.a.scene.embodiment.fingers))
    for fixture in author.spec.get('fixtures',[]):
        if fixture.get('type')!='box':raise ToolExecutionError('Unreviewed E39 rotation fixture')
        center=np.asarray([*fixture['xy'],fixture['z']]);half=np.asarray(fixture['size'])
        obstacles.append(np.asarray(list(product(*zip(center-half,center+half)))))
    poses=public_rotation_poses(tcp,current,target)
    if not rotation_clear(local,tcp,current,poses,obstacles,table_bounds_task(author.a.scene)['top']):
        raise ToolExecutionError('E39 push orientation arc lacks actual mesh/table clearance')
    path=inspect_local_pose_path(author.a,author.c,side,poses,minimum_joint_margin_rad=.02,
                                 max_rotation_step_rad=math.radians(2.))
    _log(author,'actual-public-orientation-preflight',side=side,geometry_clear=True,path=path)
    if not path['feasible']:raise ToolExecutionError('E39 push orientation lacks continuous actual native joint path')
    return path


def orient_empty(author,side,target):
    """Feedback through bounded public rotations; no direct wrist writes."""
    preflight_empty_orientation(author,side,target)
    target=np.asarray(target,float);errors=[]
    for _ in range(100):
        _empty(author,side,contact_free=True)
        current=np.asarray(author.a.tcp_rotation_task(side));delta=target@current.T
        angle=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))
        if angle<math.radians(1):return
        errors.append(angle)
        if len(errors)>=25 and min(errors[-25:-12])-min(errors[-12:])<math.radians(.1):
            raise ToolExecutionError('E39 empty push wrist made no progress')
        if math.pi-angle<.01:
            values,vectors=np.linalg.eigh((delta+np.eye(3))/2);axis=vectors[:,np.argmax(values)]
        else:axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
        i=int(np.argmax(np.abs(axis)))
        token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
        author.act(side,token,degrees=min(7.,abs(math.degrees(angle*axis[i]))))
    raise ToolExecutionError('E39 empty push wrist action bound exhausted')


def capture_closed_geometry(author,side):
    from .execution_design_e33_grasp import actual_mesh
    _empty(author,side,contact_free=True)
    author.act(side,'GRASP');author.wait(2);_empty(author,side,contact_free=True)
    tcp=author.tip(side);palm=actual_mesh(author.a,side,'panda_hand')
    fingers=[actual_mesh(author.a,side,n)for n in author.a.scene.embodiment.fingers]
    predicted=getattr(author,'_e39_forecast_closed_local',{}).get(side)
    if predicted is not None:
        rotation=np.asarray(author.a.tcp_rotation_task(side))
        actual=[(mesh-tcp)@rotation for mesh in [palm,*fingers]]
        errors=[float(np.max(np.linalg.norm(a-b,axis=1)))if a.shape==b.shape else float('inf')
                for a,b in zip(actual,predicted)]
        _log(author,'closed-preview-native-confirmation',side=side,mesh_max_error_m=errors)
        if len(actual)!=len(predicted)or max(errors)>.001:
            raise ToolExecutionError('Actual native empty closure disagrees with E39 planning preview')
    _log(author,'actual-closed-empty-hand',side=side,tcp=tcp.tolist(),rotation=author.a.tcp_rotation_task(side).tolist(),
         palm=palm.tolist(),fingers=[f.tolist()for f in fingers])
    return tcp,palm,fingers


def retreat_loaded_tray_release(author,side):
    """Empty left wrist exits nearward before rising at the far box edge."""
    _authorized(author);_empty(author,side,contact_free=True)
    if side!='left':raise ToolExecutionError('Reviewed E39 box retreat is left-hand only')
    # Preserve the achieved downward tray pose. Parent CPU audit checked nine
    # nearward samples; actual geometry is checked again, not assumed identical.
    from .execution_design_e33_grasp import actual_mesh
    meshes=[actual_mesh(author.a,side,n)for n in ('panda_hand',*author.a.scene.embodiment.fingers)]
    top=max(float(body_bounds(author,n)[1][2])for n in ('work_tray','protective_box',*author.d['target_members'],*author.d['reference_objects']))
    if min(float(m[:,2].min())for m in meshes)<top+.004:
        raise ToolExecutionError('E39 empty retreat lacks measured tray/reference clearance')
    tip=author.tip(side)
    if tip[0]>.115+.015 or abs(tip[1]-.05)>.015 or not .905<=tip[2]<=.94:
        raise ToolExecutionError('E39 release pose outside reviewed nearward-exit corridor')
    author.stage('workflow-empty-back-before-up')
    author.move(side,[-.19,float(tip[1]),float(tip[2])],lambda:_empty(author,side,contact_free=True))
    author.move(side,[-.19,float(tip[1]),1.02],lambda:_empty(author,side,contact_free=True))


def _hinge_angle(author,package):
    joint=author.spec['joints'][package['hinge_joint_index']]
    if joint['type']!='revolute'or joint['axis']!='X'or joint['parent']!=package['container']or joint['child']!=package['lid']:
        raise ToolExecutionError('E39 requires its authored actual X hinge')
    relative=author.frame(dict(actor=package['container']))[1].T@author.frame(dict(actor=package['lid']))[1]
    angle=math.atan2(float(relative[2,1]-relative[1,2])/2,float((np.trace(relative)-1)/2))
    if not -.03<=angle<=math.radians(103):raise ToolExecutionError('E39 actual lid angle outside hinge limits')
    return angle


def _native_route(author,side,rotation,positions,label):
    from .execution_design_drawer_ik_probe import inspect
    from .execution_design_clip_handover import public_rotation_poses
    from .execution_design_local_pose_path import inspect_local_pose_path
    current=author.tip(side).copy();start=np.asarray(author.a.tcp_rotation_task(side));poses=public_rotation_poses(current,start,rotation)
    for goal in positions:
        goal=np.asarray(goal,float)
        for _ in range(400):
            delta=goal-current
            if np.max(abs(delta))<=.002:break
            i=int(np.argmax(abs(delta)));current[i]+=np.sign(delta[i])*min(.010,abs(delta[i]))
            poses.append(dict(position=current.tolist(),rotation=np.asarray(rotation).tolist()))
        else:raise ToolExecutionError('E39 public route exceeded finite planning steps')
    path=inspect_local_pose_path(author.a,author.c,side,poses,minimum_joint_margin_rad=.02,
                                 max_rotation_step_rad=math.radians(2.))
    _log(author,'actual-continuous-public-route-preflight',label=label,side=side,path=path)
    if not path['feasible']:raise ToolExecutionError('E39 actual public route lacks continuous IK margin: '+label)
    results=[inspect(author.a,author.c,side,[dict(position=list(p),rotation=np.asarray(rotation).tolist())])[0]for p in positions]
    _log(author,'actual-native-route-preflight',label=label,side=side,collision_verified=False,results=results)
    if any(not r['kinematically_reachable']or r['minimum_joint_margin_rad']<.02 for r in results):
        raise ToolExecutionError('E39 actual native route lacks IK margin: '+label)


def _no_grasp_move(author,side,target):
    author.move(side,target,lambda:_empty(author,side,contact_free=True))


def forecast_closed_meshes(tcp,palm,fingers,jaw,positions,closed):
    """Read-only Panda prismatic prediction, checked against later native grip.

    This does not claim that the fingers have physically closed. It permits a
    complete route rejection before even the first public GRASP. Rigid finger
    collision meshes translate along the measured separation axis only.
    """
    tcp=np.asarray(tcp,float);jaw=np.asarray(jaw,float);positions=np.asarray(positions,float);closed=np.asarray(closed,float)
    if tcp.shape!=(3,)or jaw.shape!=(3,)or positions.shape!=(2,)or closed.shape!=(2,)or abs(np.linalg.norm(jaw)-1)>.001:
        raise ToolExecutionError('Actual Panda prismatic preview requires two measured fingers')
    if not np.isfinite(np.r_[tcp,jaw,positions,closed]).all()or np.any(positions<-.0002)or np.any(positions>.041)or np.any(closed<0)or np.any(closed>.0001):
        raise ToolExecutionError('E39 preview refuses non-Panda or nonempty closure')
    meshes=[np.asarray(palm,float)-tcp]
    for i,(mesh,sign)in enumerate(zip(fingers,(-1.,1.))):
        meshes.append(np.asarray(mesh,float)-tcp+sign*(positions[i]-closed[i])*jaw)
    return meshes


def preflight_prepacked_workflow(author):
    """No actions: reject incomplete lid and three-segment delivery routes.

    Future box centers and closed-lid bounds are planning hypotheses only. The
    live world is never assigned them; every stage later checks actual poses,
    contacts and measured closed meshes again before moving the arm.
    """
    from .execution_design_e33_grasp import actual_mesh
    _authorized(author);package=next(p for p in author.d['packages']if p['container']=='protective_box')
    box=author.frame(dict(actor='protective_box'))[0];lo,hi=body_bounds(author,'protective_box')
    closed_top=float(hi[2])+.006
    predictions={}
    for side in ('left','right'):
        _empty(author,side,contact_free=True)
        tcp=author.tip(side);rotation=push_rotation(author,side)
        current=np.asarray(author.a.tcp_rotation_task(side));robot=author.a.scene.robots[side]
        if author.a.scene.embodiment.name!='franka':raise ToolExecutionError('E39 prismatic preview is Panda-only')
        names=author.a.scene.embodiment.fingers
        fingers=[actual_mesh(author.a,side,n)for n in names];palm=actual_mesh(author.a,side,'panda_hand')
        body_ids=[robot.find_bodies(n)[0][0]for n in names]
        roots=robot.data.body_pos_w[0,body_ids].detach().cpu().numpy()
        jaw=author.a.scene.layout.task_rotation.T@(roots[0]-roots[1]);jaw/=np.linalg.norm(jaw)
        joints=robot.data.joint_pos[0,author.c.ids[side][1]].detach().cpu().numpy()
        preview=forecast_closed_meshes(tcp,palm,fingers,jaw,joints,author.a.scene.embodiment.config['gripper']['closed'])
        local=[m@current for m in preview]
        rotated=[m@rotation.T for m in local]
        preflight_empty_orientation(author,side,rotation)
        predictions[side]=dict(home=tcp,rotation=rotation,relative=rotated,local=local)
    # Full lid contact and retreat, using actual predicted closed-finger X reach.
    row=predictions['right'];lid_rotation=push_rotation(author,'right',tilt_degrees=60.)
    preflight_empty_orientation(author,'right',lid_rotation)
    lid_meshes=[mesh@lid_rotation.T for mesh in row['local']]
    palm=lid_meshes[0];finger=np.concatenate(lid_meshes[1:])
    x=float(lo[0])-float(palm[:,0].max())-.006;z=1.069;home=row['home']
    if x+float(finger[:,0].max())<float(lo[0])+.008:raise ToolExecutionError('Predicted closed fingers miss E39 lid')
    _native_route(author,'right',lid_rotation,[home,[home[0],home[1],z],[x,home[1],z],
        [x,-.225,z],[x,-.14,z],[x,-.225,z],[home[0],-.225,z],[home[0],home[1],z],home],'entire-lid-before-first-action')
    for side,axis,start,target in [('left',1,np.asarray(box),-.17),
                                  ('right',1,np.array([box[0],-.17,box[2]]),-.30),
                                  ('right',0,np.array([box[0],-.30,box[2]]),.225)]:
        row=predictions[side];relative=row['relative'];direction=1 if target>start[axis]else-1
        plan=palm_clear_contact(np.zeros(3),relative[0],relative[1:],closed_top,float(lo[2]),float(hi[2]),axis,direction)
        contact=start.copy();contact[2]=plan['tcp_z'];extent=author.objects['protective_box']['size'][axis]
        contact[axis]=start[axis]-direction*extent-plan['leading_offset']-direction*.004
        end=contact.copy();end[axis]+=target-start[axis]
        approach=contact.copy();approach[axis]-=direction*.035;home=row['home']
        lowest=min(float(m[:,2].min())for m in relative)
        high=max(float(home[2]),plan['tcp_z'],closed_top+.008-lowest)
        retreat=end.copy();retreat[axis]-=direction*.035
        positions=[home,[home[0],home[1],high],[*approach[:2],high],approach,contact,end,
                   retreat,[home[0],retreat[1],retreat[2]],[home[0],retreat[1],high],[home[0],home[1],high],home]
        _native_route(author,side,row['rotation'],positions,'entire-package-'+side+'-'+str(axis)+'-before-first-action')
    author._e39_forecast_closed_local={side:row['local']for side,row in predictions.items()}
    _log(author,'entire-prepacked-workflow-planned',actions=author.c.steps,closed_mesh_prediction_pending_actual_confirmation=True)


def preflight_lid_phase(author):
    """No actions: complete native/geometry screen for only the lid stage.

    The user permits fresh engineering phase fixtures. Delivery is tested in
    its own later checkpoint world, so a delivery candidate cannot consume or
    invalidate this lid-only physical diagnostic.
    """
    from .execution_design_e33_grasp import actual_mesh
    _authorized(author);side='right';_empty(author,side,contact_free=True)
    tcp=author.tip(side);current=np.asarray(author.a.tcp_rotation_task(side))
    rotation=push_rotation(author,side,tilt_degrees=60.)
    robot=author.a.scene.robots[side];names=author.a.scene.embodiment.fingers
    if author.a.scene.embodiment.name!='franka':raise ToolExecutionError('E39 lid preview is Panda-only')
    body_ids=[robot.find_bodies(n)[0][0]for n in names]
    roots=robot.data.body_pos_w[0,body_ids].detach().cpu().numpy()
    jaw=author.a.scene.layout.task_rotation.T@(roots[0]-roots[1]);jaw/=np.linalg.norm(jaw)
    joints=robot.data.joint_pos[0,author.c.ids[side][1]].detach().cpu().numpy()
    closed=forecast_closed_meshes(tcp,actual_mesh(author.a,side,'panda_hand'),
        [actual_mesh(author.a,side,n)for n in names],jaw,joints,author.a.scene.embodiment.config['gripper']['closed'])
    local=[m@current for m in closed];rotated=[m@rotation.T for m in local]
    preflight_empty_orientation(author,side,rotation)
    lo,_=body_bounds(author,'protective_box');x=float(lo[0])-float(rotated[0][:,0].max())-.006
    if x+float(np.concatenate(rotated[1:])[:,0].max())<float(lo[0])+.008:
        raise ToolExecutionError('Predicted closed fingers miss E39 lid')
    z=1.069;home=tcp
    positions=[home,[home[0],home[1],z],[x,home[1],z],[x,-.225,z],[x,-.14,z],
               [x,-.225,z],[home[0],-.225,z],[home[0],home[1],z]]
    _native_route(author,side,rotation,positions,'lid-only-entire-stage-before-first-action')
    author._e39_forecast_closed_local={side:local}
    _log(author,'lid-phase-entire-route-planned',actions=author.c.steps,
         closed_mesh_prediction_pending_actual_confirmation=True)


def prepare_lid_from_empty_checkpoint(author,initial_rotation=None,*,force_neutral=False):
    """Try the real current pose first, then a clear empty neutral waypoint.

    C's source wrist had a valid endpoint but the coarse five-degree local
    screen exhausted its 0.18rad joint substep. Planning now samples two-degree
    increments with the same joint/pose bounds. A neutral empty-hand route is
    available without replaying any completed packaging.
    """
    _authorized(author);side='right';_empty(author,side,contact_free=True)
    if force_neutral:
        target=push_rotation(author,side,tilt_degrees=90.)
        preflight_empty_orientation(author,side,target)
        orient_empty(author,side,target)
        preflight_lid_phase(author)
        _log(author,'measured-neutral-before-lid-branch',prior_bad_joint_path_not_replayed=True)
        return
    try:preflight_lid_phase(author);return
    except ToolExecutionError as exc:_log(author,'lid-current-pose-planning-rejected',error=str(exc))
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    high=author.tip(side).copy();high[2]=max(float(high[2]),1.)
    current=np.asarray(author.a.tcp_rotation_task(side))
    _native_route(author,side,current,[high],'empty-right-high-before-neutral-lid-pose')
    from .execution_design_e39_delivery import _static_obstacles
    from .execution_design_clip_handover import convex_meshes_clear
    from .execution_design_e33_grasp import actual_mesh
    obstacles=_static_obstacles(author,set())
    obstacles.extend(actual_mesh(author.a,'left',n)for n in ('panda_hand',*author.a.scene.embodiment.fingers))
    displacement=high-author.tip(side)
    for name in ('panda_hand',*author.a.scene.embodiment.fingers):
        mesh=actual_mesh(author.a,side,name);sweep=np.vstack((mesh,mesh+displacement))
        if not all(convex_meshes_clear(sweep,obstacle,clearance=.002)for obstacle in obstacles):
            raise ToolExecutionError('E39 empty neutral lift lacks measured hand clearance')
    _no_grasp_move(author,side,high)
    candidates=[]
    if initial_rotation is not None:candidates.append(np.asarray(initial_rotation,float))
    candidates.extend(physical_grasp_targets(author.a,author.c,side,[0,0,1],[1,0,0]))
    for target in candidates:
        try:
            preflight_empty_orientation(author,side,target)
        except ToolExecutionError as exc:
            _log(author,'lid-neutral-candidate-rejected',error=str(exc));continue
        orient_empty(author,side,target)
        try:preflight_lid_phase(author);return
        except ToolExecutionError as exc:_log(author,'lid-from-neutral-planning-rejected',error=str(exc))
    raise ToolExecutionError('No measured empty-hand neutral route to the E39 lid')


def close_lid_by_contact(author,package):
    """Push the real opened lid past vertical, then retreat for gravity closure."""
    _authorized(author);side='right';name=package['lid'];box=package['container']
    author.stage('workflow-contact-close-'+name)
    author.park_e39_idle_hand(side)
    _empty(author,side,contact_free=True)
    rotation=push_rotation(author,side,tilt_degrees=60.)
    home=author.tip(side).copy()
    # Native right Jacobian is measured here; translated-left offline results
    # are deliberately not treated as sufficient to execute a route.
    _native_route(author,side,rotation,[home,[home[0],home[1],1.069],[.105,home[1],1.069],
        [.105,-.225,1.069],[.105,-.14,1.069]],'lid-contact-approach')
    orient_empty(author,side,rotation);tcp,palm,fingers=capture_closed_geometry(author,side)
    lo,_=body_bounds(author,box)
    x=float(lo[0])-float((palm-tcp)[:,0].max())-.006
    relative=np.concatenate(fingers)-tcp
    if x+float(relative[:,0].max())<float(lo[0])+.008:
        raise ToolExecutionError('E39 palm-clear closed finger misses actual lid X span')
    z=1.069
    _native_route(author,side,rotation,[[x,-.225,z],[x,-.14,z]],'actual-closed-finger-lid-offset')
    _no_grasp_move(author,side,[home[0],home[1],z])
    _no_grasp_move(author,side,[x,home[1],z])
    _no_grasp_move(author,side,[x,-.225,z])
    box_start=author.frame(dict(actor=box))[0].copy();history=[]
    for _ in range(90):
        _empty(author,side)
        angle=_hinge_angle(author,package)
        if angle<=math.radians(80):break
        if np.max(np.abs(author.frame(dict(actor=box))[0]-box_start))>.008:
            raise ToolExecutionError('E39 protective box shifted during lid push')
        history.append(angle)
        if len(history)>=25 and max(history[-25:-12])-min(history[-12:])<math.radians(.1):
            raise ToolExecutionError('E39 lid push failed to reduce actual hinge angle')
        # Every increment is a public Cartesian action. Actual hinge feedback
        # determines when gravity may take over; no hinge position is written.
        author.act(side,'LEFT',mm=3.)
        if author.tip(side)[1]>-.11:raise ToolExecutionError('E39 lid-push contact corridor exhausted')
    else:raise ToolExecutionError('E39 lid-contact public action bound exhausted')
    author.act(side,'RIGHT',mm=10.)
    _no_grasp_move(author,side,author.tip(side)+[0,-.05,0])
    _no_grasp_move(author,side,[home[0],author.tip(side)[1],z])
    _no_grasp_move(author,side,[home[0],home[1],z])
    # Do not wait a fixed eight physics seconds after a lid already closed.
    # Its actual hinge is the unchanged native acceptance condition.
    for _ in range(3):
        if abs(_hinge_angle(author,package))<=float(package['lid_orientation_tolerance']):break
        author.wait(1)
    if abs(_hinge_angle(author,package))>float(package['lid_orientation_tolerance']):
        raise ToolExecutionError('E39 real lid did not settle closed after contact push')
    _log(author,'lid-contact-closed',lid_angle_rad=_hinge_angle(author,package),box_position=author.frame(dict(actor=box))[0].tolist())


def _guard_closed_package(author,package):
    _empty(author,'left');_empty(author,'right')
    box=package['container'];tray='work_tray'
    if not author.contact(box,'table')or not author.contact(tray,box):
        raise ToolExecutionError('E39 package push lost actual table/tray support')
    if any(not author.contact(n,tray)for n in author.d['target_members']):
        raise ToolExecutionError('E39 package push lost actual contents support')
    if abs(_hinge_angle(author,package))>float(package['lid_orientation_tolerance']):
        raise ToolExecutionError('E39 package push opened the real lid')
    _,r=author.frame(dict(actor=box))
    if float(r[2,2])<.995:raise ToolExecutionError('E39 package tilted during table push')


def push_package_segment(author,package,side,axis,target):
    """Push from an actual closed finger surface, stop by measured box center."""
    _authorized(author);_guard_closed_package(author,package)
    box=package['container'];start=author.frame(dict(actor=box))[0];direction=1 if target>start[axis]else -1
    rotation=push_rotation(author,side);home=author.tip(side).copy()
    orient_empty(author,side,rotation);tcp,palm,fingers=capture_closed_geometry(author,side)
    lo,hi=body_bounds(author,box);top=float(body_bounds(author,package['lid'])[1][2])
    plan=palm_clear_contact(tcp,palm,fingers,top,float(lo[2]),float(hi[2]),axis,direction)
    contact=np.asarray(start).copy();contact[2]=plan['tcp_z']
    face=float(lo[axis]if direction>0 else hi[axis])
    contact[axis]=face-plan['leading_offset']-direction*plan['contact_gap']
    end=contact.copy();end[axis]+=target-start[axis]
    # Approach away from the package, above its top; descend at the side only.
    approach=contact.copy();approach[axis]-=direction*.035
    lowest=min(float((m-tcp)[:,2].min())for m in [palm,*fingers])
    high=max(float(home[2]),plan['tcp_z'],top+.008-lowest)
    positions=[home,[home[0],home[1],high],[*approach[:2],high],approach,contact]
    positions.extend(np.linspace(contact,end,9))
    _native_route(author,side,rotation,positions,'closed-package-'+side+'-'+str(axis))
    _log(author,'package-contact-plan',side=side,axis=axis,direction=direction,plan=plan,
        actual_box_start=start.tolist(),target=float(target),tcp_contact=contact.tolist())
    _no_grasp_move(author,side,[home[0],home[1],high])
    _no_grasp_move(author,side,[*approach[:2],high])
    _no_grasp_move(author,side,approach)
    _no_grasp_move(author,side,contact)
    history=[];cross=1-axis
    for _ in range(180):
        _guard_closed_package(author,package)
        p=author.frame(dict(actor=box))[0];remaining=direction*(target-p[axis])
        if remaining<=.002:break
        if abs(p[cross]-start[cross])>.006:raise ToolExecutionError('E39 box drifted outside reviewed push corridor')
        if abs(author.tip(side)[2]-plan['tcp_z'])>.003:raise ToolExecutionError('E39 push wrist lost measured palm clearance')
        history.append(float(remaining))
        if len(history)>=25 and min(history[-25:-12])-min(history[-12:])<.0003:
            raise ToolExecutionError('E39 table push made no actual box progress')
        token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(direction<0)]
        author.act(side,token,mm=min(5.,max(1.,remaining*1000)))
    else:raise ToolExecutionError('E39 package push action bound exhausted')
    # Withdraw along the contact normal before any crosswise or rising move.
    token=(('BACK','FWD'),('RIGHT','LEFT'))[axis][int(direction<0)]
    author.act(side,token,mm=10.)
    retreat=author.tip(side).copy();retreat[axis]-=direction*.025
    _no_grasp_move(author,side,retreat)
    # Nearward first keeps the far box edge out of the high vertical reach.
    _no_grasp_move(author,side,[home[0],retreat[1],retreat[2]])
    _no_grasp_move(author,side,[home[0],retreat[1],high])
    _no_grasp_move(author,side,[home[0],home[1],high]);_no_grasp_move(author,side,home)
    author.wait(3);_guard_closed_package(author,package)


def deliver_closed_package(author):
    _authorized(author);package=next(p for p in author.d['packages']if p['container']==author.d['delivery_actor'])
    zone=next(z for z in author.spec['zones']if z['id']==author.d['destination_zone'])
    target=np.asarray(zone['xy'],float)
    if abs(target[0]-.225)>.001 or abs(target[1]+.30)>.001:
        raise ToolExecutionError('E39 table delivery route only reviewed for seed4201 station')
    author.stage('workflow-table-deliver-protective-box')
    push_package_segment(author,package,'left',1,-.17)
    push_package_segment(author,package,'right',1,float(target[1]))
    push_package_segment(author,package,'right',0,float(target[0]))
    author.wait(10);_guard_closed_package(author,package)
