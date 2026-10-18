"""Manager-only task review, persisted comments, and media access."""
import ast
import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Literal
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .config import ROOT


class Comment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    variant: Literal['all', 'A', 'B', 'C'] = 'all'
    author: str = Field(min_length=1, max_length=100)
    status: Literal['pending', 'keep', 'revise'] = 'pending'
    text: str = Field(min_length=1, max_length=8000)


def os_catalog(source, data=None):
    from .os_release import review_catalog
    return review_catalog(source,data)


def install_review(app, manager, secret, data, web_catalog, recordings, web_video):
    os_source = Path(os.environ.get('VIC_OS_SOURCE', '/opt/os-icl'))
    embodied_source = Path(os.environ.get('VIC_EMBODIED_SOURCE', str(ROOT / 'simulator')))
    database = data / 'task-reviews.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS comments (id TEXT PRIMARY KEY, kind TEXT, task TEXT, variant TEXT, author TEXT, status TEXT, text TEXT, created_at REAL)')
    def signing(value):
        return hmac.new(secret.encode(), ('review-access:'+value).encode(), hashlib.sha256).hexdigest()
    def access(request):
        bearer = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if bearer and hmac.compare_digest(bearer, secret):
            return
        raw = request.cookies.get('vic-review', '')
        stamp, _, signature = raw.partition('.')
        if not stamp.isdigit() or int(stamp) < time.time() or not hmac.compare_digest(signature, signing(stamp)):
            raise HTTPException(401, '请先登录任务审阅页')
    app.state.review_access = access

    @app.get('/design-handbook')
    def handbook(request: Request):
        access(request)
        return FileResponse(ROOT / 'docs/task-design.html', media_type='text/html', headers={'Cache-Control':'no-store'})

    @app.post('/review-api/access', dependencies=[Depends(manager)])
    def grant():
        stamp = str(int(time.time())+8*3600)
        r = JSONResponse(dict(ok=True))
        r.set_cookie('vic-review', stamp+'.'+signing(stamp), httponly=True, samesite='strict', max_age=8*3600)
        return r

    def embodied():
        manifest = json.loads((embodied_source / 'delivery8/release.private.json').read_text())
        return [dict(id=t['id'], kind='embodied', title=t['title'], platform='Tabletop8 · 双臂桌面仿真',
                     difficulty=t['difficulty'], length=t['length'], rules=t['rules'],
                     instruction=t['challenge']+'。依据所选版本的示范，在新的初始布局完成任务；完成后结束并保存执行结果。',
                     demo_source='仿真作者控制器示范（非真人录制）',
                     videos={v:[dict(label=f'{v} · 仿真作者示范', url=f"/review-api/media/embodied/{t['id']}/{v}")] for v in 'ABC'}) for t in manifest['tasks']]
    app.state.embodied_catalog = embodied

    def catalog():
        warnings = []; rows = []
        for t in web_catalog()['tasks']:
            rows.append(dict(id=str(t['id']), kind='web', title=t['title'], platform=' / '.join(t.get('platforms') or [t['app']]),
                             difficulty=t['difficulty'], rules={**t['variants'], **t['demo'].get('rule_explanations', {})},
                             instruction=t['inference'].get('goal') or t['inference']['instructions'],
                             constraints=t['inference'].get('constraints', []), delivery=t.get('delivery',''),
                             demo_source='同事上传录像', videos={v:[] for v in 'ABC'}))
        by_id = {r['id']:r for r in rows}
        for run in recordings():
            row = by_id.get(str(run['task_id']))
            if row is None:continue
            m = run['recording'] or {}
            if not m.get('available'):continue
            row['videos'][run['variant']].append(dict(label=f"{'v2' if run['manifest'].get('suite')=='v2' else 'v1'} · {'审核通过' if m.get('approved') else '待审核'} · {m.get('reviewer') or '未署名'} · 第 {run['epoch']+1} 轮",
                url=f"/review-api/media/web/{run['id']}/{run['epoch']}", historical=bool(m.get('archived') or m.get('contract_current') is False),
                created_at=run['created_at'], approved=bool(m.get('approved'))))
        for kind, reader in [('os', lambda:os_catalog(os_source,data)), ('embodied', embodied)]:
            try:rows.extend(reader())
            except (OSError, ValueError, KeyError, SyntaxError, StopIteration):warnings.append(f'{kind} 任务目录暂不可用，请检查服务资源挂载。')
        with sqlite3.connect(database) as db:
            counts = {(k,t):n for k,t,n in db.execute('SELECT kind,task,count(*) FROM comments GROUP BY kind,task')}
        for row in rows:
            row['comment_count'] = counts.get((row['kind'],row['id']),0)
            row['inference_url'] = f"/review?kind={row['kind']}&task={row['id']}&mode=inference"
        return dict(tasks=rows, warnings=warnings)

    @app.get('/review-api/tasks', dependencies=[Depends(manager)])
    def tasks():return catalog()

    def validate(kind, task):
        if kind == 'web' and task.isdigit() and 1 <= int(task) <= 75:return
        try:
            items = os_catalog(os_source,data) if kind == 'os' else embodied() if kind == 'embodied' else []
            if any(r['id']==task for r in items):return
        except (OSError,ValueError,KeyError):pass
        raise HTTPException(404, 'Task not found')

    @app.get('/review-api/tasks/{kind}/{task}/comments', dependencies=[Depends(manager)])
    def comments(kind:str, task:str):
        validate(kind,task)
        with sqlite3.connect(database) as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM comments WHERE kind=? AND task=? ORDER BY created_at DESC', (kind,task))]

    @app.post('/review-api/tasks/{kind}/{task}/comments', dependencies=[Depends(manager)], status_code=201)
    def comment(kind:str, task:str, body:Comment):
        validate(kind,task)
        if not body.text.strip() or not body.author.strip():raise HTTPException(422, '请填写署名和意见')
        row=dict(id=uuid.uuid4().hex, kind=kind, task=task, **body.model_dump(), created_at=time.time())
        with sqlite3.connect(database, timeout=15) as db:
            db.execute('INSERT INTO comments VALUES (:id,:kind,:task,:variant,:author,:status,:text,:created_at)',row)
        return row

    @app.get('/review-api/media/web/{run_id}/{epoch}')
    def recorded_video(run_id:str, epoch:int, request:Request):
        access(request)
        return web_video(run_id,epoch)

    @app.get('/review-api/media/{kind}/{task}/{variant}')
    def media(kind:Literal['os','embodied'], task:str, variant:Literal['A','B','C'], request:Request, take:int=0):
        access(request);validate(kind,task)
        if kind=='os':
            from .os_release import demo_file, demo_root
            try:_,path=demo_file(os_source,task,variant,take,data)
            except FileNotFoundError as exc:raise HTTPException(404,str(exc))
            except (ValueError,KeyError,OSError) as exc:raise HTTPException(503,str(exc))
            root=demo_root(os_source,data);mime='video/mp4'
        else:
            manifest=json.loads((embodied_source/'delivery8/release.private.json').read_text())
            entry=next(t for t in manifest['tasks'] if t['id']==task)
            root=embodied_source;path=(root/entry['demos'][variant]['folder']/'video.mp4').resolve();mime='video/mp4'
        if not path.is_relative_to(root.resolve()) or not path.is_file():raise HTTPException(404,'示范视频文件暂不可用')
        return FileResponse(path,media_type=mime)
