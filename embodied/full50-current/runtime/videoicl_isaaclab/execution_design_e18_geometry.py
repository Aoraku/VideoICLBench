"""Reject-only E18 engineering grasp geometry from live native collision meshes."""
import itertools
import numpy as np


def normalized_jaw_axis(measured, native_axis=None):
    jaw=np.asarray(measured,float)
    if jaw.shape!=(3,)or not np.isfinite(jaw).all():
        raise RuntimeError('Finite actual E18 jaw vector required')
    if np.linalg.norm(jaw)<1e-5:
        jaw=np.asarray(native_axis,float)
        if jaw.shape!=(3,)or not np.isfinite(jaw).all()or np.linalg.norm(jaw)<.5:
            raise RuntimeError('Actual E18 closed-finger prismatic axis unavailable')
    return jaw/np.linalg.norm(jaw)


def enabled_body_mesh(stage, body):
    """Read this rigid body's enabled colliders, excluding child rigid bodies."""
    from pxr import Usd,UsdGeom,UsdPhysics
    cache=UsdGeom.XformCache();inverse=cache.GetLocalToWorldTransform(body).GetInverse()
    parts=[];disabled=0;nested=0
    for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh):continue
        ancestor=prim;enabled=False;other_body=False
        while ancestor:
            if ancestor!=body and ancestor.HasAPI(UsdPhysics.RigidBodyAPI):
                other_body=True;break
            if ancestor.HasAPI(UsdPhysics.CollisionAPI):
                enabled=UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get() is not False
                break
            if ancestor==body:break
            ancestor=ancestor.GetParent()
        if other_body:nested+=1;continue
        if not enabled:disabled+=1;continue
        # A collider under a child rigid body belongs to that child even if
        # its own CollisionAPI was found before walking up to the body root.
        ancestor=prim.GetParent()
        while ancestor and ancestor!=body:
            if ancestor.HasAPI(UsdPhysics.RigidBodyAPI):other_body=True;break
            ancestor=ancestor.GetParent()
        if other_body:nested+=1;continue
        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
        transform=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
        parts.append(points@transform[:3,:3]+transform[3,:3])
    if not parts:raise RuntimeError('No enabled native hand collision mesh')
    return np.concatenate(parts),dict(enabled_mesh_count=len(parts),
        disabled_or_visual_mesh_count=disabled,nested_body_mesh_count=nested)


def actual_hand_clouds(author, side):
    """Collision vertices relative to the measured TCP, including the palm."""
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    from .author_orientation import _quaternion_matrix
    robot=author.scene.robots[side]
    if not hasattr(author,'_e18_enabled_hand_mesh'):author._e18_enabled_hand_mesh={}
    if side not in author._e18_enabled_hand_mesh:
        stage=omni.usd.get_context().get_stage();entries=[];reports=[]
        for name in (*author.scene.embodiment.fingers,'panda_hand'):
            body=stage.GetPrimAtPath(f'{author.scene.root_path}/{side}_robot/{name}')
            if not body:raise RuntimeError('Native E18 hand body unavailable: '+name)
            points,report=enabled_body_mesh(stage,body)
            entries.append((robot.find_bodies(name)[0][0],points));reports.append(report)
        author._e18_enabled_hand_mesh[side]=(entries,reports)
    current=np.asarray(author.tcp_rotation_task(side),float);tip=np.asarray(author.tip(side),float)
    entries,reports=author._e18_enabled_hand_mesh[side];clouds=[]
    for bid,vertices in entries:
        rotation=author.scene.layout.task_rotation.T@_quaternion_matrix(robot.data.body_quat_w[0,bid].cpu().numpy())
        position=author.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
        clouds.append((np.asarray(vertices)@rotation.T+position-tip)@current)
    if any(x.ndim!=2 or x.shape[1]!=3 or not len(x)or not np.isfinite(x).all()for x in clouds):
        raise RuntimeError('Native E18 complete hand geometry invalid')
    table=author.scene.layout.config['table'];center=np.asarray(table['position'],float)+np.asarray(getattr(author.scene,'origin',[0,0,0]),float);half=np.asarray(table['size'],float)/2
    corners=[author.scene.world_to_task(center+half*np.array(s))for s in itertools.product((-1,1),repeat=3)]
    finger_ids=[entry[0]for entry in entries[:2]]
    jaw_world=(robot.data.body_pos_w[0,finger_ids[0]]-robot.data.body_pos_w[0,finger_ids[1]]).cpu().numpy()
    jaw=current.T@author.scene.layout.task_rotation.T@jaw_world
    native_axis=None
    if np.linalg.norm(jaw)<1e-5:
        ids,names=robot.find_joints('panda_finger_joint[1-2]')
        if list(names)!=['panda_finger_joint1','panda_finger_joint2']:
            raise RuntimeError('Actual E18 prismatic finger joint identity required')
        jac=robot.root_physx_view.get_jacobians()[0]
        offset=1 if robot.is_fixed_base else 0
        axis_world=(jac[finger_ids[0]-offset,:3,ids[0]]-
                    jac[finger_ids[1]-offset,:3,ids[1]]).detach().cpu().numpy()
        native_axis=current.T@author.scene.layout.task_rotation.T@axis_world
    jaw=normalized_jaw_axis(jaw,native_axis)
    return dict(source='actual_native_collision_mesh_current_body_pose',clouds_tcp=clouds,jaw_axis_tcp=jaw,
        enabled_collision_mesh_reports=reports,table_top=float(np.max(np.asarray(corners)[:,2])))


def candidate_clearance(geometry,rotation,point,outward,bar_axis):
    """Screen complete hand/table and source bar opening; no collision claim."""
    if geometry.get('source')!='actual_native_collision_mesh_current_body_pose':
        raise RuntimeError('Actual native complete hand geometry required')
    rotation=np.asarray(rotation,float);point=np.asarray(point,float);normal=np.asarray(outward,float);bar=np.asarray(bar_axis,float)
    clouds=[np.asarray(c,float)@rotation.T for c in geometry['clouds_tcp']]
    if len(clouds)!=3:raise RuntimeError('Both fingers and palm are required')
    inward=max(float(np.max(c@(-normal)))for c in clouds[:2])
    tcp=point+normal*max(0.,inward-.0008)
    floor=[float(np.min((c+tcp)[:,2])-geometry['table_top'])for c in clouds]
    palm_front=float(np.min((clouds[2]+tcp-point)@normal))
    # Source collision bar measured97.94x2.742x2.608mm. Project its true
    # three axes onto the actual candidate jaw axis, rather than using length.
    jaw=rotation@np.asarray(geometry['jaw_axis_tcp'],float);jaw/=np.linalg.norm(jaw)
    short=np.cross(normal,bar);short/=np.linalg.norm(short)
    opening=float(.09794*abs(jaw@bar)+.002742*abs(jaw@short)+.002608*abs(jaw@normal))
    radius=max(float(np.max(np.linalg.norm(np.asarray(c,float),axis=1)))for c in geometry['clouds_tcp'])
    return dict(target_position=tcp.tolist(),rotation_safe_z_m=float(geometry['table_top']+radius+.015),hand_floor_clearances_m=floor,bar_projected_width_m=opening,palm_outside_handle_plane_m=palm_front,
        feasible=min(floor)>.002 and opening<.078 and palm_front>.003,collision_verified=False)
