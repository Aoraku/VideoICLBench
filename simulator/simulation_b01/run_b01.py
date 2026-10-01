"""SDK-controlled physical B01-A. No object teleports/attachments after reset.
IK uses a separate scratch MjData. Live dynamics receive only actuator targets.
"""
from pathlib import Path
import argparse,json,time
import numpy as np
from scipy.spatial.transform import Rotation
import mujoco
P=Path(__file__).resolve().parent
class Demo:
 def __init__(self,video=False):
  self.m=mujoco.MjModel.from_xml_path(str(P/'scene.xml'));self.d=mujoco.MjData(self.m);self.ik=mujoco.MjData(self.m)
  self.ids={};self.steps=0;self.records=[];self.video=video;self.frames=0
  home=np.array([0,-.35,0,-2.05,0,1.75,.7854])
  for arm in ['left','right']:
   js=[self.m.joint(f'{arm}_joint{i}').id for i in range(1,8)]
   qs=np.array([self.m.jnt_qposadr[j] for j in js]);ds=np.array([self.m.jnt_dofadr[j] for j in js]);acts=np.array([self.m.actuator(f'{arm}_actuator{i}').id for i in range(1,8)])
   self.ids[arm]=(qs,ds,acts,self.m.site(arm+'_tcp').id)
   self.d.qpos[qs]=home;self.d.ctrl[acts]=home
   for i in [1,2]:self.d.qpos[self.m.jnt_qposadr[self.m.joint(f'{arm}_finger_joint{i}').id]]=.04
   self.d.ctrl[self.m.actuator(arm+'_actuator8').id]=255
  mujoco.mj_forward(self.m,self.d)
  if video:
   import imageio.v2 as imageio
   self.renderer=mujoco.Renderer(self.m,height=720,width=1280)
   self.cam=mujoco.MjvCamera();self.cam.type=mujoco.mjtCamera.mjCAMERA_FREE;self.cam.lookat[:]=[.01,0,.27];self.cam.distance=1.85;self.cam.azimuth=125;self.cam.elevation=-33
   self.detail_renderer=mujoco.Renderer(self.m,height=288,width=384)
   self.detail_cam=mujoco.MjvCamera();self.detail_cam.lookat[:]=[.13,0,.055];self.detail_cam.distance=.95;self.detail_cam.azimuth=100;self.detail_cam.elevation=-48
   self.writer=imageio.get_writer(str(P/'B01_A_physics.mp4'),fps=25,codec='libx264',quality=8,macro_block_size=16)
  self.step(500)
 def positions(self):return {n:self.d.body(n).xpos.copy().tolist() for n in ['red','green','blue']}
 def event(self,s):
  rec={'time':round(self.d.time,3),'event':s,'blocks':self.positions()};self.records.append(rec);print(json.dumps(rec),flush=True)
 def step(self,n):
  for _ in range(n):
   mujoco.mj_step(self.m,self.d);self.steps+=1
   if self.video and self.steps%20==0:
    self.writer.append_data(self.frame());self.frames+=1
 def frame(self):
  self.renderer.update_scene(self.d,camera=self.cam);frame=self.renderer.render().copy()
  self.detail_renderer.update_scene(self.d,camera=self.detail_cam);detail=self.detail_renderer.render()
  frame[12:308,876:1268]=[225,230,235];frame[16:304,880:1264]=detail
  return frame
 def solve(self,arm,target,seed=None):
  qs,ds,acts,site=self.ids[arm];self.ik.qpos[:]=self.d.qpos
  if seed is not None:self.ik.qpos[qs]=seed
  target_R=np.diag([1.,-1.,-1.])
  for _ in range(180):
   mujoco.mj_forward(self.m,self.ik)
   ep=np.array(target)-self.ik.site_xpos[site];R=self.ik.site_xmat[site].reshape(3,3)
   er=Rotation.from_matrix(target_R@R.T).as_rotvec();err=np.r_[ep,er*.45]
   if np.linalg.norm(ep)<.00015 and np.linalg.norm(er)<.001:break
   jp=np.zeros((3,self.m.nv));jr=jp.copy();mujoco.mj_jacSite(self.m,self.ik,jp,jr,site)
   J=np.vstack([jp[:,ds],jr[:,ds]*.45]);dq=J.T@np.linalg.solve(J@J.T+np.eye(6)*.00015,err)
   dq*=min(1.,.14/(np.linalg.norm(dq)+1e-9));self.ik.qpos[qs]+=dq
   for k,j in enumerate([self.m.joint(f'{arm}_joint{i}').id for i in range(1,8)]):self.ik.qpos[qs[k]]=np.clip(self.ik.qpos[qs[k]],self.m.jnt_range[j,0]+.005,self.m.jnt_range[j,1]-.005)
  if np.linalg.norm(ep)>.005:raise RuntimeError(f'IK {arm}: target {target} residual {ep}')
  return self.ik.qpos[qs].copy()
 def move(self,arm,target,seconds=1.5):
  qs,ds,acts,site=self.ids[arm];start=self.d.site_xpos[site].copy();seed=self.d.qpos[qs].copy();n=max(1,int(seconds/.02))
  # Cartesian interpolation: solve each small waypoint, drive PD actuators.
  for i in range(1,n+1):
   u=i/n;s=u*u*(3-2*u);p=start+(np.array(target)-start)*s
   seed=self.solve(arm,p,seed);self.d.ctrl[acts]=seed;self.step(10)
  self.step(160)
 def grip(self,arm,closed):
  a=self.m.actuator(arm+'_actuator8').id;self.d.ctrl[a]=0 if closed else 255;self.step(400)
 def pick_place(self,arm,name,level):
  self.event(f'{arm}: approach {name}');p=self.d.body(name).xpos.copy();high=.25
  self.grip(arm,False);self.move(arm,[p[0],p[1],high]);self.move(arm,[p[0],p[1],p[2]+.003],1.3)
  self.grip(arm,True);self.event(f'{arm}: grasp {name}');self.move(arm,[p[0],p[1],high],1.5)
  self.event(f'{arm}: lifted {name}')
  if self.d.body(name).xpos[2]<.15:raise RuntimeError('Grasp failed: '+name)
  # Compensate measured cube-to-TCP displacement, without altering cube state.
  site=self.ids[arm][3];offset=self.d.body(name).xpos-self.d.site_xpos[site]
  center=np.array([.16,0,.02+.04*level]);tcp=center-offset
  self.move(arm,[tcp[0],tcp[1],high],1.8);self.move(arm,tcp+np.array([0,0,.002]),1.8)
  self.grip(arm,False);self.event(f'{arm}: release {name}');self.move(arm,[tcp[0],tcp[1],high],1.3)
  self.move(arm,[-.02,.33 if arm=='left' else -.33,.3],1.3)
 def evaluate(self):
  samples=[]
  for _ in range(50):self.step(10);samples.append(np.array([self.d.body(n).xpos.copy() for n in ['red','green','blue']]))
  p=samples[-1];drift=float(np.max(np.linalg.norm(np.array(samples)-samples[0],axis=2)))
  pairs=[]
  for i in range(self.d.ncon):
   c=self.d.contact[i];a=mujoco.mj_id2name(self.m,mujoco.mjtObj.mjOBJ_GEOM,int(c.geom1));b=mujoco.mj_id2name(self.m,mujoco.mjtObj.mjOBJ_GEOM,int(c.geom2));pairs.append([a,b])
  contacts={frozenset(x) for x in pairs};has=lambda a,b:frozenset([a,b]) in contacts
  checks={'red_on_table':has('red_cube','table'),'green_on_red':has('green_cube','red_cube'),'blue_on_green':has('blue_cube','green_cube'),'centers_aligned':bool(np.max(np.linalg.norm(p[:,:2]-[.16,0],axis=1))<.006),'heights_correct':bool(np.max(np.abs(p[:,2]-[.02,.06,.1]))<.005),'stable_1s':drift<.001,'arms_clear':all(np.linalg.norm(self.d.site_xpos[self.ids[a][3]]-p[-1])>.15 for a in self.ids)}
  return {'success':all(checks.values()),'checks':checks,'positions':self.positions(),'drift_m':drift,'sim_seconds':self.d.time,'physics_steps':self.steps,'engine':mujoco.__version__,'solver':'joint-PD with Cartesian IK; physical finger contacts','contacts':pairs,'video_frames':self.frames}
 def close(self):
  if self.video:self.writer.close();self.renderer.close();self.detail_renderer.close()
  (P/'events.json').write_text(json.dumps(self.records,indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--video',action='store_true');ap.add_argument('--preview',action='store_true');args=ap.parse_args()
 sim=Demo(args.video)
 try:
  sim.event('initial')
  if args.preview:
   import imageio.v2 as imageio
   r=mujoco.Renderer(sim.m,height=720,width=1280);cam=mujoco.MjvCamera();cam.lookat[:]=[.05,0,.12];cam.distance=1.55;cam.azimuth=125;cam.elevation=-33;r.update_scene(sim.d,camera=cam);imageio.imwrite(P/'initial.png',r.render());r.close()
  else:
   for arm,color,level in [('left','red',0),('right','green',1),('left','blue',2)]:sim.pick_place(arm,color,level)
   sim.step(1000);result=sim.evaluate();(P/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
   if args.video:
    import imageio.v2 as imageio
    imageio.imwrite(P/'final.png',sim.frame());sim.step(1000)
   if not result['success']:raise RuntimeError('Final evaluation failed')
 finally:sim.close()
