#!/usr/bin/env python3
"""Privileged author recordings through legal tokens, never agent scores."""
import argparse,json,sys,math,hashlib,os
import imageio_ffmpeg
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from simulator.benchmark.pilot import Author
from simulator.benchmark.catalog import TASKS,task_spec
from simulator.benchmark.environment import DesktopDual
CONTROLLER_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

class DesktopAuthor(Author):
    def __init__(self,env,folder,record=False,seed=0):
        super().__init__(env,folder,False,seed)
        self.yaws=[0.,0.];self.record_requested=record
        if record:
            env.sim.model.cam_fovy[env.sim.model.camera_name2id('agentview')]=60
            self.writer=imageio_ffmpeg.write_frames(str(folder/'video.mp4'),(512,384),fps=20,
                codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p');self.writer.send(None)
            self.raw_frame()
            step=env.step
            def recorded_step(action):
                result=step(action)
                if self.writer:self.raw_frame()
                return result
            env.step=recorded_step
    def raw_frame(self):
        self.writer.send(np.ascontiguousarray(self.env.sim.render(width=512,height=384,camera_name='agentview')[::-1]))
    def frame(self):
        if self.writer:
            self.recorded_actions=len(self.actions)
            if self.actions and self.env.score()['hold_seconds']>=2:
                self.writer.close();self.writer=None;self.video_end_success=True
    def act(self,arm,token):
        super().act(arm,token)
        if token.startswith('YAW_'):self.yaws[arm]+=math.radians(10)*(1 if token=='YAW_POS' else -1)
    def align(self,arm,angle):
        while abs((angle-self.yaws[arm]+math.pi)%(2*math.pi)-math.pi)>.1:
            error=(angle-self.yaws[arm]+math.pi)%(2*math.pi)-math.pi
            self.act(arm,'YAW_POS' if error>0 else 'YAW_NEG')
    def park(self,arm):
        super().park(arm);self.align(arm,0)
    def pick(self,name,arm,grasp_offset=None):
        s=self.env.by_spec[name]
        if s['kind'] not in ('bowl','tray','cup') or s['size'][1]<=.035:
            if grasp_offset is None:
                grasp_offset=min(.025,s['size'][2]*.45) if s['kind']=='bottle' else min(.009,s['size'][2]*.35)
            if s['kind'] in ('bowl','tray','cup'):
                grasp_offset=.015;self.align(arm,math.pi/2)
            if s['kind']=='bottle' and s['size'][2]<.04:
                p=self.state(name)['pos'].copy();self.align(arm,math.pi/2);self.act(arm,'RELEASE')
                self.move(arm,[p[0],p[1],1.14])
                self.move(arm,[p[0],p[1],p[2]+.009],axes=(2,))
                for _ in range(3):self.act(arm,'GRASP')
                if not self.state(name)['grasp'][arm]:raise RuntimeError('Small cylinder grasp failed')
                self.move(arm,[*self.eef(arm)[:2],1.13],axes=(2,))
                if not self.state(name)['grasp'][arm]:raise RuntimeError('Small cylinder dropped')
                return
            return super().pick(name,arm,grasp_offset)
        p=self.state(name)['pos'].copy()
        # Close across a real side wall of the open bin, not its empty cavity.
        mat=self.state(name)['mat'];angle=math.atan2(mat[1,0],mat[0,0])
        self.align(arm,angle)
        point=p+mat@np.array([0,(-1 if arm==0 else 1)*(s['size'][1]-.004),0])
        pxy=point[:2];y=point[1]
        self.act(arm,'RELEASE');self.move(arm,[*pxy,1.15])
        self.move(arm,[*pxy,p[2]+min(.008,s['size'][2]*.25)],axes=(2,))
        for _ in range(3):self.act(arm,'GRASP')
        if not self.state(name)['grasp'][arm]:raise RuntimeError(f'Failed bin-wall grasp {name} arm {arm}')
        self.move(arm,[p[0],y,1.15],axes=(2,))
        if not self.state(name)['grasp'][arm]:raise RuntimeError(f'Dropped bin {name}')
    def put(self,name,arm,target):
        target=np.asarray(target);size=np.array(self.env.by_spec[name]['size'])
        self.move(arm,[*self.eef(arm)[:2],max(1.14,target[2]+.18)],axes=(2,))
        offset=self.eef(arm)-self.state(name)['pos']
        self.move(arm,target+offset,axes=(0,1));self.wait(2)
        wall_top=None
        for g in self.env.spec['goals']:
            if g.get('object')==name and g['type']=='nest':
                other=self.env.by_spec[g['target']]
                wall_top=self.state(g['target'])['pos'][2]+other['size'][2]
        for _ in range(30):
            state=self.state(name);extent=(np.abs(state['mat'])@size)[2]
            support=target[2]-size[2]
            if wall_top is not None and self.eef(arm)[2] <= wall_top+.045:break
            if wall_top is None and state['pos'][2]-extent <= support+.025:break
            self.act(arm,'DOWN')
        for _ in range(3):self.act(arm,'RELEASE')
        self.move(arm,[*self.eef(arm)[:2],1.14],axes=(2,));self.wait(3)
    def transport(self,name,arm,xy,bottom=.8):
        self.pick(name,arm)
        for g in self.env.spec['goals']:
            if g['type']=='yaw' and g['object']==name:
                a=self.state(name)['mat'];angle=math.atan2(a[1,0],a[0,0])
                self.align(arm,self.yaws[arm]+g['value']-angle)
        size=np.array(self.env.by_spec[name]['size'])
        self.put(name,arm,[*xy,bottom+size[2]]);self.park(arm)
    def transfer(self,name,xy,bottom=.8):
        src=self.state(name)['pos'];arm=(0 if xy[1]<=0 else 1) if abs(src[1])<.06 else (0 if src[1]<0 else 1)
        target_arm=0 if xy[1]<-.07 else 1 if xy[1]>.07 else arm
        if arm!=target_arm:
            # Cross-table relay in a clear shared region, allowed except handover tasks.
            self.transport(name,arm,[-.12,0]);arm=target_arm
        self.transport(name,arm,xy,bottom)
    def solve(self,task):
        if task in ('rt02','rt07','rc10','rc11','rc22'):
            return super().solve(task)
        self.park(0);self.park(1)
        spec=self.env.spec;goals=spec['goals']
        if task=='rt04':self.transfer('large',[.10,0])
        if task=='rt08':return self.handover()
        if task=='rt10':
            self.pick('a',0);self.pick('b',1);self.wait(6);return
        if task=='rt09':return self.dual_lift()
        if task in ('rt19','rt22'):return self.reorient(task)
        done=set()
        def complete(g):
            name=g.get('object');kind=g['type']
            if kind in ('yaw','upright'):return
            # A moved support is settled before placing its child.
            if kind in ('stack','nest'):
                for other in goals:
                    if other.get('object')==g['target'] and other['type'] in ('stack','nest') and id(other) not in done:complete(other)
            if id(g) in done:return
            if kind=='place':
                z=next(z for z in spec['zones'] if z['id']==g['target'])
                siblings=[h for h in goals if h['type']=='place' and h['target']==g['target']]
                offset=(siblings.index(g)-(len(siblings)-1)/2)*.075
                xy=np.array(z['xy'])+[0,offset];bottom=.8
            elif kind=='position':xy=g['xy'];bottom=.8
            elif kind in ('stack','nest'):
                b=self.state(g['target'])['pos'];bs=np.array(self.env.by_spec[g['target']]['size']);xy=b[:2].copy()
                if kind=='stack':bottom=b[2]+bs[2]
                else:
                    bottom=b[2]-bs[2]+.008
                    siblings=[h for h in goals if h['type']=='nest' and h['target']==g['target']]
                    if len(siblings)>1:
                        axis=0 if task=='rc02' else 1
                        step=.08 if task=='rc02' else .052
                        xy[axis]+=(siblings.index(g)-(len(siblings)-1)/2)*step
            else:raise ValueError(kind)
            self.transfer(name,xy,bottom);done.add(id(g))
        for g in goals:complete(g)
        self.wait(5)
    def dual_lift(self):
        name='tray';p=self.state(name)['pos'];s=self.env.by_spec[name]
        for arm in (0,1):
            y=p[1]+(-1 if arm==0 else 1)*(s['size'][1]-.004)
            self.act(arm,'RELEASE');self.move(arm,[p[0],y,1.14])
            self.move(arm,[p[0],y,p[2]+.004],axes=(2,))
            for _ in range(3):self.act(arm,'GRASP')
        if not all(self.state(name)['grasp']):raise RuntimeError('Both tray walls must be grasped')
        for _ in range(7):
            self.env.action('UP','UP');self.actions.append(dict(left='UP',right='UP'));self.frame()
        self.wait(6)
    def reorient(self,task):
        name='phone' if task=='rt19' else 'bottle'
        self.pick(name,0,grasp_offset=.012 if task=='rt19' else .015)
        self.move(0,[.04,0,1.04])
        for _ in range(9):self.act(0,'PITCH_POS')
        axis=0 if task=='rt19' else 2
        for _ in range(25):
            v=self.state(name)['mat'][:,axis]
            target_axis=np.array([0.,0.,(1 if v[2]>=0 else -1) if task=='rt19' else 1.])
            if np.dot(v,target_axis)>.99:break
            rotation=np.cross(v,target_axis);j=int(np.argmax(np.abs(rotation[:2])))
            self.act(0,('ROLL_' if j==0 else 'PITCH_')+('POS' if rotation[j]>0 else 'NEG'))
        a=self.state(name)
        if not a['grasp'][0]:raise RuntimeError('Dropped during orientation')
        # Regrasp the upper end with the second, downward-facing hand.
        self.align(1,math.pi/2)
        self.act(1,'RELEASE');self.move(1,[*a['pos'][:2],1.25])
        for attempt in range(5):
            for _ in range(100):
                a=self.state(name);v=a['mat'][:,axis]
                endpoint=a['pos']+v*(1 if v[2]>0 else -1)*(.055 if task=='rt19' else .045)
                endpoint[2]-=attempt*.004
                error=endpoint-self.eef(1)
                if np.max(np.abs(error))<=.011:break
                j=int(np.argmax(np.abs(error)))
                self.act(1,(['FWD','LEFT','UP'] if error[j]>0 else ['BACK','RIGHT','DOWN'])[j])
            for _ in range(3):self.act(1,'GRASP')
            if self.state(name)['grasp'][1]:break
            self.act(1,'RELEASE')
        if not self.state(name)['grasp'][1]:raise RuntimeError('Upright regrasp failed')
        for _ in range(3):self.act(0,'RELEASE')
        for _ in range(5):
            self.env.action('FWD','UP');self.actions.append(dict(left='FWD',right='UP'));self.frame()
        self.move(0,[*self.eef(0)[:1],-.25,1.14],axes=(1,2))
        for _ in range(9):self.act(0,'PITCH_NEG')
        self.park(0)
        if not self.state(name)['grasp'][1]:raise RuntimeError('Receiver lost upright object')
        target=self.state('stand')['pos'][:2] if task=='rt19' else np.array([.12,.16])
        offset=self.eef(1)-self.state(name)['pos']
        self.move(1,[*(target+offset[:2]),1.14],axes=(2,0,1))
        support=.808 if task=='rt19' else .8
        size=np.array(self.env.by_spec[name]['size'])
        for _ in range(80):
            a=self.state(name);error=target-a['pos'][:2]
            if np.max(np.abs(error))>.012:
                j=int(np.argmax(np.abs(error)))
                self.act(1,(['FWD','LEFT'] if error[j]>0 else ['BACK','RIGHT'])[j]);continue
            if a['pos'][2]-(np.abs(a['mat'])@size)[2] <= support+.014:break
            self.act(1,'DOWN')
        for _ in range(3):self.act(1,'RELEASE')
        self.move(1,[*self.eef(1)[:2],1.14],axes=(2,));self.park(1);self.wait(5)

def main():
    p=argparse.ArgumentParser();p.add_argument('--tasks',nargs='+',default=list(TASKS));p.add_argument('--output',type=Path,required=True);p.add_argument('--record',action='store_true');a=p.parse_args()
    bad=False
    for task in a.tasks:
        env=DesktopDual(task_spec(task,'A'),seed=0,render=a.record)
        author=DesktopAuthor(env,a.output/f'{task}-A-0',a.record,seed=0);error=None
        try:author.solve(task)
        except Exception as exc:error=str(exc)
        finally:
            r=author.finish(error)
            r['video_fps']=20 if a.record else None
            r['render_backend']=os.environ.get('MUJOCO_GL','platform-default')
            r['camera']={'name':'agentview','fovy_degrees':60,'resolution':[512,384]} if a.record else None
            r['controller_sha256']=CONTROLLER_SHA256
            r['task_spec_sha256']=hashlib.sha256(json.dumps(env.spec,sort_keys=True).encode()).hexdigest()
            r['environment_sha256']=hashlib.sha256((Path(__file__).resolve().parents[2]/'simulator/benchmark/environment.py').read_bytes()).hexdigest()
            (author.folder/'result.private.json').write_text(json.dumps(r,indent=2));env.close()
        print(json.dumps(r),flush=True);bad|=bool(error or not r['score']['success'])
    if bad:sys.exit(1)
if __name__=='__main__':main()
