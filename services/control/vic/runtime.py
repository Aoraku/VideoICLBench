import asyncio
import contextlib
import base64
import time
import os
import socket
from urllib.parse import urlsplit
from playwright.async_api import async_playwright


class BrowserRuntime:
    """Local development only: real Chromium pixels, no DOM observation API."""

    def __init__(self):
        self.driver = None
        self.browser = None
        self.sessions = {}
        self.lock = asyncio.Lock()
        self.limits = {}

    async def ensure(self, run_id, url):
        async with self.lock:
            if run_id in self.sessions:
                return self.sessions[run_id]
            if self.driver is None:
                self.driver = await async_playwright().start()
            owned_browser = None
            origin = urlsplit(url)
            # Native workflow routes also use the secure application origin.
            # Without this mapping Chromium resolves .localhost to this container.
            if "/apps/" in origin.path or origin.hostname == "application.localhost":
                args = []
                if origin.hostname == "application.localhost":
                    backend = urlsplit(
                        os.environ.get("VIC_APPLICATION_BASE", "http://127.0.0.1:8771")
                    ).hostname
                    address = socket.gethostbyname(backend)
                    args = [
                        f"--host-resolver-rules=MAP application.localhost {address}"
                    ]
                owned_browser = await self.driver.chromium.launch(
                    headless=True, args=args
                )
                browser = owned_browser
            else:
                if self.browser is None:
                    self.browser = await self.driver.chromium.launch(headless=True)
                browser = self.browser
            context = await browser.new_context(
                viewport={"width": 1280, "height": 960},
                device_scale_factor=1,
                locale="zh-CN",
                permissions=["clipboard-read", "clipboard-write"],
            )
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle")
            except BaseException:
                await context.close()
                if owned_browser:
                    await owned_browser.close()
                raise
            session = dict(
                context=context,
                owned_browser=owned_browser,
                page=page,
                frame=0,
                actions={},
                action_lock=asyncio.Lock(),
                created=time.monotonic(),
                cursor=None,
            )
            self.sessions[run_id] = session
            return session

    async def screenshot(self, run_id, url):
        session = await self.ensure(run_id, url)
        async with session["action_lock"]:
            data = await session["page"].screenshot(type="png")
            session["frame"] += 1
            return dict(
                image="data:image/png;base64," + base64.b64encode(data).decode(),
                frame=session["frame"],
                width=1280,
                height=960,
            )

    async def capture(self, run_id, url):
        session = await self.ensure(run_id, url)
        async with session["action_lock"]:
            return await session["page"].screenshot(type="png")

    async def act(self, run_id, url, action):
        s = await self.ensure(run_id, url)
        async with s["action_lock"]:
            data = action.model_dump()
            if action.action_id in s["actions"]:
                prior, result = s["actions"][action.action_id]
                if prior != data:
                    raise ValueError("Action ID collision")
                return result
            if action.frame != s["frame"]:
                raise ValueError("Stale observation; request a new screenshot")
            limits = self.limits.get(run_id, {"max_actions": 120, "timeout_seconds": 300})
            if len(s["actions"]) >= limits["max_actions"]:
                raise ValueError("Action budget exhausted")
            if time.monotonic() - s["created"] > limits["timeout_seconds"]:
                raise ValueError("Time budget exhausted")
            page = s["page"]
            kind = action.kind
            if kind in ("click", "right_click", "double_click", "drag") and (
                action.x is None or action.y is None
            ):
                raise ValueError("Coordinates required")
            if kind in ("click", "right_click", "double_click", "drag"):
                s["cursor"] = (action.x, action.y, time.monotonic())
            if kind == "click":
                await page.mouse.click(action.x, action.y)
            elif kind == "right_click":
                await page.mouse.click(action.x, action.y, button="right")
            elif kind == "double_click":
                await page.mouse.dblclick(action.x, action.y)
            elif kind == "drag":
                if action.to_x is None or action.to_y is None:
                    raise ValueError("Drag endpoint required")
                await page.mouse.move(action.x, action.y)
                await page.mouse.down()
                await page.mouse.move(action.to_x, action.to_y, steps=10)
                await page.mouse.up()
            elif kind == "scroll":
                if action.x is not None and action.y is not None:
                    await page.mouse.move(action.x, action.y)
                await page.mouse.wheel(0, action.delta_y)
            elif kind == "key":
                if not action.key:
                    raise ValueError("Key required")
                aliases = {"Return": "Enter", "Left": "ArrowLeft", "Right": "ArrowRight",
                           "Up": "ArrowUp", "Down": "ArrowDown", "Esc": "Escape"}
                key = "+".join(aliases.get(part, part) for part in action.key.split("+"))
                await page.keyboard.press(key)
            elif kind == "text":
                await page.keyboard.insert_text(action.text)
            elif kind == "wait":
                await asyncio.sleep(action.wait_ms / 1000)
            await page.wait_for_timeout(100)
            result = dict(accepted=True, action_id=action.action_id, frame=s["frame"])
            s["actions"][action.action_id] = (data, result)
            return result

    async def clipboard(self, run_id):
        session = self.sessions.get(run_id)
        if not session:
            return None
        return await session["page"].evaluate("navigator.clipboard.readText()")

    async def close_run(self, run_id):
        self.limits.pop(run_id, None)
        s = self.sessions.pop(run_id, None)
        if s:
            with contextlib.suppress(Exception):
                await s["context"].close()
            if s.get("owned_browser"):
                with contextlib.suppress(Exception):
                    await s["owned_browser"].close()

    async def close(self):
        for run_id in list(self.sessions):
            await self.close_run(run_id)
        if self.browser:
            with contextlib.suppress(Exception):
                await self.browser.close()
        if self.driver:
            with contextlib.suppress(Exception):
                await self.driver.stop()
