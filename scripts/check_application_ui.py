"""Development control regression; this is NOT native frontend acceptance.

DOM locators are used only by this private QA harness. Agent API remains pixels.
"""

import os
import asyncio, json, importlib.util, sys, time
from pathlib import Path
import httpx
import uvicorn
from playwright.async_api import expect
from vic.main import create_app
from vic.runtime import BrowserRuntime
from vic.business import generate
from vic_apps.domain import initialize

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "references", ROOT / "tests/test_applications.py"
)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


async def main():
    secret = (
        os.environ.get("VIC_ADMIN_TOKEN")
        or (ROOT / ".local/admin-token").read_text().strip()
    )
    runtime = BrowserRuntime()
    data = Path(os.environ.get("VIC_QA_DATA", ROOT / ".local/gui-acceptance"))
    data.mkdir(parents=True, exist_ok=True)
    app = create_app(
        database_url=f"sqlite:///{data}/control.db",
        data_dir=data,
        secret=secret,
        browser=runtime,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8767, log_level="error")
    )
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    results = []
    start = time.monotonic()
    subset = (
        [int(s) for s in sys.argv[1].split(",")]
        if len(sys.argv) > 1
        else list(range(1, 76))
    )
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8767",
        headers={"Authorization": "Bearer " + secret},
        timeout=120,
    ) as client:

        async def request(method, path, **kw):
            r = await client.request(method, path, **kw)
            r.raise_for_status()
            return r.json()

        try:
            for t in subset:
                for v in "ABC":
                    run = await request(
                        "POST",
                        "/v1/runs",
                        json=dict(
                            task_id=t,
                            variant=v,
                            seed=10001,
                            mode="eval",
                            runtime="browser",
                        ),
                    )
                    path = f"/v1/runs/{run['id']}"
                    await request("GET", path + "/observation")
                    page = runtime.sessions[run["id"]]["page"]
                    await page.goto(page.url.replace("#", "?diagnostic=1#"))
                    page.set_default_timeout(12000)
                    failures = []
                    page.on("pageerror", lambda e: failures.append(str(e)))
                    commands = reference.reference(initialize(generate(t, 10001)), v)
                    try:
                        for op, target, value, ids in commands:

                            async def click(button):
                                async with page.expect_response(
                                    lambda r: (
                                        r.url.endswith("/commands")
                                        and r.request.method == "POST"
                                    )
                                ) as reply:
                                    await button.click()
                                assert (await reply.value).ok
                                await expect(
                                    page.locator(".application").first
                                ).to_be_visible()

                            row = page.locator(f'article[data-object-id="{target}"]')
                            if op == "save":
                                await page.get_by_label("编辑内容").fill(value)
                                await click(page.locator(".document-editor>button"))
                            elif op == "label":
                                async with page.expect_response(
                                    lambda r: r.url.endswith("/commands")
                                ) as reply:
                                    await page.get_by_role("button", name=f"分类 {target}", exact=True).click()
                                    await page.get_by_role("option", name=value or "清除标签", exact=False).click()
                                assert (await reply.value).ok
                            elif op in ("select", "invite"):
                                for id_ in ids:
                                    await (
                                        page.locator(f'article[data-object-id="{id_}"]')
                                        .get_by_role("button", name="选择", exact=True)
                                        .click()
                                    )
                                await click(page.locator(".application-confirm button"))
                            elif op == "order":
                                for destination, id_ in enumerate(ids):
                                    current = await page.locator(
                                        ".record-list article"
                                    ).evaluate_all(
                                        "(els)=>els.map(e=>e.dataset.objectId)"
                                    )
                                    for _ in range(current.index(id_) - destination):
                                        await (
                                            page.locator(
                                                f'article[data-object-id="{id_}"]'
                                            )
                                            .get_by_role(
                                                "button", name="↑ 上移", exact=True
                                            )
                                            .click()
                                        )
                                await click(page.locator(".application-confirm button"))
                            elif op == "action":
                                await click(
                                    row.get_by_role("button", name=value, exact=True)
                                )
                            elif op == "move":
                                await click(
                                    page.get_by_role(
                                        "button",
                                        name={
                                            "left": "← 左",
                                            "up": "↑ 上",
                                            "right": "右 →",
                                            "down": "↓ 下",
                                        }[value],
                                        exact=True,
                                    )
                                )
                            elif op == "stop":
                                await click(
                                    page.get_by_role(
                                        "button", name="停止操作", exact=True
                                    )
                                )
                            elif op in ("choose", "mark", "fill"):
                                r, c = map(int, target.split(","))
                                cell = page.get_by_role(
                                    "button", name=f"第{r + 1}行第{c + 1}列", exact=True
                                )
                                if op == "fill":
                                    await cell.click()
                                    await click(
                                        page.locator(".game-controls").get_by_role(
                                            "button", name=value, exact=True
                                        )
                                    )
                                else:
                                    await click(cell)
                        outcome = await request(
                            "POST", f"/v1/tasks/{t}/eval", json=dict(run_id=run["id"])
                        )
                        assert outcome["success"], outcome
                        assert not failures, failures
                        if v == "A" and (
                            t
                            in (
                                1,
                                15,
                                17,
                                19,
                                21,
                                36,
                                37,
                                44,
                                45,
                                46,
                                58,
                                66,
                                68,
                                70,
                                72,
                                74,
                            )
                        ):
                            image = await client.get(path + "/final-image")
                            image.raise_for_status()
                            (data / f"task-{t:03d}.png").write_bytes(image.content)
                        results.append(
                            dict(task_id=t, variant=v, success=True, run_id=run["id"])
                        )
                    except Exception as error:
                        if not page.is_closed():
                            await page.screenshot(
                                path=str(data / f"FAILED-{t}-{v}.png"), full_page=True
                            )
                        results.append(
                            dict(task_id=t, variant=v, success=False, error=str(error))
                        )
                        raise
                    finally:
                        await request("DELETE", path)
                print(
                    f"PASS task {t:03d}: A/B/C through development diagnostic controls", flush=True
                )
        finally:
            (data / "report.json").write_text(
                json.dumps(
                    dict(
                        surface="development-diagnostic",
                        elapsed=round(time.monotonic() - start, 2),
                        results=results,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            server.should_exit = True
            await serving


asyncio.run(main())
