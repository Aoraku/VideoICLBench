"""Physical robosuite environment. Only the worker/evaluator imports this module."""
import base64
import io
import math
import numpy as np
from PIL import Image
from robosuite.environments.manipulation.two_arm_env import TwoArmEnv
from robosuite.models.arenas import TableArena
from robosuite.models.tasks import ManipulationTask
from robosuite.models.objects import BoxObject, CylinderObject, CompositeObject
from robosuite.controllers import load_composite_controller_config

from .protocol import TOKENS
CAMERAS = ('agentview','robot0_eye_in_hand','robot1_eye_in_hand')


def make_object(s):
    name=s['id']; x,y,z=s['size']; rgba=s['rgba']; kind=s['kind']
    if kind in ('cup','bowl','tray'):
        # Five physical walls with an open cavity, not a solid visual box.
        w=.004
        sizes=[[x,y,w],[w,y,z],[w,y,z],[x-w,w,z],[x-w,w,z]]
        locations=[[0,0,-z+w],[-x+w,0,0],[x-w,0,0],[0,-y+w,0],[0,y-w,0]]
        return CompositeObject(name=name,total_size=[x,y,z],geom_types=['box']*5,
            geom_sizes=sizes,geom_locations=locations,geom_rgbas=[rgba]*5,
            locations_relative_to_center=True,density=250,geom_frictions=[(1,.005,.0001)]*5)
    if kind in ('bottle','plate'):
        return CylinderObject(name=name,size=[x,z],rgba=rgba,density=300,friction=[1,.005,.0001])
    return BoxObject(name=name,size=[x,y,z],rgba=rgba,density=300,friction=[1,.005,.0001])

class DesktopDual(TwoArmEnv):
    def __init__(self,spec,seed=0,render=True):
        self.layout_jitter=np.random.default_rng(seed).uniform(-.004,.004,2)
        self.spec=spec; self.by_spec={o['id']:o for o in spec['objects']}
        self.table_offset=np.array([0,0,.8]); self.events=set(); self._left_airborne=set()
        self._receive_hold={}
        self.terminal_hold=0; self.render_enabled=render
        config=load_composite_controller_config(robot='Panda')
        config['body_parts']['right']['input_ref_frame']='world'
        super().__init__(robots=['Panda','Panda'],env_configuration='parallel',
            controller_configs=config,initialization_noise=None,seed=seed,
            use_camera_obs=False,has_offscreen_renderer=render,has_renderer=False,
            control_freq=20,horizon=100000,ignore_done=True,hard_reset=False)
        self.reset()
        self.grips=[-1.,-1.]
        for robot in self.robots:
            robot.composite_controller.part_controllers['right'].reset_goal(goal_update_mode='desired')
        for _ in range(20): self.step(np.array([0]*6+[-1]+[0]*6+[-1],dtype=float))
        self.events.clear(); self._left_airborne.clear(); self.terminal_hold=0
        self.last_positions={k:v['pos'].copy() for k,v in self.snapshot().items()}

    def _load_model(self):
        super()._load_model()
        for robot,offset in zip(self.robots,(-.25,.25)):
            base=np.array(robot.robot_model.base_xpos_offset['table'](.8))+[0,offset,0]
            robot.robot_model.set_base_xpos(base)
        arena=TableArena(table_full_size=(.8,.8,.05),table_offset=self.table_offset,
                         table_friction=(1,.005,.0001))
        arena.set_origin([0,0,0])
        # Visible neutral targets; they do not reveal the goal relation.
        from robosuite.utils.mjcf_utils import new_geom
        for zone in self.spec['zones']:
            arena.worldbody.append(new_geom(name='zone_'+zone['id'],type='box',
                size=zone['half_size']+[.001],pos=zone['xy']+[.801],
                rgba=[.35,.45,.55,1],group=1,contype=0,conaffinity=0))
        self.items={s['id']:make_object(s) for s in self.spec['objects']}
        self.model=ManipulationTask(mujoco_arena=arena,
            mujoco_robots=[r.robot_model for r in self.robots],mujoco_objects=list(self.items.values()))

    def _setup_references(self):
        super()._setup_references()
        self.body_ids={k:self.sim.model.body_name2id(v.root_body) for k,v in self.items.items()}

    def _reset_internal(self):
        super()._reset_internal()
        if not self.deterministic_reset:
            for s in self.spec['objects']:
                q=s.get('quaternion',[math.cos(s['yaw']/2),0,0,math.sin(s['yaw']/2)])
                bottom=.805
                # Initialize food physically inside bowls for transfer tasks.
                for other in self.spec['objects']:
                    if other['id']!=s['id'] and other['kind'] in ('bowl','tray','cup') and other['xy']==s['xy']:
                        bottom+=.008
                half=s['size'][0] if 'quaternion' in s else s['size'][2]
                self.sim.data.set_joint_qpos(self.items[s['id']].joints[0],(np.array(s['xy'])+self.layout_jitter).tolist()+[bottom+half]+q)
            self.sim.forward()

    def reward(self,action=None): return 0.0  # no reward oracle on actor interface
    def _check_success(self): return False  # evaluation is private and terminal only

    def snapshot(self):
        out={}
        for k,obj in self.items.items():
            bid=self.body_ids[k]
            grips=[bool(self._check_grasp(r.gripper['right'],obj.contact_geoms)) for r in self.robots]
            out[k]=dict(pos=self.sim.data.body_xpos[bid].copy(),
                mat=self.sim.data.body_xmat[bid].reshape(3,3).copy(),grasp=grips)
        return out

    def predicate(self,g,state):
        a=state[g.get('object',g.get('objects',[''])[0])]; p=a['pos']; size=np.array(self.by_spec[g.get('object',g.get('objects',[''])[0])]['size'])
        typ=g['type']
        if typ=='place':
            z=next(z for z in self.spec['zones'] if z['id']==g['target'])
            extent=np.abs(a['mat'])@size
            return bool(np.all(np.abs(p[:2]-z['xy'])+extent[:2] < np.array(z['half_size'])+.008) and .80<p[2]<.80+extent[2]+.025)
        if typ=='position': return bool(np.linalg.norm(p[:2]-g['xy'])<g['tolerance'] and .8<p[2]<.96)
        if typ in ('stack','nest'):
            b=state[g['target']]; bs=np.array(self.by_spec[g['target']]['size']); bp=b['pos']
            ae=np.abs(a['mat'])@size; be=np.abs(b['mat'])@bs
            local=b['mat'].T@(p-bp)
            if typ=='nest':
                return bool(np.all(np.abs(local[:2])+ae[:2]<bs[:2]-.003+.005) and abs((local[2]-ae[2])-(-bs[2]+.008))<.015 and local[2]+ae[2]<bs[2]+.12 and self.check_contact(self.items[g['object']],self.items[g['target']]))
            return bool(np.linalg.norm(p[:2]-bp[:2])<max(.02,min(bs[:2])*.65) and abs((p[2]-ae[2])-(bp[2]+be[2]))<.012 and self.check_contact(self.items[g['object']],self.items[g['target']]))
        if typ=='upright': return bool((abs(a['mat'][2,g['axis']]) if g['axis']!=2 else a['mat'][2,2])>.96)
        if typ=='yaw':
            yaw=math.atan2(a['mat'][1,0],a['mat'][0,0]); delta=(yaw-g['value']+math.pi)%(2*math.pi)-math.pi
            return abs(delta)<g['tolerance']
        if typ=='handover': return ('handover',g['object']) in self.events
        if typ=='dual_lift': return bool(all(a['grasp']) and p[2]-size[2]>.8+g['height'])
        if typ=='paired_lift':
            return all(state[n]['grasp'][i] and state[n]['pos'][2]-self.by_spec[n]['size'][2]>.8+g['height'] for i,n in enumerate(g['objects']))
        raise ValueError(typ)

    def track(self):
        state=self.snapshot()
        for name,a in state.items():
            extent=(np.abs(a['mat'])@np.array(self.by_spec[name]['size']))[2]
            airborne=a['pos'][2]-extent>.83
            if not airborne: self._left_airborne.discard(name)
            if a['grasp'][0] and airborne: self._left_airborne.add(name)
            exclusive_receiver=a['grasp'][1] and not a['grasp'][0] and airborne and name in self._left_airborne
            self._receive_hold[name]=self._receive_hold.get(name,0)+1 if exclusive_receiver else 0
            if self._receive_hold[name]>=4:self.events.add(('handover',name))
        lift=any(g['type'] in ('dual_lift','paired_lift') for g in self.spec['goals'])
        released=lift or not any(any(a['grasp']) for a in state.values())
        stable=all(np.linalg.norm(a['pos']-self.last_positions[k])<.002 for k,a in state.items())
        valid=all(self.predicate(g,state) for g in self.spec['goals']) and released and stable
        self.terminal_hold=self.terminal_hold+1 if valid else 0
        self.last_positions={k:a['pos'].copy() for k,a in state.items()}

    def action(self,left='STILL',right='STILL'):
        if left not in TOKENS or right not in TOKENS: raise ValueError('Unknown action token')
        action=np.zeros(14)
        for i,token in enumerate((left,right)):
            if token=='GRASP': self.grips[i]=1
            elif token=='RELEASE': self.grips[i]=-1
            vec={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1),
                 'ROLL_POS':(3,1),'ROLL_NEG':(3,-1),'PITCH_POS':(4,1),'PITCH_NEG':(4,-1),'YAW_POS':(5,1),'YAW_NEG':(5,-1)}
            if token in vec:
                axis,sign=vec[token]; action[i*7+axis]=sign*(.02/.05 if axis<3 else math.radians(10)/.5)
            action[i*7+6]=self.grips[i]
        for j in range(8):
            self.step(action)
            self.track()
            action[:6]=0; action[7:13]=0

    def images(self):
        out={}
        for camera in CAMERAS:
            arr=self.sim.render(width=512,height=384,camera_name=camera)[::-1]
            stream=io.BytesIO(); Image.fromarray(arr).save(stream,format='JPEG',quality=85)
            out[camera]=base64.b64encode(stream.getvalue()).decode()
        return out

    def score(self):
        state=self.snapshot()
        return dict(success=self.terminal_hold>=10,hold_seconds=self.terminal_hold/20,
            predicates=[dict(rule=g,passed=bool(self.predicate(g,state))) for g in self.spec['goals']],
            object_positions={k:a['pos'].tolist() for k,a in state.items()},events=sorted(self.events))
