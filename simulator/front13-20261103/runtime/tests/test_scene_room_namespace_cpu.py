"""Exercise production room placement without importing Isaac Sim.

Native collision/render correctness remains the GPU probe's responsibility.
"""
import ast
from copy import deepcopy
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]/'videoicl_isaaclab'


class Config(SimpleNamespace):
    InitialStateCfg=SimpleNamespace
    OffsetCfg=SimpleNamespace


class FakeCamera:
    def __init__(self,cfg):self.cfg=cfg
    def set_world_poses(self,positions,orientations,**kwargs):self.positions=positions
    def set_world_poses_from_view(self,positions,targets):self.positions=positions;self.targets=targets


def actual_scene():
    layout_spec=importlib.util.spec_from_file_location('room_test_layout',ROOT/'layout.py')
    layout=importlib.util.module_from_spec(layout_spec);layout_spec.loader.exec_module(layout)
    paths=[];transforms={};rigs=[]
    stage=SimpleNamespace(GetPrimAtPath=lambda path:path)
    class Xform:
        @staticmethod
        def Define(stage,path):
            paths.append(path)
            return SimpleNamespace(GetPrim=lambda:path)
    class PrimPath(str):
        def IsAbsolutePath(self):return self.startswith('/')
        def IsPrimPath(self):return bool(self.strip('/')) and '.' not in self
    profile=SimpleNamespace(name='test',config_hash='hash',fingers=['finger1','finger2'],config={
        'layout':{'id':'layout','task_rotation':[1,0,0,0],'task_translation':[0,0,-.035]},
        'cameras':{'profile':'test','head':{'width':32,'height':24,'position':[0,-.4,1.3],
            'rotation':[1,0,0,0],'convention':'opengl','intrinsics':{'clipping_range':[.01,10]}},
            'wrist':{'width':16,'height':12,'intrinsics':{'clipping_range':[.01,10]}}}})
    def articulation(profile,side):
        return Config(init_state=Config(pos=(-.3 if side=='left' else .3,-.45,.765)))
    def asset(cfg):paths.append(cfg.prim_path);return Config(cfg=cfg)
    def camera(cfg):paths.append(cfg.prim_path);return FakeCamera(cfg)
    namespace=dict(deepcopy=deepcopy,np=np,math=math,os=SimpleNamespace(environ={}),Sdf=SimpleNamespace(Path=PrimPath),
        Layout=layout.Layout,select=lambda *args:profile,articulation=articulation,
        omni=SimpleNamespace(usd=SimpleNamespace(get_context=lambda:SimpleNamespace(get_stage=lambda:stage))),
        UsdGeom=SimpleNamespace(Xform=Xform),
        transform=lambda prim,position,*args:transforms.__setitem__(prim,np.asarray(position)),
        spawn_reference_rig=lambda *args,**kwargs:rigs.append(kwargs['root_path']),
        material=lambda stage,path,*args:paths.append(path),
        geometry=lambda stage,path,*args:paths.append(path),
        style=SimpleNamespace(FRAME=(0,0,0),PAD=(0,0,0),MARKER=(0,0,0)),
        Articulation=asset,RigidObject=asset,RigidObjectCfg=Config,PropCfg=Config,
        Camera=camera,CameraCfg=Config,ContactSensor=asset,ContactSensorCfg=Config,
        sim=SimpleNamespace(PinholeCameraCfg=Config),
        torch=SimpleNamespace(tensor=lambda value,**kwargs:np.asarray(value)))
    tree=ast.parse((ROOT/'scene.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TabletopScene')
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(ROOT/'scene.py'),'exec'),namespace)
    return namespace['TabletopScene'],paths,transforms,rigs


def recipe():
    return {'id':'E01','zones':[],'fixtures':[],
        'objects':[{'id':'block','xy':[.1,.2],'size':[.02,.03,.04],'yaw':0,'kind':'block'}]}


def test_two_room_namespaces_and_world_poses_stay_separate():
    Scene,paths,transforms,rigs=actual_scene()
    a=Scene(recipe(),root_path='/World/Rooms/a',origin=(0,0,0))
    b=Scene(recipe(),root_path='/World/Rooms/b',origin=(8,0,0))
    a.initialize_cameras('cpu');b.initialize_cameras('cpu')
    assert all(path.startswith(('/World/Rooms/a/','/World/Rooms/b/')) or path in
        ('/World/Rooms/a','/World/Rooms/b') for path in paths)
    assert rigs==['/World/Rooms/a/Rig','/World/Rooms/b/Rig']
    assert np.allclose(transforms['/World/Rooms/b/Rig'],[8,0,0])
    assert np.allclose(b.robots['left'].cfg.init_state.pos, [7.7,-.45,.765])
    assert np.allclose(np.asarray(b.objects['block'].cfg.init_state.pos)-a.objects['block'].cfg.init_state.pos,[8,0,0])
    assert np.allclose(b.world_to_task(b.objects['block'].cfg.init_state.pos),[.1,.2,.845])
    for name in ('head','overview'):
        assert np.allclose(b.cameras[name].positions-a.cameras[name].positions,[[8,0,0]])
    for scene in (a,b):
        sensor,_=scene.contacts['block']
        assert sensor.cfg.filter_prim_paths_expr[0]==scene.rig_root+'/Table'
        assert all(path.startswith(scene.root_path+'/') for path in sensor.cfg.filter_prim_paths_expr)


def test_default_scene_keeps_legacy_paths_and_positions():
    Scene,paths,transforms,rigs=actual_scene()
    scene=Scene(recipe());scene.initialize_cameras('cpu')
    assert rigs==['/World']
    assert scene.objects['block'].cfg.prim_path=='/World/Props/block'
    assert scene.robots['left'].cfg.prim_path=='/World/left_robot'
    assert scene.robots['left'].cfg.init_state.pos==(-.3,-.45,.765)
    assert np.allclose(scene.cameras['head'].positions,[[0,-.4,1.3]])
    assert '/World/Rig' not in paths


@pytest.mark.parametrize('origin',[(0,0),[0,float('nan'),0],[0,float('inf'),0]])
def test_invalid_origins_reject_before_scene_spawns(origin):
    Scene,paths,_,_=actual_scene()
    with pytest.raises(ValueError):Scene(recipe(),root_path='/World/Rooms/a',origin=origin)
    assert not paths
