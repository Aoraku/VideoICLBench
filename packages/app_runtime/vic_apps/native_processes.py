"""Lifecycle of the original Streamlit frontend, one process per run."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import httpx
from vic.config import ROOT


class NativeProcesses:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.code = {}
        self.gomoku = {}
        self.lock = asyncio.Lock()

    async def start_code(self, run_id, token):
        async with self.lock:
            prior = self.code.get(run_id)
            if prior and prior["process"].poll() is None:
                return prior["port"]
            if len(self.code) + len(self.gomoku) >= 12:
                raise ValueError("Code application capacity reached; close another run")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            log = (self.directory / run_id / "streamlit.log").open("ab")
            env = dict(os.environ, VIC_NATIVE_RUN=run_id, VIC_NATIVE_TOKEN=token,
                       VIC_NATIVE_SELF_BASE=os.environ.get("VIC_NATIVE_SELF_BASE", "http://127.0.0.1:8771"))
            process = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run", str(ROOT / "apps/code/app/frontend.py"),
                "--server.address=127.0.0.1", f"--server.port={port}",
                f"--server.baseUrlPath=native/code/{run_id}", "--server.headless=true",
                "--server.enableCORS=false", "--server.enableXsrfProtection=false",
                "--browser.gatherUsageStats=false", "--server.fileWatcherType=none",
            ], env=env, stdout=log, stderr=subprocess.STDOUT)
            log.close()
            self.code[run_id] = dict(process=process, port=port, started=time.monotonic())
            async with httpx.AsyncClient(trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        break
                    try:
                        response = await client.get(f"http://127.0.0.1:{port}/native/code/{run_id}/_stcore/health", timeout=1)
                        if response.is_success:
                            return port
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
            self.stop(run_id)
            raise ValueError("Original Code frontend failed to start")

    async def start_gomoku(self, run_id):
        async with self.lock:
            prior = self.gomoku.get(run_id)
            if prior and prior["process"].poll() is None:
                return prior["port"]
            if len(self.code) + len(self.gomoku) >= 12:
                raise ValueError("Native application capacity reached; close another run")
            directory = self.directory / run_id
            (directory / "gomoku-intents.txt").write_text("")
            binary = ROOT / "apps/gomoku/build/gomoku_benchmark"
            if not binary.exists():
                raise ValueError("Original SDL application requires the Linux desktop image")
            display = next(i for i in range(120, 240) if not Path(f"/tmp/.X11-unix/X{i}").exists())
            def free_port():
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    return sock.getsockname()[1]
            rfb_port, web_port = free_port(), free_port()
            log = (directory / "desktop.log").open("ab")
            env = dict(os.environ, DISPLAY=f":{display}", SDL_RENDER_DRIVER="software",
                       SDL_VIDEO_X11_REQUIRE_WM="0", VIC_BENCH_DIRECTORY=str(directory))
            children = []
            def spawn(command, **kwargs):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, **kwargs)
                children.append(process)
                return process
            try:
                spawn(["Xvfb", f":{display}", "-screen", "0", "1280x960x24", "-nolisten", "tcp"])
                for _ in range(50):
                    if Path(f"/tmp/.X11-unix/X{display}").exists():
                        break
                    await asyncio.sleep(0.1)
                spawn(["x11vnc", "-forever", "-shared", "-localhost", "-rfbport", str(rfb_port),
                       "-display", f":{display}", "-nopw", "-quiet"])
                spawn(["websockify", "--web=/usr/share/novnc", f"127.0.0.1:{web_port}", f"127.0.0.1:{rfb_port}"])
                process = spawn([str(binary)], cwd=str(ROOT / "apps/gomoku"))
                self.gomoku[run_id] = dict(process=process, children=children, port=web_port)
                async with httpx.AsyncClient(trust_env=False) as client:
                    for _ in range(100):
                        try:
                            response = await client.get(f"http://127.0.0.1:{web_port}/vnc.html", timeout=1)
                            if response.is_success and process.poll() is None:
                                return web_port
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(0.1)
                raise ValueError("SDL desktop failed to start")
            except Exception:
                for process in reversed(children):
                    process.terminate()
                self.gomoku.pop(run_id, None)
                raise
            finally:
                log.close()

    def port(self, run_id):
        item = self.code.get(run_id) or self.gomoku.get(run_id)
        if item and item["process"].poll() is None:
            return item["port"]
        return None

    def stop(self, run_id):
        desktop = self.gomoku.pop(run_id, None)
        if desktop:
            for process in reversed(desktop["children"]):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        item = self.code.pop(run_id, None)
        if item:
            item["process"].terminate()
            try:
                item["process"].wait(timeout=3)
            except subprocess.TimeoutExpired:
                item["process"].kill()
                item["process"].wait(timeout=3)

    def close(self):
        for run_id in list(self.code) + list(self.gomoku):
            self.stop(run_id)
