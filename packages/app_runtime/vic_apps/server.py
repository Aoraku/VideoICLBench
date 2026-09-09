"""Application worker: business operations only, no evaluation endpoints."""

import hashlib
import base64
import hmac
import json
import os
from pathlib import Path
import re
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
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
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

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
        return m

    class Prepare(BaseModel):
        model_config = ConfigDict(extra="forbid")
        run_id: str
        app: str
        token: str
        epoch: int
        state: dict

    @app.get("/healthz")
    def health():
        return dict(status="ok", modules=sorted(allowed))

    @app.post("/internal/prepare", dependencies=[Depends(private)])
    async def prepare(body: Prepare):
        if body.app not in allowed or not re.fullmatch("[a-f0-9]{32}", body.run_id):
            raise HTTPException(422, "Invalid application or id")
        if body.state.get("app") != body.app:
            raise HTTPException(422, "Domain mismatch")
        store.initialize(body.run_id, body.state)
        save(
            body.run_id,
            dict(
                app=body.app,
                epoch=body.epoch,
                token_hash=hashlib.sha256(body.token.encode()).hexdigest(),
                status="active",
            ),
        )
        return dict(status="ready")

    @app.post("/internal/runs/{run_id}/seal", dependencies=[Depends(private)])
    async def seal(run_id):
        m = meta(run_id)
        m["status"] = "sealed"
        save(run_id, m)
        return dict(
            state=store.snapshot(run_id), events=store.events(run_id), epoch=m["epoch"]
        )

    @app.get("/internal/runs/{run_id}", dependencies=[Depends(private)])
    async def snapshot(run_id):
        m = meta(run_id)
        return dict(
            state=store.snapshot(run_id), events=store.events(run_id), epoch=m["epoch"]
        )

    @app.delete("/internal/runs/{run_id}", dependencies=[Depends(private)])
    async def destroy(run_id):
        m = meta(run_id)
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
        if len(store.events(run_id)) >= 300:
            raise HTTPException(409, "Command budget exhausted")
        try:
            s = store.mutate(run_id, body)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return dict(epoch=m["epoch"], status=m["status"], state=s)

    dist = ROOT / "apps/portal/dist"
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

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
