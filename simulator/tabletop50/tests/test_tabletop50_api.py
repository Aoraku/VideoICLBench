import importlib
import json
import hashlib
import pytest

from fastapi.testclient import TestClient


def test_invisible_fixture_demonstration_cannot_be_served(tmp_path, monkeypatch):
    from simulator.tabletop50 import server
    monkeypatch.setattr(server, "DATA", tmp_path)
    monkeypatch.setattr(server, "source_hash", lambda: "fixture-source")
    folder = tmp_path/"demos"/"F01-A-0"; folder.mkdir(parents=True)
    (folder/"video.mp4").write_bytes(b"test-only-decoder-cache-fixture")
    digest = hashlib.sha256((folder/"video.mp4").read_bytes()).hexdigest()
    proof = dict(task="F01", variant="A", seed=0, score=dict(success=True), error=None,
                 source_unchanged=True, source_sha256="fixture-source", cross_rule_predicates=dict(A=True,B=False,C=False),
                 video=dict(recorded=True,full_episode=True,final_success=True,frames=1,sha256=digest),
                 visual_environment=dict(fixtures_visible=True))
    audit = dict(video_sha256=digest,decoded_frames=1,ending_image_mae=0,
                 visual_environment=dict(fixtures_visible=True),usable_for_agent_demo=True)
    request = server.Create(task="F01",variant="A",seed=1)
    (folder/"result.private.json").write_text(json.dumps(proof))
    (folder/"media-audit.private.json").write_text(json.dumps(audit))
    assert server.validated_demo(request) == folder/"video.mp4"
    proof["visual_environment"]["fixtures_visible"] = False
    (folder/"result.private.json").write_text(json.dumps(proof))
    with pytest.raises(server.HTTPException): server.validated_demo(request)
    proof["visual_environment"]["fixtures_visible"] = True
    (folder/"result.private.json").write_text(json.dumps(proof))
    audit["usable_for_agent_demo"] = False
    (folder/"media-audit.private.json").write_text(json.dumps(audit))
    with pytest.raises(server.HTTPException): server.validated_demo(request)


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
