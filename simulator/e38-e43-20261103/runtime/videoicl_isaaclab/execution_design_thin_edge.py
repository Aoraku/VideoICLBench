"""Read-only thin-material/table-edge geometry for public-action engineering."""
import numpy as np


def table_bounds_task(scene):
    t=scene.embodiment.config['layout']['table'];center=np.asarray(t['position'],float)+np.asarray(getattr(scene,'origin',(0,0,0)),float)
    size=np.asarray(t['size'],float);top=float(t['top'])+float(getattr(scene,'origin',(0,0,0))[2])
    corners=[scene.world_to_task([center[0]+a*size[0]/2,center[1]+b*size[1]/2,top])for a in (-1,1)for b in (-1,1)]
    corners=np.asarray(corners,float)
    if np.ptp(corners[:,2])>1e-5:raise ValueError('Horizontal actual table required')
    return dict(lower=corners.min(0),upper=corners.max(0),top=float(corners[:,2].mean()))


def edge_slide_target(grasp,base,outward,bounds,clearance=.03):
    grasp=np.asarray(grasp,float);base=np.asarray(base,float);axis=np.asarray(outward,float)
    if any(v.shape!=(3,)for v in (grasp,base,axis))or not np.isfinite(np.r_[grasp,base,axis]).all():raise ValueError('Finite material geometry required')
    norm=float(np.linalg.norm(axis))
    if norm<1e-8:raise ValueError('Nonzero measured outward direction required')
    axis=axis/norm;component=int(np.argmax(abs(axis[:2])))
    if abs(axis[2])>.01 or abs(axis[component])<.999:raise ValueError('Public edge slide requires measured axis-aligned flat material')
    sign=float(np.sign(axis[component]));edge=float(bounds['upper'if sign>0 else'lower'][component]);distance=max(0.,(edge-grasp[component])*sign+clearance)
    if distance>.4:raise ValueError('Reviewed thin-material slide exceeds bounded tabletop route')
    translated_base=base+axis*distance
    if any(translated_base[k]<bounds['lower'][k]+.01 or translated_base[k]>bounds['upper'][k]-.01 for k in (0,1)):
        raise ValueError('Material base would lose its finite tabletop support')
    return dict(axis=axis,component=component,sign=sign,table_edge=edge,distance=distance,target_grasp=grasp+axis*distance)


def check_under_table_clearance(target,current_tip,finger_geometry,bounds,component,sign,margin=.001):
    """Conservative actual-collision AABB check; never ignore a lower finger."""
    delta=np.asarray(target,float)-np.asarray(current_tip,float);edge=bounds['upper'if sign>0 else'lower'][component]
    if len(finger_geometry.get('fingers',[]))!=2:raise ValueError('Both actual collision fingers required')
    for f in finger_geometry['fingers']:
        lo=np.asarray(f['aabb_min_task_m'],float)+delta;hi=np.asarray(f['aabb_max_task_m'],float)+delta
        if lo[2]<bounds['top']+margin:
            nearest=lo[component]if sign>0 else hi[component]
            if sign*(nearest-edge)<margin:raise RuntimeError('Actual lower finger would intersect finite table')
    return True


def trailing_edge_push_pose(material_points,finger_points,tip,outward,table_top,gap=.003,clearance=.0002,center_leading_toe=False):
    """Measured trailing edge and actual near-table finger collision band."""
    material=np.asarray(material_points,float);finger=np.asarray(finger_points,float);tip=np.asarray(tip,float);axis=np.asarray(outward,float)
    if any(v.ndim!=2 or v.shape[1]!=3 or len(v)<4 for v in (material,finger)):
        raise ValueError('Actual material and finger collision vertices required')
    if not np.isfinite(np.r_[material.ravel(),finger.ravel(),tip,axis,table_top]).all():raise ValueError('Nonfinite contact geometry')
    axis=axis/np.linalg.norm(axis);k=int(np.argmax(abs(axis[:2])));sign=float(np.sign(axis[k]))
    if abs(axis[k])<.999 or abs(axis[2])>.01:raise ValueError('Axis aligned physical edge required')
    top=float(material[:,2].max());floor=float(table_top)
    if not np.isfinite(clearance)or not .00002<=clearance<=.001:
        raise ValueError('Finite positive reviewed finger clearance required')
    if top<floor+clearance+.0001:raise ValueError('No table-clear finger band overlaps actual material thickness')
    dz=floor+clearance-float(finger[:,2].min());shifted=finger.copy();shifted[:,2]+=dz
    band=shifted[shifted[:,2]<=top+.0001]
    if len(band)<2:raise ValueError('Actual finger toes missing in thin-material height band')
    tangent=1-k;mid=float((material[:,tangent].min()+material[:,tangent].max())/2)
    tangent_target=mid
    if center_leading_toe:
        projection=band@axis;front=band[projection>=float(projection.max())-.0001]
        tangent_target=mid-float(np.mean(front[:,tangent]-tip[tangent]))
    # A yawed material's global trailing corner is not its edge at the toe.
    # Intersect its convex envelope at each real toe's tangent coordinate.
    # All crossing chords span the convex section without assuming a box.
    candidates=[]
    for toe in band:
        coordinate=float(toe[tangent]+tangent_target-tip[tangent])
        at=material[np.abs(material[:,tangent]-coordinate)<1e-9]
        below=material[material[:,tangent]<coordinate-1e-9]
        above=material[material[:,tangent]>coordinate+1e-9]
        sections=[at]
        if len(below)and len(above):
            delta=above[None,:,:]-below[:,None,:]
            ratio=(coordinate-below[:,tangent,None])/delta[:,:,tangent]
            sections.append((below[:,None,:]+delta*ratio[:,:,None]).reshape(-1,3))
        section=np.concatenate(sections)
        if not len(section)or toe[2]>float(section[:,2].max())+.0001:continue
        edge=float(np.min(section@axis))
        candidates.append((edge-float((toe-tip)@axis),edge,coordinate))
    if not candidates:raise ValueError('Actual toe band does not overlap material section')
    contact_tip,trailing,coordinate=min(candidates)
    target=tip.copy();target[2]+=dz;target[k]=(contact_tip-gap)*sign;target[tangent]=tangent_target
    return target,dict(material_trailing_edge_m=trailing,global_material_trailing_edge_m=float(np.min(material@axis)),
        contact_tangent_m=coordinate,section_candidates=len(candidates),center_leading_toe=bool(center_leading_toe),material_top_m=top,table_top_m=floor,
        finger_clearance_m=clearance,finger_band_vertices=len(band),actual_mesh_vertices=len(finger),
        public_start_tip=target.tolist(),gap_m=gap)


def material_collision_points_task(policy,ref):
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    stage=omni.usd.get_context().get_stage()
    path=(f"{policy.a.scene.root_path}/Props/{ref['actor']}"if 'actor'in ref
          else f"{policy.a.scene.root_path}/Mechanisms/{ref['mechanism']}/{ref['body']}")
    body=stage.GetPrimAtPath(path)
    if not body:raise RuntimeError('Actual material rigid body missing')
    cache=UsdGeom.XformCache();inverse=cache.GetLocalToWorldTransform(body).GetInverse();vertices=[]
    for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh):continue
        ancestor=prim;collidable=False;enabled=True
        while ancestor and ancestor!=body:
            if ancestor.HasAPI(UsdPhysics.CollisionAPI):
                collidable=True;enabled=enabled and bool(UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get())
            ancestor=ancestor.GetParent()
        if not collidable or not enabled:continue
        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float);matrix=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
        vertices.append(points@matrix[:3,:3]+matrix[3,:3])
    if not vertices:raise RuntimeError('Actual material collision vertices missing')
    position,rotation=policy.frame(ref)
    return np.concatenate(vertices)@rotation.T+position


def actual_finger_points_task(author,side):
    from isaaclab.utils.math import matrix_from_quat
    author.finger_geometry(side)  # Populate read-only mesh cache, never command.
    robot=author.scene.robots[side];points=[]
    for bid,local in author._finger_collision_points[side]:
        rotation=author.scene.layout.task_rotation.T@matrix_from_quat(robot.data.body_quat_w[:,bid])[0].cpu().numpy()
        position=author.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
        points.append(local@rotation.T+position)
    return np.concatenate(points)


def mechanism_collision_points_task(policy,ref):
    return material_collision_points_task(policy,ref)


def card_side_pinch_plan(material_points,body_center,finger_points_relative,bounds,
                         outward=(1.,0.,0.),edge_inset=.006,margin=.001):
    """Read-only flat-card plan from collision vertices, with real support.

    Fingers are measured vertices relative to the future TCP at the proposed
    side-pinch orientation. This is geometry feasibility, not a grasp claim.
    """
    material=np.asarray(material_points,float);center=np.asarray(body_center,float)
    fingers=[np.asarray(v,float)for v in finger_points_relative];axis=np.asarray(outward,float)
    if material.ndim!=2 or material.shape[1]!=3 or len(material)<4 or len(fingers)!=2:
        raise ValueError('Card and both actual finger collision meshes required')
    if not np.isfinite(np.r_[material.ravel(),center,axis,*[v.ravel()for v in fingers]]).all():
        raise ValueError('Finite measured card/finger geometry required')
    norm=float(np.linalg.norm(axis))
    if norm<1e-9:raise ValueError('Nonzero card approach direction required')
    axis=axis/norm;k=int(np.argmax(abs(axis[:2])));sign=float(np.sign(axis[k]))
    if abs(axis[k])<.999 or abs(axis[2])>.01:raise ValueError('Axis aligned card approach required')
    if np.ptp(material[:,2])>.002:raise ValueError('This edge plan requires a flat thin card')
    if not 0<edge_inset<.02 or margin<=0:raise ValueError('Positive reviewed edge inset and margin required')
    grasp=center.copy();grasp[k]=(float(np.max(material@axis))-edge_inset)*sign
    grasp[2]=float((material[:,2].min()+material[:,2].max())/2)
    # Any finger vertex below the tabletop needs to remain beyond its edge.
    low=[v[v[:,2]+grasp[2]<bounds['top']+margin] for v in fingers]
    if not any(len(v)for v in low):raise ValueError('Expected a true lower finger for side pinch')
    exterior=max(margin-float(np.min(v@axis))for v in low if len(v))
    edge=float(bounds['upper'if sign>0 else'lower'][k]);target=grasp.copy();target[k]=edge+sign*exterior
    delta=target-grasp;translated_center=center+delta
    if any(translated_center[i]<bounds['lower'][i]+.005 or translated_center[i]>bounds['upper'][i]-.005 for i in (0,1)):
        raise ValueError('Card centre would lose reviewed tabletop support margin')
    if float(delta@axis)<0 or float(delta@axis)>.4:raise ValueError('Card slide outside bounded forward route')
    return dict(grasp=grasp,target_grasp=target,translation=delta,translated_center=translated_center,
                required_exterior_m=exterior,edge_inset_m=edge_inset)


def seek_actual_contact(contact,advance,max_actions):
    """Read actual contact after every bounded public action, including last."""
    if type(max_actions)is not int or max_actions<0:raise ValueError('Nonnegative action count required')
    if contact():return 0
    for count in range(1,max_actions+1):
        advance()
        if contact():return count
    return None
