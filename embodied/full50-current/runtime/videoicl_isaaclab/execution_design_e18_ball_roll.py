"""E18 engineering: roll the selected sphere clear of the roof, then grasp."""
import json
import numpy as np
from .realworld_mechanism_expert import MechanismExecutionError


def palm_roof_minimum_z(palm, inward_from_x):
    """Measure only material behind the roof front, rather than an empty AABB corner."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    points=np.asarray(palm,float);hull=ConvexHull(points).equations
    result=linprog([0.,0.,1.],A_ub=np.vstack((hull[:,:3],[-1.,0.,0.])),
        b_ub=np.r_[-hull[:,3],-inward_from_x],bounds=[(None,None)]*3,method='highs')
    if result.status==2:return None
    if not result.success:raise MechanismExecutionError('E18 actual palm/roof material query failed')
    return float(result.fun)


def plan_upper_back_push(ball, radius, clouds, palm, roof_front, roof_top,
                         fully_open_inward_extent, opening):
    point = np.asarray(ball, float)
    fingers = np.concatenate([np.asarray(c, float) for c in clouds])
    palm = np.asarray(palm, float)
    if (point.shape != (3,) or fingers.ndim != 2 or fingers.shape[1] != 3
            or palm.ndim != 2 or palm.shape[1] != 3
            or not np.isfinite(np.r_[point, fingers.ravel(), palm.ravel(),
                                      radius, roof_front, roof_top, fully_open_inward_extent, opening]).all()):
        raise ValueError('Finite measured E18 pusher geometry required')
    # Leave a practical12mm approach margin for measured translation coupling;
    # the public controller can drift several mm during a long descent.
    finger_max_x=float(fingers[:,0].max())
    x = min(point[0]+.006, roof_front-.012-finger_max_x)
    # Keep actual rear material over the ball's upper hemisphere; the TCP
    # itself may be farther forward. Search only a short coarse outward lane.
    minimum_x=point[0]+.002-finger_max_x
    if x < minimum_x:
        raise MechanismExecutionError('E18 closed pusher has no roof-clear rear-hemisphere corridor')
    target=None
    for candidate_x in [*np.arange(x,minimum_x,-.004),minimum_x]:
        candidate=np.array([candidate_x,point[1],point[2]+.008-float(fingers[:,2].min())])
        palm_low=palm_roof_minimum_z(palm,roof_front-.003-candidate[0])
        if palm_low is not None:candidate[2]=max(candidate[2],roof_top+.003-palm_low)
        if candidate[2]+float(fingers[:,2].min())<=point[2]+radius-.001:
            target=candidate;break
    if target is None:raise MechanismExecutionError('E18 closed pusher palm cannot clear roof while contacting sphere')
    goal = min(point[0], roof_front-.004-fully_open_inward_extent)
    if goal-radius < roof_front-opening+.006 or point[0]-goal > .055:
        raise MechanismExecutionError('E18 ball roll would exceed the actual open drawer floor')
    return target, float(goal)


def move_checked(worker,side,target,tolerance=.005,guard=None,max_step_mm=8.):
    target=np.asarray(target,float);stalled=0
    for _ in range(70):
        if guard:guard()
        before=worker.tip(side).copy();error=target-before
        if np.max(np.abs(error))<=tolerance:return
        # A long descent must correct transverse drift before the next step;
        # choosing only the largest residual can push the drawer before Z
        # reaches its target even though the final TCP would be reachable.
        horizontal=int(np.argmax(np.abs(error[:2])))
        axis=horizontal if abs(error[horizontal])>tolerance else int(np.argmax(np.abs(error)))
        sign=1 if error[axis]>0 else -1
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(sign<0)]
        worker.act(side,token,mm=min(max_step_mm,max(worker.min_mm,abs(error[axis])*1000)))
        if guard:guard()
        advanced=float((worker.tip(side)-before)[axis])*sign
        stalled=stalled+1 if advanced<.0002 else 0
        if stalled>=3:raise MechanismExecutionError('E18 public waypoint made no useful progress in three attempts')
    raise MechanismExecutionError('E18 bounded practical waypoint exhausted')


def choose_push_orientation(ball,radius,clouds,palm,roof_front,roof_top,open_clouds,opening):
    """Try a few nearby empty-wrist tilts using the actual collision material."""
    from .realworld_tool_expert import _axis_rotation
    for degrees in (0.,-10.,-20.,-30.):
        turn=_axis_rotation([0.,1.,0.],np.deg2rad(degrees))
        fingers=[np.asarray(c)@turn.T for c in clouds]
        full_open=max(float((np.asarray(c)@turn.T)[:,0].max())for c in open_clouds)
        try:
            target,goal=plan_upper_back_push(ball,radius,fingers,np.asarray(palm)@turn.T,
                roof_front,roof_top,full_open,opening)
        except MechanismExecutionError:
            continue
        return turn,degrees,target,goal
    raise MechanismExecutionError('E18 nearby empty-wrist tilts have no material-clear push corridor')


def tilt_empty_pusher(worker,side,target,guard,max_attempts=16):
    from .author_orientation import _axis_angle
    from .execution_design_e18_reference import choose_rotation_increment
    stalled=0
    for _ in range(max_attempts):
        guard();current=np.asarray(worker.a.tcp_rotation_task(side),float)
        error=_axis_angle(target@current.T)[1]
        if error<np.deg2rad(2.):return
        token,degrees=choose_rotation_increment(worker.a,worker.c,side,target,.5,5.)
        worker.a.act(token if side=='left'else 'STILL',token if side=='right'else 'STILL',rotation_deg=degrees)
        guard();after=_axis_angle(target@np.asarray(worker.a.tcp_rotation_task(side),float).T)[1]
        stalled=stalled+1 if error-after<np.deg2rad(.1)else 0
        if stalled>=3:break
    raise MechanismExecutionError('E18 empty pusher tilt made no useful public progress')


def run_segment(author, entry, parameters):
    cp = getattr(author, '_engineering_resume_checkpoint', {})
    spec = author.scene.spec
    boundary={'e18_roll_selected_ball_from160':(160,16011),
              'e18_roll_selected_ball_from_closed3':(3,311),
              'e18_roll_selected_ball_from_tilted40':(40,4011)}.get(entry)
    if (boundary is None or parameters != {}
            or (spec['id'], spec['variant'], spec['seed']) != ('E18', 'A', 4201)
            or spec.get('execution_design', {}).get('condition') != 'I'
            or (cp.get('source', {}).get('steps'), cp.get('source', {}).get('physics_ticks')) != boundary
            or not author.control_report.get('engineering_reference_only')
            or not getattr(author.c, '_engineering_diagnostic_only', False)
            or not getattr(author.c, '_engineering_checkpoint_readback_passed', False)):
        raise ValueError('Explicit admitted E18 A native ball-roll boundary required')
    from .execution_design_e18_reference import E18MeasuredAuthor
    from .execution_design_e18_geometry import actual_hand_clouds
    from .execution_design_e18_pinch import closed_hand_geometry
    from .execution_design_e18_ball import acquire
    worker = E18MeasuredAuthor(author, allow_existing_e18_drawer=True)
    worker.max_actions = 180
    side = 'left'; name = 'red'; start = worker.c.steps
    state, _ = worker.c.snapshot()
    if any(row['grasp'][0] for row in state.values()):
        raise MechanismExecutionError('E18 closed-pusher diagnostic starts truly empty')
    source_ball = np.asarray(state[name]['pos'], float).copy()
    cabinet = next(x for x in spec['mechanisms'] if x['id'] == 'cabinet')
    bounds = cabinet['mechanical_asset']['bounds']
    if cabinet.get('yaw', 0.) != 0.:
        raise ValueError('Original unrotated E18 cabinet required')
    roof_front = float(cabinet['position'][0]+bounds[0][0])
    roof_top = float(cabinet['position'][2]+bounds[1][2])
    radius = float(max(next(x for x in spec['objects'] if x['id'] == name)['size']))
    initial_opening = worker.displacement('drawer')
    geometry = closed_hand_geometry(author, side)
    rotation = np.asarray(author.tcp_rotation_task(side), float)
    jaw = np.asarray(geometry['jaw_axis_tcp'])
    open_clouds = [np.asarray(geometry['closed_clouds_tcp'][i]) + sign*.04*jaw
                   for i, sign in enumerate((1., -1.))]
    open_extent = max(float((c@rotation.T)[:, 0].max()) for c in open_clouds)
    worker.stage('E18-close-empty-pusher-above-selected-ball')
    robot = author.scene.robots[side]
    ids, names = robot.find_joints('panda_finger_joint[1-2]')
    if list(names) != ['panda_finger_joint1', 'panda_finger_joint2']:
        raise MechanismExecutionError('Native E18 pusher finger identity required')
    q = robot.data.joint_pos[0, ids].detach().cpu().numpy()
    if np.max(q) > .0015:
        for _ in range(3): worker.act(side, 'GRASP')
        q = robot.data.joint_pos[0, ids].detach().cpu().numpy()
    if np.max(q) > .0015:
        raise MechanismExecutionError('E18 empty pusher did not actually close before descent')
    geometry = actual_hand_clouds(author, side)
    rotation = np.asarray(author.tcp_rotation_task(side), float)
    clouds = [np.asarray(c)@rotation.T for c in geometry['clouds_tcp']]
    (author.out/'e18-ball-upper-back-geometry.private.json').write_text(json.dumps(dict(
        selected_ball_task_m=source_ball.tolist(), sphere_radius_m=radius,
        actual_opening_m=initial_opening, source_roof_front_m=roof_front, source_roof_top_m=roof_top,
        actual_finger_joint_positions_m=q.tolist(),
        closed_finger_min_relative_task=np.concatenate(clouds[:2]).min(axis=0).tolist(),
        closed_finger_max_relative_task=np.concatenate(clouds[:2]).max(axis=0).tolist(),
        palm_min_relative_task=clouds[2].min(axis=0).tolist(),
        palm_max_relative_task=clouds[2].max(axis=0).tolist(),
        full_open_inward_extent_m=open_extent), indent=2)+'\n')
    def protect():
        state, _ = worker.c.snapshot()
        if worker.displacement('drawer') < initial_opening-.005:
            raise MechanismExecutionError('E18 real ball roll pushed drawer inward five millimetres')
        p = np.asarray(state[name]['pos'], float)
        if abs(p[1]-source_ball[1]) > .012 or p[2] < source_ball[2]-.006:
            raise MechanismExecutionError('E18 selected sphere left its real rolling lane')
        if any(any(state[n]['grasp']) for n in ('green', 'blue')):
            raise MechanismExecutionError('E18 pusher accidentally acquired another sphere')
    open_task=[c@rotation.T for c in open_clouds]
    turn,tilt,target,goal=choose_push_orientation(source_ball,radius,clouds[:2],clouds[2],
        roof_front,roof_top,open_task,initial_opening)
    if tilt:
        worker.stage('E18-small-empty-pusher-tilt-above-source-roof')
        move_checked(worker,side,[*worker.tip(side)[:2],1.03],tolerance=.006,guard=protect)
        tilt_empty_pusher(worker,side,turn@rotation,protect)
        geometry=actual_hand_clouds(author,side)
        rotation=np.asarray(author.tcp_rotation_task(side),float)
        clouds=[np.asarray(c)@rotation.T for c in geometry['clouds_tcp']]
        open_extent=max(float((c@rotation.T)[:,0].max())for c in open_clouds)
        target,goal=plan_upper_back_push(source_ball,radius,clouds[:2],clouds[2],
            roof_front,roof_top,open_extent,initial_opening)
    proof = dict(source_ball_task=source_ball.tolist(), pusher_target_task=target.tolist(),
        ball_goal_x_m=goal, cabinet_roof_front_m=roof_front, cabinet_roof_top_m=roof_top,
        closed_finger_min_relative_task=np.concatenate(clouds[:2]).min(axis=0).tolist(),
        closed_finger_max_relative_task=np.concatenate(clouds[:2]).max(axis=0).tolist(),
        fully_open_inward_extent_m=open_extent, actual_initial_opening_m=initial_opening,
        selected_small_tilt_deg=tilt,source_geometry_only=True,native_push_or_grip_verified=False)
    (author.out/'e18-ball-upper-back-plan.private.json').write_text(json.dumps(proof,indent=2)+'\n')
    worker.stage('E18-place-closed-pusher-on-upper-rear-hemisphere')
    if worker.tip(side)[2]<1.0:
        move_checked(worker,side,[*worker.tip(side)[:2],1.0],tolerance=.006,guard=protect)
    move_checked(worker,side, [*target[:2], worker.tip(side)[2]], tolerance=.005, guard=protect)
    move_checked(worker,side, target, tolerance=.002, guard=protect)
    worker.stage('E18-real-selected-sphere-roll-toward-open-front')
    positions = []
    for _ in range(22):
        protect(); state, _ = worker.c.snapshot(); position = np.asarray(state[name]['pos'], float)
        if position[0] <= goal+.002: break
        worker.act(side, 'BACK', mm=3.)
        protect(); state, _ = worker.c.snapshot(); positions.append(float(state[name]['pos'][0]))
        if len(positions) >= 3 and positions[-3]-positions[-1] < .0003:
            raise MechanismExecutionError('E18 real closed pusher did not advance the selected sphere')
    else:
        raise MechanismExecutionError('E18 selected sphere roll exhausted its short public action bound')
    worker.stage('E18-sphere-really-rolled-clear-of-source-roof')
    before = np.asarray(worker.c.snapshot()[0][name]['pos'], float)
    move_checked(worker,side, worker.tip(side)+[0., 0., .012], tolerance=.002)
    actual, _ = worker.c.snapshot()
    if actual[name]['grasp'][0] and float(actual[name]['pos'][2]-before[2]) >= .005:
        return dict(local_completed=True, selected_ball=name, actions=worker.c.steps-start,
                    actual_grip=True, rolled=True, proof=proof)
    move_checked(worker,side, [*worker.tip(side)[:2], 1.03], tolerance=.006)
    _, _, _, lifted = acquire(worker)
    return dict(local_completed=True, selected_ball=name, actions=worker.c.steps-start,
                actual_grip=True, rolled=True, proof=proof, liftoff=lifted)
