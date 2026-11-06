"""One native exterior-grasp trial chosen by measured-mesh CPU screening."""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def select(tool,ref,side,transport_clearance=None):
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    from .execution_design_cutlery_grasp import orient
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_clip_grasp import convex_meshes_clear
    from .execution_design_pour_path import candidate_poses
    from .execution_design_pour_acquire import side_staging,approach_poses
    from .execution_design_pour_clearance import minimum_rim_height,outlet_offset,body_grip_reference,pour_token
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
    if tool.task!='E45' or not tool.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E45 measured exterior grasp screening only')
    body_grip_reference(tool,ref,ref['local'][2])
    state,_=tool.snapshot()
    if any(v['grasp'][0 if side=='left'else 1]for v in state.values()):
        raise ToolExecutionError('Exterior receiving hand must actually be empty')
    tool.stage('select-exterior-cup-side-approach')
    body=state[ref['actor']];cup=tool.s['containers']['cup']
    cup_mesh=material_collision_points_task(tool,ref)
    height=max(tool.clearance,float(tool.tip(side)[2]),float(cup_mesh[:,2].max())+.06)
    tool.move(side,[*tool.tip(side)[:2],height])
    bases=physical_grasp_targets(tool.a,tool.c,side,body['mat']@np.array([0.,0.,1.]),
        pinch_axis=body['mat']@np.asarray(ref['jaw_axis_local']))
    measured=capture(tool.a,tool.c,side);p=np.asarray(measured['position']);current=np.asarray(measured['rotation_task'])
    names=('panda_hand',*tool.a.scene.embodiment.fingers)
    local=[(actual_mesh(tool.a,side,n)-p)@current for n in names]
    other='left'if side=='right'else'right'
    obstacles=[actual_mesh(tool.a,other,n)for n in names]
    # The receiving tray is also a physical obstacle during the empty low
    # approach; cup-only sweeps allowed the palm to descend onto its rim.
    obstacles += [material_collision_points_task(tool,dict(actor=o['id'],local=[0,0,0]))
        for o in tool.spec['objects']if o['id']not in(ref['actor'],*tool.s['groups']['balls'])]
    floor=table_bounds_task(tool.a.scene)['top']
    receiver=material_collision_points_task(tool,dict(actor=tool.s['container'],local=[0,0,0]))
    token=pour_token(tool);recording=tool.a.scene.embodiment.config.get('author_recording',{})
    lateral_mode=getattr(tool,'_engineering_exterior_search_mode',None)=='measured_lateral_body_v1'
    rim=(np.asarray(cup['lower'])+np.asarray(cup['upper']))/2;rim[2]=cup['upper'][2]
    if recording.get('pour_outflow_rim_local')is not None:rim=np.asarray(recording['pour_outflow_rim_local'],float)
    target=tool.destination(ref['actor']).copy();target[2]+=float(recording.get('pour_rim_height_above_target_m',.13))
    mouth=max(next(o for o in tool.spec['objects']if o['id']==ref['actor'])['size'][:2])
    radius=max(max(next(o for o in tool.spec['objects']if o['id']==ball)['size'])for ball in tool.s['groups']['balls'])
    target[:2]-=outlet_offset(body['mat'],token,mouth,radius)
    transport=float(transport_clearance if transport_clearance is not None else tool.clearance)
    (tool.a.out/'cup-receiving-grasp-inputs.private.json').write_text(json.dumps(dict(
        native_kinematics=measured,mesh_coordinate_frame='tcp_local',
        hand_meshes_relative_tcp={n:m.tolist()for n,m in zip(names,local)},
        cup_collision_vertices_task=cup_mesh.tolist(),cup_position=body['pos'].tolist(),cup_rotation=body['mat'].tolist(),
        source_cup_bounds=cup,ball_radius_m=float(radius),table_top_m=float(floor),
        native_physical_hand_bases=[r.tolist()for r in bases])))
    rows=[];valid=[];choices=[]
    jaw=body['mat']@np.asarray(ref['jaw_axis_local'])
    for z in((-.010,)if lateral_mode else(-.024,-.010,0.,.010,.020)):
        for assignment,base in enumerate(bases):
            for tilt in((75.,90.)if lateral_mode else(0.,-15.,15.,-30.,30.,-45.,45.,-60.,60.)):
                r=_axis_rotation(jaw,np.deg2rad(tilt))@base;index=len(rows)
                lateral=np.zeros(2)
                if lateral_mode:
                    # A centred side grasp places the broad palm inside the
                    # source cup. Offset only across the jaw, keeping both
                    # actual fingers outside and below the source ball exit.
                    outward=local[0].mean(axis=0)@r.T
                    outward-=body['mat'][:,2]*float(outward@body['mat'][:,2])
                    outward-=jaw*float(outward@jaw)
                    if np.linalg.norm(outward)<.001:raise ToolExecutionError('Actual side palm has no exterior offset direction')
                    outward/=np.linalg.norm(outward)
                    lateral=(body['mat'].T@outward)[:2]*(.008 if tilt==75. else .004)
                candidate_ref=body_grip_reference(tool,ref,z,lateral)
                point=body['pos']+body['mat']@np.asarray(candidate_ref['local'])
                turn=public_rotation_poses(p,current,r)
                clear=rotation_clear(local,p,current,turn,[*obstacles,cup_mesh],floor)
                exit_clear=all(float(((m@r.T+point-body['pos'])@body['mat'])[:,2].max())
                    <=float(cup['upper'][2])-radius+.002 for m in local[1:])
                clear=clear and exit_clear
                staging=side_staging(point,r,local[0],jaw);approach,_=approach_poses(p,r,point,staging,height,tool.max_mm/1000.)
                table_clear=all(min(float((m@r.T+np.asarray(q['position']))[:,2].min())for m in local)>=floor+.0002 for q in approach)
                waypoints=[p,*[np.asarray(q['position'])for q in approach]]
                sweep_clear=all(convex_meshes_clear(np.vstack((m@r.T+a,m@r.T+b)),obstacle)
                    for a,b in zip(waypoints,waypoints[1:])for m in local for obstacle in[cup_mesh,*obstacles])if clear and table_clear else False
                row=dict(assignment=assignment,tilt_degrees=tilt,grasp_local=candidate_ref['local'],
                    source_ball_exit_clear=bool(exit_clear),actual_cup_approach_sweep_clear=bool(sweep_clear),pour_token=token,
                    turn_and_grasp_floor_clear=bool(clear and table_clear),continuous_path=None)
                if clear and table_clear and sweep_clear:
                    meshes={n:m@r.T for n,m in zip(names,local)};meshes['cup']=cup_mesh-point
                    offset=body['pos']+body['mat']@rim-point
                    clearance=minimum_rim_height(meshes,offset,token,float(receiver[:,2].max()))
                    proposed=target.copy();proposed[2]=max(proposed[2],clearance['minimum_rim_z_m'])
                    poses=candidate_poses(p,current,r,point,height,transport,body['mat'],candidate_ref['local'],rim,proposed,
                        token,tool.max_mm/1000.,maximum_angle_deg=155,approach_staging=staging)
                    path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],measured['q'],measured['limits'],poses)
                    row.update(continuous_path=path,swept_clear_rim_target=proposed.tolist())
                    if path['feasible']:
                        margin=min(q['minimum_joint_margin_rad']for q in path['rows'])
                        valid.append((-abs(tilt),int(margin/.02),-len(path['rows']),-abs(z),index))
                rows.append(row);choices.append((r,candidate_ref))
    chosen=max(valid)[-1]if valid else None
    (tool.a.out/'cup-receiving-hand-candidates.private.json').write_text(json.dumps(dict(
        chosen=chosen,candidates=rows,native_verified=False,collision_verified=False,
        source_geometry_unchanged=True,cpu_candidates_only=True,search_mode='measured_lateral_body_v1'if lateral_mode else'centred_body_heights_v1')))
    if chosen is None:raise ToolExecutionError('No actual exterior cup grasp has a clear continuous full-pour route')
    r,selected=choices[chosen];ref.update(selected)
    orient(tool.a,side,r);tool._engineering_exterior_frame_ready=side
    return rows[chosen]
