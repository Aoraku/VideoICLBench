import pytest
from fastapi.testclient import TestClient
from vic.main import create_app
from vic.app_client import ApplicationClient
from vic.business import transform
from vic_apps.server import create_app as app_worker
from test_api import SECRET, admin


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv("VIC_APP_DATA", str(tmp_path / "applications"))
    monkeypatch.setenv("VIC_APP_RUNTIME_TOKEN", SECRET)
    worker = TestClient(app_worker())

    def request(self, method, path, body=None):
        r = worker.request(
            method, path, headers={"Authorization": "Bearer " + SECRET}, json=body
        )
        r.raise_for_status()
        return r.json()

    monkeypatch.setattr(ApplicationClient, "call", request)
    app = create_app(
        database_url=f"sqlite:///{tmp_path}/control.db",
        data_dir=tmp_path / "control",
        secret=SECRET,
    )
    with TestClient(app) as control:
        yield control, worker


def create(c, t=1):
    r = c.post(
        "/v1/runs",
        headers=admin(),
        json=dict(task_id=t, variant="A", seed=10001, runtime="browser"),
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_task_contracts_and_scoped_evaluation(clients):
    c, w = clients
    for t in range(1, 101):
        contract = c.get(f"/v1/tasks/{t}/contract", headers=admin()).json()
        assert contract["task_id"] == t and set(contract["variants"]) == set("ABC")
        assert contract["status"] == ("implemented" if t <= 75 else "deferred-system")
    r = create(c)
    path = "/api/runs/" + r["id"]
    ui = {"Authorization": "Bearer " + r["workspace_url"].split("#")[1]}
    state = w.get(path, headers=ui).json()["state"]
    assert (
        w.post(
            path + "/commands",
            headers={"Authorization": "Bearer " + r["actor_token"]},
            json=dict(
                epoch=0, action_id="1", op="save", target="target", value="wrong"
            ),
        ).status_code
        == 403
    )
    assert c.get("/v1/workspaces/" + r["id"], headers=ui).status_code == 409
    assert (
        w.post(
            path + "/commands",
            headers=ui,
            json=dict(
                epoch=0,
                action_id="1",
                op="save",
                target="target",
                value=transform(1, 0, state),
            ),
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/v1/tasks/2/eval", headers=admin(), json={"run_id": r["id"]}
        ).status_code
        == 409
    )
    result = c.post("/v1/tasks/1/eval", headers=admin(), json={"run_id": r["id"]})
    assert result.json()["success"], result.text
    assert (
        result.json()
        == c.post("/v1/tasks/1/eval", headers=admin(), json={"run_id": r["id"]}).json()
    )
    assert (
        w.post(
            path + "/commands",
            headers=ui,
            json=dict(epoch=0, action_id="2", op="save", target="target", value="late"),
        ).status_code
        == 409
    )
    reset = c.post("/v1/runs/" + r["id"] + "/reset", headers=admin()).json()
    assert reset["epoch"] == 1
    assert w.get(path, headers=ui).status_code == 403
    fresh = {"Authorization": "Bearer " + reset["workspace_url"].split("#")[1]}
    assert (
        w.get(path, headers=fresh).json()["state"]["domain"]["messages"]
        == state["domain"]["messages"]
    )
    assert c.delete("/v1/runs/" + r["id"], headers=admin()).status_code == 200
    assert w.get(path, headers=fresh).status_code == 410


def test_attachment_bytes_and_group_members_are_business_records(clients):
    c, w = clients
    r = create(c, 11)
    token = {"Authorization": "Bearer " + r["workspace_url"].split("#")[1]}
    path = "/api/runs/" + r["id"]
    state = w.get(path, headers=token).json()["state"]
    file = state["items"][0]
    response = w.get(path + "/files/" + file["id"], headers=token)
    assert response.status_code == 200 and len(response.content) == file["size"]
    assert w.get(path + "/files/" + file["id"]).status_code == 403
