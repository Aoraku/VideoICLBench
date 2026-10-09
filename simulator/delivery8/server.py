"""Authenticated task control and image-only HTTP actors for the eight-task release."""
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
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .motion import TOKENS, finite_number
from .release import HERE, MANIFEST, TASKS, prepare, verify_demo, source_hash

DATA = Path(os.environ.get("TABLETOP8_DATA", str(HERE/"service-data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
keyfile = DATA/"platform.key"
if not keyfile.exists():
    fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f: f.write(secrets.token_urlsafe(32))
KEY = keyfile.read_text().strip()
LOCK = threading.RLock()
SESSIONS = {}
BUDGET = 1600


class Create(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: Literal["F01", "F11", "F10", "F08", "F22", "F17", "F39", "F44"]
    variant: Literal["A", "B", "C"]
    seed: int = Field(default=7, ge=1, le=2147483647)
    trial_kind: Literal["agent", "manual", "protocol_smoke"] = "agent"
    wall_seconds: int = Field(default=1800, ge=30, le=7200)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: str = "STILL"
    right: str = "STILL"
    step_mm: float | None = None
    rotation_deg: float | None = None
    expected_observation: int = Field(ge=0)

    @field_validator("left", "right")
    @classmethod
    def token(cls, value):
        if value not in TOKENS: raise ValueError("Unknown action")
        return value

    @field_validator("step_mm", "rotation_deg", mode="before")
    @classmethod
    def number(cls, value, info):
        if value is not None:
            finite_number(value, .5, 50. if info.field_name == "step_mm" else 20.)
        return value


def authorize(authorization):
    if not secrets.compare_digest(authorization or "", "Bearer "+KEY):
        raise HTTPException(401, "Platform key required")


class Session:
    def __init__(self, req):
        self.req = req
        self.id = secrets.token_urlsafe(24)
        self.count = 0; self.closed = False
        self.demo_folder = verify_demo(req.task, req.variant)
        self.source = TASKS[req.task]["demos"][req.variant]["source_sha256"]
        runtime = DATA/"runtimes"/self.source
        if source_hash(runtime) != self.source:
            raise ValueError("Frozen runtime changed")
        self.folder = DATA/"episodes"/self.id
        self.folder.mkdir(parents=True)
        self.log = (self.folder/"worker.log").open("x")
        self.proc = subprocess.Popen([sys.executable, str(HERE/"worker.py")], cwd=runtime,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
        try:
            initial = self.rpc(dict(op="init", task=req.task, variant=req.variant, seed=req.seed,
                                    folder=str(self.folder)), 300)
        except Exception:
            self.proc.kill(); self.proc.wait(); self.log.close(); raise
        self.started = time.monotonic()
        self.manifest = dict(release=MANIFEST["release"], **req.model_dump(),
            scene_source_sha256=self.source, world_sha256=initial["world_sha256"],
            motion_adapter_sha256=hashlib.sha256((HERE/"motion.py").read_bytes()).hexdigest(),
            demo_video_sha256=TASKS[req.task]["demos"][req.variant]["video_sha256"],
            action_budget=BUDGET, started_at=time.time())
        (self.folder/"manifest.private.json").write_text(json.dumps(self.manifest, indent=2))

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
        try: score = self.rpc(dict(op="score"), 60)
        except Exception: score = dict(success=False, error="worker_unavailable")
        if reason != "submitted": score["success"] = False
        try:
            ending = self.rpc(dict(op="close"), 30)
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill(); self.proc.wait(); ending = {}
        self.log.close()
        (self.folder/"result.private.json").write_text(json.dumps(dict(
            **score, reason=reason, actions=self.count, trial_kind=self.req.trial_kind,
            video=ending, elapsed_seconds=time.monotonic()-self.started), indent=2))


def session(sid):
    s = SESSIONS.get(sid)
    if s is None: raise HTTPException(404, "Unknown session")
    if not s.closed and time.monotonic()-s.started >= s.req.wall_seconds: s.close("wall_budget")
    if s.closed: raise HTTPException(410, "Episode ended")
    return s


@asynccontextmanager
async def lifespan(app):
    prepare(DATA/"runtimes")
    stop = threading.Event()
    def reap():
        while not stop.wait(5):
            with LOCK:
                for s in SESSIONS.values():
                    if not s.closed and time.monotonic()-s.started >= s.req.wall_seconds:
                        s.close("wall_budget")
    thread = threading.Thread(target=reap, daemon=True); thread.start()
    yield
    stop.set(); thread.join(timeout=6)
    with LOCK:
        for s in SESSIONS.values(): s.close("shutdown")


app = FastAPI(title="VideoICL Tabletop Eight", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health(): return dict(ok=True, release=MANIFEST["release"], tasks=8, demos=24,
                          step_mm=dict(min=.5, max=50, default=20))


@app.get("/")
def dashboard(): return FileResponse(HERE/"dashboard.html")


@app.get("/client/hosted.py")
def client_script(): return FileResponse(HERE/"hosted.py", media_type="text/plain")


@app.get("/client/prompt.txt")
def client_prompt(): return FileResponse(HERE/"prompt.txt", media_type="text/plain")


@app.get("/control/tasks")
def tasks(authorization: str | None = Header(default=None)):
    authorize(authorization)
    return [dict(id=t["id"], title=t["title"], length=t["length"], difficulty=t["difficulty"],
                 challenge=t["challenge"]) for t in TASKS.values()]


@app.post("/control/sessions")
def create(req: Create, authorization: str | None = Header(default=None)):
    authorize(authorization)
    with LOCK:
        if any(not s.closed for s in SESSIONS.values()):
            raise HTTPException(409, "Finish the active episode first")
        try: s = Session(req)
        except Exception: raise HTTPException(503, "Simulation could not start; check private logs")
        SESSIONS[s.id] = s
        return dict(session=s.id, actor_url=f"/actor/{s.id}")


@app.get("/control/status")
def status(authorization: str | None = Header(default=None)):
    authorize(authorization)
    with LOCK:
        return [dict(session=s.id, task=s.req.task, variant=s.req.variant, closed=s.closed,
                     actions=s.count) for s in SESSIONS.values()]


@app.get("/control/results/{sid}")
def results(sid: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    s = SESSIONS.get(sid)
    if s is None: raise HTTPException(404)
    if not s.closed: raise HTTPException(409, "Episode running")
    return json.loads((s.folder/"result.private.json").read_text())


@app.get("/control/execution/{sid}")
def execution(sid: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    s = SESSIONS.get(sid)
    if s is None: raise HTTPException(404)
    if not s.closed: raise HTTPException(409, "End the episode to finalize video")
    return FileResponse(s.folder/"execution.mp4", media_type="video/mp4")


@app.get("/actor/{sid}/observe")
def observe(sid: str):
    with LOCK:
        s = session(sid)
        try: images = s.rpc(dict(op="observe"))["images"]
        except Exception:
            s.close("worker_error"); raise HTTPException(503, "Simulation unavailable")
        return dict(images=images, instruction="按照示范完成这项桌面工作。",
                    observation_id=s.count, actions=s.count, remaining=BUDGET-s.count,
                    tokens=TOKENS, motion=dict(step_mm_min=.5, step_mm_max=50., default_step_mm=20.,
                    rotation_deg_min=.5, rotation_deg_max=20., default_rotation_deg=10.,
                    fine_step_mm=2., fine_rotation_deg=1., command_seconds=.4))


@app.post("/actor/{sid}/action")
def action(sid: str, req: Action):
    with LOCK:
        s = session(sid)
        if req.expected_observation != s.count: raise HTTPException(409, "Stale observation; observe again")
        if s.count >= BUDGET: raise HTTPException(409, "Action budget exhausted; submit")
        s.count += 1
        with (s.folder/"actions.private.jsonl").open("a") as f:
            f.write(json.dumps(dict(index=s.count, time=time.time(), **req.model_dump()))+"\n")
        try: s.rpc(dict(op="action", **req.model_dump(exclude={"expected_observation"})))
        except Exception:
            s.close("worker_error"); raise HTTPException(503, "Simulation unavailable")
        return dict(accepted=True, observation_id=s.count, remaining=BUDGET-s.count)


@app.get("/actor/{sid}/demo")
def demo(sid: str):
    with LOCK:
        return FileResponse(session(sid).demo_folder/"video.mp4", media_type="video/mp4")


@app.get("/actor/{sid}/demo-frames")
def demo_frames(sid: str):
    import base64
    with LOCK:
        s = session(sid)
        folder = DATA/"demo-frames"/s.demo_folder.name
        frames = sorted(folder.glob("*.jpg"))
        if len(frames) != 12: raise HTTPException(503, "Demo frames not prepared")
        return dict(frames=[base64.b64encode(p.read_bytes()).decode() for p in frames],
                    sampling="12 uniformly spaced chronological frames; full video at /demo")


@app.post("/actor/{sid}/submit")
def submit(sid: str):
    with LOCK: session(sid).close()
    return dict(ended=True)
