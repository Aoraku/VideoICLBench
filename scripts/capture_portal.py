"""Capture this project's local portal for UI verification; credentials stay private."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    root = Path(__file__).resolve().parents[1]
    token = (root / ".local/admin-token").read_text().strip()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 1000})
        failures = []
        page.on("pageerror", lambda e: failures.append(str(e)))
        await page.goto("http://127.0.0.1:8765/")
        await page.get_by_label("访问密钥").fill(token)
        await page.get_by_role("button", name="连接工作台 →").click()
        await page.get_by_role("heading", name="任务大厅").wait_for()
        await page.get_by_role(
            "cell", name="通讯 A：发送一条指定文本", exact=False
        ).click()
        await page.screenshot(path=str(root / ".local/portal.png"), full_page=True)
        await page.set_viewport_size({"width": 780, "height": 1000})
        await page.screenshot(
            path=str(root / ".local/portal-tablet.png"), full_page=True
        )
        assert not failures, failures
        await browser.close()
        print("Portal browser checks passed; screenshots saved under .local/.")


asyncio.run(main())
