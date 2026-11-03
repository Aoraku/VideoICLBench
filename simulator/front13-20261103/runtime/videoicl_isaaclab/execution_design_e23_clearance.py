"""E23 private engineering clearance from actual live collision body poses.

AABB separation is a conservative lower bound, never a contact identity proof.
Missing/unsupported collision geometry is partial and cannot clear a route.
All motion remains public; this module neither writes poses nor changes scores.
"""
import itertools
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def corners(lo,hi):
    lo=np.asarray(lo,float);hi=np.asarray(hi,float)
    if lo.shape!=(3,) or hi.shape!=(3,) or not np.isfinite([lo,hi]).all() or (lo>hi).any():
        raise ToolExecutionError('Invalid measured E23 bounds')
    return np.array(list(itertools.product(*zip(lo,hi))))


def actor_bounds(obj,body):
    mat=np.asarray(body['mat'],float);pos=np.asarray(body['pos'],float)
    half=np.asarray(obj.get('bounds_half_extent',obj['size']),float)
    center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    points=corners(center-half,center+half)@mat.T+pos
    if not np.isfinite(points).all():raise ToolExecutionError('Nonfinite E23 actor geometry')
    return dict(lo=points.min(0).tolist(),hi=points.max(0).tolist())


def separation(a,b):
    # Euclidean distance between axis-aligned boxes: a lower bound on mesh
    # separation. Overlap is only a collision candidate, never proof of contact.
    alo=np.asarray(a['lo']);ahi=np.asarray(a['hi']);blo=np.asarray(b['lo']);bhi=np.asarray(b['hi'])
    corners(alo,ahi);corners(blo,bhi)
    return float(np.linalg.norm(np.maximum(np.maximum(alo-bhi,blo-ahi),0)))


def actual_robot_collision_geometry(author):
    """Read all rigid-body collision meshes, transforming actual native poses."""
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    from isaaclab.utils.math import matrix_from_quat
    scene=author.scene
    if not hasattr(author,'_e23_robot_collision_cache'):
        stage=omni.usd.get_context().get_stage();xforms=UsdGeom.XformCache();cache={};errors=[]
        for side,robot in scene.robots.items():
            entries=[]
            for bid,name in enumerate(robot.body_names):
                body=stage.GetPrimAtPath(f'{scene.root_path}/{side}_robot/{name}')
                if not body:errors.append(f'{side}/{name}: missing USD body');continue
                inverse=xforms.GetLocalToWorldTransform(body).GetInverse();parts=[]
                for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
                    if not prim.IsA(UsdGeom.Gprim):continue
                    parent=prim;collidable=False
                    while parent:
                        if parent.HasAPI(UsdPhysics.CollisionAPI):
                            enabled=UsdPhysics.CollisionAPI(parent).GetCollisionEnabledAttr().Get()
                            collidable=enabled is not False;break
                        if parent==body:break
                        parent=parent.GetParent()
                    if not collidable:continue
                    if not prim.IsA(UsdGeom.Mesh):
                        errors.append(f'{side}/{name}: unsupported collider {prim.GetTypeName()} {prim.GetPath()}');continue
                    points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
                    if points.ndim!=2 or points.shape[1]!=3 or not len(points):
                        errors.append(f'{side}/{name}: empty collider {prim.GetPath()}');continue
                    transform=np.asarray(xforms.GetLocalToWorldTransform(prim)*inverse,float)
                    parts.append(points@transform[:3,:3]+transform[3,:3])
                if parts:entries.append((bid,name,np.concatenate(parts)))
            cache[side]=entries
        author._e23_robot_collision_cache=(cache,errors)
    cache,errors=author._e23_robot_collision_cache;result={}
    for side,entries in cache.items():
        robot=scene.robots[side];rows=[]
        for bid,name,points in entries:
            rotation=scene.layout.task_rotation.T@matrix_from_quat(robot.data.body_quat_w[:,bid])[0].cpu().numpy()
            position=scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
            measured=points@rotation.T+position
            if not np.isfinite(measured).all():raise ToolExecutionError('Nonfinite E23 robot collision mesh pose')
            rows.append(dict(name=name,body_index=bid,body_origin_task_m=position.tolist(),
                body_rotation_task=rotation.tolist(),collision_vertex_count=len(measured),
                maximum_distance_to_tcp_m=float(np.linalg.norm(measured-np.asarray(author.tip(side)),axis=1).max()),
                lo=measured.min(0).tolist(),hi=measured.max(0).tolist()))
        result[side]=rows
    return dict(source='actual_collision_mesh_live_native_body_pose',complete=not errors,
                errors=list(errors),robots=result,coordinate_frame='room_task',
                distance_interpretation='AABB lower bound; overlap is not proof of mesh contact')


def rotation_obstacle_top(tip,radius,objects,held,fixtures):
    tip=np.asarray(tip,float);top=.8;hazards=[]
    if tip.shape!=(3,) or not np.isfinite(tip).all() or not np.isfinite(radius) or radius<=0:
        raise ToolExecutionError('Actual rotation center and positive radius required')
    for name,bounds in objects.items():
        if name==held:continue
        lo=np.asarray(bounds['lo']);hi=np.asarray(bounds['hi']);corners(lo,hi)
        xy_distance=float(np.linalg.norm(np.maximum(np.maximum(lo[:2]-tip[:2],tip[:2]-hi[:2]),0)))
        if xy_distance<=radius+.02:top=max(top,float(hi[2]));hazards.append(name)
    for fixture in fixtures:
        if fixture.get('type')!='box' or fixture.get('quat',[1,0,0,0])!=[1,0,0,0]:
            raise ToolExecutionError('Unreviewed E23 fixture geometry')
        xy=np.asarray(fixture['xy'],float);half=np.asarray(fixture['size'],float)
        if np.linalg.norm(np.maximum(np.abs(tip[:2]-xy)-half[:2],0))<=radius+.02:
            top=max(top,float(fixture['z'])+float(half[2]))
    return top,hazards


def choose_rotation_station(tip,radius,objects,held,side,fixtures,*,wrist_planning=False):
    """Rank small outward translations; actual all-arm guards still gate moves."""
    if side not in ('left','right'):raise ToolExecutionError('Known E23 arm required')
    rows=[];tip=np.asarray(tip,float)
    lateral_offsets=(0.,.04,.08,.12,.16) if wrist_planning else (0.,)
    outward_offsets=(0.,.04,.08,.12,.16,.20) if wrist_planning else (0.,.04,.08,.12,.16)
    tree=objects.get('tree')
    if wrist_planning and tree is None:raise ToolExecutionError('Measured E23 tree bounds required for wrist station')
    away=1 if tree is not None and (tree['lo'][0]+tree['hi'][0])*.5<tip[0] else -1
    for offset in outward_offsets:
        for lateral in lateral_offsets:
            point=tip.copy();point[1]+=offset*(1 if side=='left'else -1);point[0]+=away*lateral
            top,hazards=rotation_obstacle_top(point,radius,objects,held,fixtures)
            rows.append(dict(tcp_task_m=point.tolist(),outward_distance_m=offset,
                away_from_tree_x_m=away*lateral,translation_distance_m=float(np.hypot(offset,lateral)),
                rotation_height_m=top+radius+.02,swept_obstacles=hazards,
                actual_path_not_verified=True))
    chosen=min(rows,key=lambda r:(round(r['rotation_height_m'],6),r['translation_distance_m']))
    return dict(chosen=chosen,candidates=rows,tracking_margin_m=.010)


def wrist_station_radius(geometry,side,hand_cup_radius):
    """Measured distal wrist sphere for planning, not a full-arm path certificate."""
    if not geometry.get('complete'):raise ToolExecutionError('Complete E23 wrist geometry required')
    rows={r['name']:r for r in geometry['robots'].get(side,[])}
    names=('panda_link6','panda_link7','panda_hand','panda_leftfinger','panda_rightfinger')
    if not all(n in rows for n in names):raise ToolExecutionError('Missing E23 distal wrist collider')
    radii=np.asarray([rows[n].get('maximum_distance_to_tcp_m',float('nan'))for n in names]+[hand_cup_radius],float)
    if not np.isfinite(radii).all()or(radii<=0).any():raise ToolExecutionError('Invalid E23 measured wrist radius')
    return float(radii.max())


def rotation_workspace(policy,name,side,geometry):
    if not geometry.get('complete') or geometry.get('source')!='actual_collision_mesh_live_native_body_pose':
        raise ToolExecutionError('Partial E23 arm collision geometry cannot certify clearance')
    state,_=policy.snapshot();tip=np.asarray(policy.tip(side),float)
    objects={n:actor_bounds(policy.objects[n],b)for n,b in state.items()}
    hand=[row for row in geometry['robots'].get(side,[]) if row['name'] in
          ('panda_hand','panda_leftfinger','panda_rightfinger')]
    if {r['name']for r in hand}!={'panda_hand','panda_leftfinger','panda_rightfinger'}:
        raise ToolExecutionError('E23 measured palm and both fingers are required')
    body=state[name];obj=policy.objects[name]
    half=np.asarray(obj.get('bounds_half_extent',obj['size']),float)
    center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    cup_points=corners(center-half,center+half)@np.asarray(body['mat']).T+np.asarray(body['pos'])
    hand_radii=np.asarray([row.get('maximum_distance_to_tcp_m',float('nan'))for row in hand],float)
    if not np.isfinite(hand_radii).all() or (hand_radii<=0).any():
        raise ToolExecutionError('Actual hand collision vertex radii required')
    radius=max(float(hand_radii.max()),float(np.linalg.norm(cup_points-tip,axis=1).max()))
    top,hazards=rotation_obstacle_top(tip,radius,objects,name,policy.spec.get('fixtures',[]))
    checks=[]
    for arm,rows in geometry['robots'].items():
        for row in rows:
            for other,bounds in objects.items():
                if other==name:continue
                checks.append(dict(side=arm,body=row['name'],object=other,
                                   separation_lower_bound_m=separation(row,bounds)))
    return dict(source='measured_hand_cup_full_rotation_sphere_and_all_arm_AABB',
        tcp_task_m=tip.tolist(),rotation_radius_m=radius,obstacle_top_z_m=top,
        swept_obstacles=hazards,target_tcp_z_m=max(float(tip[2]),top+radius+.02),
        arm_object_separations=checks,minimum_separation_m=min((x['separation_lower_bound_m']for x in checks),default=0.),
        not_collision_free_path_proof=True)


def record_geometry(policy,name,side,phase):
    geometry=actual_robot_collision_geometry(policy.a)
    workspace=rotation_workspace(policy,name,side,geometry) if geometry['complete'] else None
    state,contacts=policy.snapshot()
    tcp=np.asarray(policy.tip(side),float);rotation=np.asarray(policy.a.tcp_rotation_task(side),float)
    relative_position=rotation.T@(np.asarray(state[name]['pos'])-tcp)
    relative_rotation=rotation.T@np.asarray(state[name]['mat'])
    row=dict(phase=phase,actor=name,side=side,action_step=policy.c.steps,geometry=geometry,
             workspace=workspace,state=state,contacts=[sorted(pair)for pair in contacts],
             tcp_rotation_task=rotation.tolist(),
             measured_cup_origin_in_tcp_frame_m=relative_position.tolist(),
             measured_cup_rotation_in_tcp_frame=relative_rotation.tolist(),
             contact_forces_n=[dict(bodies=sorted(pair),force_n=float(force))for pair,force in policy.c.contact_forces.items()])
    def encode(x):
        if hasattr(x,'tolist'):return x.tolist()
        raise TypeError(type(x).__name__)
    with (policy.a.out/'e23-rotation-clearance.private.jsonl').open('a') as stream:
        stream.write(json.dumps(row,default=encode)+'\n')
    return workspace


def prepare_rotation_workspace(policy,name,side):
    from .execution_design import REVISION_V3
    if (policy.task!='E23' or policy.spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or not getattr(policy.a,'control_report',{}).get('engineering_reference_only')):
        raise ToolExecutionError('E23 clearance requires explicit v3 independent engineering')
    policy.require_held({'actor':name},side)
    initial=record_geometry(policy,name,side,'before-public-clearance-lift')
    if initial is None:raise ToolExecutionError('Missing full E23 arm collision geometry')
    state,_=policy.snapshot();bounds={n:actor_bounds(policy.objects[n],b)for n,b in state.items()}
    planning_radius=wrist_station_radius(actual_robot_collision_geometry(policy.a),side,initial['rotation_radius_m'])
    station=choose_rotation_station(policy.tip(side),planning_radius,bounds,name,side,policy.spec.get('fixtures',[]),wrist_planning=True)
    station['measured_wrist_radius_m']=planning_radius
    policy.operations.append(dict(stage='E23-measured-rotation-station',**station))
    def movement_guard():
        measured=record_geometry(policy,name,side,'during-public-clearance-translation')
        if measured is None or measured['minimum_separation_m']<.005:
            raise ToolExecutionError('E23 all-arm clearance uncertain during actual station transfer')
        policy.require_held({'actor':name},side)
    policy.stage('measured-cup-rotation-outward-'+name)
    policy.move(side,station['chosen']['tcp_task_m'],movement_guard)
    at_station=record_geometry(policy,name,side,'after-public-outward-transfer')
    if at_station is None:raise ToolExecutionError('Missing E23 actual station measurement')
    policy.stage('measured-cup-rotation-clearance-'+name)
    target=np.asarray(policy.tip(side),float).copy()
    target[2]=max(at_station['target_tcp_z_m'],station['chosen']['rotation_height_m'])+station['tracking_margin_m']
    policy.move(side,target,movement_guard)
    final=record_geometry(policy,name,side,'after-public-clearance-lift')
    if final is None or final['minimum_separation_m']<.005:
        raise ToolExecutionError('E23 all-arm obstacle clearance remains uncertain after actual lift')
    policy.require_held({'actor':name},side)
    policy._e23_rotation_station=(name,side,np.asarray(policy.tip(side),float).copy())
    return final


def verify_rotation_clearance(policy,name,side,phase):
    measured=record_geometry(policy,name,side,phase)
    if measured is None or measured['minimum_separation_m']<.005:
        raise ToolExecutionError('E23 full-arm object clearance is uncertain during rotation')
    if measured['target_tcp_z_m']>float(policy.tip(side)[2])+.003:
        raise ToolExecutionError('E23 hand/cup rotation envelope lost measured vertical clearance')
    policy.require_held({'actor':name},side)
    return measured


def restore_rotation_station(policy,name,side):
    """Correct accumulated real TCP drift through ordinary public translations."""
    record=getattr(policy,'_e23_rotation_station',None)
    if record is None or record[:2]!=(name,side):
        raise ToolExecutionError('E23 actual established rotation station required')
    target=np.asarray(record[2],float);actual=np.asarray(policy.tip(side),float)
    drift=float(np.max(np.abs(target-actual)))
    if not np.isfinite(drift) or drift>.025:
        raise ToolExecutionError('E23 TCP left measured station by more than 25mm')
    if drift<=.002:return
    def guard():
        measured=record_geometry(policy,name,side,'during-public-station-restoration')
        if measured is None or measured['minimum_separation_m']<.005:
            raise ToolExecutionError('E23 station restoration lacks full-arm clearance')
        policy.require_held({'actor':name},side)
    policy.stage('restore-measured-rotation-station-'+name)
    policy.move(side,target,guard,tolerance=.001)
    verify_rotation_clearance(policy,name,side,'after-public-station-restoration')
