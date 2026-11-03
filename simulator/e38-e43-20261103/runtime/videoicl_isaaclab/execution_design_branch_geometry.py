"""Read-only collision guards for explicitly restored engineering branches."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def swept_pose_clearance(bodies,tip,target,rotation,obstacles,table_top,allowed_payload=(),margin=.001):
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    tip,target,rotation=map(lambda x:np.asarray(x,float),(tip,target,rotation))
    if tip.shape!=(3,)or target.shape!=(3,)or rotation.shape!=(3,3)or not np.isfinite(np.r_[tip,target,rotation.ravel()]).all():raise ValueError('Finite actual swept pose required')
    if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5)or np.linalg.det(rotation)<.999:raise ValueError('Proper actual rotation required')
    angle=math.acos(float(np.clip((np.trace(rotation)-1)/2,-1,1)));minimum=10.
    for label,points in bodies.items():
        points=np.asarray(points,float)
        if points.ndim!=2 or points.shape[1]!=3 or len(points)<4 or not np.isfinite(points).all():raise ValueError('Complete actual collision mesh required')
        end=(points-tip)@rotation.T+target
        radius=float(np.linalg.norm(points-tip,axis=1).max());arc=radius*(1-math.cos(angle/2))
        cloud=np.r_[points,end];low=float(cloud[:,2].min())-arc;minimum=min(minimum,low-table_top)
        if low<table_top+.0003:raise ToolExecutionError('Actual held branch hand or payload crosses table clearance')
        hull=None
        for actor,parts in obstacles.items():
            if label=='payload'and actor in allowed_payload:continue
            for part in parts:
                part=np.asarray(part,float);pad=margin+arc
                if np.any(cloud.max(0)+2*pad<part.min(0))or np.any(part.max(0)+2*pad<cloud.min(0)):continue
                if hull is None:hull=ConvexHull(cloud,qhull_options='QJ')
                obstacle=ConvexHull(part,qhull_options='QJ')
                a=np.r_[hull.equations[:,:3],obstacle.equations[:,:3]]
                b=-np.r_[hull.equations[:,3],obstacle.equations[:,3]]+pad
                result=linprog([0,0,0],A_ub=a,b_ub=b,bounds=[(None,None)]*3,method='highs')
                if result.success:raise ToolExecutionError('Actual held branch '+label+' sweep intersects '+actor)
                if result.status!=2:raise ToolExecutionError('Held branch collision separation unresolved')
    return dict(actual_collision_bodies=len(bodies),minimum_table_clearance_m=minimum,margin_m=margin)


def cooked_mesh_vertices(cooking,stage_id,path,path_to_int):
    """Read the native cooker representation; never guess a decomposition."""
    received=[];errors=[]
    def callback(result,meshes):
        for mesh in meshes:
            vertices=np.asarray(mesh.vertices,float)
            if vertices.ndim!=2 or vertices.shape[1]!=3 or len(vertices)<4 or not np.isfinite(vertices).all():
                errors.append('Actual cooked convex vertices are incomplete');continue
            received.append(vertices)
    cooking.request_convex_collision_representation(stage_id,path_to_int(path),False,callback)
    if errors:raise ToolExecutionError(errors[0])
    if not received:raise ToolExecutionError('Actual cooked convex pieces unavailable; branch guard refused')
    return received


def cooked_floor_height(parts,box_position,box_rotation,xy,ceiling):
    """First actual cooked solid hit by a vertical ray into the open box."""
    from scipy.spatial import ConvexHull
    box_position,box_rotation,xy=map(lambda x:np.asarray(x,float),(box_position,box_rotation,xy))
    hits=[]
    for world in parts:
        local=(np.asarray(world,float)-box_position)@box_rotation;hull=ConvexHull(local,qhull_options='QJ');low=-float('inf');high=float('inf');inside=True
        for nx,ny,nz,offset in hull.equations:
            b=-float(nx*xy[0]+ny*xy[1]+offset)
            if abs(nz)<1e-10:
                if b< -1e-8:inside=False;break
            elif nz>0:high=min(high,b/nz)
            else:low=max(low,b/nz)
        if inside and low<=high+1e-8 and np.isfinite(high)and high<=float(ceiling)+1e-5:hits.append(high)
    if not hits:raise ToolExecutionError('No actual cooked source floor under sole control point')
    return float(max(hits))


def collision_parts_task(policy,actor):
    """Use actual cooked convex pieces, including native container cavities."""
    from pxr import Usd,UsdGeom,UsdPhysics
    from pxr import PhysicsSchemaTools
    import omni.usd,omni.physx
    cache=getattr(policy.a,'_branch_collision_parts',None)
    if cache is None:cache={};policy.a._branch_collision_parts=cache
    if actor not in cache:
        stage=omni.usd.get_context().get_stage();body=stage.GetPrimAtPath(f'{policy.a.scene.root_path}/Props/{actor}')
        if not body:raise ToolExecutionError('Actual branch obstacle body missing: '+actor)
        transforms=UsdGeom.XformCache();inverse=transforms.GetLocalToWorldTransform(body).GetInverse();parts=[];evidence=[]
        for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
            mesh=prim.IsA(UsdGeom.Mesh);cube=prim.IsA(UsdGeom.Cube)
            if not mesh and not cube:continue
            ancestor=prim;collidable=False;enabled=True
            while ancestor and ancestor!=body:
                if ancestor.HasAPI(UsdPhysics.CollisionAPI):collidable=True;enabled=enabled and bool(UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get())
                ancestor=ancestor.GetParent()
            if not collidable or not enabled:continue
            matrix=np.asarray(transforms.GetLocalToWorldTransform(prim)*inverse,float)
            approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get())if prim.HasAPI(UsdPhysics.MeshCollisionAPI)else None
            if cube:
                half=float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2.
                meshes=[np.array([[x,y,z]for x in(-half,half)for y in(-half,half)for z in(-half,half)])]
                representation='actual_native_collision_cube'
            elif approximation in('convexHull','convexDecomposition'):
                meshes=cooked_mesh_vertices(omni.physx.get_physx_cooking_interface(),omni.usd.get_context().get_stage_id(),str(prim.GetPath()),PhysicsSchemaTools.sdfPathToInt)
                representation='actual_native_cooked_convex_pieces'
            else:
                meshes=[np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)]
                representation='conservative_original_mesh_hull'
            parts.extend(points@matrix[:3,:3]+matrix[3,:3]for points in meshes)
            evidence.append(dict(path=str(prim.GetPath()),source_approximation=approximation,representation=representation,parts=len(meshes)))
        if not parts:raise ToolExecutionError('No actual branch obstacle collision pieces: '+actor)
        cache[actor]=parts
        audits=getattr(policy.a,'_branch_collision_parts_evidence',None)
        if audits is None:audits={};policy.a._branch_collision_parts_evidence=audits
        audits[actor]=evidence
    pos,r=policy.frame(dict(actor=actor));return [part@r.T+pos for part in cache[actor]]


class HeldGeometry:
    def __init__(self,policy,actor,side,allowed_payload=(),require_hold=True):
        self.p=policy;self.actor=actor;self.side=side;self.allowed=tuple(allowed_payload);self.require_hold=bool(require_hold)
    def check(self,target=None,rotation=None):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
        if self.require_hold:self.p.require_held(dict(actor=self.actor),self.side)
        tip=self.p.tip(self.side);bodies={n:actual_mesh(self.p.a,self.side,n)for n in('panda_hand',*self.p.a.scene.embodiment.fingers)}
        if self.require_hold:bodies['payload']=material_collision_points_task(self.p,dict(actor=self.actor))
        state,_=self.p.snapshot();obstacles={name:collision_parts_task(self.p,name)for name in state if not self.require_hold or name!=self.actor}
        result=swept_pose_clearance(bodies,tip,tip if target is None else target,np.eye(3)if rotation is None else rotation,
                                   obstacles,table_bounds_task(self.p.a.scene)['top'],self.allowed)
        result['obstacle_convex_piece_counts']={name:len(parts)for name,parts in obstacles.items()}
        result['collision_representation_evidence']=getattr(self.p.a,'_branch_collision_parts_evidence',{})
        self.last_report=result
        return result
    def __call__(self):return self.check()
    def rotate(self,axis,angle):return self.check(rotation=_axis_rotation(axis,angle))
    def move(self,target):
        self.check(target=target)
        self.p.move(self.side,target,tolerance=.002,guard=lambda:self.check(target=target))
        self.check()


def public_rotation_holds(policy,side,guard,max_holds=6,task_accepted=None):
    rows=[]
    for _ in range(max_holds):
        if task_accepted is not None:
            guard()
            if task_accepted():return rows
        error=float(policy.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])
        if not np.isfinite(error):raise ToolExecutionError('Nonfinite actual pending rotation error')
        if error<=math.radians(.5):break
        guard();policy.act(side,'STILL');guard()
        rows.append(dict(step=policy.c.steps,orientation_error_rad=float(policy.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])))
    if task_accepted is not None:
        guard()
        if task_accepted():return rows
    remaining=float(policy.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])
    if not np.isfinite(remaining)or remaining>math.radians(.5):
        raise ToolExecutionError('Accepted rotation did not settle within public hold bound')
    return rows


def install_public_guard(policy,geometry):
    """Wrap only this branch policy; every command still calls its public act."""
    original=getattr(policy,'_branch_public_original_act',policy.act);policy._branch_public_original_act=original;released={'value':False}
    translations={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}
    rotations={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
    def act(side=None,token='STILL',mm=1.,degrees=5.,follower=None):
        if released['value']:raise ToolExecutionError('Branch ends at release; post-release motion needs a separate checkpoint branch')
        geometry()
        if side==geometry.side and token in translations:
            axis,sign=translations[token];target=policy.tip(side).copy();target[axis]+=sign*max(policy.min_mm,min(policy.max_mm,float(mm)))/1000;geometry.check(target=target)
        if side==geometry.side and token in rotations:
            axis,sign=rotations[token];geometry.rotate(np.eye(3)[axis],sign*math.radians(max(policy.min_deg,min(policy.max_deg,float(degrees)))))
        original(side,token,mm=mm,degrees=degrees,follower=follower)
        if side==geometry.side and token=='RELEASE':released['value']=True
        else:geometry()
    policy.act=act
    return released
