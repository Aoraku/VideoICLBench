"""OS-ICL lifecycle and pixel-only agent transport; grading stays upstream."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from typing import Literal

from .runtime import BrowserRuntime
from .schemas import Action
from . import os_release, human_recording


class OSRunRequest(BaseModel):
    case_id: str = Field(pattern=r"^OS-[EMH]-\d{2}$")
    variant: Literal["A", "B", "C"] = "A"
    seed: int = Field(default=20261005, ge=0, le=2**31-1)
    interaction: Literal["human", "agent"] = "human"
    mode: Literal["demo", "eval"] = "eval"
    timeout_seconds: int = Field(default=3600, ge=30, le=7200)
    max_actions: int = Field(default=800, ge=1, le=5000)


def install_os_routes(app, manager, secret: str, data: Path, *, upstream=None, source=None, runtime=None):
    upstream = upstream or os.environ.get("VIC_OS_BASE", "http://os:8790")
    source = Path(source or os.environ.get("VIC_OS_SOURCE", "/opt/os-icl"))
    runs = data / "os-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runtime = runtime or BrowserRuntime(viewport={"width": 1280, "height": 720}, locale="en-US")
    app.state.os_runtime = runtime
    locks = {}

    def lock(sid):
        return locks.setdefault(sid, asyncio.Lock())

    def save(run):
        target = runs / (run["id"] + ".json")
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(run, ensure_ascii=False, indent=2))
        temp.chmod(0o600)
        temp.replace(target)

    def read(sid):
        if not sid.startswith("osl_") or not sid[4:].isalnum():
            raise HTTPException(404, "OS run not found")
        path = runs / (sid + ".json")
        if not path.is_file():
            raise HTTPException(404, "OS run not found")
        return json.loads(path.read_text())

    def browser_token(sid):
        return hmac.new(secret.encode(), ("os-browser:" + sid).encode(), "sha256").hexdigest()

    def authorize(run, request, *, browser=False):
        provided = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if hmac.compare_digest(provided, secret):
            return
        if browser:
            supplied = request.query_params.get("access") or request.cookies.get("vic-os", "")
            if hmac.compare_digest(supplied, browser_token(run["id"])):
                return
        elif hmac.compare_digest(hashlib.sha256(provided.encode()).hexdigest(), run["token_hash"]):
            return
        raise HTTPException(403, "OS session credential required")

    async def api(path, method="GET", body=None):
        try:
            async with httpx.AsyncClient(base_url=upstream, timeout=30) as client:
                response = await client.request(method, path, json=body)
        except httpx.RequestError:
            raise HTTPException(503, "OS service unavailable")
        if response.status_code >= 400:
            raise HTTPException(response.status_code, "OS service rejected the request")
        return response.json()

    def demo(case_id, variant, take=0):
        try:return os_release.demo_file(source,case_id,variant,take,data)
        except FileNotFoundError as exc:raise HTTPException(404,str(exc))
        except (OSError,ValueError,KeyError) as exc:raise HTTPException(503,str(exc))

    def catalogue():
        try:return os_release.catalog(source)
        except (OSError,ValueError,KeyError) as exc:raise HTTPException(503,str(exc))

    def media():
        try:return os_release.demonstrations(source,data)
        except (OSError,ValueError,KeyError) as exc:raise HTTPException(503,str(exc))

    def launch(run):
        return f"/os-sim/{run['id']}/?access={browser_token(run['id'])}"

    def public(run):
        return {k: run[k] for k in ("id", "case_id", "variant", "seed", "interaction", "created_at", "status", "public_task", "demo_sha256", "benchmark_version")} | {
            "application_url": launch(run), "result": run.get("result"), "demonstrations":run.get("demonstrations",[]), "demo_notice":run.get("demo_notice", ""), "mode":run.get("mode","eval"), "lesson":run.get("lesson"), "recording":run.get("recording")}

    @app.get("/os-api/cases", dependencies=[Depends(manager)])
    async def cases():
        release=catalogue();result=await api('/api/v2/cases')
        if result.get('benchmark_version')!=release['benchmark_version'] or {c['id'] for c in result['cases']}!={c['id'] for c in release['cases']}:
            raise HTTPException(503,'OS service and platform release do not match')
        entries,notice=media()
        return dict(cases=[{**c,'recording_status':{v:('已完成录制' if any(e.get('approved') for e in entries if e['case_id']==c['id'] and e['convention']=='ABC'.index(v) and not e['historical']) else '待审核' if any(e['case_id']==c['id'] and e['convention']=='ABC'.index(v) and not e['historical'] for e in entries) else '待录制') for v in 'ABC'}} for c in release['cases']],demonstrations=len(entries),benchmark_version=release['benchmark_version'],demo_notice=notice)

    @app.get('/os-api/cases/{case_id}/demos',dependencies=[Depends(manager)])
    async def case_demos(case_id:str,variant:Literal['A','B','C']='A'):
        if case_id not in {c['id'] for c in catalogue()['cases']}:raise HTTPException(404,'OS task not found')
        entries,notice=media()
        choices=[e for e in entries if e['case_id']==case_id and e['convention']=='ABC'.index(variant)]
        return dict(videos=[dict(run_id=e['run_id'],approved=e.get('approved',False),historical=e['historical'],created_at=e['created_at'],seed=e['seed'],sha256=e['sha256'],label=f"seed {e['seed']} · {e.get('recording_actor','来源未标注')} · 视觉审核 {e['visual_review']}",
                         url=f'/os-api/cases/{case_id}/demo?variant={variant}&take={i}') for i,e in enumerate(choices)],notice=notice)

    @app.get('/os-api/cases/{case_id}/demo',dependencies=[Depends(manager)])
    async def case_demo(case_id:str,variant:Literal['A','B','C']='A',take:int=0):
        _,path=demo(case_id,variant,take)
        return FileResponse(path,media_type='video/mp4')

    @app.post('/os-api/runs',dependencies=[Depends(manager)])
    async def create(body:OSRunRequest):
        release=catalogue();case=next((c for c in release['cases'] if c['id']==body.case_id),None)
        if not case:raise HTTPException(404,'OS task not found')
        entries,notice=media()
        choices=[e for e in entries if e['case_id']==body.case_id and e['convention']=='ABC'.index(body.variant)
                 and e.get('approved') and not e['historical'] and e.get('recording_actor')=='human_browser']
        if body.mode=='eval' and body.seed in set(case['demo_seeds']) | {seed for e in choices for seed in e['example_seeds']}:
            raise HTTPException(422,'Evaluation seed must differ from demonstration seeds')
        if body.interaction=='agent' and (body.mode!='eval' or not choices):
            raise HTTPException(409,'需要先录制并审核一段包含全部局部示例的人工 demo。')
        chosen=choices[-1:]
        for entry in chosen:os_release.recording_file(source,entry,data)
        sessions=[]
        for seed in (case['demo_seeds'] if body.mode=='demo' else [body.seed]):
            session=await api('/api/v2/sessions','POST',dict(case_id=body.case_id,convention='ABC'.index(body.variant),seed=seed,
                mode='practice' if body.mode=='demo' else 'evaluation',plan_variant='module-demo' if body.mode=='demo' else 'standard',
                external_task_id='videoicl:'+body.case_id,recording_actor='human_browser' if body.mode=='demo' else 'not-attested'))
            if not session.get('compatible') or session['benchmark_version']!=release['benchmark_version']:
                raise HTTPException(503,'OS session implementation is incompatible')
            sessions.append(session)
        actor=secrets.token_urlsafe(32);session=sessions[0]
        run={**body.model_dump(),'id':session['id'],'token_hash':hashlib.sha256(actor.encode()).hexdigest(),
            'created_at':time.time(),'status':'running','benchmark_version':session['benchmark_version'],
            'fingerprint':release['implementation']['fingerprint'],'design_version':release['design_version'],
            'public_task':dict(assignment=session['case']['task'],title=case['title']),
            'demo_sha256':chosen[0]['sha256'] if chosen else None,'result':None,'demo_notice':notice,
            'demonstrations':[dict(id=e['id'],seed=e['seed'],sha256=e['sha256'],url=f"/os-api/runs/{session['id']}/demo") for e in chosen]}
        if body.mode=='demo':
            run['lesson']={'sessions':[s['id'] for s in sessions],'seeds':case['demo_seeds'],'index':0,'total':len(sessions),'finished':False,'results':[]}
        save(run)
        for child in sessions[1:]:save({**run,'id':child['id'],'lesson_root':run['id'],'lesson':None})
        return {**public(run),'actor_token':actor}

    @app.get("/os-api/runs/{sid}", dependencies=[Depends(manager)])
    async def get_run(sid):
        run=read(sid)
        if run.get("lesson_root"):run=read(run["lesson_root"])
        result=public(run)
        result['current_design']=run.get('fingerprint')==catalogue()['implementation']['fingerprint']
        if run.get("lesson"):result["application_url"]=launch(read(run["lesson"]["sessions"][run["lesson"]["index"]]))
        return result

    @app.get("/os-api/runs/{sid}/demo")
    async def run_demo(sid: str, request: Request, take:int=0):
        run = read(sid); authorize(run, request)
        entries=run.get('demonstrations',[])
        if take<0 or take>=len(entries):raise HTTPException(404,'Demo unavailable')
        entry_path=os_release.demo_root(source,data)/(entries[take]['id']+'.json')
        entry=json.loads(entry_path.read_text())
        if not entry.get('approved') or entry['sha256']!=entries[take]['sha256']:raise HTTPException(409,'Demo approval or checksum changed')
        return FileResponse(os_release.recording_file(source,entry,data),media_type='video/mp4')

    async def agent_ready(sid, request):
        run = read(sid); authorize(run, request)
        if run["interaction"] != "agent" or run["status"] != "running":
            raise HTTPException(409, "OS agent environment is not running")
        # Never silently recreate a lost browser and overwrite an in-flight task.
        if run.get("browser_started") and sid not in runtime.sessions:
            raise HTTPException(409, "OS environment interrupted; start a fresh run")
        runtime.limits[sid] = {k: run[k] for k in ("timeout_seconds", "max_actions")}
        url = "http://127.0.0.1:8765" + launch(run)
        if not run.get("browser_started"):
            await runtime.ensure(sid, url)
            run["browser_started"] = True; save(run)
        return run, url

    @app.get("/os-api/runs/{sid}/observation")
    async def observe(sid: str, request: Request):
        async with lock(sid):
            _, url = await agent_ready(sid, request)
            return {**await runtime.screenshot(sid, url), "epoch": 0}

    @app.post("/os-api/runs/{sid}/actions")
    async def act(sid: str, body: Action, request: Request):
        async with lock(sid):
            _, url = await agent_ready(sid, request)
            if body.epoch != 0 or any(v is not None and v >= 720 for v in (body.y, body.to_y)):
                raise HTTPException(422, "Coordinates or epoch outside the OS viewport")
            try:
                return await runtime.act(sid, url, body)
            except ValueError as exc:
                raise HTTPException(409, str(exc))

    @app.post('/os-api/runs/{sid}/check',dependencies=[Depends(manager)])
    async def check(sid:str):
        run=read(sid)
        if run.get('lesson'):
            lesson=run['lesson']
            results=[(await api(f'/api/v2/sessions/{child}/judge','POST',{}))['result'] for child in lesson['sessions']]
            return {'success':all(r['success'] for r in results),'groups':results,'passed':sum(r['success'] for r in results),'total':len(results)}
        return (await api(f'/api/v2/sessions/{sid}/judge','POST',{}))['result']

    @app.post('/os-api/runs/{sid}/eval', dependencies=[Depends(manager)])
    async def evaluate(sid:str):
        async with lock(sid):
            run=read(sid)
            if run.get('mode')=='demo':return await check(sid)
            if run.get('result') is None:
                session=await api(f'/api/v2/sessions/{sid}/finish','POST',{})
                run.update(result=session['result'],status='completed');save(run);await runtime.close_run(sid)
            return {'run_id':sid,**run['result']}

    async def advance(sid):
        child=read(sid);root_id=child.get('lesson_root',sid)
        async with lock(root_id):
            run=read(root_id);lesson=run.get('lesson')
            if not lesson:raise HTTPException(404,'Not a demonstration')
            if lesson['sessions'][lesson['index']]!=sid:raise HTTPException(409,'This example is no longer active')
            if not lesson['finished']:
                result=(await api(f'/api/v2/sessions/{sid}/judge','POST',{}))['result']
                if not result['success']:raise HTTPException(409,'本组尚未完成。请核对操作范围和保存结果，再继续。')
                lesson['results'].append(result)
                await api(f'/api/v2/sessions/{sid}/finish','POST',{})
                if lesson['index']+1==lesson['total']:
                    lesson['finished']=True;run['result']={'success':True,'passed':lesson['total'],'total':lesson['total']}
                else:lesson['index']+=1
                save(run)
            return dict(finished=lesson['finished'],application_url=launch(read(lesson['sessions'][lesson['index']])) )

    @app.post('/os-api/runs/{sid}/recordings/upload',dependencies=[Depends(manager)])
    async def upload(sid:str,request:Request):
        async with lock(sid):
            run=read(sid)
            if not run.get('lesson'):raise HTTPException(409,'只能为示范环境上传录像')
            mime=request.headers.get('Content-Type','').split(';')[0]
            if mime not in {'video/mp4','video/webm'}:raise HTTPException(415,'请上传 WebM 或 MP4')
            root=os_release.demo_root(source,data);root.mkdir(parents=True,exist_ok=True)
            rid=uuid.uuid4().hex;incoming=root/(rid+'.upload');output=root/(rid+'.mp4')
            try:
                size=0
                with incoming.open('wb') as stream:
                    async for chunk in request.stream():
                        size+=len(chunk)
                        if size>human_recording.MAX_BYTES:raise HTTPException(413,'录像不得超过 150 MB')
                        stream.write(chunk)
                try:meta=await asyncio.to_thread(human_recording.convert,incoming,output,mime,0)
                except ValueError as exc:raise HTTPException(422,str(exc))
                with output.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                entry={**meta,'id':rid,'run_id':sid,'case_id':run['case_id'],'convention':'ABC'.index(run['variant']),
                    'seed':run['lesson']['seeds'][0],'example_seeds':run['lesson']['seeds'], 'video':output.name,'sha256':digest,
                    'recording_actor':'human_browser','approved':False,'created_at':time.time(),
                    'design_version':run['design_version'],'fingerprint':run['fingerprint']}
                (root/(rid+'.json')).write_text(json.dumps(entry,ensure_ascii=False,indent=2))
                run['recording']=entry;save(run);return entry
            finally:
                incoming.unlink(missing_ok=True)
                if not (root/(rid+'.json')).exists():output.unlink(missing_ok=True)

    @app.get('/os-api/runs/{sid}/recordings/video',dependencies=[Depends(manager)])
    async def recorded_video(sid:str):
        entry=read(sid).get('recording')
        if not entry:raise HTTPException(404,'尚无录像')
        return FileResponse(os_release.recording_file(source,entry,data),media_type='video/mp4')

    @app.post('/os-api/runs/{sid}/recordings/review',dependencies=[Depends(manager)])
    async def review_recording(sid:str,request:Request):
        async with lock(sid):
            body=await request.json();reviewer=str(body.get('reviewer','')).strip();note=str(body.get('note','')).strip()
            if not reviewer or len(reviewer)>100 or len(note)>8000:raise HTTPException(422,'请填写有效审核人和备注')
            run=read(sid);entry=run.get('recording')
            if not entry:raise HTTPException(409,'请先上传录像')
            if entry['fingerprint']!=catalogue()['implementation']['fingerprint']:raise HTTPException(409,'录像与当前任务版本不匹配')
            result=await check(sid)
            if not result['success']:raise HTTPException(409,'所有示范组通过自动检查后才能审核')
            os_release.recording_file(source,entry,data)
            entry.update(approved=True,reviewer=reviewer,note=note,reviewed_at=time.time(),checks=result,status='approved')
            path=os_release.demo_root(source,data)/(entry['id']+'.json');temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps(entry,ensure_ascii=False,indent=2));temp.replace(path)
            save(run);return entry

    @app.api_route("/os-sim/{sid}/{path:path}", methods=["GET", "POST"])
    async def proxy(sid: str, path: str, request: Request):
        run = read(sid); authorize(run, request, browser=True)
        base = f"/os-sim/{sid}"
        if request.query_params.get("access"):
            response = RedirectResponse(base + f"/?session={sid}", status_code=303)
            response.set_cookie("vic-os", browser_token(sid), httponly=True, samesite="strict", path=base+"/")
            return response
        if path=='lesson-next' and request.method=='POST':return await advance(sid)
        allowed_static={'','desktop.js','desktop.css','lesson-controls.js'}
        allowed_api={f'api/v2/sessions/{sid}',f'api/v2/sessions/{sid}/action',f'api/v2/sessions/{sid}/ui-event',f'api/v2/sessions/{sid}/finish'}
        if path=='lesson-controls.js':
            owner=read(run.get('lesson_root',sid));lesson=owner.get('lesson')
            if not lesson:raise HTTPException(404)
            code='''const b=document.createElement('button'); b.textContent=LABEL; Object.assign(b.style,{position:'fixed',right:'16px',bottom:'56px',zIndex:'99999',padding:'12px',borderRadius:'8px'});document.body.append(b);b.onclick=async()=>{b.disabled=true;try{const r=await fetch('lesson-next',{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.detail);if(d.finished){b.textContent='示范已完成，请返回工作台保存和审核';}else location.replace(d.application_url);}catch(e){alert(e.message);b.disabled=false;}};'''.replace('LABEL',json.dumps(f"示范 {lesson['index']+1}/{lesson['total']} · "+('完成练习' if lesson['index']+1==lesson['total'] else '下一组')))
            return Response(code,media_type='text/javascript')
        if path not in allowed_static|allowed_api or (request.method=='POST' and not path.endswith(('/action','/ui-event','/finish'))):
            raise HTTPException(404,'OS route unavailable')
        if request.method=='POST' and run['status']!='running':raise HTTPException(409,'OS session is completed')
        try:
            async with httpx.AsyncClient(base_url=upstream,timeout=30) as client:
                response=await client.request(request.method,'/'+path,content=await request.body(),
                    headers={'Content-Type':request.headers.get('Content-Type','application/json')})
        except httpx.RequestError:raise HTTPException(503,'OS service unavailable')
        content=response.content;mime=response.headers.get('Content-Type','application/octet-stream')
        if path=='':
            content=content.decode().replace('href="/',f'href="{base}/').replace('src="/',f'src="{base}/').encode()
            if run.get('mode')=='demo':content=content.replace(b'</body>',f'<script src="{base}/lesson-controls.js"></script></body>'.encode())
        elif path=='desktop.js':
            text=content.decode()
            if 'fetch(url,' not in text:raise HTTPException(503,'OS frontend transport is incompatible')
            text=text.replace('fetch(url,',f'fetch({json.dumps(base)} + url,')
            # Task goals belong to the external prompt, never desktop chrome.
            text=text.replace("${btn('task-info','Task instructions')}",'')
            content=text.encode()
        return Response(content, status_code=response.status_code, headers={"Content-Type": mime})
