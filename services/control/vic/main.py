import asyncio
import hashlib
import hmac
import json
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from . import business
from .catalog import catalog, task, task_digest
from .config import ROOT, DATA, PUBLIC_BASE, admin_token
from .models import make_database, Run
from .schemas import CreateRun, Action, Mutation, Review, EvaluateTask
from .store import WorkspaceStore
from .runtime import BrowserRuntime
from .recording import Recorder
from .provenance import provenance
from .app_client import ApplicationClient
from . import application_eval
from vic_apps.domain import initialize as initialize_domain


def create_app(database_url=None, data_dir=None, secret=None, browser=None):
    for required in (
        "tasks/catalog.json",
        "sources.lock.json",
        "apps/portal/dist/index.html",
    ):
        if not (ROOT / required).is_file():
            raise RuntimeError(
                f"Missing runtime asset: {required}; set VIC_ROOT to the built workspace"
            )
    data = Path(data_dir or DATA)
    data.mkdir(parents=True, exist_ok=True)
    secret = secret or admin_token()
    sessions = make_database(database_url) if database_url else make_database()
    store = WorkspaceStore(data / "runs")
    runtime = browser or BrowserRuntime()
    recorder = Recorder(data / "artifacts", runtime)
    implementation = provenance()
    applications = ApplicationClient(secret)
    locks = {}

    @asynccontextmanager
    async def lifespan(app):
        # Never silently resume a process that lost its browser and input log.
        with sessions() as db:
            for run in db.scalars(select(Run).where(Run.status == "running")):
                run.status = "interrupted"
            db.commit()
        yield
        await recorder.close()
        await runtime.close()

    app = FastAPI(
        title="VideoICL-Bench",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store = store
    app.state.sessions = sessions
    app.state.runtime = runtime

    def token(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer credential required")
        return authorization[7:]

    def manager(t=Depends(token)):
        if not hmac.compare_digest(t, secret):
            raise HTTPException(403, "Manager credential required")

    def get_run(run_id):
        with sessions() as db:
            run = db.get(Run, run_id)
            if not run:
                raise HTTPException(404, "Run not found")
            return run

    def authorize(run_id, t):
        run = get_run(run_id)
        if not hmac.compare_digest(t, secret) and not hmac.compare_digest(
            hashlib.sha256(t.encode()).hexdigest(), run.token_hash
        ):
            raise HTTPException(403, "Credential does not belong to this run")
        return run

    def ui_token(run):
        return hmac.new(
            secret.encode(), f"ui:{run.id}:{run.epoch}".encode(), "sha256"
        ).hexdigest()

    def authorize_ui(run_id, t):
        run = get_run(run_id)
        if not hmac.compare_digest(t, ui_token(run)):
            raise HTTPException(403, "Workspace credential required")
        return run

    def url(run):
        return (
            applications.url(run, ui_token(run))
            if run.runtime == "browser"
            else f"{PUBLIC_BASE}/workspace/{run.id}#{ui_token(run)}"
        )

    def lock(run_id):
        return locks.setdefault(run_id, asyncio.Lock())

    def active(run):
        if run.status not in ("ready", "running"):
            raise HTTPException(
                409, f"Run is {run.status}; reset or create another run"
            )

    def summarize(run):
        return dict(
            id=run.id,
            task_id=run.task_id,
            variant=run.variant,
            mode=run.mode,
            runtime=run.runtime,
            status=run.status,
            epoch=run.epoch,
            result=run.result,
            created_at=run.created_at.isoformat(),
            manifest=run.manifest,
        )

    def save_status(run_id, status):
        with sessions() as db:
            r = db.get(Run, run_id)
            r.status = status
            db.commit()

    @app.get("/healthz")
    def health():
        return {"status": "ok", "service": "videoicl-control"}

    @app.get("/v1/capabilities", dependencies=[Depends(manager)])
    def capabilities():
        return dict(
            runtimes={
                "web-dev": True,
                "browser": True,
                "windows": False,
                "linux": False,
                "android": False,
            },
            application_modules=13,
            application_tasks=75,
            system_tasks_deferred=25,
            software_workspaces=65,
            game_workspaces=10,
            native_app_certified=0,
            frontend_review="human-review-required",
            recording_entry_required=True,
            native_process_capacity=12,
            recording_fps=recorder.fps,
            official_evaluation_ready=False,
        )

    @app.get("/v1/tasks", dependencies=[Depends(manager)])
    def tasks():
        return catalog()

    @app.get("/v1/tasks/{task_id}/contract", dependencies=[Depends(manager)])
    def contract(task_id: int):
        if not 1 <= task_id <= 100:
            raise HTTPException(404, "Task not found")
        return json.loads(
            (ROOT / "tasks/contracts" / f"{task_id:03d}.json").read_text()
        )

    @app.post("/v1/tasks/{task_id}/eval", dependencies=[Depends(manager)])
    async def eval_task(task_id: int, body: EvaluateTask):
        run = get_run(body.run_id)
        if run.task_id != task_id:
            raise HTTPException(409, "Task and run mismatch")
        result = await evaluate(body.run_id)
        return dict(**result, task_id=task_id, variant=run.variant)

    @app.get("/v1/runs", dependencies=[Depends(manager)])
    def runs():
        with sessions() as db:
            return [
                summarize(r)
                for r in db.scalars(
                    select(Run).order_by(Run.created_at.desc()).limit(200)
                )
            ]

    @app.post("/v1/runs", dependencies=[Depends(manager)], status_code=201)
    def create(body: CreateRun):
        if body.runtime not in ("web-dev", "browser"):
            raise HTTPException(
                409,
                "Runtime worker is not configured; no simulated fallback will be used",
            )
        if body.task_id > 75:
            raise HTTPException(
                409, "Task is specified but not connected to an executable runtime"
            )
        if (body.mode == "demo" and body.seed >= 1000) or (
            body.mode == "eval" and body.seed < 1000
        ):
            raise HTTPException(
                422, "Demo seeds: 0–999; evaluation/development seeds: 1000 and above"
            )
        initial = business.generate(body.task_id, body.seed)
        if body.runtime == "browser":
            initial = initialize_domain(initial)
        run_id = uuid.uuid4().hex
        actor = secrets.token_urlsafe(32)
        source_lock = json.loads((ROOT / "sources.lock.json").read_text())
        run = Run(
            id=run_id,
            task_id=body.task_id,
            variant=body.variant,
            seed=body.seed,
            mode=body.mode,
            runtime=body.runtime,
            status="ready",
            epoch=0,
            token_hash=hashlib.sha256(actor.encode()).hexdigest(),
            initial=initial,
            manifest=dict(
                task_digest=task_digest(body.task_id),
                initial_digest=hashlib.sha256(
                    json.dumps(initial, sort_keys=True).encode()
                ).hexdigest(),
                source_commits={
                    x["module"]: x["commit"] for x in source_lock["sources"]
                },
                implementation=implementation,
                surface="native-task-workspace"
                if body.runtime == "browser"
                else "development-workspace",
                official=False,
            ),
        )
        store.initialize(run.id, initial)
        if run.runtime == "browser":
            try:
                applications.prepare(run, ui_token(run))
            except Exception as e:
                raise HTTPException(503, "Application worker unavailable") from e
        with sessions() as db:
            db.add(run)
            db.commit()
            db.refresh(run)
        return dict(**summarize(run), actor_token=actor, workspace_url=url(run))

    @app.get("/v1/runs/{run_id}", dependencies=[Depends(manager)])
    def details(run_id):
        run = get_run(run_id)
        return dict(
            **summarize(run),
            workspace_url=url(run),
            rule=task(run.task_id)["variants"][run.variant],
            events=[]
            if run.status == "destroyed"
            else (
                applications.snapshot(run_id)["events"]
                if run.runtime == "browser"
                else store.events(run_id)
            ),
        )

    @app.get("/v1/workspaces/{run_id}")
    def workspace(run_id, t=Depends(token)):
        run = authorize_ui(run_id, t)
        if run.runtime == "browser":
            raise HTTPException(409, "Use the application origin")
        if run.status in ("destroying", "destroyed"):
            raise HTTPException(410, "Workspace destroyed")
        return dict(epoch=run.epoch, status=run.status, state=store.snapshot(run_id))

    @app.post("/v1/workspaces/{run_id}/mutations")
    async def mutation(run_id, body: Mutation, t=Depends(token)):
        run = authorize_ui(run_id, t)
        if run.runtime == "browser":
            raise HTTPException(409, "Use the application origin")
        active(run)
        if body.epoch != run.epoch:
            raise HTTPException(409, "Stale execution epoch")
        if len(store.events(run_id)) >= 200:
            raise HTTPException(409, "Workspace action budget exhausted")
        try:
            state = store.mutate(run_id, body)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return dict(epoch=run.epoch, status=run.status, state=state)

    @app.get("/v1/runs/{run_id}/observation")
    async def observation(run_id, t=Depends(token)):
        async with lock(run_id):
            run = authorize(run_id, t)
            active(run)
            try:
                shot = await runtime.screenshot(run_id, url(run))
            except Exception:
                save_status(run_id, "environment_error")
                raise HTTPException(
                    503,
                    "Browser unavailable; inspect worker logs and installed Chromium",
                )
            save_status(run_id, "running")
            return dict(**shot, epoch=run.epoch, status="running", official=False)

    @app.post("/v1/runs/{run_id}/actions")
    async def action(run_id, body: Action, t=Depends(token)):
        async with lock(run_id):
            run = authorize(run_id, t)
            active(run)
            if body.epoch != run.epoch:
                raise HTTPException(409, "Stale execution epoch")
            if run_id in recorder.active and not hmac.compare_digest(t, secret):
                raise HTTPException(
                    409, "Recording is human-controlled; Agent input is disabled"
                )
            try:
                result = await runtime.act(run_id, url(run), body)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            save_status(run_id, "running")
            dest = data / "runs" / run_id / "input.jsonl"
            # Browser runtime provides idempotency; archive only first acceptance.
            previous = (
                {json.loads(x)["action_id"] for x in dest.read_text().splitlines()}
                if dest.exists()
                else set()
            )
            if body.action_id not in previous:
                with dest.open("a") as f:
                    f.write(json.dumps(body.model_dump()) + "\n")
            return result

    @app.post("/v1/runs/{run_id}/reset", dependencies=[Depends(manager)])
    async def reset(run_id):
        async with lock(run_id):
            run = get_run(run_id)
            if run.status in ("destroying", "destroyed"):
                raise HTTPException(410, "Create a new run after destruction")
            if run_id in recorder.active:
                raise HTTPException(409, "Stop recording before reset")
            save_status(run_id, "resetting")
            await runtime.close_run(run_id)
            archive = data / "runs" / run_id / f"epoch-{run.epoch}"
            archive.mkdir(exist_ok=True)
            if run.runtime == "browser":
                current = applications.seal(run_id)
                (archive / "application.json").write_text(json.dumps(current))
            (archive / "state.json").write_text(json.dumps(store.snapshot(run_id)))
            (archive / "events.json").write_text(json.dumps(store.events(run_id)))
            (archive / "result.json").write_text(json.dumps(run.result))
            input_file = data / "runs" / run_id / "input.jsonl"
            if input_file.exists():
                input_file.rename(archive / "input.jsonl")
            artifacts = data / "artifacts" / run_id
            if artifacts.exists():
                recording_archive = artifacts / f"epoch-{run.epoch}"
                recording_archive.mkdir(exist_ok=True)
                for artifact in list(artifacts.glob("*.png")) + [
                    artifacts / "tutorial.mp4",
                    artifacts / "recording.json",
                ]:
                    if artifact.exists():
                        artifact.rename(recording_archive / artifact.name)
            store.initialize(run_id, run.initial)
            with sessions() as db:
                row = db.get(Run, run_id)
                row.epoch += 1
                row.status = "resetting"
                row.result = None
                db.commit()
                db.refresh(row)
                if row.runtime == "browser":
                    try:
                        applications.prepare(row, ui_token(row))
                    except Exception as exc:
                        row.status = "environment_error"
                        db.commit()
                        raise HTTPException(503, "Application reset failed") from exc
                row.status = "ready"
                db.commit()
                db.refresh(row)
                return dict(**summarize(row), workspace_url=url(row))

    @app.post("/v1/runs/{run_id}/evaluate", dependencies=[Depends(manager)])
    async def evaluate(run_id):
        async with lock(run_id):
            run = get_run(run_id)
            if run.result:
                return run.result
            if run.status != "recorded":
                active(run)
            if run_id in recorder.active:
                raise HTTPException(409, "Stop recording before evaluating")
            save_status(run_id, "sealing")
            state = store.snapshot(run_id)
            events = store.events(run_id)
            if run.runtime == "browser":
                sealed = applications.seal(run_id)
                state = sealed["state"]
                events = sealed["events"]
                clipboard = (
                    await runtime.clipboard(run_id)
                    if run.task_id == 43 and run.variant == "B"
                    else None
                )
                result = application_eval.evaluate(
                    run.initial, state, run.variant, events, clipboard
                )
            else:
                result = business.evaluate(run.initial, state, run.variant, events)
            result.update(
                run_id=run_id,
                status="completed",
                epoch=run.epoch,
                official=False,
                evidence_ref=f"/v1/runs/{run_id}/evidence",
            )
            dest = data / "artifacts" / run_id
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"evidence-{run.epoch}.json").write_text(
                json.dumps(
                    dict(
                        initial=run.initial,
                        final=state,
                        events=events,
                        manifest=run.manifest,
                        result=result,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if run.runtime == "browser" and run_id in runtime.sessions:
                (dest / f"final-{run.epoch}.png").write_bytes(
                    await runtime.capture(run_id, url(run))
                )
                await runtime.close_run(run_id)
            if run.runtime == "browser":
                applications.release(run_id)
            with sessions() as db:
                row = db.get(Run, run_id)
                row.result = result
                row.status = "completed"
                db.commit()
            return result

    @app.get("/v1/runs/{run_id}/final-image", dependencies=[Depends(manager)])
    def final_image(run_id):
        run = get_run(run_id)
        path = data / "artifacts" / run_id / f"final-{run.epoch}.png"
        if not path.exists():
            raise HTTPException(404, "No final screenshot")
        return FileResponse(path, media_type="image/png")

    @app.get("/v1/runs/{run_id}/evidence", dependencies=[Depends(manager)])
    def evidence(run_id):
        run = get_run(run_id)
        path = data / "artifacts" / run_id / f"evidence-{run.epoch}.json"
        if not path.exists():
            raise HTTPException(404, "No sealed evidence")
        return FileResponse(path, media_type="application/json")

    @app.post("/v1/runs/{run_id}/recordings/start", dependencies=[Depends(manager)])
    async def start_recording(run_id):
        async with lock(run_id):
            run = get_run(run_id)
            active(run)
            if run.mode != "demo":
                raise HTTPException(409, "Tutorial recording requires a demo run")
            try:
                await recorder.start(
                    run_id,
                    url(run),
                    task(run.task_id)["variants"][run.variant],
                    epoch=run.epoch,
                )
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            return dict(status="recording", fps=recorder.fps)

    @app.post("/v1/runs/{run_id}/recordings/stop", dependencies=[Depends(manager)])
    async def stop_recording(run_id):
        async with lock(run_id):
            get_run(run_id)
            try:
                meta = await recorder.stop(run_id)
                if get_run(run_id).runtime == "browser":
                    applications.seal(run_id)
                save_status(run_id, "recorded")
                return meta
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            except RuntimeError as exc:
                raise HTTPException(503, str(exc))

    @app.get("/v1/runs/{run_id}/recordings/video", dependencies=[Depends(manager)])
    def video(run_id):
        get_run(run_id)
        path = data / "artifacts" / run_id / "tutorial.mp4"
        if not path.exists():
            raise HTTPException(404, "No recording")
        return FileResponse(path, media_type="video/mp4")

    @app.post("/v1/runs/{run_id}/recordings/review", dependencies=[Depends(manager)])
    async def review(run_id, body: Review):
        run = get_run(run_id)
        path = data / "artifacts" / run_id / "recording.json"
        if not path.exists():
            raise HTTPException(409, "No recording to review")
        if body.approved and (not run.result or not run.result["success"]):
            raise HTTPException(409, "A passing demonstration is required")
        meta = json.loads(path.read_text())
        if meta.get("epoch") != run.epoch:
            raise HTTPException(409, "Recording belongs to another execution epoch")
        meta.update(body.model_dump())
        meta["status"] = "approved" if body.approved else "rejected"
        meta["task_digest"] = run.manifest["task_digest"]
        meta["seed"] = run.seed
        meta["variant"] = run.variant
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return meta

    @app.delete("/v1/runs/{run_id}", dependencies=[Depends(manager)])
    async def delete(run_id):
        async with lock(run_id):
            get_run(run_id)
            if run_id in recorder.active:
                raise HTTPException(409, "Stop recording first")
            if get_run(run_id).runtime == "browser":
                applications.destroy(run_id)
            save_status(run_id, "destroying")
            await runtime.close_run(run_id)
            save_status(run_id, "destroyed")
            # Keep evidence and metadata for audit; destroy writable workspace.
            shutil.rmtree(data / "runs" / run_id, ignore_errors=True)
            return dict(status="destroyed")

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-src 'self'; frame-ancestors 'self'"
        )
        return response

    dist = ROOT / "apps/portal/dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    @app.get("/workspace/{run_id}")
    def index(run_id=None):
        if not (dist / "index.html").exists():
            raise HTTPException(503, "Build apps/portal first")
        return FileResponse(dist / "index.html")

    return app
