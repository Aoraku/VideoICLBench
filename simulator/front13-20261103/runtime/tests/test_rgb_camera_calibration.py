"""Run the production camera calibration method without importing Isaac."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parents[1]/'videoicl_isaaclab'


def test_pose_update_enabled_when_dataclass_default_is_not_a_class_attribute():
    from dataclasses import dataclass, field
    @dataclass
    class CameraCfg:
        update_latest_camera_pose: bool = field(default_factory=lambda: False)
    # Isaac configclass uses default factories, which remove class attributes.
    assert not hasattr(CameraCfg,'update_latest_camera_pose')
    tree=ast.parse((ROOT/'scene.py').read_text())
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='camera_pose_kwargs' for t in n.targets))
    namespace={'CameraCfg':CameraCfg}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[assignment],type_ignores=[])),
                 'production_camera_cfg','exec'),namespace)
    assert CameraCfg(**namespace['camera_pose_kwargs']).update_latest_camera_pose is True


class Tensor:
    def __init__(self,value):self.value=np.asarray(value)
    def __getitem__(self,key):return Tensor(self.value[key])
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.value
    def tolist(self):return self.value.tolist()


def test_pool_origin_removed_once_and_task_rotation_preserved():
    spec=importlib.util.spec_from_file_location('calibration_test_layout',ROOT/'layout.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    tree=ast.parse((ROOT/'scene.py').read_text())
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='rgb_camera_calibration')
    method.body=[n for n in method.body if not isinstance(n,ast.ImportFrom)]
    code=ast.Module(body=[method],type_ignores=[])
    namespace={'np':np,'rotation_matrix':module.rotation_matrix}
    exec(compile(ast.fix_missing_locations(code),'production_scene_calibration','exec'),namespace)
    theta=.7;q=[np.cos(theta/2),0,0,np.sin(theta/2)]
    outputs=[]
    for origin in ([0,0,0],[18,12,3]):
        layout=module.Layout(dict(id='test',task_rotation=q,task_translation=[.2,-.4,.1]))
        layout.task_translation+=origin
        known_local=np.array([.3,.2,1.1]);world=layout.task_to_world(known_local)
        data=SimpleNamespace(pos_w=Tensor([world]),quat_w_opengl=Tensor([q]),
            intrinsic_matrices=Tensor([[[100,0,80],[0,100,60],[0,0,1]]]),output={'rgb':np.zeros((1,120,160,3))})
        scene=SimpleNamespace(layout=layout,origin=np.array(origin),world_to_task=layout.world_to_task,cameras={'head':SimpleNamespace(data=data)})
        result=namespace['rgb_camera_calibration'](scene,'head')
        transform=np.array(result['T_task_from_camera'])
        assert np.allclose(transform[:3,3],known_local)
        assert np.allclose(transform[:3,:3],np.eye(3))
        assert (result['width'],result['height'])==(160,120)
        optical=np.diag([1.,-1.,-1.,1.])
        assert np.allclose(result['T_task_from_camera_optical'], transform @ optical)
        assert np.allclose(np.array(result['T_world_from_task']) @ np.array(result['T_task_from_camera_optical']),
                           result['T_world_from_camera_optical'])
        outputs.append(transform)
    assert np.allclose(*outputs)
    data.pos_w=Tensor([[float('nan'),0,0]])
    result=namespace['rgb_camera_calibration'](scene,'head')
    assert result==dict(available=False,reason='camera_calibration_not_ready',invalid_fields=['pos_w'])
    import json
    json.dumps(result,allow_nan=False)
