"""Engineering-only bottle pickup above the measured palm collision boundary."""
import json
import numpy as np
from .execution_design import REVISION_V3

def narrow_horizontal_axis(vertices):
    """Minimum-width direction of the actual horizontal convex footprint."""
    from scipy.spatial import ConvexHull
    vertices=np.asarray(vertices,float)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or not np.isfinite(vertices).all():
        raise ValueError('Finite actual bottle hull required')
    xy=vertices[:,:2];outline=xy[ConvexHull(xy).vertices]
    edge=np.roll(outline,-1,axis=0)-outline
    axes=np.stack((-edge[:,1],edge[:,0]),axis=1)
    axes/=np.linalg.norm(axes,axis=1)[:,None]
    widths=np.ptp(xy@axes.T,axis=0)
    return np.r_[axes[int(np.argmin(widths))],0.]

def section(points,z):
    """Conservative convex-hull plane section, including every crossing chord."""
    pts=np.asarray(points,float);pieces=[p[:2]for p in pts if abs(p[2]-z)<1e-8]
    below=pts[pts[:,2]<z];above=pts[pts[:,2]>z]
    for a in below:
        for b in above:
            pieces.append((a+(b-a)*((z-a[2])/(b[2]-a[2])))[:2])
    if not pieces:raise ValueError('No bottle collision section at grasp height')
    return np.asarray(pieces,float)

def plan_grasp(vertices,tcp,palm,fingers,margin=.006,floor=.8):
    """Translation-only clearance proposal, not an IK or grasp guarantee."""
    vertices,tcp,palm=map(lambda x:np.asarray(x,float),(vertices,tcp,palm))
    fingers=[np.asarray(x,float)for x in fingers]
    if len(fingers)!=2 or any(x.ndim!=2 or x.shape[1]!=3 or len(x)<4 for x in [vertices,palm,*fingers]):raise ValueError('Actual collision meshes required')
    if not all(np.isfinite(x).all()for x in [vertices,tcp,palm,*fingers]):raise ValueError('Finite collision geometry required')
    centers=[f.mean(axis=0)for f in fingers];grip=(centers[0]+centers[1])/2
    axis=centers[1]-centers[0];axis/=np.linalg.norm(axis)
    if abs(axis[2])>.15:raise ValueError('Bottle reference requires a nearly horizontal actual jaw')
    xy_axis=axis[:2]/np.linalg.norm(axis[:2]);finger_z=grip[2]-tcp[2]
    top=float(vertices[:,2].max());bottom=float(vertices[:,2].min())
    # Keep the lowest palm point above the entire target, rather than letting
    # the palm push the tall bottle before the fingers can close around it.
    target_z=max(top-float(palm[:,2].min()-tcp[2])+margin,
                 float(floor)-min(float(f[:,2].min()-tcp[2])for f in fingers)+.0003)
    contact_z=target_z+finger_z
    if not bottom+.005<contact_z<top-.005:raise ValueError('No palm-clear bottle grasp within collision hull')
    cross=section(vertices,contact_z);center=(cross.min(axis=0)+cross.max(axis=0))/2
    a,b=sorted((f[:,:2]@xy_axis for f in fingers),key=lambda p:p.mean())
    opening=float(b.min()-a.max());width=float(np.ptp(cross@xy_axis))
    if opening<width+.004:raise ValueError('Actual open fingers do not clear bottle section')
    target=np.r_[center-(grip-tcp)[:2],target_z]
    return dict(tcp_target_task_m=target.tolist(),contact_plane_z_m=float(contact_z),
        bottle_top_z_m=top,palm_clearance_m=float(palm[:,2].min()-tcp[2]+target_z-top),
        actual_opening_m=opening,bottle_section_width_m=width,
        source='actual_palm_and_finger_collision_meshes_and_pinned_bottle_hull',native_grasp_verified=False)

def actual_mesh(author,side,name):
    from pxr import Usd,UsdGeom,UsdPhysics
    from isaaclab.utils.math import matrix_from_quat
    import omni.usd
    stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache()
    body=stage.GetPrimAtPath(f'{author.scene.root_path}/{side}_robot/{name}')
    if not body:raise ValueError('Actual robot collision body missing')
    inverse=cache.GetLocalToWorldTransform(body).GetInverse();parts=[]
    for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
        ancestor=prim;collision=False
        while ancestor and ancestor!=body:
            if ancestor.HasAPI(UsdPhysics.CollisionAPI):collision=True;break
            ancestor=ancestor.GetParent()
        if collision and prim.IsA(UsdGeom.Mesh):
            points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
            matrix=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
            parts.append(points@matrix[:3,:3]+matrix[3,:3])
    if not parts:raise ValueError('No actual robot collision mesh vertices')
    robot=author.scene.robots[side];bid=robot.find_bodies(name)[0][0]
    rotation=author.scene.layout.task_rotation.T@matrix_from_quat(robot.data.body_quat_w[:,bid])[0].cpu().numpy()
    position=author.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
    return np.concatenate(parts)@rotation.T+position

def grasp_position(author,side,obj):
    scene=author.scene
    if not getattr(author,'_execution_design_reference_authorized',False)or scene.spec['id']!='E33'or scene.spec.get('execution_design',{}).get('revision')!=REVISION_V3:
        raise ValueError('Explicit v3 E33 engineering reference required')
    if scene.embodiment.name!='franka':raise ValueError('E33 palm clearance requires reviewed Panda geometry')
    state,_=author.c.snapshot();body=state[obj['id']]
    hull=obj['source_containment_hull']
    if hull['source_asset_sha256']!=obj['source_asset']['sha256']or not np.allclose(hull['descriptor_half_size'],obj['size']):raise ValueError('Stale bottle hull')
    vertices=np.asarray(hull['vertices_local'])@np.asarray(body['mat']).T+np.asarray(body['pos'])
    def measured_plan():
        current,_=author.c.snapshot();b=current[obj['id']]
        points=np.asarray(hull['vertices_local'])@np.asarray(b['mat']).T+np.asarray(b['pos'])
        return plan_grasp(points,author.tip(side),actual_mesh(author,side,'panda_hand'),
            [actual_mesh(author,side,name)for name in scene.embodiment.fingers])
    try:
        plan=measured_plan()
    except ValueError as exc:
        if str(exc)!='Actual open fingers do not clear bottle section':raise
        if any(b['grasp'][0 if side=='left'else 1]for b in state.values()):
            raise RuntimeError('Bottle jaw reorientation requires an empty hand') from exc
        # A settled bottle may lie sideways. Pinch its real short section,
        # rather than assuming the initial vertical axis survived settling.
        direction=narrow_horizontal_axis(vertices)
        author.align_gripper_axis(side,direction)
        plan=measured_plan()
        plan['public_jaw_alignment_task_axis']=direction.tolist()
    plan.update(object=obj['id'],side=side,step=author.c.steps)
    with (author.out/'e33-palm-clear-grasp.private.jsonl').open('a')as f:f.write(json.dumps(plan)+'\n')
    return np.asarray(plan['tcp_target_task_m'],float)
