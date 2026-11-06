"""Conservative loaded-cup/palm clearance through real public tilt steps."""
import math
import numpy as np
from .realworld_tool_expert import _axis_rotation


def body_grip_reference(policy,ref,height_local=-.024,lateral_local=None):
    """Pinch the exterior cup body without putting a finger inside its mouth."""
    if policy.task!='E45' or not policy.a.control_report.get('engineering_reference_only'):
        raise ValueError('E45 engineering exterior cup grasp only')
    obj=next(o for o in policy.spec['objects']if o['id']==ref['actor'])
    if obj.get('source_asset',{}).get('sha256')!='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b':
        raise ValueError('Reviewed source hollow cup required')
    cup=policy.s['containers']['cup'];height=float(height_local)
    if not np.isfinite(height)or not cup['lower'][2]+.010<=height<=cup['upper'][2]-.015:
        raise ValueError('Exterior pinch must remain on the actual source side wall')
    if lateral_local is None:
        lateral_local=ref['local'][:2]if ref.get('engineering_exterior_body_grip')is True else[0.,0.]
    lateral=np.asarray(lateral_local,float);jaw=np.asarray(ref['jaw_axis_local'],float)
    if (lateral.shape!=(2,)or not np.isfinite(lateral).all()or jaw.shape!=(3,)
            or not np.isfinite(jaw).all()or np.linalg.norm(lateral)>.012000001
            or abs(float(lateral@jaw[:2]))>1e-7):
        raise ValueError('Bounded exterior offset perpendicular to the actual source jaw required')
    return dict(ref,local=[*lateral.tolist(),height],engineering_exterior_body_grip=True)


def pour_token(policy):
    """An isolated engineer may choose the opposite real tilt around its axis."""
    source=policy.s['tool_expert']['pour_rotation_token']
    selected=getattr(policy,'_engineering_pour_token',None)
    if selected is None:return source
    opposite={'PITCH_DOWN':'PITCH_UP','PITCH_UP':'PITCH_DOWN','ROLL_LEFT':'ROLL_RIGHT','ROLL_RIGHT':'ROLL_LEFT'}
    if (policy.task!='E45' or not policy.a.control_report.get('engineering_reference_only')
            or selected not in(source,opposite.get(source))):
        raise ValueError('Engineering cup tilt must preserve the source rotation axis')
    return selected


def exterior_grip_readback(policy,side,ref):
    from .execution_design_e33_grasp import actual_mesh
    from .realworld_tool_expert import ToolExecutionError
    body=policy.snapshot()[0][ref['actor']];cup=policy.s['containers']['cup']
    radius=max(max(next(o for o in policy.spec['objects']if o['id']==ball)['size'])for ball in policy.s['groups']['balls'])
    top_limit=float(cup['upper'][2])-radius+.002
    rows=[];blocked=False
    for name in policy.a.scene.embodiment.fingers:
        points=(actual_mesh(policy.a,side,name)-body['pos'])@body['mat']
        upper=float(points[:,2].max());interior=[]
        profile=np.asarray(cup['radius_profile'],float)
        for point in points:
            # This is an exit guard, not a no-wall-contact grasp test. A
            # low body pinch may sit inside the radial wall envelope while
            # remaining wholly below the ball exit corridor. Actual hand/ball
            # contacts are independently rejected on every physical tick.
            if max(cup['lower'][2],top_limit-radius)<=point[2]<=cup['upper'][2]:
                internal_radius=float(np.interp(point[2],profile[:,0],profile[:,1]))
                interior.append(float(np.linalg.norm(point[:2])-internal_radius))
        rows.append(dict(body=name,maximum_cup_local_z_m=upper,allowed_top_m=top_limit,
            minimum_source_cavity_clearance_m=min(interior)if interior else None,
            outlet_corridor_lowest_z_m=top_limit-radius))
        blocked=blocked or upper>top_limit or bool(interior and min(interior)<-.001)
    import json
    (policy.a.out/'actual-exterior-cup-grasp.private.json').write_text(json.dumps(dict(
        grasp_local=ref['local'],fingers=rows,source_geometry_unchanged=True,native_grasp_required=True)))
    if blocked:raise ToolExecutionError('Actual exterior cup fingers obstruct the source ball exit')
    return rows


def wall_grip_reference(policy,ref,lower_m=.012):
    """Reference waypoint on the same source wall; no semantic/geometry edit."""
    result=dict(ref,local=list(ref['local']))
    if policy.task!='E45' or not policy.a.control_report.get('engineering_reference_only'):
        raise ValueError('E45 engineering source-wall grasp only')
    cup=policy.s['containers']['cup'];z=float(result['local'][2])-float(lower_m)
    if not cup['lower'][2]+.025<=z<=cup['upper'][2]-.015:
        raise ValueError('Cup pinch must remain on the source side wall')
    result['local'][2]=z
    return result


def outlet_offset(rotation,token,mouth_radius,ball_radius):
    """Horizontal centre-of-ball offset from the mouth centre at the low lip."""
    body=np.asarray(rotation,float);normal=body[:,2]
    axis=np.array([1.,0.,0.])if token.startswith('ROLL')else np.array([0.,1.,0.])
    sign=1 if token in('ROLL_LEFT','PITCH_UP')else-1
    if normal[2]>-.6:
        for angle in range(5,156,5):
            predicted=_axis_rotation(axis,math.radians(sign*angle))@body
            if predicted[2,2]<-.75:
                normal=predicted[:,2];break
    tangent=np.array([0.,0.,-1.])+normal[2]*normal
    length=float(np.linalg.norm(tangent))
    if length<.1:return np.zeros(2)
    return (float(mouth_radius)+float(ball_radius))*tangent[:2]/length


def move_clear_rim(policy,side,rimref,target,guard):
    """Use actual palm clearance and adequate XY aim, allowing a higher rim.

    A slipping cup changes the palm/rim transform. Re-read it rather than
    driving the palm into the tray to recover an obsolete rigid offset.
    """
    import json
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task
    from .realworld_tool_expert import ToolExecutionError
    target=np.asarray(target,float);history=[]
    receiver=material_collision_points_task(policy,{'actor':policy.s['container'],'local':[0,0,0]})
    top=float(receiver[:,2].max());names=('panda_hand',*policy.a.scene.embodiment.fingers)
    for iteration in range(100):
        guard();point=policy.point(rimref);tcp=policy.tip(side)
        low=min(float(actual_mesh(policy.a,side,name)[:,2].min())for name in names)
        low=min(low,float(material_collision_points_task(policy,rimref)[:,2].min()))
        error=target-point;metric=max(max(abs(error[:2]))-.010,target[2]-point[2]-.004,top+.004-low,0.)
        row=dict(stage=policy.a.stage,action=policy.c.steps,iteration=iteration,
            rim_task=point.tolist(),target_task=target.tolist(),lowest_loaded_mesh_z_m=low,receiver_top_m=top,
            horizontal_error_m=float(max(abs(error[:2]))),actual_clearance_m=low-top,
            allows_higher_rim=True,physical_goal_not_asserted=True)
        with(policy.a.out/'actual-rim-clearance-feedback.private.jsonl').open('a')as stream:
            stream.write(json.dumps(row)+'\n')
        if metric<=0:return
        history.append(metric)
        if len(history)>=20 and min(history[-19:])>=history[-20]-.0003:
            raise ToolExecutionError('Measured clear-rim route stalled without physical progress')
        if low<top+.004:
            policy.act(side,'UP',mm=min(policy.max_mm,(top+.008-low)*1000.));continue
        if max(abs(error[:2]))>.010:
            i=int(np.argmax(abs(error[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[i][int(error[i]<0)]
            policy.act(side,token,mm=min(policy.max_mm,abs(error[i])*1000.));continue
        policy.act(side,'UP',mm=min(policy.max_mm,max(.5,error[2]*1000.)))
    raise ToolExecutionError('Measured clear-rim public action bound exhausted')


def minimum_rim_height(meshes_relative_tcp,rim_relative_tcp,token,obstacle_top,
                       maximum_angle_deg=160.,step_angle_deg=5.,margin_m=.008):
    """Keep all actual held meshes above the receiver, including fixed-TCP arcs.

    Meshes and rim are measured at the initial upright held pose in task axes.
    Each public tilt first turns at the old TCP, then translates to recenter the
    measured rim. This explicitly bounds both parts rather than endpoints only.
    """
    if token not in ('PITCH_UP','PITCH_DOWN','ROLL_LEFT','ROLL_RIGHT'):
        raise ValueError('Explicit public tilt token required')
    rim=np.asarray(rim_relative_tcp,float);top=float(obstacle_top);margin=float(margin_m)
    if rim.shape!=(3,)or not np.isfinite(rim).all()or not np.isfinite([top,margin]).all()or margin<0:
        raise ValueError('Finite measured rim and obstacle clearance required')
    if not 0<step_angle_deg<=10 or not step_angle_deg<=maximum_angle_deg<=170:
        raise ValueError('Bounded physical tilt sweep required')
    meshes={name:np.asarray(v,float)for name,v in meshes_relative_tcp.items()}
    if not meshes or any(v.ndim!=2 or v.shape[1]!=3 or not len(v)or not np.isfinite(v).all()for v in meshes.values()):
        raise ValueError('Actual held collision mesh points required')
    axis=np.array([1.,0.,0.])if token.startswith('ROLL')else np.array([0.,1.,0.])
    sign=1. if token in('ROLL_LEFT','PITCH_UP')else-1.
    result=[];required=-math.inf
    for previous in np.arange(0.,maximum_angle_deg,step_angle_deg):
        stop=min(previous+step_angle_deg,maximum_angle_deg)
        previous_rotation=_axis_rotation(axis,math.radians(sign*previous))
        old_rim_z=float((previous_rotation@rim)[2])
        for angle in np.linspace(previous,stop,int(math.ceil((stop-previous)/.5))+1):
            rotation=_axis_rotation(axis,math.radians(sign*angle))
            # The initial TCP still corresponds to the previous rim offset.
            # Afterwards the endpoint moves to its new offset; both endpoint
            # heights also bound every axis translation between those poses.
            offset=max(old_rim_z,float((rotation@rim)[2]))
            for name,mesh in meshes.items():
                height=top+margin+offset-float((mesh@rotation.T)[:,2].min())
                if height>required:
                    required=height
                    result.append(dict(angle_degrees=float(angle),body=name,minimum_rim_z_m=height,
                        previous_angle_degrees=float(previous)))
    return dict(minimum_rim_z_m=float(required),margin_m=margin,maximum_angle_degrees=maximum_angle_deg,
        includes_fixed_tcp_rotation_and_recenter=True,controlling_samples=result,
        geometry_modified=False,native_success_asserted=False)


def held_pour_poses(position,rotation,rim_offset,target,transport_height,token,maximum_step_m=.012,return_position=None,
                    return_rotation=None):
    from .execution_design_tool_pose_paths import append_public_move
    from .execution_design_clip_handover import public_rotation_poses
    position=np.asarray(position,float);rotation=np.asarray(rotation,float);rim=np.asarray(rim_offset,float)
    poses=[];cursor=append_public_move(poses,position,[*position[:2],transport_height],rotation,maximum_step_m)
    cursor=append_public_move(poses,cursor,np.asarray(target)-rim,rotation,maximum_step_m)
    axis=[1.,0.,0.]if token.startswith('ROLL')else[0.,1.,0.]
    sign=1 if token in('ROLL_LEFT','PITCH_UP')else-1
    for angle in range(5,156,5):
        turn=_axis_rotation(axis,math.radians(sign*angle));current=turn@rotation
        poses.append(dict(position=cursor.tolist(),rotation=current.tolist()))
        cursor=append_public_move(poses,cursor,np.asarray(target)-turn@rim,current,maximum_step_m)
    restored=rotation if return_rotation is None else np.asarray(return_rotation,float)
    poses+=public_rotation_poses(cursor,current,restored)
    cursor=append_public_move(poses,cursor,[*cursor[:2],transport_height],restored,maximum_step_m)
    rest=position if return_position is None else np.asarray(return_position,float)
    cursor=append_public_move(poses,cursor,[*rest[:2],transport_height],restored,maximum_step_m)
    append_public_move(poses,cursor,rest+[0,0,.001],restored,maximum_step_m)
    return poses


def actual_clear_target(policy,side,rimref,target,token,return_tcp,return_body_rotation):
    """Measure real held meshes, choose clearance, screen the entire loaded path."""
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .realworld_tool_expert import ToolExecutionError
    import json
    tcp=policy.tip(side);names=('panda_hand',*policy.a.scene.embodiment.fingers)
    meshes={name:actual_mesh(policy.a,side,name)-tcp for name in names}
    meshes['cup']=material_collision_points_task(policy,rimref)-tcp
    receiver=material_collision_points_task(policy,{'actor':policy.s['container'],'local':[0,0,0]})
    rim_offset=policy.point(rimref)-tcp;plan=minimum_rim_height(meshes,rim_offset,token,float(receiver[:,2].max()))
    target=np.asarray(target,float).copy();target[2]=max(target[2],plan['minimum_rim_z_m'])
    measured=capture(policy.a,policy.c,side)
    body=policy.snapshot()[0][rimref['actor']]
    return_rotation=np.asarray(return_body_rotation)@body['mat'].T@np.asarray(measured['rotation_task'])
    poses=held_pour_poses(tcp,np.asarray(measured['rotation_task']),rim_offset,target,policy.clearance,token,policy.max_mm/1000.,return_tcp,return_rotation)
    path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],measured['q'],measured['limits'],poses)
    (policy.a.out/'actual-loaded-pour-clearance.private.json').write_text(json.dumps(dict(
        clearance=plan,rim_target=target.tolist(),continuous_path=path,
        native_success_asserted=False,actual_receiver_not_moved=True)))
    if not path['feasible']:raise ToolExecutionError('Swept-clear loaded cup route is not continuously reachable')
    return target
