"""Actual open-finger side plane, pitched to avoid pressing the thin food down."""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def contact_face_pitch(mesh,rotation,direction,normal_local):
    """One actual hull face is rotated to an upward10degree support normal."""
    from scipy.spatial import ConvexHull
    normal=np.asarray(normal_local,float)
    if normal.shape!=(3,)or not np.isfinite(normal).all()or abs(np.linalg.norm(normal)-1.)>1e-5:
        raise ToolExecutionError('Finite unit actual finger-face normal required')
    planes=ConvexHull(np.asarray(mesh,float)).equations
    if float((planes[:,:3]@normal).max())<.99999:
        raise ToolExecutionError('Measured normal does not match an actual finger hull face')
    world=np.asarray(rotation)@normal;opposition=-float(world@direction)
    if opposition<.5:raise ToolExecutionError('Measured food-contact face points away from the source food')
    angle=np.deg2rad(10.)-np.arctan2(float(world[2]),opposition)
    if not 0.<angle<np.deg2rad(60.):raise ToolExecutionError('Measured contact face needs an unsupported large turn')
    return float(angle)


def prepare(policy,food,tool_side,direction,guard,contact_face=None):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_tool_pose_paths import append_public_move
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_e28_backstop import finger_target
    from .execution_design_cutlery_grasp import orient
    from .execution_design_thin_edge import table_bounds_task
    if policy.task!='E46' or not policy.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E46 actual open-finger pitch diagnostic only')
    side='left'if tool_side=='right'else'right';guard()
    state,_=policy.snapshot()
    if any(state[food]['grasp'])or policy.c.grips[side]<.035:
        raise ToolExecutionError('Reoriented backstop hand must be open and food ungrasped')
    measured=capture(policy.a,policy.c,side);p=np.asarray(measured['position']);r=np.asarray(measured['rotation_task'])
    direction=np.asarray(direction,float);direction[2]=0.;direction/=np.linalg.norm(direction)
    names=('panda_hand',*policy.a.scene.embodiment.fingers)
    local=[(actual_mesh(policy.a,side,n)-p)@r for n in names]
    # Put the two open fingers side-by-side across the push direction before
    # pitching; otherwise the far open finger would cross the table by 20mm.
    closing=(local[2].mean(axis=0)-local[1].mean(axis=0))@r.T
    closing[2]=0.;closing/=np.linalg.norm(closing)
    transverse=np.array([-direction[1],direction[0],0.])
    if transverse@closing<0:transverse=-transverse
    yaw=float(np.arctan2(np.cross(closing,transverse)[2],closing@transverse))
    axis=np.cross([0.,0.,1.],direction)
    body=state[food];obj=next(o for o in policy.spec['objects']if o['id']==food)
    half=np.abs(body['mat'])@np.asarray(obj['size']);floor=table_bounds_task(policy.a.scene)['top']
    retreat=p+direction*.10;above=np.r_[retreat[:2],max(.93,p[2])]
    other=[actual_mesh(policy.a,tool_side,n)for n in names]
    rows=[];valid=[]
    # The two transverse finger assignments are physically equivalent. Keep
    # the real15degree support face, and choose once using the whole route.
    for extra in((0.,)if contact_face is not None else(0.,np.pi)):
        candidate_yaw=yaw+extra
        pre=_axis_rotation([0.,0.,1.],candidate_yaw)@r;pitch=np.deg2rad(15.)
        if contact_face is not None:
            if contact_face.get('body')not in names[1:]:raise ToolExecutionError('Explicit measured contact-finger body required')
            chosen=names.index(contact_face['body'])
            pitch=contact_face_pitch(local[chosen],pre,direction,contact_face['normal_tcp_local'])
        desired=_axis_rotation(axis,pitch)@pre
        if contact_face is None:chosen=min((float((m@desired.T+p).mean(axis=0)@direction),i)for i,m in enumerate(local[1:],1))[1]
        mesh=local[chosen]@desired.T+p
        center,target=finger_target(body['pos'],half,direction,dict(aabb_min_task_m=mesh.min(0).tolist(),aabb_max_task_m=mesh.max(0).tolist()))
        placement=p+target-center
        minimum=float(min((m@desired.T+placement)[:,2].min()for m in local))
        raise_m=max(0.,floor+.0005-minimum);placement[2]+=raise_m
        finger_bottom=float((local[chosen]@desired.T+placement)[:,2].min())
        reachable_food=finger_bottom<=float(body['pos'][2]+half[2])-.0002
        poses=[];cursor=append_public_move(poses,p,retreat,r,policy.max_mm/1000.)
        cursor=append_public_move(poses,cursor,above,r,policy.max_mm/1000.)
        turn=public_rotation_poses(cursor,r,desired);poses+=turn
        clear=rotation_clear(local,cursor,r,turn,other,floor)
        cursor=append_public_move(poses,cursor,[*placement[:2],above[2]],desired,policy.max_mm/1000.)
        append_public_move(poses,cursor,placement,desired,policy.max_mm/1000.)
        path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],measured['q'],measured['limits'],poses)if clear and reachable_food else None
        row=dict(transverse_yaw_degrees=float(np.rad2deg(candidate_yaw)),pitch_degrees=float(np.rad2deg(pitch)),axis_task=axis.tolist(),
            whole_hand_minimum_z_before_m=minimum,actual_table_top_m=float(floor),clearance_raise_m=raise_m,
            chosen_finger_lowest_z_m=finger_bottom,food_highest_z_m=float(body['pos'][2]+half[2]),
            chosen_finger_body=names[chosen],placement_task=placement.tolist(),desired_rotation=desired.tolist(),
            actual_mesh_table_clear=bool(clear),can_reach_actual_food=bool(reachable_food),continuous_path=path,
            measured_contact_face=contact_face,
            predicted_reoriented_face_normal=(desired@np.asarray(contact_face['normal_tcp_local'])).tolist()if contact_face else None)
        rows.append(row)
        if path and path['feasible']:
            valid.append((int(min(q['minimum_joint_margin_rad']for q in path['rows'])/.03),-len(path['rows']),len(rows)-1))
    selected=max(valid)[-1]if valid else None
    preflight=dict(candidates=rows,chosen=selected,
        actual_hand_meshes_relative_tcp={name:mesh.tolist()for name,mesh in zip(names,local)},
        native_kinematics=measured,source_food_state=dict(position=body['pos'].tolist(),rotation=body['mat'].tolist(),half=half.tolist()),
        geometry_or_friction_changed=False)
    (policy.a.out/'E46-pitched-backstop-geometry.private.json').write_text(json.dumps(preflight,indent=2)+'\n')
    (policy.a.out/'E46-pitched-backstop-path.private.json').write_text(json.dumps(dict(candidates=rows,chosen=selected,geometry_or_friction_changed=False)))
    if selected is None:raise ToolExecutionError('Pitched open backstop lacks a continuous native-J route')
    desired=np.asarray(rows[selected]['desired_rotation']);placement=np.asarray(rows[selected]['placement_task'])
    policy.stage('withdraw-original-open-backstop');policy.move(side,retreat,guard)
    policy.stage('turn-empty-backstop-clear-of-table');policy.move(side,above,guard);orient(policy.a,side,desired)
    policy.stage('place-pitched-open-backstop');policy.move(side,[*placement[:2],above[2]],guard)
    policy.move(side,placement,guard,tolerance=.001)
    for _ in range(8):
        guard();body=policy.snapshot()[0][food]
        if any(body['grasp']):raise ToolExecutionError('Pitched loading hand grasped the food')
        if any(policy.contact(food,side+'_finger'+str(i))for i in(1,2)):return
        policy.move(side,policy.tip(side)-direction*.001,guard,tolerance=.0005)
    raise ToolExecutionError('Pitched open backstop did not make measured side contact')
