"""Per-arm sensor poses preserve old profiles and reach the native render update."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from videoicl_isaaclab.embodiments import load_profile

def profile(tmp_path,overrides=None):
    c=json.loads((ROOT/'configs/franka-wrist-taskview-v2.json').read_text())
    if overrides is not None:c['cameras']['wrist_by_arm']=overrides
    p=tmp_path/'profile.json';p.write_text(json.dumps(c));return load_profile(p)

def test_old_profiles_keep_exact_shared_pose(tmp_path):
    p=profile(tmp_path)
    for side in ('left','right'):
        assert p.wrist_camera_pose(side)==dict(position=p.camera_position,rotation=p.camera_rotation,convention=p.camera_convention)

@pytest.mark.parametrize('overrides',[
    {'other':{}}, {'left':{'intrinsics':{}}}, {'left':{'link':'palm'}},
    {'left':{'position':[0,0]}}, {'left':{'position':[0,float('nan'),0]}},
    {'left':{'rotation':[0,0,0,0]}}, {'right':{'convention':'wrong'}}, []])
def test_invalid_arm_overrides_rejected_before_native_boot(tmp_path,overrides):
    with pytest.raises(ValueError):profile(tmp_path,overrides)

def test_sync_uses_each_arm_pose_and_falls_back_on_other_arm(tmp_path):
    p=profile(tmp_path,{'left':{'position':[.1,.2,.3],'rotation':[1,0,0,0],'convention':'ros'}})
    tree=ast.parse((ROOT/'videoicl_isaaclab/scene.py').read_text())
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='sync_wrist_cameras')
    calls=[]
    def combine(base_pos,base_quat,offset_pos,offset_quat):
        calls.append((offset_pos,offset_quat));return base_pos+offset_pos,offset_quat
    ns=dict(torch=SimpleNamespace(tensor=lambda x,**kw:np.asarray(x),float32=np.float32),combine_frame_transforms=combine)
    exec(compile(ast.Module(body=[method],type_ignores=[]),'production_sync','exec'),ns)
    captured={}
    class Camera:
        def __init__(self,name):self.name=name
        def set_world_poses(self,pos,quat,convention):captured[self.name]=(pos,quat,convention)
    def robot(x):
        return SimpleNamespace(find_bodies=lambda name:([0],None),device='cpu',
            data=SimpleNamespace(body_pos_w=np.asarray([[[x,0,0]]]),body_quat_w=np.asarray([[[1,0,0,0]]])))
    scene=SimpleNamespace(embodiment=p,robots={'left':robot(1),'right':robot(2)},
        cameras={'left_wrist':Camera('left'),'right_wrist':Camera('right')})
    ns['sync_wrist_cameras'](scene)
    assert np.allclose(captured['left'][0],[[1.1,.2,.3]])
    assert captured['left'][2]=='ros'
    assert np.allclose(calls[1][0],[p.camera_position])
    assert np.allclose(captured['right'][1],[p.camera_rotation])
    assert captured['right'][2]==p.camera_convention
