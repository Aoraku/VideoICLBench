"""Data-driven, versioned robot rigs. No task geometry belongs in this module."""
from dataclasses import dataclass
import hashlib,json,os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
CONFIG_ROOT=ROOT/'configs'
TASK_ROBOTS=json.loads((CONFIG_ROOT/'tasks.json').read_text())


@dataclass(frozen=True)
class Embodiment:
    config: dict
    path: Path
    config_hash: str

    @property
    def name(self):return self.config['name']
    @property
    def arm_joints(self):return list(self.config['kinematics']['arm_joints'])
    @property
    def finger_joints(self):return list(self.config['gripper']['joints'])
    @property
    def hand(self):return self.config['kinematics']['hand']
    @property
    def fingers(self):return tuple(self.config['kinematics']['contact_links'])
    @property
    def tcp(self):return tuple(self.config['kinematics']['tcp'])
    @property
    def camera_link(self):return self.config['cameras']['wrist']['link']
    @property
    def camera_position(self):return tuple(self.config['cameras']['wrist']['position'])
    @property
    def camera_rotation(self):return tuple(self.config['cameras']['wrist']['rotation'])
    @property
    def camera_convention(self):return self.config['cameras']['wrist']['convention']
    def wrist_camera_pose(self,side):
        """Optional arm-specific optical pose; shared lens/link settings remain unchanged."""
        if side not in ('left','right'):raise ValueError('Unknown wrist camera arm: '+str(side))
        common=self.config['cameras']['wrist']
        override=self.config['cameras'].get('wrist_by_arm',{}).get(side,{})
        return dict(position=tuple(override.get('position',common['position'])),
                    rotation=tuple(override.get('rotation',common['rotation'])),
                    convention=override.get('convention',common['convention']))
    @property
    def base_x(self):
        from .layout import Layout
        return float(Layout(self.config['layout']).world_to_task(self.config['robots']['left']['position'])[0])
    @property
    def base_y(self):
        from .layout import Layout
        return float(Layout(self.config['layout']).world_to_task(self.config['robots']['left']['position'])[1])

    def asset_path(self):
        asset=self.config['asset']
        path=os.environ.get(asset.get('env','')) or asset.get('path')
        if not path:raise ValueError('Set '+asset['env']+' to the native robot USD')
        resolved=Path(path).expanduser()
        if not resolved.is_absolute():resolved=ROOT/resolved
        if not resolved.is_file():raise FileNotFoundError('Missing robot asset '+str(resolved)+'; see scripts/convert_robotwin.py')
        return str(resolved.resolve())

    def gripper_values(self,opening):
        g=self.config['gripper']
        return [closed+(opened-closed)*opening for opened,closed in zip(g['open'],g['closed'])]


def load_profile(path):
    path=Path(path);raw=path.read_bytes();c=json.loads(raw)
    if c.get('schema_version')!=1:raise ValueError('Unsupported embodiment config version')
    for k in ('name','reference','asset','layout','robots','kinematics','gripper','actuators','cameras','physics','control'):
        if k not in c:raise ValueError('Missing embodiment section: '+k)
    if set(c['robots'])!={'left','right'}:raise ValueError('Expected exactly two named robot mounts')
    joints=c['kinematics']['arm_joints'];grip=c['gripper']
    if len(joints)!=len(set(joints)) or set(joints)&set(grip['joints']):raise ValueError('Overlapping/repeated actuator joints')
    if not len(grip['joints'])==len(grip['open'])==len(grip['closed']):raise ValueError('Invalid gripper transmission')
    if len(c['kinematics']['contact_links'])!=2:raise ValueError('Two real finger contact links are required')
    for side,mount in c['robots'].items():
        if not np.isclose(np.linalg.norm(mount['rotation']),1.,atol=1e-6):raise ValueError('Nonunit base quaternion')
        if set(mount['initial_joints'])!=set(joints+grip['joints']):raise ValueError('Incomplete initial joint state: '+side)
    for key in ('head','wrist'):
        camera=c['cameras'][key]
        if min(camera['width'],camera['height'])<=0:raise ValueError('Invalid camera resolution')
        if camera['convention'] not in ('opengl','ros'):raise ValueError('Specify optical axis convention')
        if not np.isclose(np.linalg.norm(camera['rotation']),1.,atol=1e-6):raise ValueError('Nonunit camera quaternion')
    overrides=c['cameras'].get('wrist_by_arm',{})
    if not isinstance(overrides,dict) or set(overrides)-{'left','right'}:
        raise ValueError('wrist_by_arm requires left/right pose overrides')
    for side,override in overrides.items():
        if not isinstance(override,dict) or set(override)-{'position','rotation','convention'}:
            raise ValueError('Arm-specific wrist settings may override only optical pose')
        pose=dict(c['cameras']['wrist'],**override)
        position=np.asarray(pose['position'],dtype=float)
        rotation=np.asarray(pose['rotation'],dtype=float)
        if position.shape!=(3,) or not np.isfinite(position).all():raise ValueError('Invalid arm-specific camera position')
        if rotation.shape!=(4,) or not np.isfinite(rotation).all() or not np.isclose(np.linalg.norm(rotation),1.,atol=1e-6):
            raise ValueError('Invalid arm-specific camera quaternion')
        if pose['convention'] not in ('opengl','ros'):raise ValueError('Invalid arm-specific camera convention')
    from .layout import Layout
    Layout(c['layout']).validate()
    return Embodiment(c,path.resolve(),hashlib.sha256(raw).hexdigest())


ROBOTS={}
for path in sorted((CONFIG_ROOT/'embodiments').glob('*.json')):
    if path.name.startswith('.'):continue
    profile=load_profile(path)
    if profile.name in ROBOTS:raise ValueError('Duplicate embodiment '+profile.name)
    ROBOTS[profile.name]=profile
FRANKA=ROBOTS['franka'];ARX_X5=ROBOTS['arx_x5'];UR5_WSG=ROBOTS['ur5_wsg']


def select(task,override=None):
    name=override or TASK_ROBOTS[task]
    if name in ROBOTS:return ROBOTS[name]
    path=Path(name)
    if path.is_file():return load_profile(path)
    raise ValueError('Unknown embodiment: '+str(name))


def articulation(profile,side):
    from isaaclab.assets import ArticulationCfg
    from isaaclab.actuators import ImplicitActuatorCfg
    import isaaclab.sim as sim
    c=profile.config;p=c['physics'];mount=c['robots'][side]
    actuators={}
    for name,joints in [('arm',profile.arm_joints),('gripper',profile.finger_joints)]:
        a=c['actuators'][name]
        actuators[name]=ImplicitActuatorCfg(joint_names_expr=joints,
            effort_limit_sim=a['effort_limit'],velocity_limit_sim=a['velocity_limit'],
            stiffness=a['stiffness'],damping=a['damping'],armature=a['armature'])
    return ArticulationCfg(spawn=sim.UsdFileCfg(usd_path=profile.asset_path(),activate_contact_sensors=True,
        rigid_props=sim.RigidBodyPropertiesCfg(disable_gravity=p['disable_gravity'],max_depenetration_velocity=5.,
            solver_position_iteration_count=p['solver_position_iterations'],solver_velocity_iteration_count=p['solver_velocity_iterations']),
        articulation_props=sim.ArticulationRootPropertiesCfg(enabled_self_collisions=p['self_collision'],
            solver_position_iteration_count=p['solver_position_iterations'],solver_velocity_iteration_count=p['solver_velocity_iterations'],fix_root_link=True)),
        init_state=ArticulationCfg.InitialStateCfg(pos=tuple(mount['position']),rot=tuple(mount['rotation']),joint_pos=mount['initial_joints'].copy()),actuators=actuators)
