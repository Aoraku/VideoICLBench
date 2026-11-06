"""GUI transport only. Main-thread queue keeps physics frozen between commits."""
import base64,hashlib,hmac,io,json,os,queue,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from PIL import Image
from .control import TOKENS
from .profiles import PROTOCOL


def serve(controller,scene,simulation,out,port,budget=1000,demo=None,manager_token=None,author_preview=False):
    from .checkpoint import save as checkpoint
    out=Path(out)
    if demo:
        demo=Path(demo)
        validation=json.loads(demo.with_name('demo.private.json').read_text())
        if scene.spec.get('status')=='template-generated-pending-asset-adapter':
            raise ValueError('A generic template preview is not a task demonstration')
        if scene.spec.get('task_adapter') and (
                validation.get('task_adapter')!=scene.spec['task_adapter'] or
                validation.get('task_revision')!=scene.spec.get('task_revision')):
            raise ValueError('Demonstration was recorded for another task recipe revision')
        if not (validation.get('success') and validation.get('seed')==0
                and validation.get('backend')=='isaaclab_physx'
                and validation.get('protocol')==PROTOCOL
                and validation.get('embodiment')==scene.embodiment.name
                and validation.get('layout_profile')==scene.spec['layout_profile']
                and validation.get('camera_profile')==scene.spec['camera_profile']
                and validation.get('embodiment_config_sha256')==scene.spec['embodiment_config_sha256']
                and validation.get('task')==scene.spec['id'] and validation.get('variant')==scene.spec['variant']
                and validation.get('video_sha256')==hashlib.sha256(demo.read_bytes()).hexdigest()):
            raise ValueError('A validated independent Isaac Lab demonstration is required')
    jobs=queue.Queue();episode=uuid.uuid4().hex;status='ready';frames={}
    names={'head':'head','wrist_left':'left_wrist','wrist_right':'right_wrist'}
    def refresh():
        for _ in range(3):simulation.render();scene.update(simulation.get_physics_dt())
        for name,key in names.items():
            buffer=io.BytesIO();Image.fromarray(scene.cameras[key].data.output['rgb'][0,:,:,:3].cpu().numpy()).save(buffer,format='JPEG',quality=94)
            frames[name]=buffer.getvalue()
    def state():return dict(status=status,steps=controller.steps,max_pairs=budget,
        gripper_closed={s:x<.01 for s,x in controller.grips.items()},recording=status=='running',
        supported_actions=sorted(TOKENS),message='Follow the demonstration.')
    def append(name,value):
        with (out/name).open('a') as f:f.write(json.dumps(value)+'\n');f.flush();os.fsync(f.fileno())
    refresh()
    protocol=dict(episode_id=episode,live_cameras=list(names),camera_profile=scene.spec['camera_profile'],backend='isaaclab_physx',
        rule_version=PROTOCOL,
        embodiment=scene.embodiment.name,layout_profile=scene.spec['layout_profile'],
        control_frame='grasp_center',embodiment_config_sha256=scene.spec['embodiment_config_sha256'],
        task=scene.spec['id'],variant=scene.spec['variant'],seed=scene.spec['seed'],budget=budget,
        paused_between_actions=True,simulation_seconds_per_step=scene.embodiment.config['physics']['action_seconds'],
        demo_video_sha256=hashlib.sha256(demo.read_bytes()).hexdigest() if demo else None,
        mode='author_preview' if author_preview else 'evaluation')
    checkpoint(controller,out,episode,status,budget)
    class Handler(BaseHTTPRequestHandler):
        def manager(self):return bool(manager_token and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+manager_token))
        def log_message(self,*a):pass
        def reply(self,value,mime='application/json'):
            data=json.dumps(value).encode() if mime=='application/json' else value
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.path=='/api/private-result':
                if not self.manager():return self.send_error(403)
                name='result.provisional.private.json' if status=='budget_paused' else 'result.private.json'
                path=out/name
                return self.reply(json.loads(path.read_text())) if path.exists() else self.send_error(409)
            if self.path=='/':return self.reply((Path(__file__).resolve().parents[1]/'ui/index.html').read_bytes(),'text/html; charset=utf-8')
            if self.path=='/api/state':return self.reply(state())
            if self.path=='/api/protocol':return self.reply(protocol)
            if self.path=='/api/observe':return self.reply(dict(state=state(),images={k:base64.b64encode(v).decode() for k,v in frames.items()}))
            if self.path=='/demo.mp4' and demo:return self.reply(demo.read_bytes(),'video/mp4')
            if self.path.startswith('/stream/'):
                name=self.path.rsplit('/',1)[-1]
                if name not in frames:return self.send_error(404)
                self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame');self.end_headers()
                try:
                    while True:
                        b=frames[name];self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(b)).encode()+b'\r\n\r\n'+b+b'\r\n');self.wfile.flush();time.sleep(.5)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            self.send_error(404)
        def do_POST(self):
            try:body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
            except ValueError:return self.send_error(400)
            if self.path=='/api/ui-event':append('gui_events.jsonl',dict(time=time.time(),**body));return self.reply(dict(ok=True))
            if self.path in ('/api/checkpoint','/api/budget') and not self.manager():return self.send_error(403)
            if self.path not in ('/api/start','/api/step','/api/stop','/api/abort','/api/checkpoint','/api/budget'):return self.send_error(404)
            event=threading.Event();slot={};jobs.put((self.path,body,event,slot))
            event.wait();self.reply(slot)
    http=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    print('READY '+str(port),flush=True)
    try:
        while True:
            path,body,event,slot=jobs.get()
            try:
                if path=='/api/start':
                    if status!='ready':raise ValueError('Already started')
                    if demo is None and not author_preview:raise ValueError('No newly validated Isaac Lab demo assigned; evaluation is not ready')
                    status='running';controller.started=True
                elif path=='/api/step':
                    if status!='running':raise ValueError('Episode not running')
                    left,right=body.get('left',['STILL']),body.get('right',['STILL'])
                    if any(not isinstance(seq,list) or not 1<=len(seq)<=9 or any(t not in TOKENS for t in seq) for seq in (left,right)):raise ValueError('Invalid action queue')
                    count=max(len(left),len(right))
                    if controller.steps+count>budget:raise ValueError('Queue exceeds remaining step budget; shorten the queue')
                    for i in range(count):
                        commands=[left[i] if i<len(left) else 'STILL',right[i] if i<len(right) else 'STILL']
                        pending=out/'action_pending.private.json'
                        pending.write_text(json.dumps(dict(step_before=controller.steps,commands=commands)))
                        receipt=controller.action(*commands,step_mm=float(body.get('step_m',.02))*1000)
                        append('actions.jsonl',dict(time=time.time(),left=commands[0],right=commands[1],**receipt))
                        if controller.steps==budget:status='budget_paused'
                        checkpoint(controller,out,episode,status,budget);pending.unlink()
                    refresh()
                    if status=='budget_paused':
                        score=dict(controller.evaluator.result(),steps=controller.steps,reason='step_budget_reached',
                            resume_available=True,outcome='budget_paused',episode_id=episode)
                        (out/'result.provisional.private.json').write_text(json.dumps(score,indent=2))
                elif path=='/api/stop':
                    if status not in ('running','submitted','budget_paused'):raise ValueError('Cannot score an unstarted or aborted episode')
                    if status=='budget_paused':
                        slot.update(ok=True,state=state(),resume_available=True);continue
                    if status!='submitted':
                        score=dict(controller.evaluator.result(),steps=controller.steps,reason='submitted')
                        (out/'result.private.json').write_text(json.dumps(score,indent=2))
                        status='submitted';refresh()
                        checkpoint(controller,out,episode,status,budget)
                elif path=='/api/abort':status='aborted'
                elif path=='/api/checkpoint':
                    slot.update(checkpoint=checkpoint(controller,out,episode,status,budget))
                elif path=='/api/budget':
                    total=body.get('max_pairs')
                    if type(total) is not int or total<=budget:raise ValueError('Explicitly supply a larger cumulative step allowance')
                    if status not in ('running','budget_paused'):raise ValueError('Only a live unfinished world can continue')
                    budget=total;protocol['budget']=budget;status='running'
                    (out/'protocol.json').write_text(json.dumps(protocol,indent=2));checkpoint(controller,out,episode,status,budget)
                slot.update(ok=True,state=state())
            except Exception as exc:slot.update(ok=False,message=type(exc).__name__+': '+str(exc),state=state())
            finally:event.set()
    finally:http.shutdown();http.server_close()
