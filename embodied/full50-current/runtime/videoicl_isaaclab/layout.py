"""RoboDojo's standard dual-X5 rig, in its original world coordinates.

Task recipes/scoring retain their audited coordinate frame. The entire task
is rigidly placed in the reference rig: +X forward -> world +Y, +Y left ->
world -X; recipe table z=.8 -> reference table z=.765. No task is rescaled.
Sources: env_cfg/{robot/dual_x5,camera/camera_config,scene/default}.yml,
env_cfg/camera/template.py, env/robot_manager/robot_config/x5.py.
"""
import math
import numpy as np


def rotation_matrix(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def multiply_quaternions(a,b):
    w,x,y,z=a;v,i,j,k=b
    return (w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v)


class Layout:
    def __init__(self,config):
        self.config=config;self.name=config['id']
        self.task_quat=tuple(config['task_rotation'])
        self.task_rotation=rotation_matrix(self.task_quat)
        self.task_translation=np.asarray(config['task_translation'])

    def task_to_world(self,position):return np.asarray(position)@self.task_rotation.T+self.task_translation
    def world_to_task(self,position):return (np.asarray(position)-self.task_translation)@self.task_rotation
    def world_quaternion(self,quaternion):return multiply_quaternions(self.task_quat,quaternion)

    def validate(self):
        if not np.allclose(self.task_rotation.T@self.task_rotation,np.eye(3),atol=1e-6):raise ValueError('Invalid task rotation')
        table=self.config['table']
        if not np.isclose(table['position'][2]+table['size'][2]/2,table['top']):raise ValueError('Table collider and declared top differ')
        if not np.isclose(self.task_to_world([0,0,.8])[2],table['top']):raise ValueError('Task and table heights differ')

LAYOUT_PROFILE = 'robodojo-standard-dual-x5-v1'
TASK_ROTATION = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
TASK_TRANSLATION = np.array([0., 0., -.035])
TASK_QUAT = (math.sqrt(.5), 0., 0., math.sqrt(.5))
TABLE_POSITION = (0., -.05, .74)
TABLE_SIZE = (1.4, 1.1, .05)
ROBOT_POSITIONS = {'left': (-.3, -.45, .765), 'right': (.3, -.45, .765)}
ROBOT_ROTATION = TASK_QUAT  # normalized source [0.707, 0, 0, 0.707]
HEAD_POSITION = (0., -.41, 1.308)
HEAD_ROTATION = (math.cos(math.pi/12), math.sin(math.pi/12), 0., 0.)
HEAD_INTRINSICS = dict(focal_length=10., horizontal_aperture=22.212,
                       vertical_aperture=14.266, clipping_range=(.005, 10.))


def task_to_world(position):
    return np.asarray(position) @ TASK_ROTATION.T + TASK_TRANSLATION


def world_to_task(position):
    return (np.asarray(position)-TASK_TRANSLATION) @ TASK_ROTATION


def world_quaternion(quaternion):
    w, x, y, z = quaternion
    s = math.sqrt(.5)
    return (s*(w-z), s*(x-y), s*(x+y), s*(w+z))
