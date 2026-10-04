"""OS-ICL lifecycle and pixel-only agent transport; grading stays upstream."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from typing import Literal

from .runtime import BrowserRuntime
from .schemas import Action


class OSRunRequest(BaseModel):
    case_id: str = Field(pattern=r"^OS-[A-Z]+-\d{2}$")
    variant: Literal["A", "B", "C"] = "A"
    seed: int = Field(default=20261005, ge=0, le=2**31-1)
    interaction: Literal["human", "agent"] = "human"
    timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    max_actions: int = Field(default=120, ge=1, le=1000)


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
        if not sid.startswith("vos_") or not sid[4:].isalnum():
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

    def demo(case_id, variant):
        manifest = source / "data/manifests/os-icl-1.0.0.json"
        if not manifest.is_file():
            raise HTTPException(503, "OS release manifest unavailable")
        entries = json.loads(manifest.read_text())["entries"]
        entry = next((e for e in entries if e["case_id"] == case_id and e["rule"] == "ABC".index(variant)), None)
        if not entry:
            raise HTTPException(404, "OS demonstration not found")
        path = (source / entry["video"]).resolve()
        if not path.is_relative_to(source.resolve()) or not path.is_file():
            raise HTTPException(503, "OS demonstration unavailable")
        return entry, path

    def launch(run):
        return f"/os-sim/{run['id']}/?access={browser_token(run['id'])}"

    def public(run):
        return {k: run[k] for k in ("id", "case_id", "variant", "seed", "interaction", "created_at", "status", "public_task", "demo_sha256", "benchmark_version")} | {
            "application_url": launch(run), "result": run.get("result")}

    @app.get("/os-api/cases", dependencies=[Depends(manager)])
    async def cases():
        result = await api("/api/v1/cases")
        result.update(demonstrations=108, benchmark_version="1.0.0")
        return result

    @app.get("/os-api/cases/{case_id}/demo", dependencies=[Depends(manager)])
    async def case_demo(case_id: str, variant: Literal["A", "B", "C"] = "A"):
        _, path = demo(case_id, variant)
        return FileResponse(path, media_type="video/webm")

    @app.post("/os-api/runs", dependencies=[Depends(manager)])
    async def create(body: OSRunRequest):
        entry, _ = demo(body.case_id, body.variant)
        # A different seed ensures the query is not the recorded demonstration.
        if body.seed == entry["seed"]:
            raise HTTPException(422, "Evaluation seed must differ from demonstration seed")
        session = await api("/api/v1/sessions", "POST", {"case_id": body.case_id, "rule": "ABC".index(body.variant),
            "seed": body.seed, "mode": "evaluation", "external_task_id": "videoicl:" + body.case_id})
        actor = secrets.token_urlsafe(32)
        run = {**body.model_dump(), "id": session["id"], "token_hash": hashlib.sha256(actor.encode()).hexdigest(),
            "created_at": time.time(), "status": "running", "benchmark_version": session["benchmark_version"],
            "public_task": {"assignment": session["case"]["task"], "title": session["case"]["title"],
                "inference": "Infer the policy from the assigned demonstration and apply it to the new items. Complete the task using the interface, then call finish."},
            "demo_sha256": entry["sha256"], "result": None}
        save(run)
        return {**public(run), "actor_token": actor}

    @app.get("/os-api/runs/{sid}", dependencies=[Depends(manager)])
    async def get_run(sid):
        return public(read(sid))

    @app.get("/os-api/runs/{sid}/demo")
    async def run_demo(sid: str, request: Request):
        run = read(sid); authorize(run, request)
        _, path = demo(run["case_id"], run["variant"])
        return FileResponse(path, media_type="video/webm")

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

    @app.post("/os-api/runs/{sid}/eval", dependencies=[Depends(manager)])
    async def evaluate(sid: str):
        async with lock(sid):
            run = read(sid)
            if run.get("result") is None:
                session = await api(f"/api/v1/sessions/{sid}")
                if session["status"] != "finished":
                    session = await api(f"/api/v1/sessions/{sid}/finish", "POST", {})
                run["result"] = session["result"]
                run["status"] = "completed"
                save(run)
                await runtime.close_run(sid)
            return {"run_id": sid, **run["result"]}

    @app.api_route("/os-sim/{sid}/{path:path}", methods=["GET", "POST"])
    async def proxy(sid: str, path: str, request: Request):
        run = read(sid); authorize(run, request, browser=True)
        base = f"/os-sim/{sid}"
        if request.query_params.get("access"):
            response = RedirectResponse(base + f"/?session={sid}&visual=1", status_code=303)
            response.set_cookie("vic-os", browser_token(sid), httponly=True, samesite="strict", path=base+"/")
            return response
        allowed_static = {"", "app.js", "styles.css", "os-shell.js", "os-shell.css"}
        allowed_api = {"api/v1/cases", f"api/v1/sessions/{sid}", f"api/v1/sessions/{sid}/action", f"api/v1/sessions/{sid}/finish"}
        if path not in allowed_static | allowed_api or (request.method == "POST" and not path.endswith(("/action", "/finish"))):
            raise HTTPException(404, "OS route unavailable")
        if request.method == "POST" and run["status"] != "running":
            raise HTTPException(409, "OS session is completed")
        async with httpx.AsyncClient(base_url=upstream, timeout=30) as client:
            response = await client.request(request.method, "/"+path, content=await request.body(),
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")})
        content = response.content
        mime = response.headers.get("Content-Type", "application/octet-stream")
        if path == "":
            content = content.decode().replace('href="/', f'href="{base}/').replace('src="/', f'src="{base}/').encode()
        elif path == "app.js":
            text = content.decode().replace('fetch(url,', f'fetch({json.dumps(base)} + url,')
            # Keep the original simulator and event handlers, with studio chrome outside the agent viewport.
            marker = '  if(state.replay){'
            visual = '''  if(new URLSearchParams(location.search).get("visual")==="1"){
    document.body.classList.add("recording-mode");
    root.innerHTML=`<main class="recording-only">${simulator}<div class="recording-toolbar"><button class="btn success" id="finish">Finish and evaluate</button>${s.result?`<span>${s.result.success?"success":"fail"}</span>`:""}</div></main>`;
    bindSession(); return;
  }
'''
            if marker not in text:
                raise HTTPException(503, "OS frontend version is not compatible")
            content = text.replace(marker, visual+marker, 1).encode()
        return Response(content, status_code=response.status_code, headers={"Content-Type": mime})
