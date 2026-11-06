"""Use a finite low inner-pad face, rather than an infinite tilted plane."""
import json
import numpy as np
from scipy.spatial import ConvexHull
from .realworld_tool_expert import ToolExecutionError,_axis_rotation

def face_candidates(meshes,direction,floor,food,half,food_rotation=None,food_size=None):
    candidates=[]
    food_rotation=np.eye(3)if food_rotation is None else np.asarray(food_rotation,float)
    food_size=np.asarray(half if food_size is None else food_size,float)
    # Prefer a true vertical pad directly opposing the blade. A diagonal
    # corner contact can let the food escape tangentially during insertion.
    food_axis=food_rotation[:,int(np.argmax(np.abs(food_rotation.T@direction)))].copy()
    desired_normal=-np.sign(float(food_axis@direction))*food_axis
    desired_normal[2]=0.;desired_normal/=np.linalg.norm(desired_normal)
    yaw_choices=[]
    for mesh in meshes[1:]:
        for plane in ConvexHull(mesh).equations:
            n=np.diag([1.,-1.,-1.])@plane[:3]
            if abs(n[2])>.12:continue
            yaw=float(np.rad2deg(np.arctan2(desired_normal[1],desired_normal[0])-np.arctan2(n[1],n[0])))
            yaw=(yaw+180.)%360.-180.
            if not any(abs(yaw-x)<.1 for x in yaw_choices):yaw_choices.append(yaw)
    yaw_choices += [45.,-45.,135.,-135.,0.,180.,90.,-90.]
    for yaw in yaw_choices:
        rotation=_axis_rotation([0.,0.,1.],np.deg2rad(yaw))@np.diag([1.,-1.,-1.])
        world=[m@rotation.T for m in meshes]
        height=floor+.0003-min(m[:,2].min()for m in world)
        for finger in (1,2):
            hull=ConvexHull(world[finger])
            for tri,plane in zip(hull.simplices,hull.equations):
                normal=plane[:3]
                if normal@direction>-.65 or abs(normal[2])>.12:continue
                points=world[finger][tri]+[0,0,height]
                low=max(float(points[:,2].min()),float(food[2]-half[2]+.0005))
                high=min(float(points[:,2].max()),float(food[2]+half[2]-.0005))
                if low>high:continue
                z=(low+high)/2;section=[]
                for a,b in zip(points,np.roll(points,1,axis=0)):
                    if (a[2]-z)*(b[2]-z)<=0 and abs(a[2]-b[2])>1e-10:section.append(a+(b-a)*(z-a[2])/(b[2]-a[2]))
                if not section:continue
                center=np.mean(section,axis=0)
                # Offset along the actual finite face normal. Offsetting along
                # the blade axis moves an oblique pad inside the food and its
                # lower toe presses the top before the side face can seat.
                extent=float(np.abs(food_rotation.T@normal)@food_size)
                # A narrow pad must approach the actual box support corner,
                # not the normal projection of its centre (outside the facet).
                local_normal=food_rotation.T@normal
                support_sign=np.sign(local_normal);support_sign[np.abs(local_normal)<.05]=0.
                target=food-food_rotation@(support_sign*food_size);target[2]=z
                missing=extent+.0006-float(normal@(food-target))
                target[:2]-=normal[:2]*missing/float(normal[:2]@normal[:2])
                position=target-center;position[2]+=height
                candidates.append(dict(yaw=yaw,finger=finger,normal=normal.tolist(),position=position.tolist(),rotation=rotation.tolist(),finite_z_band=[low,high]))
    return candidates

def prepare(policy,food,tool_side,direction,guard,already_oriented=False):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_tool_pose_paths import append_public_move
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_cutlery_grasp import orient
    from .execution_design_thin_edge import table_bounds_task
    side='left'if tool_side=='right'else'right';guard()
    measured=capture(policy.a,policy.c,side);p=np.asarray(measured['position']);r=np.asarray(measured['rotation_task'])
    names=('panda_hand',*policy.a.scene.embodiment.fingers)
    meshes=[(actual_mesh(policy.a,side,n)-p)@r for n in names]
    state=policy.snapshot()[0];body=state[food];obj=next(o for o in policy.spec['objects']if o['id']==food)
    half=np.abs(body['mat'])@np.asarray(obj['size']);floor=table_bounds_task(policy.a.scene)['top']
    rows=face_candidates(meshes,direction,floor,body['pos'],half,body['mat'],obj['size'])
    retreat=p if already_oriented else p+direction*.10;above=np.r_[retreat[:2],max(.94,p[2])]
    other=[actual_mesh(policy.a,tool_side,n)for n in names];selected=None
    for row in rows:
        desired=np.asarray(row['rotation']);placement=np.asarray(row['position']);poses=[]
        cursor=append_public_move(poses,p,retreat,r,policy.max_mm/1000.)
        cursor=append_public_move(poses,cursor,above,r,policy.max_mm/1000.)
        turn=public_rotation_poses(cursor,r,desired);poses+=turn
        if not rotation_clear(meshes,cursor,r,turn,other,floor):continue
        cursor=append_public_move(poses,cursor,[*placement[:2],above[2]],desired,policy.max_mm/1000.)
        append_public_move(poses,cursor,placement,desired,policy.max_mm/1000.)
        path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],measured['q'],measured['limits'],poses)
        row['path']=path
        if path['feasible']:selected=row;break
    (policy.a.out/'E46-finite-backstop-plan.private.json').write_text(json.dumps(dict(candidates=rows,selected=selected)))
    if selected is None:raise ToolExecutionError('No finite low pad face has a native continuous route')
    placement=np.asarray(selected['position']);desired=np.asarray(selected['rotation'])
    def move(target,tolerance=.002):
        target=np.asarray(target,float);best=float(np.linalg.norm(target-policy.tip(side)));last=policy.c.steps;last_improvement=last
        def progress():
            nonlocal best,last,last_improvement
            guard()
            if policy.c.steps==last:return
            last=policy.c.steps;error=float(np.linalg.norm(target-policy.tip(side)))
            if error<best-.0001:best=error;last_improvement=last
            if last-last_improvement>=12:raise ToolExecutionError('Finite side-pad waypoint has no net progress')
        policy.move(side,target,progress,tolerance=tolerance)
    if not already_oriented:
        policy.stage('finite-pad-retreat');move(retreat);move(above)
    orient(policy.a,side,desired)
    policy.stage('finite-pad-low-side-contact');move([*placement[:2],above[2]]);move(placement,tolerance=.001)
    for _ in range(8):
        guard()
        if any(policy.contact(food,side+'_finger'+str(i))for i in (1,2)):return
        move(policy.tip(side)+np.asarray(selected['normal'])*.001,tolerance=.0005)
    raise ToolExecutionError('Finite side pad failed to contact food')
