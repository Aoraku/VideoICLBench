"""Engineering cup handoff through real table support and public actions."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def choose_pour_hand(tips, target):
    target=np.asarray(target,float)
    if target.shape!=(3,) or not np.isfinite(target).all():raise ToolExecutionError('Invalid pour destination')
    return min(('left','right'),key=lambda s:float(np.linalg.norm(np.asarray(tips[s])[:2]-target[:2])))


def handoff_if_needed(tool, ref, side, rest_point):
    if getattr(tool,'_engineering_preserve_held_pour_hand',False):
        tool.require_held(ref,side);return side,rest_point
    desired=choose_pour_hand({s:tool.tip(s)for s in ('left','right')},tool.destination(ref['actor']))
    if desired==side:return side,rest_point
    # The near table centre is outside the tray footprint. Confirm actual
    # projections before using it; source dimensions are not changed.
    state,_=tool.snapshot();cup=state[ref['actor']];obj=next(o for o in tool.spec['objects']if o['id']==ref['actor'])
    center=np.array([-.19,0.,cup['pos'][2]])
    half=np.abs(cup['mat'])@np.asarray(obj['size'])
    for o in tool.spec['objects']:
        if o['id'] in (ref['actor'],*tool.s['groups']['balls']):continue
        other=state[o['id']];extent=np.abs(other['mat'])@np.asarray(o['size'])
        if np.all(abs(other['pos'][:2]-center[:2])<extent[:2]+half[:2]+.01):
            raise ToolExecutionError('Cup handoff staging overlaps actual obstacle')
    point=tool.point(ref)+center-cup['pos']
    tool.stage('cup-table-handoff');tool.park(ref,side,point)
    state,_=tool.snapshot();body=state[ref['actor']]
    if not tool.contact(ref['actor'],'table') or any(body['grasp']) or body['mat'][2,2]<.98:
        raise ToolExecutionError('Cup handoff lacks released upright table support')
    bounds=tool.s['containers']['cup']
    for name in tool.s['groups']['balls']:
        local=body['mat'].T@(state[name]['pos']-body['pos'])
        if np.any(local<np.asarray(bounds['lower'])) or np.any(local>np.asarray(bounds['upper'])):
            raise ToolExecutionError('Cup handoff lost contained ball')
    # Withdraw the empty previous hand before opposite-hand acquisition.
    tool.move(side,[*tool.tip(side)[:2],tool.clearance])
    tool.move(side,[-.19,.30 if side=='left'else-.30,tool.clearance])
    # The empty opposite hand need not traverse the high 1.06m waypoint
    # used by the original long loaded transfer. Bound clearance by current
    # object tops plus 60mm; retaining a needless high point caused the old
    # opposite-hand approach to stall before reaching the supported cup.
    state,_=tool.snapshot()
    tops=[float(state[o['id']]['pos'][2]+(np.abs(state[o['id']]['mat'])@np.asarray(o['size']))[2])
          for o in tool.spec['objects']]
    previous=tool.clearance
    tool.clearance=min(previous,max(tops)+.06)
    try:
        orient_empty_pour_hand(tool,ref,desired,transport_clearance=previous)
        tool.acquire(ref,desired)
    finally:tool.clearance=previous
    return desired,point


def orient_empty_pour_hand(tool,ref,side,transport_clearance=None):
    """Screen both real finger assignments and jaw-axis tilts through pouring."""
    if ref.get('engineering_exterior_body_grip')is True:
        from .execution_design_pour_grasp_search import select
        return select(tool,ref,side,transport_clearance)
    import json
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    from .execution_design_cutlery_grasp import orient
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_pour_path import candidate_poses
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_clip_grasp import convex_meshes_clear
    from .execution_design_pour_clearance import minimum_rim_height,outlet_offset
    from .realworld_tool_expert import _axis_rotation
    state,_=tool.snapshot()
    if any(v['grasp'][0 if side=='left'else 1]for v in state.values()):
        raise ToolExecutionError('Cup receiving hand must be empty')
    tool.stage('select-empty-cup-hand-assignment')
    point=tool.point(ref);height=max(tool.clearance,float(point[2])+.07,float(tool.tip(side)[2]))
    tool.move(side,[*tool.tip(side)[:2],height])
    body=state[ref['actor']];jaw=body['mat']@np.asarray(ref['jaw_axis_local'])
    outward=body['mat']@np.array([0.,0.,1.])
    try:bases=physical_grasp_targets(tool.a,tool.c,side,outward,pinch_axis=jaw)
    except AssertionError as exc:raise ToolExecutionError('Physical cup grasp frame is not orthonormal')from exc
    measured=capture(tool.a,tool.c,side);current=np.asarray(measured['position']);current_rotation=np.asarray(measured['rotation_task'])
    names=('panda_hand',*tool.a.scene.embodiment.fingers)
    local=[(actual_mesh(tool.a,side,n)-current)@current_rotation for n in names]
    other='right'if side=='left'else'left';obstacles=[actual_mesh(tool.a,other,n)for n in names]
    floor=table_bounds_task(tool.a.scene)['top'];cup=tool.s['containers']['cup']
    rim=(np.asarray(cup['lower'])+np.asarray(cup['upper']))/2;axis=cup.get('rim_axis',2)
    rim[axis]=cup['upper'][axis]if cup.get('rim_side','upper')=='upper'else cup['lower'][axis]
    recording=tool.a.scene.embodiment.config.get('author_recording',{})
    if recording.get('pour_adaptive_rim_height_m')is not None:
        raise ToolExecutionError('E45 public candidate requires its frozen fixed rim-height profile')
    if recording.get('pour_outflow_rim_local')is not None:rim=np.asarray(recording['pour_outflow_rim_local'],float)
    target=tool.destination(ref['actor']).copy();target[2]+=float(recording.get('pour_rim_height_above_target_m',.13))
    mouth=max(next(o for o in tool.spec['objects']if o['id']==ref['actor'])['size'][:2])
    radius=max(max(next(o for o in tool.spec['objects']if o['id']==ball)['size'])for ball in tool.s['groups']['balls'])
    target[:2]-=outlet_offset(body['mat'],tool.s['tool_expert']['pour_rotation_token'],mouth,radius)
    cup_vertices=material_collision_points_task(tool,ref)-point
    receiver_vertices=material_collision_points_task(tool,dict(actor=tool.s['container'],local=[0,0,0]))
    rim_offset=body['pos']+body['mat']@rim-point
    transport=float(transport_clearance if transport_clearance is not None else tool.clearance)
    if np.allclose(ref['local'],[0.,0.,-.024]):
        (tool.a.out/'cup-receiving-grasp-inputs.private.json').write_text(json.dumps(dict(
            native_kinematics=measured,hand_meshes_relative_tcp={n:m.tolist()for n,m in zip(names,local)},
            cup_collision_vertices_task=(cup_vertices+point).tolist(),cup_position=body['pos'].tolist(),cup_rotation=body['mat'].tolist(),
            source_grasp_local=ref['local'],grasp_point_task=point.tolist(),source_cup_bounds=cup,
            ball_radius_m=float(radius),receiver_top_m=float(receiver_vertices[:,2].max()),table_top_m=float(floor))))
    rows=[];valid=[];rotations=[]
    for assignment,base in enumerate(bases):
        for tilt in (0.,-30.,-45.,30.,45.,-15.,15.):
            r=_axis_rotation(jaw,np.deg2rad(tilt))@base;index=len(rotations);rotations.append(r)
            turn=public_rotation_poses(current,current_rotation,r)
            clear=rotation_clear(local,current,current_rotation,turn,obstacles,floor)
            # Include actual tilted finger/palm table clearance at the grasp.
            clear=clear and min((m@r.T+point)[:,2].min()for m in local)>=floor+.0002
            exit_clear=True
            if np.allclose(ref['local'],[0.,0.,-.024]):
                # The exterior pinch may not place a fingertip in the ball's
                # exit band. Check the actual empty-hand meshes before moving.
                exit_clear=all(float(((mesh@r.T+point-body['pos'])@body['mat'])[:,2].max())
                    <=float(cup['upper'][2])-radius+.002 for mesh in local[1:])
                clear=clear and exit_clear
            loaded_meshes={str(n):mesh@r.T for n,mesh in enumerate(local)}
            loaded_meshes['cup']=cup_vertices
            clearance=minimum_rim_height(loaded_meshes,rim_offset,tool.s['tool_expert']['pour_rotation_token'],
                float(receiver_vertices[:,2].max()))
            candidate_target=target.copy();candidate_target[2]=max(candidate_target[2],clearance['minimum_rim_z_m'])
            staging=None
            cup_approach_clear=True
            if np.allclose(ref['local'],[0.,0.,-.024]):
                from .execution_design_pour_acquire import side_staging,approach_poses
                staging=side_staging(point,r,local[0])
                approach,_=approach_poses(current,r,point,staging,height,tool.max_mm/1000.)
                cup_approach_clear=all(all(convex_meshes_clear(mesh@r.T+np.asarray(row['position']),cup_vertices+point)
                    for mesh in local)for row in approach)
                clear=clear and cup_approach_clear
            poses=candidate_poses(current,current_rotation,r,point,height,transport,body['mat'],ref['local'],rim,candidate_target,
                tool.s['tool_expert']['pour_rotation_token'],tool.max_mm/1000.,maximum_angle_deg=155,approach_staging=staging)
            path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],
                measured['q'],measured['limits'],poses)if clear else None
            rows.append(dict(assignment=assignment,tilt_degrees=tilt,turn_and_grasp_floor_clear=bool(clear),continuous_path=path,
                swept_clear_rim_target=candidate_target.tolist(),full_loaded_mesh_clearance_m=clearance['margin_m'],
                source_ball_exit_clear=bool(exit_clear),actual_cup_approach_sweep_clear=bool(cup_approach_clear)))
            if path and path['feasible']:
                valid.append((-abs(tilt),int(min(x['minimum_joint_margin_rad']for x in path['rows'])/.02),
                    -sum(x['maximum_joint_step_rad']for x in path['rows']),index))
    chosen=max(valid)[3]if valid else None
    with (tool.a.out/'cup-receiving-hand-candidates.private.json').open('w')as f:
        json.dump(dict(chosen=chosen,candidates=rows,native_verified=False,collision_verified=False,
            actual_rim_target=target.tolist(),transport_height=transport,return_yaw_approximation=True),f)
    if chosen is None:raise ToolExecutionError('No equivalent cup hand assignment with continuous complete pour margin')
    orient(tool.a,side,rotations[chosen])
    if np.allclose(ref['local'],[0.,0.,-.024]):tool._engineering_exterior_frame_ready=side
