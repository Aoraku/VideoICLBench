"""Reject-only empty-arm E24 transit screening from measured native geometry.

The nominal continuous joint path is a feasibility screen, not an assertion
that PhysX executed it. Execution uses small public Cartesian waypoints and
fresh full-arm collision/branch readback. No scene or robot state is assigned.
"""
import math
import json
import numpy as np
from scipy.optimize import least_squares
from .author_orientation import _axis_angle
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_e23_clearance import actual_robot_collision_geometry,actor_bounds,separation,corners
from .execution_design_drawer_ik_probe import forward_at_delta
from .execution_design_e24_collision import separation_certificate,actual_object_parts


def prefix_transforms(position,jacobian,delta):
    position=np.asarray(position,float);jacobian=np.asarray(jacobian,float)
    transforms=[np.eye(4)]
    for i,angle in enumerate(delta):
        axis=jacobian[3:,i];axis=axis/np.linalg.norm(axis);pivot=position+np.cross(axis,jacobian[:3,i])
        r=_axis_rotation(axis,float(angle));t=np.eye(4);t[:3,:3]=r;t[:3,3]=pivot-r@pivot
        transforms.append(transforms[-1]@t)
    return transforms


def body_influence(name):
    if name in ('panda_hand','panda_leftfinger','panda_rightfinger','panda_link8'):return 7
    if name.startswith('panda_link')and name[10:].isdigit():
        n=int(name[10:])
        if 0<=n<=7:return n
    raise ToolExecutionError('Unreviewed E24 arm body '+name)


def swept_vertex_bound(model,cloud,delta):
    """Arc-length bound for every vertex over a linear joint interpolation.

    Distances between successive reference joint pivots and the terminal
    vertex radius form a conservative serial-chain reach bound in any pose.
    This accounts for geometry between collision samples, not only endpoints.
    """
    n=cloud['influence']
    if n==0:return 0.
    pivots=np.array([model['position']+np.cross(model['jacobian'][3:,i],model['jacobian'][:3,i])for i in range(n)])
    terminal=float(np.linalg.norm(cloud['points']-pivots[-1],axis=1).max())
    lengths=np.linalg.norm(np.diff(pivots,axis=0),axis=1)
    reaches=np.array([terminal+float(lengths[i:].sum())for i in range(n)])
    return float(np.abs(np.asarray(delta)[:n])@reaches)


def cloud_bounds(model,q):
    ts=prefix_transforms(model['position'],model['jacobian'],np.asarray(q)-model['q'])
    rows=[]
    for cloud in model['clouds']:
        t=ts[cloud['influence']];points=cloud['points']@t[:3,:3].T+t[:3,3]
        rows.append(dict(name=cloud['name'],lo=points.min(0),hi=points.max(0)))
    return rows


def screen_joint_segment(model,start,end,obstacles,margin=.005,maximum_motion_bound=.001):
    if not 0<maximum_motion_bound<=.005:raise ValueError('At most five-mm certified intersample motion bound')
    start=np.asarray(start,float);end=np.asarray(end,float);delta=end-start
    largest=max(swept_vertex_bound(model,c,delta)for c in model['clouds'])
    pieces=max(1,int(math.ceil(largest/maximum_motion_bound)))
    if pieces>2000:raise ToolExecutionError('E24 nominal segment has excessive joint travel')
    minimum=float('inf');checked=0
    for obstacle in obstacles:corners(obstacle['lo'],obstacle['hi'])
    obstacle_low=np.asarray([o['lo']for o in obstacles],float).reshape(-1,3)
    obstacle_high=np.asarray([o['hi']for o in obstacles],float).reshape(-1,3)
    bounds=[swept_vertex_bound(model,c,delta/pieces)for c in model['clouds']]
    # A sample plus the complete between-sample motion bound encloses every
    # actual vertex along this nominal joint interpolation.
    for i in range(pieces+1):
        q=start+delta*(i/pieces)
        transforms=prefix_transforms(model['position'],model['jacobian'],q-model['q'])
        for cloud,bound in zip(model['clouds'],bounds):
            t=transforms[cloud['influence']];points=cloud['points']@t[:3,:3].T+t[:3,3]
            low=points.min(0);high=points.max(0);corners(low,high)
            if not obstacles:continue
            gaps=np.linalg.norm(np.maximum(np.maximum(low-obstacle_high,obstacle_low-high),0.),axis=1)
            # Same AABB lower bound and complete arc enclosure. Only the
            # broad phase is batched; close meshes use the original plane
            # certificate, in original obstacle order.
            for index in np.flatnonzero(gaps<margin+bound+1e-12):
                obstacle=obstacles[index];gap=separation(dict(lo=low,hi=high),obstacle)
                if gap<margin+bound and 'points'in obstacle:gap=separation_certificate(points,obstacle['points'])
                gaps[index]=gap
                if gap<margin+bound:
                    raise ToolExecutionError('E24 nominal full-arm swept clearance rejected '+cloud['name']+' / '+obstacle['name'])
            minimum=min(minimum,float(gaps.min())-bound);checked+=len(obstacles)
    return dict(samples=pieces+1,checks=checked,minimum_clearance_lower_bound_m=minimum)


def linear_waypoints(start,end,step=.005):
    start=np.asarray(start,float);end=np.asarray(end,float)
    count=max(1,int(math.ceil(float(np.max(np.abs(end-start)))/step)))
    return [start+(end-start)*(i/count)for i in range(1,count+1)]


def group_dense_waypoints(plan,start_point,start_q,maximum_distance=.005):
    """Retain dense points and corners while selecting bounded public goals."""
    if not 0<maximum_distance<=.005:raise ValueError('At most five millimetres per group')
    groups=[];group=[];origin=np.asarray(start_point,float);q0=np.asarray(start_q,float)
    previous=origin.copy();direction=None;travel=0.;first=0
    def emit():
        nonlocal group,origin,q0,travel,first
        if not group:return
        groups.append(dict(start_point=origin.copy(),start_q=q0.copy(),rows=list(group),
            point=np.asarray(group[-1]['point']),q=np.asarray(group[-1]['q']),path_length_m=travel,
            dense_start_index=first,dense_end_index=first+len(group)-1))
        first+=len(group);origin=np.asarray(group[-1]['point']);q0=np.asarray(group[-1]['q']);group=[];travel=0.
    for row in plan:
        point=np.asarray(row['point'],float);step=point-previous;length=float(np.linalg.norm(step))
        new_direction=step/length if length>1e-12 else direction
        corner=direction is not None and new_direction is not None and not np.allclose(direction,new_direction,atol=1e-7,rtol=0)
        if corner or travel+length>maximum_distance+1e-12:emit()
        if length>maximum_distance+1e-12:raise ValueError('Dense source waypoint spacing exceeds group limit')
        group.append(row);travel+=length;previous=point;direction=new_direction
    emit();return groups


def certify_groups(model,groups,obstacles,screen=None):
    screen=screen_joint_segment if screen is None else screen;result=[]
    for group in groups:
        q0=group['start_q'];q1=group['q'];length=group['path_length_m'];travel=0.;previous=group['start_point'];deviation=0.
        for row in group['rows']:
            point=np.asarray(row['point']);travel+=float(np.linalg.norm(point-previous));previous=point
            fraction=travel/length if length>1e-12 else 0.
            deviation=max(deviation,float(np.max(np.abs(np.asarray(row['q'])-(q0+(q1-q0)*fraction)))))
        if deviation>.05:raise ToolExecutionError('Grouped chord leaves original 0.05rad dense branch')
        proof=screen(model,q0,q1,obstacles,margin=.005)
        result.append(dict(point=group['point'].tolist(),q=q1.tolist(),dense_waypoint_count=len(group['rows']),
            dense_start_index=group.get('dense_start_index'),dense_end_index=group.get('dense_end_index'),
            path_length_m=length,maximum_dense_chord_joint_deviation_rad=deviation,
            direct_joint_chord_swept_certificate=proof,native_execution_verified=False))
    return result


def dense_branch_deviation(position,q,group):
    """Compare actual joints with the nearest retained dense path segment."""
    point=np.asarray(position,float);q=np.asarray(q,float);before=group['start_point'];prior=group['start_q']
    best=float('inf');deviation=float('inf')
    for row in group['rows']:
        after=np.asarray(row['point']);next_q=np.asarray(row['q']);delta=after-before;den=float(delta@delta)
        fraction=float(np.clip((point-before)@delta/den,0,1))if den>1e-20 else 0.
        distance=float(np.linalg.norm(point-(before+fraction*delta)))
        if distance<best:
            best=distance;deviation=float(np.max(np.abs(q-(prior+fraction*(next_q-prior)))))
        before=after;prior=next_q
    return deviation


def move_grouped_public(policy,side,point,guard):
    """Original discrete move policy with explicit guards around each act."""
    point=np.asarray(point,float);history=[]
    for _ in range(180):
        guard();error=point-policy.tip(side)
        if np.max(np.abs(error))<=.001:return
        axis=int(np.argmax(np.abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        policy.act(side,token,mm=abs(error[axis])*1000)
        guard()
        feedback=policy.c.action_feedback().get('control_feedback',{}).get(side,{})
        if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names') or feedback.get('consecutive_ik_refusals',0)>0):
            raise ToolExecutionError('E24 public grouped transit controller rejected an action')
        history.append(policy.tip(side).copy())
        if len(history)>12 and max(np.linalg.norm(x-history[-1])for x in history[-12:])<.0003:
            raise ToolExecutionError('Cartesian motion stalled: '+policy.a.stage)
    raise ToolExecutionError('Unreachable actual tool waypoint: '+policy.a.stage)


def plan_transit(model,targets,obstacles):
    q0=model['q'];q=q0.copy();current=model['position'].copy();rotation=model['rotation'];lo=model['limits'][:,0]+.05;hi=model['limits'][:,1]-.05
    if not(np.all(q>lo)and np.all(q<hi)):raise ToolExecutionError('E24 actual arm lacks initial joint margin')
    out=[]
    screen_joint_segment(model,q,q,obstacles)
    for endpoint in targets:
        for point in linear_waypoints(current,endpoint,step=.001):
            def residual(candidate):
                p,r=forward_at_delta(model['position'],rotation,model['jacobian'],candidate-q0)
                axis,angle=_axis_angle(rotation@r.T)
                return np.r_[10*(p-point),axis*angle,.005*(candidate-q)]
            fit=least_squares(residual,q,bounds=(lo,hi),max_nfev=150,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            p,r=forward_at_delta(model['position'],rotation,model['jacobian'],fit.x-q0)
            error=float(np.linalg.norm(p-point));angle=float(_axis_angle(rotation@r.T)[1]);distance=float(np.linalg.norm(fit.x-q))
            if error>.0007 or angle>.015 or distance>.15:
                raise ToolExecutionError('E24 continuous nearby IK transit rejected')
            collision=screen_joint_segment(model,q,fit.x,obstacles)
            out.append(dict(point=point.tolist(),q=fit.x.tolist(),position_error_m=error,orientation_error_rad=angle,**collision))
            q=fit.x.copy()
        current=np.asarray(endpoint,float).copy()
    return out


def capture_model(policy,side):
    from isaaclab.utils.math import matrix_from_quat
    from .execution_design_jacobian_reference import capture
    robot=policy.a.scene.robots[side];arm,_,bid=policy.c.ids[side]
    if [robot.joint_names[i]for i in arm]!=['panda_joint'+str(i)for i in range(1,8)]:
        raise ToolExecutionError('E24 reviewed Panda chain required')
    geometry=actual_robot_collision_geometry(policy.a)
    if not geometry['complete']:raise ToolExecutionError('Incomplete E24 full-arm collision geometry')
    measured=capture(policy.a,policy.c,side)
    task=policy.a.scene.layout.task_rotation.T;jac=np.asarray(measured['jacobian'],float)
    if not np.isfinite(jac).all()or not np.allclose(np.linalg.norm(jac[3:],axis=0),1,atol=.002):raise ToolExecutionError('Invalid E24 native joint axes')
    cache,_=policy.a._e23_robot_collision_cache;clouds=[]
    required={'panda_link'+str(i)for i in range(8)}|{'panda_hand','panda_leftfinger','panda_rightfinger'}
    if {entry[1]for entry in cache[side]}!=required:raise ToolExecutionError('Incomplete reviewed E24 arm mesh coverage')
    for body_index,name,points in cache[side]:
        rotation=task@matrix_from_quat(robot.data.body_quat_w[:,body_index])[0].cpu().numpy()
        position=policy.a.scene.world_to_task(robot.data.body_pos_w[0,body_index].cpu().numpy())
        clouds.append(dict(name=name,influence=body_influence(name),points=points@rotation.T+position))
    q=np.asarray(measured['q'],float);limits=np.asarray(measured['limits'],float)
    return dict(position=np.asarray(measured['position'],float),rotation=np.asarray(measured['rotation_task'],float),jacobian=jac,q=q,limits=limits,clouds=clouds),geometry


def obstacles_at_snapshot(policy,side,geometry):
    from .execution_design_e24_lid import table_bounds
    state,_=policy.snapshot();index=0 if side=='left'else 1
    if any(body['grasp'][index]for body in state.values()):raise ToolExecutionError('E24 empty transit arm is holding an object')
    obstacles=actual_object_parts(policy)
    lo,hi=table_bounds(policy);obstacles.append(dict(name='table',lo=lo,hi=hi))
    if policy.spec.get('fixtures'):raise ToolExecutionError('E24 transit fixtures require explicit collision binding')
    # Stationary arm bodies are obstacles; their existing unrelated contacts
    # are not re-labelled as motion of the selected empty arm.
    for other,rows in geometry['robots'].items():
        if other!=side:obstacles.extend(dict(name=other+':'+r['name'],lo=r['lo'],hi=r['hi'])for r in rows)
    return obstacles


def measured_height(model,target,obstacles):
    tip=model['position'];target=np.asarray(target,float);height=float(target[2]);contributors=[]
    for cloud in model['clouds']:
        if cloud['name']not in ('panda_hand','panda_leftfinger','panda_rightfinger'):continue
        relative=cloud['points']-tip;lo=relative.min(0);hi=relative.max(0)
        sweep_lo=np.minimum(tip[:2],target[:2])+lo[:2];sweep_hi=np.maximum(tip[:2],target[:2])+hi[:2]
        for obstacle in obstacles:
            if obstacle['name'].startswith(('left:','right:')):continue
            olo=np.asarray(obstacle['lo']);ohi=np.asarray(obstacle['hi'])
            if np.all(sweep_hi>=olo[:2]-.005)and np.all(sweep_lo<=ohi[:2]+.005):
                value=float(ohi[2]-lo[2]+.020);height=max(height,value);contributors.append(dict(body=cloud['name'],obstacle=obstacle['name'],required_tip_z=value))
    return height,contributors


def empty_pusher_transfer(policy,side,approach):
    """Screen first, then execute empty descent and exterior XY travel publicly."""
    from .execution_design import REVISION_V3
    if policy.task!='E24'or policy.spec.get('execution_design',{}).get('revision')!=REVISION_V3 or not policy.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E24 v3 engineering transit only')
    model,geometry=capture_model(policy,side);obstacles=obstacles_at_snapshot(policy,side,geometry)
    height,contributors=measured_height(model,approach,obstacles)
    start=model['position'];targets=[np.array([start[0],start[1],height]),np.array([approach[0],approach[1],height])]
    def record(row):
        with (policy.a.out/'e24-transit.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
    record(dict(stage='E24-measured-empty-pusher-transit-input',side=side,step=policy.c.steps,
        model={k:([dict(name=c['name'],influence=c['influence'],points=c['points'].tolist())for c in value]if k=='clouds'else value.tolist())for k,value in model.items()},
        obstacles=[{k:(v.tolist()if isinstance(v,np.ndarray)else v)for k,v in o.items()}for o in obstacles],
        targets=[t.tolist()for t in targets],measured_height_m=height,contributors=contributors))
    try:
        plan=plan_transit(model,targets,obstacles)
        groups=group_dense_waypoints(plan,model['position'],model['q'])
        group_receipts=certify_groups(model,groups,obstacles)
    except Exception as exc:
        record(dict(stage='E24-transit-preflight-rejected',error=str(exc),public_transit_actions=0));raise
    evidence=dict(stage='E24-measured-empty-pusher-transit',measured_height_m=height,contributors=contributors,
                  source='native_jacobian_same_tick_full_collision_mesh',nominal_path=plan,
                  dense_planning_step_m=.001,execution_group_limit_m=.005,execution_groups=group_receipts,
                  nominal_path_only=True,actual_execution_verified=False)
    policy.operations.append(evidence)
    record(evidence)
    policy.stage('E24-measured-empty-pusher-transit')
    for group_index,group in enumerate(groups):
        def guard():
            actual,geometry_now=capture_model(policy,side);objects_now=obstacles_at_snapshot(policy,side,geometry_now)
            screen_joint_segment(actual,actual['q'],actual['q'],objects_now)
            if dense_branch_deviation(actual['position'],actual['q'],group)>.05:
                raise ToolExecutionError('E24 actual public transit departed retained dense joint branch')
        move_grouped_public(policy,side,group['point'],guard)
        robot=policy.a.scene.robots[side];arm=policy.c.ids[side][0];q=robot.data.joint_pos[0,arm].detach().cpu().numpy()
        deviation=float(np.max(np.abs(q-group['q'])))
        record(dict(step=policy.c.steps,group_index=group_index,dense_start_index=group['dense_start_index'],dense_end_index=group['dense_end_index'],
            actual_tip=np.asarray(policy.tip(side)).tolist(),actual_q=q.tolist(),nominal_q=group['q'].tolist(),maximum_joint_deviation_rad=deviation))
        if deviation>.05:raise ToolExecutionError('E24 actual public transit departed screened joint branch')
    return height
