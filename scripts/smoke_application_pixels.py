"""Pixel-only recording smoke test against an actual application module."""

import json
import os
import time
import uuid
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
token = (
    os.environ.get("VIC_ADMIN_TOKEN")
    or (root / ".local/admin-token").read_text().strip()
)
with httpx.Client(
    base_url=os.environ.get("VIC_TEST_BASE", "http://127.0.0.1:8765"),
    headers={"Authorization": "Bearer " + token},
    timeout=120,
) as c:
    response = c.post(
        "/v1/runs",
        json=dict(task_id=1, variant="A", seed=1, mode="demo", runtime="browser"),
    )
    response.raise_for_status()
    run = response.json()
    path = "/v1/runs/" + run["id"]
    c.get(path + "/observation").raise_for_status()
    c.post(path + "/recordings/start").raise_for_status()
    # Test harness knows the fixture and rule; the tested execution channel is pixels.
    # Never pass the fixture or private rule to a model under evaluation.
    from vic.business import generate

    text = generate(1, 1)["source"]["text"]
    answer = text[:1].lower() + text[1:].upper()

    def act(kind, **kwargs):
        shot = c.get(path + "/observation")
        shot.raise_for_status()
        shot = shot.json()
        result = c.post(
            path + "/actions",
            json=dict(
                epoch=run["epoch"],
                frame=shot["frame"],
                action_id=uuid.uuid4().hex,
                kind=kind,
                **kwargs,
            ),
        )
        result.raise_for_status()

    act("click", x=850, y=350)
    act("text", text=answer)
    act("click", x=760, y=635)
    time.sleep(0.5)
    recording = c.post(path + "/recordings/stop")
    recording.raise_for_status()
    assert c.get(path).json()["status"] == "recorded"
    assert (
        c.post(
            path + "/actions",
            json=dict(
                epoch=0, frame=0, action_id=uuid.uuid4().hex, kind="wait", wait_ms=1
            ),
        ).status_code
        == 409
    )
    result = c.post(path + "/evaluate")
    result.raise_for_status()
    assert result.json()["success"], result.text
    assert c.post(path + "/evaluate").json() == result.json()
    destination = root / ".local/application-pixel-result.json"
    destination.write_text(
        json.dumps(
            dict(run_id=run["id"], result=result.json(), recording=recording.json()),
            indent=2,
        )
    )
    print("PASS: pixel input → real workspace → sealed evaluation → MP4 recording")
    print("Automated smoke recording is not an approved human tutorial.")
