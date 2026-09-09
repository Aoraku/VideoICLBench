import pytest
from fastapi.testclient import TestClient
from vic.main import create_app

SECRET = "test-admin-credential-" + "x" * 40


@pytest.fixture
def client(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path}/control.db",
        data_dir=tmp_path,
        secret=SECRET,
    )
    with TestClient(app) as c:
        yield c


def admin():
    return {"Authorization": "Bearer " + SECRET}


def create(client, **changes):
    body = dict(task_id=1, variant="A", seed=1000, mode="eval", runtime="web-dev")
    body.update(changes)
    r = client.post("/v1/runs", headers=admin(), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def ui(run):
    return {"Authorization": "Bearer " + run["workspace_url"].split("#")[1]}


def mutate(client, run, **changes):
    body = dict(
        epoch=run["epoch"],
        action_id="one",
        op="save",
        target="target",
        value="wrong",
        ids=[],
    )
    body.update(changes)
    return client.post(
        f"/v1/workspaces/{run['id']}/mutations", headers=ui(run), json=body
    )


def test_auth_and_scope(client):
    assert client.get("/v1/tasks").status_code == 401
    a, b = create(client), create(client)
    actor = {"Authorization": "Bearer " + a["actor_token"]}
    assert client.get("/v1/tasks", headers=actor).status_code == 403
    assert client.post(f"/v1/runs/{a['id']}/evaluate", headers=actor).status_code == 403
    assert client.get(f"/v1/workspaces/{a['id']}", headers=actor).status_code == 403
    assert (
        client.get(f"/v1/runs/{b['id']}/observation", headers=actor).status_code == 403
    )
    assert client.get(f"/v1/workspaces/{b['id']}", headers=ui(a)).status_code == 403


def test_independent_state_reset_and_stale_credentials(client):
    a, b = create(client), create(client)
    assert mutate(client, a).status_code == 200
    b_state = client.get(f"/v1/workspaces/{b['id']}", headers=ui(b)).json()["state"]
    assert b_state["outputs"] == {}
    reset = client.post(f"/v1/runs/{a['id']}/reset", headers=admin()).json()
    assert reset["epoch"] == 1
    assert mutate(client, a).status_code == 403
    fresh = client.get(f"/v1/workspaces/{a['id']}", headers=ui(reset)).json()
    assert fresh["state"]["outputs"] == {}
    assert mutate(client, reset, epoch=0).status_code == 409


def test_idempotency_seal_and_stable_evaluation(client):
    run = create(client)
    r1 = mutate(client, run)
    r2 = mutate(client, run)
    assert r1.json() == r2.json()
    assert mutate(client, run, value="different").status_code == 422
    result = client.post(f"/v1/runs/{run['id']}/evaluate", headers=admin())
    assert result.status_code == 200
    assert result.json()["success"] is False
    assert (
        result.json()
        == client.post(f"/v1/runs/{run['id']}/evaluate", headers=admin()).json()
    )
    assert mutate(client, run, action_id="two").status_code == 409
    evidence = client.get(result.json()["evidence_ref"], headers=admin()).json()
    assert len(evidence["events"]) == 1
    assert evidence["result"] == result.json()


def test_no_simulated_native_runtime(client):
    for runtime in ["windows", "linux", "android"]:
        assert (
            client.post(
                "/v1/runs",
                headers=admin(),
                json=dict(task_id=1, variant="A", seed=1000, runtime=runtime),
            ).status_code
            == 409
        )
    assert (
        client.post(
            "/v1/runs", headers=admin(), json=dict(task_id=99, variant="A", seed=1000)
        ).status_code
        == 409
    )


def test_seed_partitions_and_review_guard(client):
    assert (
        client.post(
            "/v1/runs",
            headers=admin(),
            json=dict(task_id=1, variant="A", seed=0, mode="eval"),
        ).status_code
        == 422
    )
    run = create(client, seed=0, mode="demo")
    assert (
        client.post(
            f"/v1/runs/{run['id']}/recordings/review",
            headers=admin(),
            json={"approved": True, "reviewer": "tester"},
        ).status_code
        == 409
    )


def test_destroyed_workspace_cannot_be_resurrected(client):
    run = create(client)
    path = f"/v1/runs/{run['id']}"
    assert client.delete(path, headers=admin()).status_code == 200
    assert client.post(path + "/reset", headers=admin()).status_code == 410
    assert client.get(f"/v1/workspaces/{run['id']}", headers=ui(run)).status_code == 410
    assert client.get(path, headers=admin()).json()["status"] == "destroyed"
    assert not (client.app.state.store.directory / run["id"]).exists()


def test_reset_archives_recording_and_invalidates_review(client, tmp_path):
    import json

    run = create(client, seed=0, mode="demo")
    path = f"/v1/runs/{run['id']}"
    artifact = tmp_path / "artifacts" / run["id"]
    artifact.mkdir(parents=True)
    (artifact / "recording.json").write_text(
        json.dumps({"epoch": 0, "status": "pending_review"})
    )
    (artifact / "tutorial.mp4").write_bytes(b"test fixture")
    assert client.post(path + "/reset", headers=admin()).status_code == 200
    assert (artifact / "epoch-0/tutorial.mp4").exists()
    assert client.get(path + "/recordings/video", headers=admin()).status_code == 404
    assert (
        client.post(
            path + "/recordings/review",
            headers=admin(),
            json={"approved": True, "reviewer": "tester"},
        ).status_code
        == 409
    )
