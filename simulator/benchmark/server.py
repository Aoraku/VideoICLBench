"""Loopback author API + capability-scoped image-only actor sessions."""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import subprocess
import sys
import threading
import time
from typing import Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .catalog import CATALOG, TASKS
from .provenance import harness_sha256

DATA=Path(os.environ.get('EMBODIED_DATA','.local/embodied50-data')).resolve()
DATA.mkdir(parents=True,exist_ok=True)
TOKEN_PATH=DATA/'admin.token'
if not TOKEN_PATH.exists():
    fd=os.open(TOKEN_PATH,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f: f.write(secrets.token_urlsafe(32))
ADMIN=TOKEN_PATH.read_text().strip()
LOCK=threading.RLock()
SESSIONS={}
from .protocol import TOKENS, CONDITIONS

def admin(authorization):
    if not secrets.compare_digest(authorization or '',f'Bearer {ADMIN}'):
        raise HTTPException(401,'Author token required')

class Create(BaseModel):
    model_config=ConfigDict(extra='forbid')
    task: str
    variant: str='A'
    seed: int=0
    condition: str='no_demo'
    trial_kind: Literal['manual_author','agent','author_replay','protocol_smoke']='manual_author'
    action_budget: int=Field(default=1000,ge=1,le=1000)
    wall_seconds: int=Field(default=1800,ge=1,le=3600)
class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    left: str='STILL'
    right: str='STILL'

class Session:
    def __init__(self,req):
        self.id=secrets.token_urlsafe(24); self.req=req; self.count=0; self.closed=False
        self.folder=DATA/'runs'/self.id; self.folder.mkdir(parents=True)
        self.started=time.monotonic(); self.touched=self.started
        self.logfile=(self.folder/'worker.log').open('w')
        self.proc=subprocess.Popen([sys.executable,'-m','simulator.benchmark.worker'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.logfile,text=True,bufsize=1)
        try: self.rpc(dict(op='init',task=req.task,variant=req.variant,seed=req.seed),timeout=300)
        except Exception:
            self.proc.kill(); self.proc.wait(); self.logfile.close(); raise
        self.started=time.monotonic(); self.touched=self.started
        manifest=dict(req.model_dump(),session=self.id,created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            catalog_sha256=hashlib.sha256(Path(__file__).with_name('tasks.json').read_bytes()).hexdigest(),
            harness_sha256=harness_sha256(),backend='robosuite-1.5.1',mujoco='3.2.6',action_interface='dual-tokens-v1',
            demo_sha256=demo_manifest(req).get('video_sha256'),status='running')
        (self.folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    def rpc(self,payload,timeout=120):
        self.proc.stdin.write(json.dumps(payload)+'\n'); self.proc.stdin.flush()
        if not select.select([self.proc.stdout],[],[],timeout)[0]: raise RuntimeError('Simulation timed out')
        line=self.proc.stdout.readline()
        if not line: raise RuntimeError('Simulation exited')
        result=json.loads(line)
        if 'error' in result: raise RuntimeError(result['error'])
        return result['result']
    def close(self,reason='submitted'):
        if self.closed: return
        self.closed=True
        try: score=self.rpc({'op':'score'},timeout=30)
        except Exception: score={'success':False,'error':'worker_unavailable'}
        result=dict(score,reason=reason,actions=self.count,wall_seconds=time.monotonic()-self.started,trial_kind=self.req.trial_kind)
        # Deadline expiry never converts into a successful submission.
        if reason!='submitted': result['success']=False
        (self.folder/'result.json').write_text(json.dumps(result,indent=2))
        try:
            self.rpc({'op':'close'},timeout=10); self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill(); self.proc.wait()
        self.logfile.close()
    def log(self,row):
        with (self.folder/'actions.jsonl').open('a') as f:
            f.write(json.dumps(dict(row,elapsed=time.monotonic()-self.started))+'\n')

def demo_manifest(req):
    if req.condition in ('no_demo','text'): return {}
    kind=req.condition.split('_')[0]
    path=DATA/'demos'/req.task/kind/'manifest.json'
    if not path.exists(): raise HTTPException(409,f'{kind} demo missing; author must import a validated A demonstration')
    m=json.loads(path.read_text())
    if m.get('task')!=req.task or m.get('variant')!='A' or not m.get('author_verified') or m.get('task_revision',1)!=TASKS[req.task].get('task_revision',1):
        raise HTTPException(409,'Demo requires author-verified A recording matching current task revision')
    return m

def session(sid):
    s=SESSIONS.get(sid)
    if not s: raise HTTPException(404,'Unknown session')
    if not s.closed and time.monotonic()-s.started>s.req.wall_seconds: s.close('wall_budget')
    if s.closed: raise HTTPException(410,'Episode ended')
    s.touched=time.monotonic()
    return s

def reaper(stop):
    while not stop.wait(5):
        with LOCK:
            for s in list(SESSIONS.values()):
                if not s.closed and time.monotonic()-s.started>s.req.wall_seconds: s.close('wall_budget')

@asynccontextmanager
async def lifespan(app):
    stop=threading.Event(); thread=threading.Thread(target=reaper,args=(stop,),daemon=True); thread.start()
    yield
    stop.set()
    with LOCK:
        for s in SESSIONS.values(): s.close('shutdown')

app=FastAPI(title='VideoICL Embodied 50',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
@app.get('/health')
def health(): return {'ok':True,'tasks':len(TASKS),'backend':'robosuite-dual-panda','active':sum(not s.closed for s in SESSIONS.values())}
@app.get('/admin/catalog')
def catalog(authorization: str|None=Header(default=None)):
    admin(authorization)
    availability={}
    for task,spec in TASKS.items():
        availability[task]={}
        for kind in ('sim','human'):
            root=DATA/'demos'/task/kind
            try:
                manifest=json.loads((root/'manifest.json').read_text())
                ready=(manifest.get('task')==task and manifest.get('variant')=='A'
                    and manifest.get('author_verified') and manifest.get('task_revision',1)==spec.get('task_revision',1)
                    and (root/'video.mp4').is_file() and all((root/f'frame{i:02d}.jpg').is_file() for i in range(16)))
            except (OSError,ValueError):ready=False
            availability[task][kind]=bool(ready)
    return dict(CATALOG,demonstrations=availability)
@app.post('/admin/sessions')
def create(req:Create,authorization: str|None=Header(default=None)):
    admin(authorization)
    if req.task not in TASKS or req.variant not in ('A','B','C') or req.condition not in CONDITIONS:
        raise HTTPException(422,'Invalid task, variant or condition')
    demo_manifest(req)
    with LOCK:
        if any(not s.closed for s in SESSIONS.values()): raise HTTPException(409,'One CPU world at a time; finish the active session first')
        try: s=Session(req)
        except HTTPException: raise
        except Exception as e: raise HTTPException(503,str(e)) from e
        SESSIONS[s.id]=s
        return {'session':s.id,'actor_url':f'/s/{s.id}','observe_url':f'/actor/{s.id}/observe'}
@app.get('/admin/results/{sid}')
def results(sid:str,authorization: str|None=Header(default=None)):
    admin(authorization)
    if not all(c.isalnum() or c in '-_' for c in sid): raise HTTPException(404)
    p=DATA/'runs'/sid/'result.json'
    if not p.exists(): raise HTTPException(404,'Result not ready')
    return json.loads(p.read_text())
@app.post('/admin/cancel/{sid}')
def cancel(sid:str,authorization: str|None=Header(default=None)):
    admin(authorization)
    with LOCK: session(sid).close('cancelled')
    return {'ended':True}
@app.get('/actor/{sid}/observe')
def observe(sid:str):
    with LOCK:
        s=session(sid)
        try: result=s.rpc({'op':'observe'})
        except Exception:
            s.close('worker_error'); raise HTTPException(503,'Worker failed')
        frame=s.folder/'observations'/f'{s.count:04d}'; frame.mkdir(parents=True,exist_ok=True)
        for name,data in result['images'].items(): (frame/f'{name}.jpg').write_bytes(base64.b64decode(data))
        return dict(result,actions=s.count,remaining=s.req.action_budget-s.count,
                    seconds_remaining=max(0,int(s.req.wall_seconds-(time.monotonic()-s.started))))
@app.post('/actor/{sid}/action')
def action(sid:str,req:Action):
    if req.left not in TOKENS or req.right not in TOKENS: raise HTTPException(422,'Invalid token')
    with LOCK:
        s=session(sid)
        if s.count>=s.req.action_budget: raise HTTPException(409,'Action budget reached; submit episode')
        s.count+=1; s.log(dict(index=s.count,left=req.left,right=req.right))
        try: s.rpc(dict(op='action',**req.model_dump()))
        except Exception:
            s.close('worker_error'); raise HTTPException(503,'Worker failed')
        return {'accepted':True,'actions':s.count,'remaining':s.req.action_budget-s.count}
@app.post('/actor/{sid}/submit')
def submit(sid:str):
    with LOCK: session(sid).close()
    return {'ended':True}  # no success, goal, state, reward, or predicate returned to actor
@app.get('/actor/{sid}/demo')
def demo(sid:str):
    with LOCK:
        s=session(sid); condition=s.req.condition
        if condition=='no_demo': return {'condition':condition}
        if condition=='text': return {'condition':condition,'instruction':TASKS[s.req.task]['title']}
        m=demo_manifest(s.req); kind=condition.split('_')[0]
        root=DATA/'demos'/s.req.task/kind
        if condition.endswith('_video'): return {'condition':condition,'video':f'/actor/{sid}/demo/video','duration':m['duration']}
        return {'condition':condition,'frames':[base64.b64encode((root/f'frame{i:02d}.jpg').read_bytes()).decode() for i in range(16)]}
@app.get('/actor/{sid}/demo/video')
def video(sid:str):
    with LOCK:
        s=session(sid)
        if not s.req.condition.endswith('_video'): raise HTTPException(404)
        demo_manifest(s.req)
        path=DATA/'demos'/s.req.task/s.req.condition.split('_')[0]/'video.mp4'
        return FileResponse(path,media_type='video/mp4')
@app.get('/s/{sid}',response_class=HTMLResponse)
def ui(sid:str):
    with LOCK: session(sid)
    return Path(__file__).with_name('operator.html').read_text().replace('__SESSION__',sid)
