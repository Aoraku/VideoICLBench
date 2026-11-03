"""Measured Panda POE transforms for private whole-arm/table screening."""
import math
import numpy as np


def link_joint_count(name):
    suffix=name.removeprefix('panda_link')
    return min(7,int(suffix))if suffix.isdigit()else 7


def prefix_transforms(measured,joints):
    from .execution_design_drawer_ik_probe import skew
    p=np.asarray(measured['position'],float);J=np.asarray(measured['jacobian'],float)
    q=np.asarray(measured['q'],float);delta=np.asarray(joints,float)-q
    if p.shape!=(3,)or J.shape!=(6,7)or q.shape!=(7,)or delta.shape!=(7,):
        raise ValueError('Complete native Panda TCP/J/q required')
    if not np.isfinite(np.r_[p,J.ravel(),q,delta]).all():raise ValueError('Finite native POE reference required')
    transforms=[np.eye(4)];T=np.eye(4)
    for j,angle in enumerate(delta):
        axis=J[3:,j];axis=axis/np.linalg.norm(axis);pivot=p+np.cross(axis,J[:3,j]);K=skew(axis)
        R=np.eye(3)+math.sin(angle)*K+(1-math.cos(angle))*K@K
        A=np.eye(4);A[:3,:3]=R;A[:3,3]=pivot-R@pivot;T=T@A;transforms.append(T.copy())
    return transforms


def transformed_meshes(measured,meshes,joints):
    frames=prefix_transforms(measured,joints);result={}
    for name,points in meshes.items():
        T=frames[link_joint_count(name)];result[name]=np.asarray(points,float)@T[:3,:3].T+T[:3,3]
    return result


def capture_native_meshes(a,side):
    from scipy.spatial import ConvexHull
    from .execution_design_e33_grasp import actual_mesh
    from pxr import Usd,UsdPhysics
    import omni.usd
    meshes={};omitted=[];stage=omni.usd.get_context().get_stage()
    for name in a.scene.robots[side].body_names:
        try:points=actual_mesh(a,side,name)
        except ValueError:
            root=stage.GetPrimAtPath(f'{a.scene.root_path}/{side}_robot/{name}')
            if any(p.HasAPI(UsdPhysics.CollisionAPI)and UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get()is not False
                   for p in Usd.PrimRange(root,Usd.TraverseInstanceProxies())):
                raise RuntimeError('Native collision body mesh coverage missing: '+name)
            omitted.append(name);continue
        # A linear table-plane minimum is identical on these convex vertices.
        meshes[name]=np.asarray(points)[ConvexHull(points,qhull_options='QJ').vertices]
    if 'panda_link6'not in meshes or'panda_hand'not in meshes:raise RuntimeError('Critical native arm geometry required')
    return meshes,omitted


class LiveTableGuard:
    def __init__(self,a,side,meshes,floor):
        from scipy.spatial.transform import Rotation
        self.a=a;self.side=side;self.floor=float(floor);self.names=list(meshes);self.indices=[];self.local=[]
        robot=a.scene.robots[side];layout=a.scene.layout
        for name,points in meshes.items():
            index=list(robot.body_names).index(name);self.indices.append(index)
            quat=robot.data.body_quat_w[0,index].detach().cpu().numpy();R=layout.task_rotation.T@Rotation.from_quat(quat[[1,2,3,0]]).as_matrix()
            pos=a.scene.world_to_task(robot.data.body_pos_w[0,index].detach().cpu().numpy())
            self.local.append((points-pos)@R)
        self.initial=self.values();self.initial_min=min(self.initial.values());self.cleared=False
    def values(self):
        from scipy.spatial.transform import Rotation
        robot=self.a.scene.robots[self.side];layout=self.a.scene.layout
        q=robot.data.body_quat_w[0,self.indices].detach().cpu().numpy();p=robot.data.body_pos_w[0,self.indices].detach().cpu().numpy()
        rotations=Rotation.from_quat(q[:,[1,2,3,0]]).as_matrix();result={}
        for name,points,R,world_pos in zip(self.names,self.local,rotations,p):
            taskR=layout.task_rotation.T@R;position=self.a.scene.world_to_task(world_pos)
            result[name]=float((points@taskR.T+position)[:,2].min())
        return result
    def check(self):
        values=self.values();lowest=min(values.values())
        if lowest>self.floor+.003:self.cleared=True
        lower=self.floor+.001 if self.cleared else min(self.initial_min-.0003,self.floor-.0003)
        if lowest<lower:raise RuntimeError('Actual whole right arm lost table clearance: '+str(values))
        return values
