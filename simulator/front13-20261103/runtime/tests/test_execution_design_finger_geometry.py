"""Actual mesh and body-frame math using synthetic transforms, not physics acceptance."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

from videoicl_isaaclab.execution_design_probe import engineering_robot_diagnostics,pooled_author_class

class Tensor(np.ndarray):
    def cpu(self):return self
    def numpy(self):return np.asarray(self)
    def detach(self):return self

class Matrix:
    def __init__(self,x):self.x=np.asarray(x)
    def GetInverse(self):return Matrix(np.linalg.inv(self.x))
    def __mul__(self,other):return Matrix(self.x@other.x)
    def __array__(self,dtype=None,copy=None):return np.asarray(self.x,dtype=dtype)

def methods(rotation):
    path=Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py';tree=ast.parse(path.read_text())
    cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Demonstration')
    funcs=[x for x in cls.body if isinstance(x,ast.FunctionDef)and x.name in ('finger_geometry','floor_clear_tcp')]
    scope=dict(np=np,matrix_from_quat=lambda q:np.asarray([rotation]).view(Tensor))
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(path),'exec'),scope)
    return type('Author',(),{k:scope[k]for k in ('finger_geometry','floor_clear_tcp')})

@pytest.mark.parametrize('root',['/World','/World/Rooms/room_09'])
def test_namespaced_rotated_mesh_uses_actual_body_pose_and_room_frame(root,monkeypatch):
    rotation=np.array([[0.,0.,1.],[0.,1.,0.],[-1.,0.,0.]])
    task_rotation=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    room_origin=np.array([12.,-6.,0.]);calls=[]
    points=np.array([[0.,0.,0.],[.01,.02,.03],[-.02,.01,-.01]])
    local=np.eye(4);local[:3,:3]=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    local[3,:3]=[.005,.006,.007]
    bodyworld=np.eye(4);bodyworld[3,:3]=room_origin+[.3,.2,1.]
    class Prim:
        def __init__(self,kind,parent=None):self.kind=kind;self.parent=parent
        def HasAPI(self,api):return self.kind=='collision'
        def GetParent(self):return self.parent
        def IsA(self,cls):return self.kind=='mesh'
    body=Prim('body');collision=Prim('collision',body);mesh=Prim('mesh',collision)
    class Mesh:
        def __init__(self,prim):assert prim is mesh
        def GetPointsAttr(self):return SimpleNamespace(Get=lambda:points)
    cache=SimpleNamespace(GetLocalToWorldTransform=lambda prim:Matrix(bodyworld if prim is body else local@bodyworld))
    def lookup(path):calls.append(path);assert path.startswith(root+'/right_robot/');return body
    usd=SimpleNamespace(get_context=lambda:SimpleNamespace(get_stage=lambda:SimpleNamespace(GetPrimAtPath=lookup)))
    monkeypatch.setitem(sys.modules,'omni',SimpleNamespace(usd=usd));monkeypatch.setitem(sys.modules,'omni.usd',usd)
    monkeypatch.setitem(sys.modules,'pxr',SimpleNamespace(Usd=SimpleNamespace(PrimRange=lambda *a:[body,collision,mesh],TraverseInstanceProxies=lambda:None),UsdGeom=SimpleNamespace(XformCache=lambda:cache,Mesh=Mesh),UsdPhysics=SimpleNamespace(CollisionAPI=object())))
    pose=np.array([[[12.2,-5.7,.9],[12.2,-5.66,.9]]]).view(Tensor)
    robot=SimpleNamespace(find_bodies=lambda name:([['f1','f2'].index(name)],[]),data=SimpleNamespace(body_pos_w=pose,body_quat_w=np.zeros((1,2,4))))
    a=methods(rotation)();a.scene=SimpleNamespace(root_path=root,robots={'right':robot},embodiment=SimpleNamespace(fingers=['f1','f2']),layout=SimpleNamespace(task_rotation=task_rotation),world_to_task=lambda x:task_rotation.T@(x-room_origin));a.tip=lambda side:np.array([.1,.2,1.])
    got=a.finger_geometry('right');localpoints=points@local[:3,:3]+local[3,:3]
    expected=localpoints@(task_rotation.T@rotation).T+(task_rotation.T@(pose[0,0]-room_origin))
    np.testing.assert_allclose(got['fingers'][0]['aabb_min_task_m'],expected.min(0))
    np.testing.assert_allclose(got['fingers'][0]['aabb_max_task_m'],expected.max(0))
    np.testing.assert_allclose(got['fingers'][0]['lowest_point_task_m'],expected[np.argmin(expected[:,2])])
    assert calls==[root+'/right_robot/f1',root+'/right_robot/f2']
    assert a.floor_clear_tcp('right',.8)==pytest.approx(.8-got['lowest_z_task_m']+1.+.0003)
    # Cache is mesh-local only. Every read must observe changed actual poses.
    pose[:,:,2]+=.12;second=a.finger_geometry('right')
    assert second['lowest_z_task_m']==pytest.approx(got['lowest_z_task_m']+.12)
    assert len(calls)==2


def test_post_action_geometry_failure_does_not_undo_accepted_action(tmp_path):
    calls=[]
    def action_batch(x):calls.append(x);return {'r':dict(step_before=0,step_after=1)}
    a=pooled_author_class(type('Base',(),{}),SimpleNamespace(action_batch=action_batch),'r')()
    a.scene=SimpleNamespace(spec={},robots={},embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50.],'rotation_deg':[.5,20.]}}));a.c=SimpleNamespace(steps=0);a.stage='approach';a.out=tmp_path
    def fail(*a):raise RuntimeError('geometry missing')
    a.finger_geometry=fail;a.tip=fail
    assert a.act('UP')['step_after']==1 and len(calls)==1
    import json
    row=json.loads((tmp_path/'demo-actions.private.jsonl').read_bytes())
    assert 'geometry missing'in row['robot_diagnostics']['right']['diagnostic_error']['finger_geometry']
    assert row['diagnostic_error']['tips'].endswith('geometry missing')


def test_robot_diagnostics_follow_actual_arm_indices_and_joint_limits():
    robot=SimpleNamespace(joint_names=['finger','armB','armA'],data=SimpleNamespace(joint_pos=np.array([[.02,.3,-.2]]),joint_pos_limits=np.array([[[0,.04],[-1,1],[-2,2]]])))
    a=SimpleNamespace(scene=SimpleNamespace(robots={'right':robot}),c=SimpleNamespace(ids={'right':([2,1],[0],0)}),finger_geometry=lambda side:dict(source='actual'))
    d=engineering_robot_diagnostics(a)
    assert d['right']['arm_joints']==dict(names=['armA','armB'],positions_rad=[-.2,.3],limits_rad=[[-2,2],[-1,1]])
    assert 'diagnostic_error'in d['left']


def test_actual_grip_force_and_finger_measurements_are_logged_without_actuation():
    calls=[]
    robot=SimpleNamespace(joint_names=['f2','a','f1'],data=SimpleNamespace(
        joint_pos=np.array([[.018,.3,.021]]),joint_vel=np.array([[.002,0.,-.001]]),
        joint_pos_limits=np.array([[[0,.04],[-1,1],[0,.04]]])))
    def snapshot():
        calls.append('sensor_read')
        return {'phone':{'grasp':[True,False]}},set()
    c=SimpleNamespace(ids={s:([1],[2,0],0) for s in ('left','right')},snapshot=snapshot,
        contact_forces={frozenset(('phone','left_finger1')):2.4,
                        frozenset(('phone','left_finger2')):0.0})
    a=SimpleNamespace(scene=SimpleNamespace(robots={s:robot for s in ('left','right')}),
        c=c,finger_geometry=lambda side:dict(source='actual'))
    d=engineering_robot_diagnostics(a)
    assert calls==['sensor_read']
    assert d['left']['finger_joints']==dict(names=['f1','f2'],positions_m=[.021,.018],velocities_m_s=[-.001,.002])
    assert d['object_grasps']=={'phone':[True,False]}
    assert [r['force_n'] for r in d['contact_forces_n']]==[2.4,0.0]
    c.contact_forces={frozenset(('phone','table')):float('nan')}
    d=engineering_robot_diagnostics(a)
    assert 'contact_forces_n' not in d
    assert 'Invalid measured contact force' in d['contact_diagnostic_error']
