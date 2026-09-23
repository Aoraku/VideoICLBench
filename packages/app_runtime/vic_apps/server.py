"""Application worker: business operations only, no evaluation endpoints."""

import asyncio
import hashlib
import base64
import hmac
import json
import os
from pathlib import Path
import re
from fastapi import FastAPI, Header, HTTPException, Depends, Request, WebSocket
from fastapi.responses import FileResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from typing import Literal
from vic.config import ROOT
from vic.schemas import Mutation
from .store import ApplicationStore


def create_app():
    root = Path(os.environ.get("VIC_APP_DATA", ROOT / ".local/applications"))
    root.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get("VIC_APP_RUNTIME_TOKEN", "")
    if len(secret) < 32:
        raise RuntimeError("Application worker credential required")
    allowed = set(
        os.environ.get(
            "VIC_APP_MODULES",
            "chat,im,music,news,media,blog,studio,travel,shop,bank,code,gomoku,games",
        ).split(",")
    )
    store = ApplicationStore(root)
    from .native_processes import NativeProcesses
    native = NativeProcesses(root)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    desktop_watchers = {}

    @app.on_event("shutdown")
    async def close_native():
        for watcher in desktop_watchers.values():
            watcher.cancel()
        await asyncio.gather(*desktop_watchers.values(), return_exceptions=True)
        native.close()

    def private(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + secret):
            raise HTTPException(403, "Worker credential required")

    def meta(run_id):
        if not re.fullmatch("[a-f0-9]{32}", run_id):
            raise HTTPException(404, "Unknown run")
        path = root / run_id / "instance.json"
        if not path.exists():
            raise HTTPException(404, "Unknown run")
        return json.loads(path.read_text())

    def save(run_id, m):
        (root / run_id / "instance.json").write_text(json.dumps(m))

    def auth(run_id, t):
        m = meta(run_id)
        if not hmac.compare_digest(
            m["token_hash"],
            hashlib.sha256(t.removeprefix("Bearer ").encode()).hexdigest(),
        ):
            raise HTTPException(403, "Application credential required")
        if m["status"] == "destroyed":
            raise HTTPException(410, "Destroyed")
        return m

    from .gomoku_native import GomokuBridge
    gomoku = GomokuBridge(root, store, meta)

    def stop_native(run_id):
        watcher = desktop_watchers.pop(run_id, None)
        if watcher:
            watcher.cancel()
        native.stop(run_id)
        gomoku.offsets.pop(run_id, None)

    class Prepare(BaseModel):
        model_config = ConfigDict(extra="forbid")
        run_id: str
        app: str
        token: str
        epoch: int
        state: dict
        interaction: Literal["agent", "human"] = "agent"

    @app.get("/healthz")
    def health():
        return dict(status="ok", modules=sorted(allowed))

    @app.post("/internal/prepare", dependencies=[Depends(private)])
    async def prepare(body: Prepare):
        if body.app not in allowed or not re.fullmatch("[a-f0-9]{32}", body.run_id):
            raise HTTPException(422, "Invalid application or id")
        if body.state.get("app") != body.app:
            raise HTTPException(422, "Domain mismatch")
        stop_native(body.run_id)
        store.initialize(body.run_id, body.state)
        save(
            body.run_id,
            dict(
                app=body.app,
                epoch=body.epoch,
                token_hash=hashlib.sha256(body.token.encode()).hexdigest(),
                status="active",
                interaction=body.interaction,
            ),
        )
        return dict(status="ready")

    @app.post("/internal/runs/{run_id}/seal", dependencies=[Depends(private)])
    async def seal(run_id):
        gomoku.drain(run_id)
        m = meta(run_id)
        m["status"] = "sealed"
        save(run_id, m)
        return dict(
            state=store.snapshot(run_id), events=store.events(run_id), epoch=m["epoch"]
        )

    @app.post("/internal/runs/{run_id}/release", dependencies=[Depends(private)])
    async def release(run_id):
        if meta(run_id)["status"] == "active":
            raise HTTPException(409, "Seal before releasing native processes")
        stop_native(run_id)
        return dict(status="released")

    @app.get("/internal/runs/{run_id}", dependencies=[Depends(private)])
    async def snapshot(run_id):
        gomoku.drain(run_id)
        m = meta(run_id)
        return dict(
            state=store.snapshot(run_id), events=store.events(run_id), epoch=m["epoch"]
        )

    @app.delete("/internal/runs/{run_id}", dependencies=[Depends(private)])
    async def destroy(run_id):
        m = meta(run_id)
        stop_native(run_id)
        m["status"] = "destroyed"
        save(run_id, m)
        for name in ("app.sqlite3", "app.sqlite3-wal", "app.sqlite3-shm"):
            (root / run_id / name).unlink(missing_ok=True)
        return dict(status="destroyed")

    @app.get("/api/runs/{run_id}")
    async def state(run_id, authorization: str = Header(default="")):
        m = auth(run_id, authorization)
        if m["status"] == "destroyed":
            raise HTTPException(410, "Destroyed")
        return dict(epoch=m["epoch"], status=m["status"], state=store.snapshot(run_id))

    @app.get("/api/runs/{run_id}/files/{file_id}")
    async def attachment(run_id, file_id, authorization: str = Header(default="")):
        m = auth(run_id, authorization)
        if m["status"] == "destroyed":
            raise HTTPException(410, "Destroyed")
        item = store.snapshot(run_id).get("domain", {}).get("files", {}).get(file_id)
        if item is None:
            raise HTTPException(404, "File not found")
        return Response(
            base64.b64decode(item["content"]), media_type="application/octet-stream"
        )

    @app.post("/api/runs/{run_id}/commands")
    async def command(run_id, body: Mutation, authorization: str = Header(default="")):
        m = auth(run_id, authorization)
        if m["status"] != "active" or m["epoch"] != body.epoch:
            raise HTTPException(409, "Application sealed or stale epoch")
        if m.get("interaction", "agent") == "agent" and len(store.events(run_id)) >= 300:
            raise HTTPException(409, "Command budget exhausted")
        try:
            s = store.mutate(run_id, body)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return dict(epoch=m["epoch"], status=m["status"], state=s)

    dist = ROOT / "apps/portal/dist"
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    chat_dist = ROOT / "apps/chat/frontend/frontend/dist"
    news_dist = ROOT / "apps/news/src/main/resources/web"
    music_dist = ROOT / "apps/music/blog/static/benchmark"
    if music_dist.exists():
        app.mount("/native-assets/music", StaticFiles(directory=music_dist), name="native-music-assets")
    if news_dist.exists():
        app.mount("/native-assets/news", StaticFiles(directory=news_dist), name="native-news-assets")
    if chat_dist.exists():
        app.mount("/native-assets/chat", StaticFiles(directory=chat_dist), name="native-chat-assets")

    @app.get("/native/chat/{run_id}/{page:path}")
    @app.get("/native/chat/{run_id}")
    async def native_chat(run_id, page=""):
        if meta(run_id)["app"] != "chat":
            raise HTTPException(404, "Application mismatch")
        if not chat_dist.exists():
            raise HTTPException(503, "Original Chat frontend must be built")
        return FileResponse(chat_dist / "index.html")

    @app.get("/native/news/{run_id}")
    async def native_news(run_id):
        if meta(run_id)["app"] != "news":
            raise HTTPException(404, "Application mismatch")
        return FileResponse(news_dist / "index.html")

    @app.post("/native/music/{run_id}/authorize")
    async def authorize_music(run_id, authorization: str = Header(default="")):
        if auth(run_id, authorization)["app"] != "music":
            raise HTTPException(404, "Application mismatch")
        response = Response(status_code=204)
        response.set_cookie("vic_music", authorization.removeprefix("Bearer "),
                            httponly=True, samesite="strict", path=f"/native/music/{run_id}/")
        return response

    @app.get("/native/music/{run_id}/{page:path}")
    def native_music(run_id, page, request: Request):
        if meta(run_id)["app"] != "music":
            raise HTTPException(404, "Application mismatch")
        token = request.cookies.get("vic_music", "")
        if not token:
            return HTMLResponse('''<!doctype html><meta charset="utf-8"><title>青楽</title><p>正在打开音乐资料库…</p><script>
const run=location.pathname.split('/')[3],key='vic-music:'+run;
const token=location.hash.slice(1)||sessionStorage.getItem(key)||'';
sessionStorage.setItem(key,token);
fetch('/native/music/'+run+'/authorize',{method:'POST',headers:{Authorization:'Bearer '+token}}).then(r=>{if(!r.ok)throw Error('登录已失效');history.replaceState({},'',location.pathname);location.reload()}).catch(e=>document.querySelector('p').textContent=e.message);
</script>''')
        auth(run_id, token)
        from .music_native import render_music
        try:
            return HTMLResponse(render_music(run_id, store.snapshot(run_id), page, request.url.query))
        except ValueError as exc:
            raise HTTPException(404, str(exc))

    @app.get("/native-assets/im/{page:path}")
    def native_im(page):
        dist = ROOT / "apps/im/Frontend/out"
        file = (dist / (page or "index.html")).resolve()
        if not file.is_relative_to(dist.resolve()):
            raise HTTPException(404, "Not found")
        if file.is_dir():
            file = file / "index.html"
        if not file.is_file():
            file = file.with_suffix(".html")
        if not file.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(file)

    media_assets = ROOT / "apps/media/assets"
    if media_assets.exists():
        app.mount("/native-assets/media", StaticFiles(directory=media_assets), name="media-assets")

    @app.get("/native/product/{module}/{run_id}")
    async def product(module, run_id):
        if module not in ("media", "blog", "studio", "travel", "shop", "bank", "games") or meta(run_id)["app"] != module:
            raise HTTPException(404, "Application mismatch")
        return FileResponse(dist / "index.html")

    @app.post("/native/{module}/{run_id}/authorize")
    async def authorize_code(module, run_id, authorization: str = Header(default="")):
        if module not in ("code", "gomoku") or auth(run_id, authorization)["app"] != module:
            raise HTTPException(404, "Application mismatch")
        if auth(run_id, authorization)["status"] != "active":
            raise HTTPException(409, "Application is not active")
        token = authorization.removeprefix("Bearer ")
        try:
            if module == "code":
                await native.start_code(run_id, token)
            else:
                gomoku.export(run_id)
                await native.start_gomoku(run_id)
                if run_id not in desktop_watchers:
                    async def watch():
                        while True:
                            gomoku.drain(run_id)
                            await asyncio.sleep(0.08)
                    desktop_watchers[run_id] = asyncio.create_task(watch())
        except ValueError as exc:
            raise HTTPException(503, str(exc))
        response = Response(status_code=204)
        response.set_cookie(f"vic_{module}", token, httponly=True, samesite="strict", path=f"/native/{module}/{run_id}/")
        return response

    @app.api_route("/native/{module}/{run_id}/{page:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def native_code(module, run_id, page, request: Request):
        if module not in ("code", "gomoku") or meta(run_id)["app"] != module:
            raise HTTPException(404, "Application mismatch")
        token = request.cookies.get(f"vic_{module}", "")
        if not token:
            if page or request.method != "GET":
                raise HTTPException(403, "Application credential required")
            return HTMLResponse('''<!doctype html><meta charset="utf-8"><title>Liugu OJ</title><p>正在打开在线评测系统…</p><script>
const module=location.pathname.split('/')[2],run=location.pathname.split('/')[3],key='vic-'+module+':'+run;
const token=location.hash.slice(1)||sessionStorage.getItem(key)||'';sessionStorage.setItem(key,token);
fetch('/native/'+module+'/'+run+'/authorize',{method:'POST',headers:{Authorization:'Bearer '+token}}).then(async r=>{if(!r.ok)throw Error((await r.json()).detail);history.replaceState({},'',location.pathname);location.reload()}).catch(e=>document.querySelector('p').textContent=e.message);
</script>''')
        auth(run_id, token)
        port = native.port(run_id)
        if not port:
            raise HTTPException(410, "Code instance closed; reset this run")
        if module == "gomoku" and not page:
            return HTMLResponse('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>五子棋</title>
<style>html,body,#screen{margin:0;width:100%;height:100%;overflow:hidden;background:#fff}#status{position:fixed;inset:0;display:grid;place-content:center;font:16px system-ui;color:#60746a}</style>
<div id="screen"></div><div id="status">正在打开五子棋…</div>
<script type="module">import RFB from './core/rfb.js';
const protocol=location.protocol==='https:'?'wss:':'ws:';
const rfb=new RFB(document.getElementById('screen'),protocol+'//'+location.host+location.pathname+'websockify');
rfb.scaleViewport=true;rfb.background='#fff';rfb.showDotCursor=false;
rfb.addEventListener('connect',()=>document.getElementById('status').remove());
rfb.addEventListener('disconnect',()=>{const status=document.createElement('div');status.id='status';status.textContent='棋谱连接已关闭，请返回工作台重新打开。';document.body.appendChild(status)});
</script></html>''')
        import httpx
        upstream = f"http://127.0.0.1:{port}/" + (f"native/code/{run_id}/" if module=="code" else "") + page
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            result = await client.request(request.method, upstream, params=request.query_params,
                                          content=await request.body(), headers={"Content-Type": request.headers.get("content-type", "")})
        return Response(result.content, status_code=result.status_code,
                        headers={k:v for k,v in result.headers.items() if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection")})

    @app.websocket("/native/{module}/{run_id}/{page:path}")
    async def native_code_socket(websocket: WebSocket, module, run_id, page):
        import asyncio
        import websockets
        try:
            if module not in ("code", "gomoku") or auth(run_id, websocket.cookies.get(f"vic_{module}", ""))["app"] != module:
                raise HTTPException(403, "Application mismatch")
        except HTTPException:
            await websocket.close(code=1008)
            return
        port = native.port(run_id)
        if not port:
            await websocket.close(code=1011)
            return
        protocols = [x.strip() for x in websocket.headers.get("sec-websocket-protocol", "").split(",") if x.strip()]
        try:
            upstream_url = f"ws://127.0.0.1:{port}/" + (f"native/code/{run_id}/" if module=="code" else "") + page
            async with websockets.connect(upstream_url, subprotocols=protocols, max_size=None, proxy=None) as upstream:
                await websocket.accept(subprotocol=upstream.subprotocol)
                async def outbound():
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        await upstream.send(message.get("bytes") if message.get("bytes") is not None else message.get("text", ""))
                async def inbound():
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                tasks = [asyncio.create_task(outbound()), asyncio.create_task(inbound())]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task_ in tasks:
                        task_.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, websockets.WebSocketException):
            await websocket.close(code=1011)

    @app.get("/apps/{module}/{run_id}")
    async def view(module, run_id):
        if module not in allowed or meta(run_id)["app"] != module:
            raise HTTPException(404, "Application mismatch")
        return FileResponse(dist / "index.html")

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return app
