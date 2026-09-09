"""Development capacity check: five recorded sessions plus ten pixel agents."""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
import httpx
from vic.business import generate

ROOT = Path(__file__).resolve().parents[1]


async def main():
    token = (
        os.environ.get("VIC_ADMIN_TOKEN")
        or (ROOT / ".local/admin-token").read_text().strip()
    )
    base = os.environ.get("VIC_TEST_BASE", "http://127.0.0.1:8765")
    headers = {"Authorization": "Bearer " + token}
    started = time.monotonic()
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=180) as c:

        async def request(method, path, **kwargs):
            r = await c.request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()

        async def create(i):
            seed = i + 10 if i < 5 else i + 1010
            run = await request(
                "POST",
                "/v1/runs",
                json=dict(
                    task_id=1,
                    variant="A",
                    seed=seed,
                    mode="demo" if i < 5 else "eval",
                    runtime="browser",
                ),
            )
            run["_seed"] = seed
            run["_human"] = i < 5
            await request("GET", f"/v1/runs/{run['id']}/observation")
            return run

        runs = await asyncio.gather(*(create(i) for i in range(15)))

        async def execute(run):
            path = f"/v1/runs/{run['id']}"
            actor = (
                headers
                if run["_human"]
                else {"Authorization": "Bearer " + run["actor_token"]}
            )
            if run["_human"]:
                await request("POST", path + "/recordings/start")
            source = generate(1, run["_seed"])["source"]["text"]
            for kind, args in [
                ("click", dict(x=850, y=350)),
                ("text", dict(text=source[:1].lower() + source[1:].upper())),
                ("click", dict(x=760, y=635)),
            ]:
                shot = await request("GET", path + "/observation", headers=actor)
                await request(
                    "POST",
                    path + "/actions",
                    headers=actor,
                    json=dict(
                        epoch=0,
                        frame=shot["frame"],
                        action_id=uuid.uuid4().hex,
                        kind=kind,
                        **args,
                    ),
                )
            if run["_human"]:
                await request("POST", path + "/recordings/stop")
            result = await request("POST", path + "/evaluate")
            assert result["success"], result
            evidence = await request("GET", path + "/evidence")
            assert evidence["initial"]["source"]["text"] == source
            assert evidence["result"]["official"] is False
            return {"run_id": run["id"], "recorded": run["_human"], "success": True}

        try:
            results = await asyncio.gather(*(execute(run) for run in runs))
            denied = await c.get(
                f"/v1/runs/{runs[1]['id']}/observation",
                headers={"Authorization": "Bearer " + runs[0]["actor_token"]},
            )
            assert denied.status_code == 403
            await request("POST", f"/v1/runs/{runs[0]['id']}/reset")
            for run in runs[1:]:
                assert (await request("GET", f"/v1/runs/{run['id']}"))["result"][
                    "success"
                ]
            report = dict(
                surface="application-benchmark",
                official=False,
                sessions=15,
                recorded=5,
                agent_sessions=10,
                elapsed_seconds=round(time.monotonic() - started, 2),
                results=results,
            )
            (ROOT / ".local/application-concurrency-result.json").write_text(
                json.dumps(report, indent=2)
            )
            print(
                "PASS: 15 isolated pixel sessions, including 5 concurrent recordings; independent browser processes and application databases."
            )
        finally:
            for run in runs:
                await c.delete(f"/v1/runs/{run['id']}")


if __name__ == "__main__":
    asyncio.run(main())
