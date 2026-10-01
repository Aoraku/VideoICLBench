"""Turn-based physical twin. No task semantics in the action interpreter."""
from pathlib import Path
import sys
import json
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'simulation_b01'))
from run_b01 import Demo

TOKENS = {'MV_FWD', 'MV_BACK', 'MV_LEFT', 'MV_RIGHT', 'MV_UP', 'MV_DOWN',
          'ROTATE_CW', 'ROTATE_CCW', 'GRASP', 'RELEASE', 'STILL'}
VECTORS = {'MV_FWD': [1,0,0], 'MV_BACK': [-1,0,0],
           'MV_LEFT': [0,1,0], 'MV_RIGHT': [0,-1,0],
           'MV_UP': [0,0,1], 'MV_DOWN': [0,0,-1]}

class World(Demo):
    def __init__(self, seed=17, capture=None):
        self.capture = None
        super().__init__(False)
        # Physical wrist cameras: camera lives on the hand, offset beside the fingers.
        xml=ET.parse(ROOT.parent/'simulation_b01/scene.xml')
        # MuJoCo cameras look along local -Z; aim beyond the TCP down the fingers.
        # Image right is hand +Y (world -Y at the nominal grasp pose),
        # consistent with the overhead view. No object-dependent tracking.
        camera_pos=np.array([.05,0.,.015])
        look_at=np.array([0.,0.,.14])
        z=camera_pos-look_at;z/=np.linalg.norm(z)
        x=np.array([0.,1.,0.]);y=np.cross(z,x)
        quat=Rotation.from_matrix(np.column_stack([x,y,z])).as_quat()
        for arm in ['left','right']:
            hand=next(b for b in xml.iter('body') if b.get('name')==arm+'_hand')
            ET.SubElement(hand,'camera',name='wrist_'+arm,pos=' '.join(map(str,camera_pos)),
                          quat=' '.join(map(str,quat[[3,0,1,2]])),fovy='75')
        q,vel,ctrl=self.d.qpos.copy(),self.d.qvel.copy(),self.d.ctrl.copy()
        self.m=mujoco.MjModel.from_xml_string(ET.tostring(xml.getroot(),encoding='unicode'))
        self.d=mujoco.MjData(self.m);self.ik=mujoco.MjData(self.m)
        self.d.qpos[:]=q;self.d.qvel[:]=vel;self.d.ctrl[:]=ctrl
        mujoco.mj_forward(self.m,self.d)
        self.video = False
        self.seed = seed
        # Reset-only layout randomization, never used by action execution.
        rng = np.random.default_rng(seed)
        slots = np.array([[.00,.20,.021],[.10,-.22,.021],[.26,.24,.021]])
        slots[:,:2] += rng.integers(-2,3,(3,2)) * .01
        for color, pos in zip(['red','green','blue'],slots):
            j = self.m.joint(color+'_free').id
            q = self.m.jnt_qposadr[j]
            self.d.qpos[q:q+3] = pos
        mujoco.mj_forward(self.m,self.d)
        self.step(500)
        # Fixed, task-independent start pose; no automatic object alignment.
        for arm,y in [('left',.33),('right',-.33)]:
            super().move(arm,[-.02,y,.25],1.5)
        self.targets = {a:self.d.site_xpos[self.ids[a][3]].copy() for a in self.ids}
        self.rotations = {a:np.diag([1.,-1.,-1.]) for a in self.ids}
        self.closed = {a:False for a in self.ids}
        self.capture = capture
        self.steps = 0

    def step(self,n):
        for _ in range(n):
            mujoco.mj_step(self.m,self.d)
            self.steps += 1
            if self.capture and self.steps % 20 == 0:
                self.capture()

    def ik_target(self,arm,pos,rot,seed):
        qs,ds,_,site = self.ids[arm]
        self.ik.qpos[:] = self.d.qpos
        self.ik.qpos[qs] = seed
        joints = [self.m.joint(f'{arm}_joint{i}').id for i in range(1,8)]
        for _ in range(160):
            mujoco.mj_forward(self.m,self.ik)
            ep = pos-self.ik.site_xpos[site]
            er = Rotation.from_matrix(rot@self.ik.site_xmat[site].reshape(3,3).T).as_rotvec()
            if np.linalg.norm(ep)<.0002 and np.linalg.norm(er)<.002:
                return self.ik.qpos[qs].copy()
            jp=np.zeros((3,self.m.nv));jr=jp.copy()
            mujoco.mj_jacSite(self.m,self.ik,jp,jr,site)
            J=np.vstack([jp[:,ds],jr[:,ds]*.45])
            dq=J.T@np.linalg.solve(J@J.T+np.eye(6)*.00015,np.r_[ep,er*.45])
            dq*=min(1.,.14/(np.linalg.norm(dq)+1e-9))
            self.ik.qpos[qs] += dq
            for k,j in enumerate(joints):
                self.ik.qpos[qs[k]]=np.clip(self.ik.qpos[qs[k]],self.m.jnt_range[j,0]+.005,self.m.jnt_range[j,1]-.005)
        raise ValueError('Target pose unreachable; choose a smaller motion or another direction.')

    def act_pair(self,pair,step_m=.02):
        if set(pair)!={'left','right'} or any(t not in TOKENS for t in pair.values()):
            raise ValueError('Unknown action')
        if step_m not in (.005,.01,.02):
            raise ValueError('Step must be 5, 10 or 20 mm')
        ends={a:p.copy() for a,p in self.targets.items()}
        rotations={a:r.copy() for a,r in self.rotations.items()}
        for arm,token in pair.items():
            if token in VECTORS:
                ends[arm]+=np.array(VECTORS[token])*step_m
            elif token.startswith('ROTATE'):
                angle=np.deg2rad(10 if token=='ROTATE_CCW' else -10)
                rotations[arm]=Rotation.from_rotvec([0,0,angle]).as_matrix()@rotations[arm]
            if not (-.18<=ends[arm][0]<=.42 and -.4<=ends[arm][1]<=.4 and .018<=ends[arm][2]<=.45):
                raise ValueError('Workspace limit; command not executed.')
        # Solve all waypoints BEFORE mutation: an invalid pair executes neither arm.
        seeds={a:self.d.qpos[self.ids[a][0]].copy() for a in self.ids}
        path=[]
        for k in range(1,31):
            u=k/30;s=u*u*(3-2*u);row={}
            for arm,token in pair.items():
                if token in VECTORS or token.startswith('ROTATE'):
                    rv=Rotation.from_matrix(rotations[arm]@self.rotations[arm].T).as_rotvec()
                    rot=Rotation.from_rotvec(rv*s).as_matrix()@self.rotations[arm]
                    p=self.targets[arm]+(ends[arm]-self.targets[arm])*s
                    seeds[arm]=self.ik_target(arm,p,rot,seeds[arm])
                    row[arm]=seeds[arm].copy()
            path.append(row)
        for arm,token in pair.items():
            if token in ('GRASP','RELEASE'):
                self.closed[arm]=(token=='GRASP')
                self.d.ctrl[self.m.actuator(arm+'_actuator8').id]=0 if self.closed[arm] else 255
        for row in path:
            for arm,q in row.items():
                self.d.ctrl[self.ids[arm][2]]=q
            self.step(10)  # BOTH arms share these exact same physics steps.
        self.step(150)
        self.targets=ends;self.rotations=rotations

    def judge(self,order):
        """Private final-state + contact + stability checks; no feedback during play."""
        self.step(500)
        samples=[]
        for _ in range(51):
            samples.append(np.array([self.d.body(n).xpos.copy() for n in order]))
            self.step(10)
        p=samples[-1]
        pairs=set()
        robot_contact=False
        cubes={self.m.geom(n+'_cube').id for n in ['red','green','blue']}
        for c in self.d.contact[:self.d.ncon]:
            a,b=int(c.geom1),int(c.geom2)
            na=mujoco.mj_id2name(self.m,mujoco.mjtObj.mjOBJ_GEOM,a) or ''
            nb=mujoco.mj_id2name(self.m,mujoco.mjtObj.mjOBJ_GEOM,b) or ''
            pairs.add(frozenset([a,b]))
            for block,other in [(a,b),(b,a)]:
                if block in cubes:
                    body=self.m.geom_bodyid[other]
                    name=mujoco.mj_id2name(self.m,mujoco.mjtObj.mjOBJ_BODY,int(body)) or ''
                    robot_contact |= name.startswith(('left_','right_'))
        def contact(a,b):return frozenset([self.m.geom(a).id,self.m.geom(b).id]) in pairs
        drift=float(np.max(np.linalg.norm(np.array(samples)-samples[0],axis=2)))
        checks={
            'bottom_on_table':contact(order[0]+'_cube','table'),
            'middle_on_bottom':contact(order[1]+'_cube',order[0]+'_cube'),
            'top_on_middle':contact(order[2]+'_cube',order[1]+'_cube'),
            'heights':bool(np.max(np.abs(p[:,2]-[.02,.06,.10]))<.006),
            'alignment':bool(np.max(np.linalg.norm(p[:,:2]-p[0,:2],axis=1))<.012),
            'on_mat':bool(np.linalg.norm(p[0,:2]-[.16,0])<.05),
            'upright':all(float(self.d.body(n).xmat.reshape(3,3)[2,2])>.98 for n in order),
            'stable_1s':drift<.001,
            'no_robot_contact':not robot_contact,
            'grippers_clear':all(np.linalg.norm(self.d.site_xpos[self.ids[a][3]]-p[-1])>.12 for a in self.ids),
        }
        return {'success':all(checks.values()),'checks':checks,'drift_m':drift,
                'expected_bottom_to_top':list(order),'positions':self.positions()}
