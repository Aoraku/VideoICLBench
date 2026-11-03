from types import SimpleNamespace,ModuleType
import sys
import numpy as np
import pytest
from videoicl_isaaclab.author_mplib_planner import (
    _native_scene_paths,_native_shape_group,_native_robot_link,
    capture_scene,validate_scene,NATIVE_USD_SHA256)


@pytest.mark.parametrize('root,rig',[
    ('/World','/World'),
    ('/World/Rooms/room_00','/World/Rooms/room_00/Rig'),
])
def test_actual_scene_namespace_preserves_exact_actor_and_robot_labels(root,rig):
    paths=_native_scene_paths(SimpleNamespace(root_path=root,rig_root=rig))
    assert paths['table']==rig+'/Table'
    assert _native_shape_group(root+'/Props/driver/collision',None,paths,'left')==('driver','prop')
    assert _native_shape_group(root+'/Mechanisms/socket/link/collision',None,paths,'left')==('socket/link','mechanism')
    owner=root+'/left_robot/panda_hand'
    assert _native_shape_group(owner+'/collision',owner,paths,'left')==(owner,'active_robot')
    owner=root+'/right_robot/panda_hand'
    assert _native_shape_group(owner+'/collision',owner,paths,'left')==(owner,'other_robot')


def measured_world():
    root='/World/Rooms/room_00';table=root+'/Rig/Table'
    shapes=[dict(source_prim=table,group='static',actor=table)]
    shapes+=[dict(source_prim=root+'/right_robot/link'+str(i)+'/collision',
                  group='other_robot',actor='right'+str(i))for i in range(11)]
    shapes+=[dict(source_prim=root+'/Props/driver/collision',group='prop',actor='driver')]
    return dict(schema='author-mplib-scene-v1',dt=.004,task='E37',side='left',
        native_robot_usd_sha256=NATIVE_USD_SHA256,missing_geometry=[],
        robots=dict(left={},right={}),shapes=shapes,native_table_prim_path=table,
        active_collision_prims=list(range(11)),enabled_collision_prim_count=24,
        object_ids=['driver'],attached_actors=['driver'],native_grasp={'driver':True},
        allowed_contact_pairs=[]),dict(expected_active_collision_prims=11)


def test_room_table_and_both_complete_native_arms_keep_all_coverage_gates():
    snapshot,profile=measured_world()
    assert validate_scene(snapshot,profile)
    snapshot['missing_geometry']=[dict(path='/OtherRoom/Props/body',reason='No measured rigid-body pose')]
    with pytest.raises(ValueError,match='coverage incomplete'):validate_scene(snapshot,profile)


@pytest.mark.parametrize('fault,message',[
    ('table','table missing'),('peer','arm chain incomplete'),('count','cardinality mismatch'),
    ('grasp','two-finger grasp'),
])
def test_namespace_support_never_waives_missing_table_peer_shape_or_grasp(fault,message):
    snapshot,profile=measured_world()
    if fault=='table':snapshot['native_table_prim_path']='/World/Table'
    elif fault=='peer':snapshot['shapes'][1]['group']='static'
    elif fault=='count':snapshot['enabled_collision_prim_count']+=1
    else:snapshot['native_grasp']['driver']=False
    with pytest.raises(ValueError,match=message):validate_scene(snapshot,profile)


@pytest.mark.parametrize('root', ['/World','/World/Rooms/room_00'])
def test_full_capture_keeps_physx_object_witness_and_all_native_geometry(monkeypatch,root):
    """Exercise the whole reader, including the former prim_paths shadow bug."""
    from itertools import product
    from videoicl_isaaclab import author_mplib_planner as module
    class Collision:pass
    class Rigid:pass
    class Mesh:
        def __init__(self,prim):self.prim=prim
        def GetPointsAttr(self):return SimpleNamespace(Get=lambda:np.array(list(product((-.01,.01),repeat=3))))
    prims={}
    class Prim:
        def __init__(self,path,collision=False,rigid=False):
            self.path=path;self.collision=collision;self.rigid=rigid
        def HasAPI(self,api):return self.collision if api is Collision else self.rigid if api is Rigid else False
        def IsA(self,kind):return kind is Mesh and self.collision
        def GetPath(self):return self.path
        def GetTypeName(self):return 'Mesh'if self.collision else'Xform'
        def IsPseudoRoot(self):return self.path=='/'
        def GetParent(self):return get(self.path.rsplit('/',1)[0]or'/')
        def __bool__(self):return True
    def get(path):
        if path not in prims:prims[path]=Prim(path)
        return prims[path]
    def collision(path):prims[path]=Prim(path,collision=True)
    def rigid(path):prims[path]=Prim(path,rigid=True)
    rig=root if root=='/World'else root+'/Rig';collision(rig+'/Table')
    names=['panda_link'+str(i)for i in range(8)]+['panda_hand','panda_leftfinger','panda_rightfinger']
    for side in ('left','right'):
        for name in names:
            path=root+'/'+side+'_robot/'+name;rigid(path);collision(path+'/collision')
    actor=root+'/Props/driver';rigid(actor);collision(actor+'/collision')
    stage=SimpleNamespace(GetPseudoRoot=lambda:get('/'),GetPrimAtPath=get)
    context=SimpleNamespace(get_stage=lambda:stage,get_stage_id=lambda:17)
    Collision.__init__=lambda self,prim:None
    Collision.GetCollisionEnabledAttr=lambda self:SimpleNamespace(Get=lambda:True)
    Rigid.__init__=lambda self,prim:None
    Rigid.GetRigidBodyEnabledAttr=lambda self:SimpleNamespace(Get=lambda:True)
    usd=SimpleNamespace(PrimRange=lambda *args:[p for p in prims.values()if p.collision],TraverseInstanceProxies=lambda:None)
    geom=SimpleNamespace(Mesh=Mesh,XformCache=lambda:SimpleNamespace(GetLocalToWorldTransform=lambda prim:np.eye(4)))
    pxr=ModuleType('pxr');pxr.Usd=usd;pxr.UsdGeom=geom;pxr.UsdPhysics=SimpleNamespace(CollisionAPI=Collision,RigidBodyAPI=Rigid)
    omni=ModuleType('omni');omni.__path__=[];omni_usd=ModuleType('omni.usd');omni_usd.get_context=lambda:context;omni.usd=omni_usd
    monkeypatch.setitem(sys.modules,'pxr',pxr);monkeypatch.setitem(sys.modules,'omni',omni);monkeypatch.setitem(sys.modules,'omni.usd',omni_usd)
    quaternion=np.array([[1.,0.,0.,0.]])
    data=SimpleNamespace(body_pos_w=np.zeros((1,11,3)),body_quat_w=np.tile(quaternion,(1,11,1)),joint_pos=np.zeros((1,9)),joint_vel=np.zeros((1,9)),root_pos_w=np.zeros((1,3)),root_quat_w=quaternion)
    robots={side:SimpleNamespace(body_names=names,joint_names=['q'+str(i)for i in range(9)],data=data)for side in ('left','right')}
    view=SimpleNamespace(prim_paths=[actor],count=1,get_transforms=lambda:np.array([[0,0,0,0,0,0,1.]]),get_masses=lambda:np.array([.2]))
    obj=SimpleNamespace(data=SimpleNamespace(root_pos_w=np.zeros((1,3)),root_quat_w=quaternion,root_vel_w=np.zeros((1,6))),root_physx_view=view)
    scene=SimpleNamespace(root_path=root,rig_root=rig,robots=robots,objects={'driver':obj},mechanisms={},spec=dict(id='E37',variant='A',objects=[dict(id='driver')]),embodiment=SimpleNamespace(config={},asset_path=lambda:'native.usd',tcp=[0,0,.1034]))
    c=SimpleNamespace(ids={s:([0,1,2,3,4,5,6],[7,8],8)for s in robots},pose=lambda side:(np.zeros((1,3)),quaternion),snapshot=lambda:({'driver':{'grasp':[True,False]}},set()),physics_ticks=16640,dt=.004,contact_forces={})
    monkeypatch.setattr(module,'_target',lambda *args:(np.eye(4),[]));monkeypatch.setattr(module,'_sha',lambda path:NATIVE_USD_SHA256)
    monkeypatch.setattr(module,'_list',lambda value:np.asarray(value).tolist())
    result=capture_scene(scene,c,'left',[0,0,1.])
    assert result['missing_geometry']==[]
    assert result['native_rigid_body_witnesses']['driver']['native_root_path']==actor
    assert len(result['active_native_geometry'])==11 and len(result['shapes'])==13
    assert result['enabled_collision_prim_count']==24
    assert _native_robot_link(result,root+'/left_robot/panda_hand/collision')=='panda_hand'
    with pytest.raises(ValueError,match='outside'):_native_robot_link(result,root+'/right_robot/panda_hand/collision')
    assert validate_scene(result,dict(expected_active_collision_prims=11))
