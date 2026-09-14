"""Exercise human keyboard input through the portal's remote image surface."""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright, expect
from vic.business import generate


async def main():
    root = Path(__file__).resolve().parents[1]
    token = os.environ.get("VIC_ADMIN_TOKEN") or (
        root / ".local/admin-token"
    ).read_text().strip()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 1100})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(os.environ.get("VIC_TEST_BASE", "http://127.0.0.1:8765") + "/")
        await page.get_by_label("访问密钥").fill(token)
        await page.get_by_role("button", name="连接工作台 →").click()
        await page.get_by_role(
            "cell", name="通讯 A：发送一条指定文本", exact=False
        ).click()
        await page.get_by_role("button", name="准备独立环境 →").click()
        await page.get_by_role("img", name="远程环境画面").wait_for()
        remote = page.get_by_label("远程操作画面")
        box = await remote.bounding_box()

        async def click(x, y):
            await remote.click(
                position={"x": x * box["width"] / 1280, "y": y * box["height"] / 960}
            )

        await click(850, 350)
        source = generate(1, 0)["source"]["text"]
        answer = source[:1].lower() + source[1:].upper()
        await page.keyboard.type(answer, delay=5)
        await click(760, 635)
        await page.get_by_role("button", name="结束并评测").click()
        await expect(page.get_by_role("heading", name="任务通过")).to_be_visible(
            timeout=60000
        )
        assert not errors, errors
        await page.screenshot(
            path=str(root / ".local/portal-input-pass.png"), full_page=True
        )
        await browser.close()
        print(
            "PASS: portal mouse/fast keyboard queue → remote browser → successful evaluation."
        )


asyncio.run(main())
