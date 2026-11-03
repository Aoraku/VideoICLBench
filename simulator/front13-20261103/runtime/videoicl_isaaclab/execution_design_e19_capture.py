"""Read-only per-physics-tick E19C cap-release diagnostics."""
from .execution_design import REVISION_V3


class CapReleaseCapture:
    def __init__(self,controller):
        self.c=controller;self.indices={}
        for side,robot in controller.scene.robots.items():
            joints,names=robot.find_joints('panda_joint[1-7]')
            fingers,fnames=robot.find_joints('panda_finger_joint[1-2]')
            bodies={name:robot.find_bodies(name)[0][0]for name in controller.scene.embodiment.fingers}
            if len(joints)!=7 or len(fingers)!=2 or len(bodies)!=2:
                raise ValueError('E19C diagnostics require actual Panda arm and fingers')
            self.indices[side]=(joints,list(names),fingers,list(fnames),bodies)

    def sample(self,tick,state,contacts):
        robots={}
        for side,robot in self.c.scene.robots.items():
            joints,names,fingers,fnames,bodies=self.indices[side];data=robot.data
            robots[side]=dict(arm_joint_names=names,arm_q_rad=data.joint_pos[0,joints],
                arm_qd_rad_s=data.joint_vel[0,joints],finger_joint_names=fnames,
                finger_q_m=data.joint_pos[0,fingers],finger_qd_m_s=data.joint_vel[0,fingers],
                actual_finger_bodies={name:dict(position_world_m=data.body_pos_w[0,bid],
                    quaternion_world_wxyz=data.body_quat_w[0,bid])for name,bid in bodies.items()})
        return dict(tick=tick,native_physics_tick=self.c.physics_ticks,actions=self.c.steps,
            source='actual_native_tensor_and_contact_sensor_readback_per_physics_tick',
            state={name:state[name]for name in ('cap_red','water_bottle')},
            contacts=sorted(sorted(pair)for pair in contacts),
            contact_forces_n=[dict(bodies=sorted(pair),force_n=float(force))
                for pair,force in self.c.contact_forces.items()],robots=robots)


def capture_for(controller):
    spec=controller.scene.spec
    if (spec.get('id')=='E19'and spec.get('variant')=='C'
            and spec.get('execution_design',{}).get('revision')==REVISION_V3):
        return CapReleaseCapture(controller)
    return None
