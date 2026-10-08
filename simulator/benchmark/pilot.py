"""Privileged author acceptance controller using ONLY the public action alphabet.
Reads state to plan engineering trajectories; never counted as independent agent.
Does not set qpos, teleport props, alter contacts, or inject successful states.
"""
import argparse
import hashlib
import json
from pathlib import Path
import imageio_ffmpeg
import numpy as np
from .catalog import task_spec
from .environment import DesktopDual
from .provenance import harness_sha256

PILOT=('rt12','rt07','rt02','rc10','rc22','rc11')

class Author:
    def __init__(self,env,folder,record=False,seed=0):
        self.env=env; self.folder=folder; self.seed=seed; self.actions=[]; self.writer=None; self.record_requested=record; self.recorded_actions=0; self.video_end_success=False
        folder.mkdir(parents=True,exist_ok=False)
        if record:
            self.writer=imageio_ffmpeg.write_frames(str(folder/'video.mp4'),(512,384),fps=2.5,
                codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p');self.writer.send(None)
            self.frame()
    def frame(self):
        if self.writer:
            frame=self.env.sim.render(width=512,height=384,camera_name='agentview')[::-1]
            self.writer.send(np.ascontiguousarray(frame))
            self.recorded_actions=len(self.actions)
            if self.actions and self.env.score()['hold_seconds']>=2:
                self.writer.close();self.writer=None;self.video_end_success=True
    def act(self,arm,token):
        if len(self.actions)>=1000: raise RuntimeError('Action budget exhausted')
        pair=['STILL','STILL'];pair[arm]=token
        self.env.action(*pair);self.actions.append(dict(left=pair[0],right=pair[1]));self.frame()
        snapshot={k:dict(pos=v['pos'].tolist(),grasp=v['grasp']) for k,v in self.env.snapshot().items()}
        with (self.folder/'trace.private.jsonl').open('a') as f:f.write(json.dumps(dict(index=len(self.actions),action=pair,eef0=self.eef(0).tolist(),eef1=self.eef(1).tolist(),objects=snapshot))+'\n')
    def wait(self,n=3):
        for _ in range(n):self.act(0,'STILL')
    def eef(self,arm):
        return (self.env._eef0_xpos if arm==0 else self.env._eef1_xpos).copy()
    def state(self,name):return self.env.snapshot()[name]
    def move(self,arm,target,axes=(2,0,1),tol=.011):
        target=np.asarray(target)
        for axis in axes:
            history=[]
            for _ in range(80):
                pos=self.eef(arm);error=target[axis]-pos[axis]
                if abs(error)<=tol:break
                history.append(pos[axis])
                if len(history)>10 and max(history[-8:])-min(history[-8:])<.002:
                    raise RuntimeError(f'Arm {arm} stalled axis {axis} at {pos.tolist()} target {target.tolist()}')
                self.act(arm,(['FWD','LEFT','UP'] if error>0 else ['BACK','RIGHT','DOWN'])[axis])
            else:raise RuntimeError(f'Arm {arm} did not reach {target.tolist()}')
    def park(self,arm):self.move(arm,[-.12,-.31 if arm==0 else .31,1.15])
    def pick(self,name,arm,grasp_offset=None):
        p=self.state(name)['pos'].copy()
        self.act(arm,'RELEASE')
        self.move(arm,[p[0],p[1],1.14])
        if grasp_offset is None:grasp_offset=.025 if self.env.by_spec[name]['kind']=='bottle' else .009
        self.move(arm,[p[0],p[1],p[2]+grasp_offset],axes=(2,))
        for _ in range(3):self.act(arm,'GRASP')
        if not self.state(name)['grasp'][arm]:
            raise RuntimeError(f'Failed grasp {name} arm {arm}, eef {self.eef(arm).tolist()}, object {self.state(name)["pos"].tolist()}')
        self.move(arm,[*p[:2],1.13],axes=(2,))
        if not self.state(name)['grasp'][arm]:raise RuntimeError(f'Dropped {name} after lift')
    def put(self,name,arm,target):
        target=np.asarray(target)
        offset=self.eef(arm)-self.state(name)['pos']
        self.move(arm,[*self.eef(arm)[:2],max(1.13,target[2]+.18)],axes=(2,))
        self.move(arm,target+offset,axes=(0,1))
        # Release just above support, allowing the physical object to settle.
        self.move(arm,target+offset+[0,0,.012],axes=(2,))
        for _ in range(3):self.act(arm,'RELEASE')
        self.move(arm,[*self.eef(arm)[:2],1.14],axes=(2,))
        self.wait()
    def transport(self,name,arm,xy,bottom=.8):
        self.pick(name,arm)
        size=np.array(self.env.by_spec[name]['size'])
        self.put(name,arm,[*xy,bottom+size[2]])
        self.park(arm)
    def solve(self,task):
        self.park(0);self.park(1)
        if task=='rt12':self.transport('cup',0,[.16,0])
        elif task=='rt02':
            self.transport('blue',1,[.02,0])
            self.pick('green',0)
            p=self.state('blue')['pos'];self.put('green',0,p+[0,0,.05]);self.park(0)
            self.pick('red',0)
            p=self.state('green')['pos'];self.put('red',0,p+[0,0,.05]);self.park(0)
        elif task=='rc10':
            for _ in range(9):self.act(0,'YAW_POS')
            self.transport('food',0,[-.12,0])
            self.transport('food',1,self.state('right')['pos'][:2],bottom=.808)
        elif task=='rc11':
            self.transport('a',0,self.state('left')['pos'][:2],bottom=.808)
            self.transport('b',1,self.state('right')['pos'][:2],bottom=.808)
        elif task=='rc22':
            a=self.state('a')['pos'].copy();b=self.state('b')['pos'].copy()
            self.transport('a',0,[-.04,-.06]);self.transport('b',1,[-.12,.04])
            self.transport('b',0,a[:2]);self.transport('a',1,b[:2])
        elif task=='rt07':self.handover()
        else:raise ValueError(task)
        self.wait(5)
    def handover(self):
        # Separate grips along Y keep each wrist on its own side of the table.
        for arm in (0,1):
            for _ in range(9):self.act(arm,'YAW_POS')
        p=self.state('item')['pos'].copy()
        self.act(0,'RELEASE')
        self.move(0,[p[0],p[1]-.10,1.14])
        self.move(0,[p[0],p[1]-.10,p[2]],axes=(2,))
        for _ in range(3):self.act(0,'GRASP')
        if not self.state('item')['grasp'][0]:raise RuntimeError('Giving arm failed end grasp')
        self.move(0,[-.12,-.10,1.04],axes=(2,0,1))
        if not self.state('item')['grasp'][0]:raise RuntimeError('Giving arm dropped block')
        a=self.state('item');end=a['pos']+a['mat']@np.array([0,.10,0])
        self.act(1,'RELEASE')
        self.move(1,[end[0],end[1],1.14])
        for attempt in range(5):
            for _ in range(100):
                a=self.state('item');end=a['pos']+a['mat']@np.array([0,.10,0])
                target=end+np.array([0,0,.004-attempt*.004]);error=target-self.eef(1)
                if np.max(np.abs(error))<=.011:break
                axis=int(np.argmax(np.abs(error)))
                self.act(1,(['FWD','LEFT','UP'] if error[axis]>0 else ['BACK','RIGHT','DOWN'])[axis])
            for _ in range(3):self.act(1,'GRASP')
            if self.state('item')['grasp'][1]:break
            self.act(1,'RELEASE')
        if not self.state('item')['grasp'][1]:raise RuntimeError('Receiving arm failed end grasp')
        for _ in range(3):self.act(0,'RELEASE')
        if not self.state('item')['grasp'][1]:raise RuntimeError('Receiving arm did not retain ownership')
        self.park(0)
        self.put('item',1,[.14,0,.825]);self.park(1)
    def finish(self,error=None):
        if self.writer:self.writer.close()
        result=dict(task=self.env.spec['id'],variant=self.env.spec['variant'],
            kind='privileged-author-token-acceptance',independent_agent=False,seed=self.seed,task_revision=self.env.spec.get('task_revision',1),
            harness_sha256=harness_sha256(),actions_sha256=hashlib.sha256(json.dumps(self.actions,sort_keys=True).encode()).hexdigest(),
            video_fps=2.5 if self.record_requested else None,video_recorded_actions=self.recorded_actions,video_end_success=self.video_end_success,
            actions=len(self.actions),score=self.env.score(),error=error)
        (self.folder/'result.private.json').write_text(json.dumps(result,indent=2))
        (self.folder/'actions.json').write_text(json.dumps(self.actions,indent=2))
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--tasks',nargs='+',choices=PILOT,default=list(PILOT))
    p.add_argument('--variant',choices=['A'],default='A');p.add_argument('--seed',type=int,default=0)
    p.add_argument('--output',type=Path,default=Path('.local/pilot'));p.add_argument('--record',action='store_true');a=p.parse_args()
    summary=[]
    for task in a.tasks:
        env=DesktopDual(task_spec(task,a.variant),seed=a.seed,render=a.record)
        author=Author(env,a.output/f'{task}-{a.variant}-{a.seed}',a.record,seed=a.seed)
        error=None
        try:author.solve(task)
        except Exception as exc:error=str(exc)
        finally:
            result=author.finish(error);env.close()
        print(json.dumps(result),flush=True);summary.append(result)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'summary.private.json').write_text(json.dumps(summary,indent=2))
    if any(r['error'] or not r['score']['success'] for r in summary):raise SystemExit(1)
if __name__=='__main__':main()
