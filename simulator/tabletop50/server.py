"""Separate FPV service. Rule, seed, state and scores remain author-private."""
from contextlib import asynccontextmanager
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

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .catalog import IMPLEMENTED
from .families import FAMILIES, REVISION
from .protocol import TOKENS
from scripts.tabletop50.record import source_hash

DATA = Path(os.environ.get("TABLETOP50_DATA", ".local/tabletop50-service")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
token_path = DATA/"admin.token"
if not token_path.exists():
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream: stream.write(secrets.token_urlsafe(32))
ADMIN = token_path.read_text().strip()
LOCK = threading.RLock()
SESSIONS = {}


class Create(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str
    variant: Literal["A", "B", "C"]
    seed: int
    demo_seed: int = 0
    condition: Literal["no_demo", "sim_video"] = "sim_video"
    trial_kind: Literal["agent", "manual_author", "protocol_smoke"] = "agent"
    wall_seconds: int = Field(default=1800, ge=1, le=3600)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: str = "STILL"
    right: str = "STILL"


def admin(authorization):
    if not secrets.compare_digest(authorization or "", "Bearer "+ADMIN):
        raise HTTPException(401, "Author token required")


def validated_demo(req):
    if req.condition == "no_demo": return None
    if req.seed == req.demo_seed: raise HTTPException(409, "Inference needs a different instance seed")
    folder = DATA/"demos"/f"{req.task}-{req.variant}-{req.demo_seed}"
    try:
        p = json.loads((folder/"result.private.json").read_text())
        cross = p["cross_rule_predicates"]
        assert (p["task"], p["variant"], p["seed"]) == (req.task, req.variant, req.demo_seed)
        assert p["score"]["success"] and not p["error"] and p["source_unchanged"]
        assert p["source_sha256"] == source_hash()
        assert cross[req.variant] and sum(cross.values()) == 1
        assert p["video"]["recorded"] and p["video"]["full_episode"] and p["video"]["final_success"]
        assert hashlib.sha256((folder/"video.mp4").read_bytes()).hexdigest() == p["video"]["sha256"]
        assert (folder/"media-audit.private.json").is_file()
        audit = json.loads((folder/"media-audit.private.json").read_text())
        assert audit["video_sha256"] == p["video"]["sha256"]
        assert audit["decoded_frames"] == p["video"]["frames"] and audit["ending_image_mae"] < 20
    except (OSError, ValueError, KeyError, AssertionError):
        raise HTTPException(409, "Matching current-source decoded demonstration unavailable")
    return folder/"video.mp4"


class Session:
    def __init__(self, req):
        self.req = req; self.id = secrets.token_urlsafe(24); self.closed = False; self.count = 0
        self.demo = validated_demo(req)
        self.folder = DATA/"runs"/self.id; self.folder.mkdir(parents=True)
        self.log = (self.folder/"worker.log").open("x")
        self.proc = subprocess.Popen([sys.executable, "-m", "simulator.tabletop50.worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
        try: self.rpc(dict(op="init", task=req.task, variant=req.variant, seed=req.seed), 300)
        except Exception:
            self.proc.kill(); self.proc.wait(); self.log.close(); raise
        self.started = time.monotonic()
        (self.folder/"manifest.private.json").write_text(json.dumps(dict(
            req.model_dump(), revision=REVISION, source_sha256=source_hash(), action_budget=1600), indent=2))

    def rpc(self, payload, timeout=120):
        self.proc.stdin.write(json.dumps(payload)+"\n"); self.proc.stdin.flush()
        if not select.select([self.proc.stdout], [], [], timeout)[0]: raise RuntimeError("Worker timeout")
        line = self.proc.stdout.readline()
        if not line: raise RuntimeError("Worker exited")
        reply = json.loads(line)
        if "error" in reply: raise RuntimeError(reply["error"])
        return reply["result"]

    def close(self, reason="submitted"):
        if self.closed: return
        self.closed = True
        try: score = self.rpc(dict(op="score"), 30)
        except Exception: score = dict(success=False, error="worker_unavailable")
        if reason != "submitted": score["success"] = False
        (self.folder/"result.private.json").write_text(json.dumps(dict(score, reason=reason,
            actions=self.count, trial_kind=self.req.trial_kind), indent=2))
        try:
            self.rpc(dict(op="close"), 10); self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill(); self.proc.wait()
        self.log.close()


def session(sid):
    s = SESSIONS.get(sid)
    if s is None: raise HTTPException(404)
    if not s.closed and time.monotonic()-s.started >= s.req.wall_seconds: s.close("wall_budget")
    if s.closed: raise HTTPException(410, "Episode ended")
    return s


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    def reap():
        while not stop.wait(5):
            with LOCK:
                for s in SESSIONS.values():
                    if not s.closed and time.monotonic()-s.started >= s.req.wall_seconds: s.close("wall_budget")
    thread = threading.Thread(target=reap, daemon=True); thread.start()
    yield
    stop.set(); thread.join(timeout=6)
    with LOCK:
        for s in SESSIONS.values(): s.close("shutdown")


app = FastAPI(title="Tabletop50 FPV", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health(): return dict(ok=True, revision=REVISION, designed_families=50, runtime_recipes=len(IMPLEMENTED))


@app.get("/admin/catalog")
def catalog(authorization: str | None = Header(default=None)):
    admin(authorization); return FAMILIES


@app.post("/admin/sessions")
def create(req: Create, authorization: str | None = Header(default=None)):
    admin(authorization)
    if req.task not in IMPLEMENTED: raise HTTPException(422, "Runtime recipe unavailable")
    with LOCK:
        if any(not s.closed for s in SESSIONS.values()): raise HTTPException(409, "Finish active world first")
        try: s = Session(req)
        except HTTPException: raise
        except Exception: raise HTTPException(503, "Simulation failed; see private worker log")
        SESSIONS[s.id] = s
        return dict(session=s.id, actor_url=f"/actor/{s.id}")


@app.get("/actor/{sid}/observe")
def observe(sid: str):
    with LOCK:
        s = session(sid)
        try: result = s.rpc(dict(op="observe"))
        except Exception:
            s.close("worker_error"); raise HTTPException(503, "Simulation unavailable")
        return dict(images=result["images"], instruction="按照示范完成这项桌面工作。",
                    actions=s.count, remaining=1600-s.count, tokens=TOKENS)


@app.post("/actor/{sid}/action")
def action(sid: str, req: Action):
    if req.left not in TOKENS or req.right not in TOKENS: raise HTTPException(422)
    with LOCK:
        s = session(sid)
        if s.count >= 1600: raise HTTPException(409, "Submit episode")
        s.count += 1
        with (s.folder/"actions.private.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(index=s.count, **req.model_dump()))+"\n")
        try: s.rpc(dict(op="action", **req.model_dump()))
        except Exception:
            s.close("worker_error"); raise HTTPException(503, "Simulation unavailable")
        return dict(accepted=True, remaining=1600-s.count)


@app.get("/actor/{sid}/demo")
def demo(sid: str):
    with LOCK:
        s = session(sid)
        if s.demo is None: return dict(condition="no_demo")
        return FileResponse(s.demo, media_type="video/mp4", filename="demonstration.mp4")


@app.post("/actor/{sid}/submit")
def submit(sid: str):
    with LOCK: session(sid).close()
    return dict(ended=True)


@app.get("/admin/results/{sid}")
def result(sid: str, authorization: str | None = Header(default=None)):
    admin(authorization)
    if sid not in SESSIONS: raise HTTPException(404)
    path = SESSIONS[sid].folder/"result.private.json"
    if not path.is_file(): raise HTTPException(409, "Episode running")
    return json.loads(path.read_text())
