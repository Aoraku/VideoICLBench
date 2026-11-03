"""Exterior cup-body pinch through a low side approach beneath the wide rim."""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def side_staging(point,rotation,palm_relative_tcp,jaw_axis_task=None):
    point=np.asarray(point,float);palm=np.asarray(palm_relative_tcp,float)@np.asarray(rotation).T
    direction=palm.mean(axis=0);direction[2]=0.
    jaw=None
    if jaw_axis_task is not None:
        jaw=np.asarray(jaw_axis_task,float).copy();jaw[2]=0.
        if jaw.shape!=(3,)or not np.isfinite(jaw).all()or np.linalg.norm(jaw)<.1:
            raise ToolExecutionError('Actual horizontal source jaw direction required')
        jaw/=np.linalg.norm(jaw);direction-=jaw*float(direction@jaw)
    if np.linalg.norm(direction)<.01:
        # An upright palm is centred above its TCP. Use the actual transverse
        # hand axis (perpendicular to the jaw axis), then reject any cup sweep
        # collision rather than treating this valid geometry as malformed.
        direction=np.asarray(rotation,float)[:,0].copy();direction[2]=0.
        if jaw is not None:direction-=jaw*float(direction@jaw)
    if np.linalg.norm(direction)<1e-9:raise ToolExecutionError('Actual palm must define an exterior cup approach side')
    direction/=np.linalg.norm(direction)
    return point+direction*.13


def side_entry_waypoints(staging,point):
    """Align the small lateral axis outside the cup before advancing its mouth."""
    staging=np.asarray(staging,float);point=np.asarray(point,float)
    alignment=staging.copy();axis=int(np.argmin(np.abs((point-staging)[:2])))
    alignment[axis]=point[axis]
    return[alignment,point]


def approach_poses(position,rotation,point,staging,height,maximum_step_m):
    from .execution_design_tool_pose_paths import append_public_move
    poses=[];cursor=np.asarray(position,float)
    for goal in ([*cursor[:2],height],[*staging[:2],height],staging,*side_entry_waypoints(staging,point)):
        cursor=append_public_move(poses,cursor,goal,rotation,maximum_step_m)
    return poses,cursor


def acquire(policy,ref,side):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_clip_grasp import convex_meshes_clear
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_pour_clearance import exterior_grip_readback,body_grip_reference
    if policy.task!='E45' or not policy.a.control_report.get('engineering_reference_only')or ref.get('engineering_exterior_body_grip')is not True:
        raise ToolExecutionError('Reviewed E45 exterior source-body approach only')
    checked=body_grip_reference(policy,ref,ref['local'][2])
    if not np.allclose(checked['local'],ref['local']):raise ToolExecutionError('Actual exterior source-wall coordinates required')
    policy.stage('prepare-exterior-cup-body-grasp')
    body=policy.snapshot()[0][ref['actor']];origin=body['pos'].copy();up=body['mat'][:,2].copy()
    def guard():
        current=policy.snapshot()[0][ref['actor']]
        if float(current['mat'][:,2]@up)<np.cos(np.deg2rad(20.)):
            raise ToolExecutionError('Source cup tipped during exterior body approach')
        if np.linalg.norm(current['pos']-origin)>.02:
            raise ToolExecutionError('Source cup was pushed away during exterior body approach')
        if any(policy.contact(ball,f'{s}_finger{i}')for ball in policy.s['groups']['balls']for s in('left','right')for i in(1,2)):
            raise ToolExecutionError('Exterior acquiring hand contacted source cup contents')
    policy.act(side,'RELEASE');guard()
    if getattr(policy,'_engineering_exterior_frame_ready',None)!=side:
        height=max(policy.clearance,float(policy.tip(side)[2]),float(origin[2])+.12)
        policy.move(side,[*policy.tip(side)[:2],height],guard)
        policy.a.align_gripper_axis(side,body['mat']@np.asarray(ref['jaw_axis_local']))
    measured=capture(policy.a,policy.c,side);p=np.asarray(measured['position']);r=np.asarray(measured['rotation_task'])
    point=policy.point(ref);height=max(policy.clearance,float(p[2]),point[2]+.1)
    names=('panda_hand',*policy.a.scene.embodiment.fingers)
    local=[(actual_mesh(policy.a,side,n)-p)@r for n in names]
    staging=side_staging(point,r,local[0],body['mat']@np.asarray(ref['jaw_axis_local']))
    poses,_=approach_poses(p,r,point,staging,height,policy.max_mm/1000.)
    cup=material_collision_points_task(policy,ref);floor=table_bounds_task(policy.a.scene)['top']
    other='left'if side=='right'else'right'
    obstacles=[cup,*[actual_mesh(policy.a,other,n)for n in names]]
    obstacles += [material_collision_points_task(policy,dict(actor=o['id'],local=[0,0,0]))
        for o in policy.spec['objects']if o['id']not in(ref['actor'],*policy.s['groups']['balls'])]
    waypoints=[p,*[np.asarray(row['position'])for row in poses]]
    clear=all(min(float((m@r.T+q)[:,2].min())for m in local)>=floor+.0002 for q in waypoints)
    clear=clear and all(convex_meshes_clear(np.vstack((m@r.T+a,m@r.T+b)),obstacle)
        for a,b in zip(waypoints,waypoints[1:])for m in local for obstacle in obstacles)
    path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],measured['q'],measured['limits'],poses)if clear else None
    (policy.a.out/'exterior-cup-side-approach.private.json').write_text(json.dumps(dict(
        staging_task=staging.tolist(),grasp_task=point.tolist(),cup_mesh_sweep_clear=bool(clear),continuous_path=path,
        maximum_native_opening_m=.08,source_mouth_width_m=.08255403044790554,source_geometry_unchanged=True)))
    if not path or not path['feasible']:raise ToolExecutionError('Actual side approach to cup body lacks a clear continuous route')
    def move(target,tolerance=.002):
        target=np.asarray(target,float);best=float(np.linalg.norm(target-policy.tip(side)));last=policy.c.steps;improved=last
        def progress():
            nonlocal best,last,improved
            guard()
            if policy.c.steps==last:return
            last=policy.c.steps;error=float(np.linalg.norm(target-policy.tip(side)))
            if error<best-.0001:best=error;improved=last
            if last-improved>=12:raise ToolExecutionError('Exterior cup waypoint has no net progress')
        policy.move(side,target,progress,tolerance=tolerance)
    policy.stage('descend-outside-wide-cup-rim')
    for target in ([*p[:2],height],[*staging[:2],height],staging):move(target)
    policy.stage('side-enter-below-cup-rim')
    for target in side_entry_waypoints(staging,point):move(target,tolerance=.001)
    policy.stage('exterior-source-cup-clamp');stable=0
    for _ in range(5):
        policy.act(side,'GRASP');guard()
        stable=stable+1 if policy.held(ref,side)else 0
        if stable>=3:exterior_grip_readback(policy,side,ref);return
    raise ToolExecutionError('Exterior source cup body did not acquire a bilateral grip')
