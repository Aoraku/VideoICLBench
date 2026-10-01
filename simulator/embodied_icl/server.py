"""GUMI-derived browser console -> one shared MuJoCo world -> private judge."""
import base64
import argparse
import io
import json
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
import mujoco
import imageio.v2 as imageio
from PIL import Image
from physics import ROOT, World, TOKENS

ORDERS={'A':('red','green','blue'),'B':('green','blue','red'),'C':('blue','red','green')}

class Engine:
    def __init__(self,args):
        self.args=args
        self.run=ROOT/'private_runs'/uuid.uuid4().hex[:12]
        self.run.mkdir(parents=True)
        self.status='ready';self.count=0;self.message='Watch the demonstration, then START.'
        self.frames={};self.writer=None;self.frame_count=0;self.revision=0
        self.world=World(seed=args.seed)
        self.renderer=mujoco.Renderer(self.world.m,height=288,width=384)
        self.world.capture=self.render
        self.render()
        self.initial=[float(x) for x in self.world.d.qpos]
        self.write_json('episode.json',{'variant':args.variant,'seed':args.seed,'order':ORDERS[args.variant],
            'kind':'interactive_episode','demo_source':'simulated_robot','physics':'MuJoCo',
            'initial_qpos':self.initial,'max_pairs':args.max_pairs,'action_time_s':.9,
            'simulation_clock':'paused between GUI actions; simultaneous arms within each action'})

    def write_json(self,name,value):
        (self.run/name).write_text(json.dumps(value,indent=2))

    def state(self):
        # Strict whitelist: no object state, variant, expected order, holding truth or judge signal.
        return {'status':self.status,'recording':self.status=='running','steps':self.count,
                'total_pairs':self.count,'rollout':'episode','message':self.message,
                'task_text':'Watch the demonstration. Reproduce its arrangement on the mat.',
                'gripper_closed':dict(self.world.closed),'max_pairs':self.args.max_pairs}

    def render(self,record=True):
        w=self.world
        cams={}
        for name,look,dist,az,el in [
            ('overhead',[.12,0,.02],.95,0,-90),
            ('agentview',[.12,0,.14],1.02,0,-25)]:
            c=mujoco.MjvCamera();c.lookat[:]=look;c.distance=dist;c.azimuth=az;c.elevation=el;cams[name]=c
        for arm in ['left','right']:
            c=mujoco.MjvCamera();c.type=mujoco.mjtCamera.mjCAMERA_FIXED
            c.fixedcamid=w.m.camera('wrist_'+arm).id
            cams['wrist_'+arm]=c
        images={}
        for name,c in cams.items():
            self.renderer.update_scene(w.d,camera=c)
            pixels=self.renderer.render().copy();images[name]=pixels
            b=io.BytesIO();Image.fromarray(pixels).save(b,format='JPEG',quality=88)
            self.frames[name]=b.getvalue()
        mosaic=np.vstack([np.hstack([images['overhead'],images['agentview']]),
                          np.hstack([images['wrist_left'],images['wrist_right']])])
        self.mosaic=mosaic
        if self.writer and record:
            self.writer.append_data(mosaic);self.frame_count+=1

    def execute(self,path,body):
        # Queued on the simulation thread: snapshots cannot overlap an action.
        if path=='/api/observe':
            self.render(record=False)
            return {'ok':True,'observation_id':f'{self.run.name}:{self.revision}',
                    'state':self.state(), 'images':{name:base64.b64encode(data).decode('ascii')
                                                   for name,data in self.frames.items()}}
        if path not in ('/api/start','/api/step','/api/stop'):
            raise ValueError('Unsupported endpoint.')
        if 'expected_observation' in body and body['expected_observation']!=f'{self.run.name}:{self.revision}':
            raise ValueError('Stale observation; obtain a fresh image before acting.')
        # Invalidate even failed/partially executed commands; never replay a stale decision.
        self.revision+=1
        if path=='/api/start':
            if self.status!='ready':raise ValueError('This episode can only be started once.')
            self.writer=imageio.get_writer(self.run/'execution.mp4',fps=25,codec='libx264',quality=8)
            self.status='running';self.world.step(250)
            self.message='Episode started.'
        elif path=='/api/step':
            if self.status!='running':raise ValueError('Episode is not running.')
            step=float(body.get('step_m',.02))
            actions={}
            for arm in ['left','right']:
                seq=body.get(arm,['STILL'])
                if isinstance(seq,str):seq=[seq]
                if not isinstance(seq,list) or not 1<=len(seq)<=9 or any(t not in TOKENS for t in seq):
                    raise ValueError('Invalid bounded action sequence.')
                actions[arm]=seq
            n=max(map(len,actions.values()))
            if self.count+n>self.args.max_pairs:raise ValueError('Action budget exhausted. Submit the episode.')
            executed=0
            for i in range(n):
                pair={a:s[i] if i<len(s) else 'STILL' for a,s in actions.items()}
                before=self.world.d.time
                self.world.act_pair(pair,step)
                self.count+=1;executed+=1
                with (self.run/'actions.jsonl').open('a') as f:
                    f.write(json.dumps({'step':self.count,'actions':pair,'step_m':step,
                        'sim_start':before,'sim_end':self.world.d.time,'wall_time':time.time()})+'\n')
                with (self.run/'private_states.jsonl').open('a') as f:
                    f.write(json.dumps({'step':self.count,'positions':self.world.positions()})+'\n')
            self.message=f'Executed {executed} pair(s).'
            return {'ok':True,'executed':executed,'state':self.state()}
        elif path=='/api/stop':
            if self.status!='running':raise ValueError('Episode is not running.')
            self.status='submitted'
            result=self.world.judge(ORDERS[self.args.variant])
            self.world.step(500)
            self.writer.close();self.writer=None
            result.update({'steps':self.count,'video_frames':self.frame_count,'seed':self.args.seed,
                           'variant':self.args.variant,'demo_source':'simulated_robot'})
            self.write_json('result.json',result)
            Image.fromarray(self.mosaic).save(self.run/'final.png')
            self.message='Submitted. Episode locked; evaluation saved privately.'
            print('PRIVATE_RESULT',self.run, result['success'],flush=True)
        else:raise ValueError('Unsupported endpoint.')
        return {'ok':True,'message':self.message,'state':self.state()}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--variant',choices=ORDERS,default='A')
    ap.add_argument('--seed',type=int,default=17)
    ap.add_argument('--port',type=int,default=18621)
    ap.add_argument('--max-pairs',type=int,default=400)
    args=ap.parse_args();engine=Engine(args);jobs=queue.Queue()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,data,mime='application/json',status=200):
            if isinstance(data,dict):data=json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/':return self.reply((ROOT/'static/index.html').read_bytes(),'text/html; charset=utf-8')
            if path=='/recorder.js':return self.reply((ROOT/'static/recorder.js').read_bytes(),'text/javascript')
            if path=='/api/state':return self.reply(engine.state())
            if path.startswith('/stream/'):
                name=path.removeprefix('/stream/')
                if name not in engine.frames:return self.reply({},status=404)
                self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame')
                self.send_header('Cache-Control','no-store');self.end_headers()
                try:
                    while True:
                        data=engine.frames[name]
                        self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n')
                        self.wfile.flush();time.sleep(.15)
                except (BrokenPipeError,ConnectionResetError):return
            if path=='/demo.mp4':
                p=ROOT/'demos'/args.variant/'demo.mp4'
                if not p.exists():return self.reply({'error':'Demo unavailable'},status=503)
                size=p.stat().st_size;start,end=0,size-1
                header=self.headers.get('Range','')
                if header.startswith('bytes='):
                    try:
                        lo,hi=header[6:].split('-');start=int(lo or 0);end=min(int(hi) if hi else size-1,size-1)
                    except ValueError:return self.reply({},status=416)
                    if start>end or start<0:return self.reply({},status=416)
                self.send_response(206 if header else 200);self.send_header('Content-Type','video/mp4')
                self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
                if header:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                try:
                    with p.open('rb') as f:f.seek(start);self.wfile.write(f.read(end-start+1))
                except (BrokenPipeError,ConnectionResetError):pass
                return
            if path.startswith('/demo-frame/'):
                name=path.removeprefix('/demo-frame/')
                if name not in [f'{i:02}.jpg' for i in range(12)]:return self.reply({},status=404)
                p=ROOT/'demos'/args.variant/name
                return self.reply(p.read_bytes(),'image/jpeg') if p.exists() else self.reply({},status=404)
            return self.reply({},status=404)
        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'):
                return self.reply({'ok':False,'message':'Origin not allowed'},status=403)
            if urlparse(self.path).path=='/api/screen-chunk':
                from urllib.parse import parse_qs
                n=int(self.headers.get('Content-Length',0))
                if not 0<n<16000000:return self.reply({},status=413)
                seq=int(parse_qs(urlparse(self.path).query).get('seq',['-1'])[0])
                if seq!=getattr(engine,'screen_seq',0):return self.reply({},status=409)
                ext='mp4' if 'mp4' in self.headers.get('Content-Type','') else 'webm'
                with (engine.run/('webpage_capture.'+ext)).open('ab') as f:f.write(self.rfile.read(n))
                engine.screen_seq=seq+1
                return self.reply({'ok':True})
            try:
                n=int(self.headers.get('Content-Length',0))
                if n>4096:raise ValueError('Request too large')
                body=json.loads(self.rfile.read(n) or '{}')
                if not isinstance(body,dict):raise ValueError('Expected object')
            except (ValueError,json.JSONDecodeError):return self.reply({'ok':False,'message':'Invalid request'},status=400)
            path=urlparse(self.path).path
            if path=='/api/ui-event':
                # Optional click audit, not a source of task or scoring information.
                allowed={k:body[k] for k in ('kind','side','token','count','step_m') if k in body}
                with (engine.run/'gui_events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),**allowed})+'\n')
                return self.reply({'ok':True})
            done=threading.Event();slot={};jobs.put((path,body,done,slot))
            if not done.wait(180):return self.reply({'ok':False,'message':'Execution pending; check state'},status=504)
            return self.reply(slot)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    print('READY',args.port,'PRIVATE_RUN',engine.run,flush=True)
    try:
        while True:
            path,body,done,slot=jobs.get()
            try:slot.update(engine.execute(path,body))
            except Exception as e:
                # No traceback/internal state exposed to the browser.
                slot.update({'ok':False,'message':str(e) if isinstance(e,ValueError) else 'Execution error',
                             'state':engine.state()})
                print('SERVER_ERROR',repr(e),flush=True)
            finally:done.set()
    finally:
        if engine.writer:engine.writer.close()
        engine.renderer.close();server.shutdown()

if __name__=='__main__':main()
