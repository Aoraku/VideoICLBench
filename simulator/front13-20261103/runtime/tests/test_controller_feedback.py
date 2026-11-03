"""Robot-only feedback frame conversion without an Isaac process."""
import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from videoicl_isaaclab.layout import rotation_matrix


class Tensor:
    def __init__(self, data):self.array = np.asarray(data)
    def __getitem__(self, index):return Tensor(self.array[index])
    def cpu(self):return self
    def detach(self):return self
    def numpy(self):return self.array
    def tolist(self):return self.array.tolist()


def test_feedback_removes_room_origin_and_robot_base_rotation():
    source = Path(__file__).resolve().parents[1] / 'videoicl_isaaclab/control.py'
    cls = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'Controller')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'public_feedback')
    namespace = {'__package__': 'videoicl_isaaclab'}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
    q = np.asarray([2. ** -.5, 0., 0., 2. ** -.5])
    rotation = rotation_matrix(q)
    for origin in [np.asarray([0., 0., 0.]), np.asarray([8., 16., 0.])]:
        robot = SimpleNamespace(data=SimpleNamespace(root_pos_w=Tensor([origin]),
            root_quat_w=Tensor([q]), joint_pos=Tensor([[.5, -.5, .01, .01]])))
        scene = SimpleNamespace(robots={'left': robot}, layout=SimpleNamespace(task_quat=q),
            world_to_task=lambda position, origin=origin: (position - origin) @ rotation,
            embodiment=SimpleNamespace(arm_joints=['arm_1', 'arm_2'],
                config={'gripper': {'open': [.04, .04], 'closed': [0., 0.]}}))
        controller = SimpleNamespace(scene=scene, ids={'left': ([0, 1], [2, 3], 0)},
            pose=lambda side: (Tensor([[1., 0., 2.]]), Tensor([[1., 0., 0., 0.]])))
        result = namespace['public_feedback'](controller)
        left = result['arms']['left']
        np.testing.assert_allclose(left['tcp_position'], [1., 0., 2.], atol=1e-12)
        np.testing.assert_allclose(left['tcp_quaternion_wxyz'], [1., 0., 0., 0.], atol=1e-12)
        assert left['joint_positions_rad'] == [.5, -.5]
        assert left['gripper_open_fraction'] == .25
        assert set(result) == {'coordinate_frame', 'units', 'arms'}
        assert set(left) == {'tcp_position', 'tcp_quaternion_wxyz', 'joint_names', 'joint_positions_rad', 'gripper_open_fraction',
            'tcp_position_world_m', 'tcp_quaternion_world_wxyz', 'finger_joint_positions',
            'finger_joint_position_units', 'holding_status', 'contact_status', 'measured_sensors'}
        assert left['holding_status'] == left['contact_status'] == 'not_measured'
        assert left['finger_joint_positions'] == [.01, .01]
        assert all(x['available'] is False for x in left['measured_sensors'].values())
        robot.data.joint_vel=Tensor([[.1,.2,.003,.004]])
        robot.data.soft_joint_pos_limits=Tensor([[[-1,1],[-2,2],[0,.04],[0,.04]]])
        robot.data.body_vel_w=Tensor([[[1.,2.,3.,0.,0.,1.]]])
        tcp=np.asarray(left['tcp_position_world_m'])
        robot.data.body_pos_w=Tensor([[tcp - [.1,0,0]]])
        scene.layout.task_rotation=rotation
        updated=namespace['public_feedback'](controller)['arms']['left']['measured_sensors']
        np.testing.assert_allclose(updated['tcp_linear_velocity_task_m_s']['value'], rotation.T @ [1,2.1,3])
        assert updated['joint_velocities_rad_s']['value']==[.1,.2]
        assert updated['joint_soft_limits_rad']['value']==[[-1,1],[-2,2]]
        assert updated['finger_joint_velocities_m_s']['value']==[.003,.004]
