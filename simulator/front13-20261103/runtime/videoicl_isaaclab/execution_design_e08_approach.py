"""Measured empty-gripper approach for independent E08 engineering only."""
import json,math
import numpy as np


def swept_clearance(material,bodies,tip,target,table_top=.8,margin=.001):
    """Conservative convex sweeps of the actual palm and both open fingers."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    material=np.asarray(material,float);tip=np.asarray(tip,float);target=np.asarray(target,float)
    if len(bodies)!=3 or material.ndim!=2 or material.shape[1]!=3:
        raise ValueError('Actual shoe, palm and both fingers required')
    if not np.isfinite(np.r_[material.ravel(),tip,target]).all():raise ValueError('Nonfinite approach geometry')
    mh=ConvexHull(material);clearances=[]
    for body in bodies:
        points=np.asarray(body,float)
        if not np.isfinite(points).all():raise ValueError('Nonfinite actual robot collision vertices')
        translated=points+target-tip
        low=float(min(points[:,2].min(),translated[:,2].min()))
        if low<table_top+.0003:raise RuntimeError('Actual E08 swept hand intersects table clearance')
        h=ConvexHull(np.concatenate((points,translated)))
        result=linprog([0,0,0],A_ub=np.r_[h.equations[:,:3],mh.equations[:,:3]],
            b_ub=-np.r_[h.equations[:,3],mh.equations[:,3]]+margin,bounds=[(None,None)]*3,method='highs')
        if result.success:raise RuntimeError('Actual E08 swept hand intersects shoe hull')
        if result.status!=2:raise RuntimeError('E08 clearance solver did not establish separation')
        clearances.append(low-table_top)
    return dict(minimum_table_clearance_m=min(clearances),collision_margin_m=margin,
                actual_robot_bodies=3,shoe_collision_vertices=len(material))


def approach_path(tip,target,height):
    """Match the public route: rise, each horizontal axis, then descend."""
    tip=np.asarray(tip,float);target=np.asarray(target,float)
    high=max(float(height),float(tip[2]),float(target[2])+.12)
    return [tip.copy(),np.array([tip[0],tip[1],high]),
            np.array([target[0],tip[1],high]),np.array([target[0],target[1],high]),target.copy()]


def path_clearance(material,bodies,tip,waypoints):
    """Check the same axis-separated path that the public mover executes."""
    tip=np.asarray(tip,float);receipts=[]
    for start,end in zip(waypoints[:-1],waypoints[1:]):
        if np.linalg.norm(np.asarray(end)-start)<1e-9:continue
        receipts.append(swept_clearance(material,[np.asarray(body)+start-tip for body in bodies],start,end))
    if not receipts:raise ValueError('Nonempty E08 approach path required')
    return dict(waypoints=[np.asarray(p).tolist()for p in waypoints],segments=receipts,
                minimum_table_clearance_m=min(row['minimum_table_clearance_m']for row in receipts))


def settle_accepted_rotation(policy,side,guard):
    """Public STILL preserves the accepted angular target; never reissues it."""
    previous=float(policy.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])
    rows=[]
    for _ in range(4):
        if previous<=math.radians(.5):break
        guard();policy.act(side,'STILL');guard()
        error=float(policy.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])
        rows.append(dict(step=policy.c.steps,orientation_error_rad=error))
        if previous-error<math.radians(.05):break
        previous=error
    return rows


def reversed_jaw_turns(rotation):
    """Two explicit quarter turns avoid the ambiguous 180-degree axis sign."""
    rotation=np.asarray(rotation,float)
    quarter=np.array([[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]])
    return rotation@quarter,rotation@np.diag([-1.,-1.,1.])


def turn_empty(policy,side,target,guard):
    from .author_orientation import _axis_angle
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    errors=[]
    for _ in range(60):
        guard();axis,angle=_axis_angle(target@np.asarray(policy.a.tcp_rotation_task(side)).T)
        if angle<math.radians(.75):return
        errors.append(float(angle))
        feedback=policy.c.action_feedback()['control_feedback'][side]
        if feedback.get('joint_limit_names') and len(errors)>6 and errors[-7]-min(errors[-6:])<math.radians(.25):
            raise RuntimeError('E08 equivalent-jaw turn reached actual joint limit without angular progress')
        k=int(np.argmax(abs(axis)));policy.act(side,labels[k][int(axis[k]<0)],degrees=min(5.,max(.5,abs(math.degrees(angle*axis[k])))))
        waits=settle_accepted_rotation(policy,side,guard)
        with(policy.a.out/'e08-equivalent-jaw-turn.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(step=policy.c.steps,target=target.tolist(),remaining_angle_before_rad=float(angle),waits=waits))+'\n')
    raise RuntimeError('E08 equivalent-jaw turn exceeded bounded public actions')


def approach(policy,side,ref):
    a=policy.a
    if (policy.task!='E08' or policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or not a.control_report.get('engineering_reference_only') or a.scene.embodiment.name!='franka'):
        raise ValueError('E08 v3 Panda engineering-only approach required')
    from .author_orientation import _axis_angle
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task
    pos,rotation=policy.frame(ref);pos=np.asarray(pos).copy();rotation=np.asarray(rotation).copy()
    if rotation[2,2]<.99:raise RuntimeError('E08 heel requires upright actual shoe')
    angle=-math.radians(50);c,s=math.cos(angle),math.sin(angle)
    tilt=np.array([[c,0,s],[0,1,0],[-s,0,c]])
    initial_r=np.asarray(a.tcp_rotation_task(side))
    desired=rotation@tilt@rotation.T@initial_r
    def source_stable():
        p,r=policy.frame(ref)
        if np.linalg.norm(np.asarray(p)-pos)>.002 or np.max(abs(np.asarray(r)-rotation))>.035:
            raise RuntimeError('E08 shoe moved during approach; refusing stale grasp point')
    import os
    if os.environ.get('VIC_E08_COM_REFERENCE_DIAGNOSTIC')=='1':
        from .execution_design_e08_com_diagnostic import run
        run(policy,side,source_stable)
    if os.environ.get('VIC_E08_COM_REFERENCE_GUARD')=='1':
        from .execution_design_e08_com_diagnostic import run
        previous_stage=a.stage;run(policy,side,source_stable,stop_after=False);policy.stage(previous_stage)
    from .execution_design_drawer_ik_probe import inspect
    point=policy.point(ref)
    # Actual constrained-solver continuation passes at this higher staging;
    # lower staging and equivalent 180-degree turns hit real joint limits.
    stages=[np.array([point[0],point[1]+.08,1.04])]
    check=inspect(a,policy.c,side,[dict(position=p.tolist(),rotation=desired.tolist())for p in [point,*stages]])
    entry=inspect(a,policy.c,side,[dict(position=p.tolist(),rotation=np.asarray(a.tcp_rotation_task(side)).tolist())for p in stages])
    possible=[i for i,row in enumerate(check[1:])if all(x['kinematically_reachable'] and x['minimum_joint_margin_rad']>=.02 for x in(row,entry[i]))]
    if not check[0]['kinematically_reachable'] or not possible:
        raise RuntimeError('E08 tilted grasp/staging lacks measured joint-limit-safe IK')
    staging=stages[possible[0]]
    policy.move(side,[*policy.tip(side)[:2],max(float(staging[2]),float(policy.tip(side)[2]))],guard=source_stable)
    policy.move(side,staging,guard=source_stable)
    initial=np.asarray(policy.tip(side)).copy()
    def empty_stable():
        source_stable();tip=np.asarray(policy.tip(side));state,_=policy.snapshot()
        if tip[2]<.92 or np.linalg.norm(tip-initial)>.03 or any(v['grasp'][0 if side=='left'else 1]for v in state.values()):
            raise RuntimeError('E08 equivalent-jaw turn left actual empty safe envelope')
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(48):
        tip=np.asarray(policy.tip(side));state,_=policy.snapshot()
        if tip[2]<.92 or np.linalg.norm(tip-initial)>.03 or any(v['grasp'][0 if side=='left'else 1]for v in state.values()):
            raise RuntimeError('E08 empty tilt left measured safe staging envelope')
        current=np.asarray(a.tcp_rotation_task(side));axis,angle=_axis_angle(desired@current.T)
        # 50 degrees is a trajectory proposal, not a task requirement. A
        # measured pose is admissible only when the full hand clears the
        # pinned shoe and table and its endpoint retains real joint margin.
        if angle<math.radians(15.):
            bodies=[actual_mesh(a,side,name)for name in ('panda_hand',*a.scene.embodiment.fingers)]
            route=approach_path(tip,point,staging[2])
            try:geometry=path_clearance(material_collision_points_task(policy,ref),bodies,tip,route)
            except RuntimeError:geometry=None
            if geometry is not None:
                actual_ik=inspect(a,policy.c,side,[dict(position=point.tolist(),rotation=current.tolist())])[0]
                if actual_ik['kinematically_reachable'] and actual_ik['minimum_joint_margin_rad']>=.02:
                    with(a.out/'e08-achieved-grasp-pose.private.jsonl').open('a')as stream:
                        stream.write(json.dumps(dict(step=policy.c.steps,target_error_degrees=math.degrees(angle),
                            achieved_rotation=current.tolist(),geometry=geometry,endpoint_ik=actual_ik,
                            acceptance='actual_full_hand_sweep_and_joint_margin',native_grasp_verified=False))+'\n')
                    break
        if angle<math.radians(.75):raise RuntimeError('E08 target orientation lacks actual safe grasp endpoint')
        k=int(np.argmax(abs(axis)));policy.act(side,labels[k][int(axis[k]<0)],degrees=min(5.,max(.5,abs(math.degrees(angle*axis[k])))))
        waits=settle_accepted_rotation(policy,side,source_stable)
        with(a.out/'e08-angular-settling.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(step=policy.c.steps,waits=waits))+'\n')
    else:raise RuntimeError('E08 tilted empty palm did not converge to a safe actual grasp pose')
    point=policy.point(ref)
    route=approach_path(policy.tip(side),point,staging[2])
    bodies=[actual_mesh(a,side,name)for name in ('panda_hand',*a.scene.embodiment.fingers)]
    receipt=path_clearance(material_collision_points_task(policy,ref),bodies,policy.tip(side),route)
    receipt.update(actor=ref['actor'],step=policy.c.steps,tcp_target=point.tolist(),nominal_tilt_degrees=-50.,native_grasp_verified=False)
    with(a.out/'e08-approach-clearance.private.jsonl').open('a')as stream:stream.write(json.dumps(receipt)+'\n')
    for waypoint in route[1:]:policy.move(side,waypoint,guard=source_stable,tolerance=.0008)
    source_stable()
    if np.max(abs(policy.point(ref)-policy.tip(side)))>.0015:raise RuntimeError('E08 actual heel target not reached')
