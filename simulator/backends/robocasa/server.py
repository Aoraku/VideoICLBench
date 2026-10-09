"""RoboCasa v0.2 console. --replay runs recorded controls, never a VLM.
State/geometry remain private; the browser receives only RGB + execution status.
"""
import os
os.environ.setdefault('MUJOCO_GL','egl')
import argparse,io,json,time,threading,queue,base64,hashlib,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import numpy as np,h5py,robosuite,robocasa
from PIL import Image
from robocasa.scripts.playback_dataset import reset_to
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18651);p.add_argument('--replay',action='store_true');p.add_argument('--episode',default='demo_2');p.add_argument('--dataset',required=True);p.add_argument('--demo-kind',choices=['human','sim'],default='human');p.add_argument('--run-label',default='');p.add_argument('--ui',default='index.html');p.add_argument('--media-dir',type=Path,default=None);p.add_argument('--run-root',type=Path,default=None);a=p.parse_args()
root=Path(__file__).resolve().parent
media=a.media_dir or root/'media'
f=h5py.File(a.dataset,'r');meta=json.loads(f['data'].attrs['env_args'])
k=meta['env_kwargs'];k.update(env_name=meta['env_name'],has_renderer=False,has_offscreen_renderer=True,use_camera_obs=False)
env=robosuite.make(**k)
ep=a.episode;d=f['data'][ep]
reset_to(env,{'states':d['states'][0],'model':d.attrs['model_file'],'ep_meta':d.attrs.get('ep_meta')})
from mug_scene import make_mug_scene
make_mug_scene(env)
if not a.replay:
 controller=env.robots[0].composite_controller.part_controllers['right']
 controller._goal_update_mode='desired'
 controller.goal_pos=None;controller.goal_ori=None
actions=d['actions'][:]; frames={}; cmds=queue.Queue(); count=0;status='ready';closed=False
message='Mug engineering replay — not an Agent run.' if a.replay else 'Watch the demonstration, then START. Right arm only.'
run_root=a.run_root or root/'private_runs'
label=a.run_label or uuid.uuid4().hex[:12]
if Path(label).name!=label or label in ('.','..'):raise ValueError('run-label must be a simple name')
run=run_root/label;run.mkdir(parents=True,exist_ok=False)
(run/'initial_state_sha256.txt').write_text(hashlib.sha256(env.sim.get_state().flatten().tobytes()).hexdigest())
(run/'provenance.json').write_text(json.dumps({'task':'MicrowaveMugCustom','episode':ep,'mode':'mug_engineering_replay' if a.replay else 'manual_GUI','VLM':False,'reset_policy':'initial state only; env.step for every subsequent action','versions':{'robocasa':robocasa.__version__,'robosuite':robosuite.__version__}},indent=2))
cameras={'overhead':'robot0_agentview_left','wrist_left':'robot0_agentview_right','agentview':'robot0_agentview_center','wrist_right':'robot0_eye_in_hand'}
def render():
 for key,cam in cameras.items():
  pixels=env.sim.render(height=288,width=384,camera_name=cam)[::-1]
  b=io.BytesIO();Image.fromarray(pixels).save(b,format='JPEG',quality=85);frames[key]=b.getvalue()
def state():
 return {'status':status,'steps':count,'max_pairs':len(actions) if a.replay else 1000,'gripper_closed':{'left':False,'right':closed},'controls_locked':a.replay and status=='running','recording':status=='running','message':message,'mode':'mug_engineering_replay' if a.replay else 'manual_GUI'}
def log(name,data):
 with (run/name).open('a') as h:h.write(json.dumps({'time':time.time(),**data})+'\n')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,data,kind='application/json',code=200):
  if not isinstance(data,bytes):data=json.dumps(data).encode()
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/api/state':return self.send(state())
  if path=='/':return self.send((root/a.ui).read_bytes(),'text/html; charset=utf-8')
  if path=='/demo.mp4':return self.send((media/('human_demo.mp4' if a.demo_kind=='human' else 'sim_demo.mp4')).read_bytes(),'video/mp4')
  if path.startswith('/demo-frame/') and path.rsplit('/',1)[-1] in [f'{i:02}.jpg' for i in range(16)]:return self.send((media/('demo_frames' if a.demo_kind=='human' else 'sim_demo_frames')/path.rsplit('/',1)[-1]).read_bytes(),'image/jpeg')
  if path.startswith('/snapshot/') and path.rsplit('/',1)[-1] in frames:
   b=io.BytesIO();Image.open(io.BytesIO(frames[path.rsplit('/',1)[-1]])).resize((256,192)).save(b,format='JPEG',quality=50);return self.send(b.getvalue(),'image/jpeg')
  if path.startswith('/stream/') and path.rsplit('/',1)[-1] in frames:
   key=path.rsplit('/',1)[-1];self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame');self.end_headers()
   try:
    while True:
     b=frames[key];self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(b)).encode()+b'\r\n\r\n'+b+b'\r\n');self.wfile.flush();time.sleep(.5)
   except (BrokenPipeError,ConnectionResetError):pass
   return
  self.send({'error':'Not found'},code=404)
 def do_POST(self):
  try:
   n=int(self.headers.get('Content-Length','0'))
   if n>8192:raise ValueError('request too large')
   body=json.loads(self.rfile.read(n) or b'{}')
   if self.path=='/api/ui-event':log('gui_events.jsonl',body);return self.send({'ok':True})
   if self.path not in ['/api/start','/api/step','/api/stop','/api/observe']:return self.send({'ok':False},code=404)
   reply=queue.Queue();cmds.put((self.path,body,reply));self.send(reply.get(timeout=90))
  except Exception as e:self.send({'ok':False,'message':str(e)},code=400)
render();threading.Thread(target=ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever,daemon=True).start();print('READY',a.port,flush=True)
translation={'MV_FWD':(1,0,0),'MV_BACK':(-1,0,0),'MV_LEFT':(0,1,0),'MV_RIGHT':(0,-1,0),'MV_UP':(0,0,1),'MV_DOWN':(0,0,-1)}
allowed=set(translation)|{'STILL','GRASP','RELEASE','ROTATE_CW','ROTATE_CCW','ROLL_POS','ROLL_NEG','PITCH_POS','PITCH_NEG'}
try:
 while True:
  try:path,body,reply=cmds.get(timeout=.001 if status=='running' and a.replay else .2)
  except queue.Empty:path=None
  if path:
   try:
    if path=='/api/observe':
     reply.put({'ok':True,'observation_id':count,'state':state(),'images':{key:base64.b64encode(value).decode() for key,value in frames.items()}})
     continue
    if 'expected_observation' in body and body['expected_observation']!=count:raise ValueError('Stale observation')
    if path=='/api/start':
     if status!='ready':raise ValueError('Already started')
     status='running'
    elif path=='/api/stop':
     if status!='running':raise ValueError('Submit requires a running episode')
     status='submitted';message='Submitted.'
     (run/'result.json').write_text(json.dumps({'success':bool(env._check_success() and env.sim.data.body_xmat[env.obj_body_id['obj']].reshape(3,3)[2,2]>.9),'upright_cos':float(env.sim.data.body_xmat[env.obj_body_id['obj']].reshape(3,3)[2,2]),'steps':count,'agent_run':None,'controller':'external_manual_actions'},indent=2))
    elif path=='/api/step':
     if a.replay or status!='running':raise ValueError('Manual controls unavailable in this mode/state')
     left=body.get('left',['STILL']);right=body.get('right',['STILL']);step=float(body.get('step_m',.02))
     if isinstance(left,str):left=[left]
     if isinstance(right,str):right=[right]
     if left!=['STILL']:raise ValueError('This platform task has one right arm')
     if not 1<=len(right)<=9 or any(t not in allowed for t in right) or step not in [.005,.01,.02] or count+len(right)>1000:raise ValueError('Invalid bounded action')
     for t in right:
      if t in ['GRASP','RELEASE']:closed=t=='GRASP'
      for sub in range(8):
       v=np.zeros(env.action_dim);v[6]=1 if closed else -1;v[-1]=1
       if sub==0:
        if t in translation:v[:3]=np.array(translation[t])*step/.05
        if t.startswith('ROTATE_'):v[5]=(1 if t=='ROTATE_CCW' else -1)*np.deg2rad(10)/.5
        if t.startswith('ROLL_'):v[3]=(1 if t=='ROLL_POS' else -1)*np.deg2rad(10)/.5
        if t.startswith('PITCH_'):v[4]=(1 if t=='PITCH_POS' else -1)*np.deg2rad(10)/.5
       env.step(v)
      count+=1;log('actions.jsonl',{'token':t,'step_m':step});render()
     message='Action completed.'
    reply.put({'ok':True,'state':state()})
   except Exception as e:reply.put({'ok':False,'message':str(e),'state':state()})
  if a.replay and status=='running':
   begun=time.monotonic();env.step(actions[count]);closed=bool(actions[count][6]>0);count+=1
   if count%2==0 or count==len(actions):render()
   if count%100==0:print('STEP',count,flush=True)
   if count==len(actions):
    result={'success':bool(env._check_success() and env.sim.data.body_xmat[env.obj_body_id['obj']].reshape(3,3)[2,2]>.9),'upright_cos':float(env.sim.data.body_xmat[env.obj_body_id['obj']].reshape(3,3)[2,2]),'steps':count,'agent_run':False,'mode':'mug_engineering_replay','episode':ep}
    (run/'result.json').write_text(json.dumps(result,indent=2));status='submitted';message='Mug engineering replay completed — not an Agent run.';print(result,flush=True)
   time.sleep(max(0,.05-(time.monotonic()-begun)))
finally:env.close();f.close()
