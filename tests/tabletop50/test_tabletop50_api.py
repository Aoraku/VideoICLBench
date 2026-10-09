import importlib
import json

from fastapi.testclient import TestClient


def test_actor_boundary_and_rule_matching(tmp_path, monkeypatch):
    monkeypatch.setenv("TABLETOP50_DATA", str(tmp_path))
    from simulator.tabletop50 import server
    api = importlib.reload(server)
    api.SESSIONS.clear()
    headers = {"Authorization": "Bearer "+api.ADMIN}
    with TestClient(api.app) as client:
        assert client.get("/admin/catalog").status_code == 401
        assert client.post("/admin/sessions", headers=headers, json=dict(
            task="F01", variant="B", seed=0)).status_code == 409
        # A verified A video must never silently serve a B episode.
        folder = tmp_path/"demos"/"F01-A-0"; folder.mkdir(parents=True)
        (folder/"result.private.json").write_text(json.dumps(dict(task="F01", variant="A", seed=0)))
        assert client.post("/admin/sessions", headers=headers, json=dict(
            task="F01", variant="B", seed=1)).status_code == 409
        response = client.post("/admin/sessions", headers=headers, json=dict(
            task="F01", variant="B", seed=7, condition="no_demo", trial_kind="protocol_smoke"))
        assert response.status_code == 200, response.text
        sid = response.json()["session"]
        obs = client.get(f"/actor/{sid}/observe")
        assert obs.status_code == 200, obs.text
        assert set(obs.json()) == {"images", "instruction", "actions", "remaining", "tokens"}
        assert set(obs.json()["images"]) == {"fpv", "robot0_eye_in_hand", "robot1_eye_in_hand"}
        assert client.post(f"/actor/{sid}/action", json=dict(left="UP_FINE")).status_code == 200
        assert client.post(f"/actor/{sid}/submit").json() == {"ended": True}
        assert client.get(f"/admin/results/{sid}").status_code == 401
        result = client.get(f"/admin/results/{sid}", headers=headers).json()
        assert result["trial_kind"] == "protocol_smoke" and result["success"] is False
        assert client.get(f"/actor/{sid}/observe").status_code == 410
