"""MCP transport for native agents. No model calls or conversation management."""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
import threading
import uuid
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import BeforeValidator, WithJsonSchema


def normalize_coordinate(value):
    # Some gateways encode a single integer as "65, ". Accept only this
    # unambiguous formatting variant, never a pair, expression or fractional pixel.
    if isinstance(value, str) and re.fullmatch(r"\s*\d+\s*,?\s*", value):
        return int(value.strip().rstrip(",").strip())
    return value


PixelCoordinate = Annotated[int | str | None, BeforeValidator(normalize_coordinate),
                            WithJsonSchema({"anyOf": [{"type": "integer"}, {"type": "null"}]})]


def normalize_point(x, y):
    # A redundant "x,y" string is safe only when the separate y agrees.
    if isinstance(x, str):
        pair = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", x)
        if pair and y is not None and int(pair[2]) == y:
            x = int(pair[1])
    if isinstance(x, str) or isinstance(y, str):
        raise ValueError("Conflicting or invalid pixel coordinates; use separate integer x and y")
    return x, y


class Computer:
    def __init__(self, config: dict):
        self.config = config
        self.http = httpx.Client(base_url=config["control_url"], timeout=90,
            headers={"Authorization": "Bearer " + config["actor_token"]})
        self.path = config.get("run_path", "/v1/runs/" + config["run_id"])
        self.frame = None
        self.epoch = None
        self.lock = threading.RLock()
        self.actions = 0
        self.started = time.monotonic()
        self.closed = False
        self.output = Path(config["output_dir"])
        self.output.mkdir(parents=True, exist_ok=True)
        log = self.output / "computer.jsonl"
        if log.exists():
            self.actions = sum(json.loads(line).get("type") == "action" for line in log.read_text().splitlines())

    def log(self, event: dict):
        with (self.output / "computer.jsonl").open("a") as f:
            f.write(json.dumps({"time": time.time(), **event}, ensure_ascii=False) + "\n")

    def check(self):
        if self.closed:
            raise ValueError("This session is finished")
        if self.remaining_seconds() <= 0:
            raise ValueError("Session time budget exhausted")

    def remaining_seconds(self):
        return max(0, round(self.config["deadline_unix"] - time.time() if "deadline_unix" in self.config
                            else self.config.get("timeout_seconds", 600) - (time.monotonic() - self.started)))

    def response_ok(self, response):
        if response.status_code in (401, 403, 410, 503) or (
            response.status_code == 409 and any(state in response.text for state in
                ("environment_error", "interrupted", "destroyed", "completed"))
        ):
            self.closed = True
            (self.output / "environment-error.json").write_text(json.dumps({
                "http_status": response.status_code,
                "message": "Environment unavailable; stop this inference, do not retry tools."}))
        response.raise_for_status()

    def observe(self):
        with self.lock:
            return self._observe()

    def _observe(self):
        self.check()
        started = time.monotonic()
        response = self.http.get(self.path + "/observation")
        self.response_ok(response)
        observation = response.json()
        self.frame, self.epoch = observation["frame"], observation["epoch"]
        encoded = observation["image"].split(",", 1)[1]
        filename = f"frame-{self.epoch}-{self.frame:05d}.png"
        (self.output / filename).write_bytes(base64.b64decode(encoded))
        self.log({"type": "observation", "frame_id": self.frame, "file": filename,
                  "duration_seconds": time.monotonic() - started})
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
            "frame_id": self.frame, "width": observation["width"], "height": observation["height"],
            "remaining_seconds": self.remaining_seconds(),
            "remaining_actions": self.config.get("max_actions", 100) - self.actions})),
            ImageContent(type="image", mimeType="image/png", data=encoded)])

    def act(self, frame_id: int, kind: str, **kwargs):
        with self.lock:
            return self._act(frame_id, kind, **kwargs)

    def _act(self, frame_id: int, kind: str, **kwargs):
        self.check()
        if self.frame is None or frame_id != self.frame:
            raise ValueError("Observe first; action must reference the most recent frame_id")
        if self.actions >= self.config.get("max_actions", 100):
            raise ValueError("Action budget exhausted")
        body = {"epoch": self.epoch, "frame": frame_id, "action_id": uuid.uuid4().hex,
                "kind": kind, **{k: v for k, v in kwargs.items() if v is not None}}
        # No blind retries: an ambiguous transport failure may have executed the input.
        self.frame = None
        started = time.monotonic()
        response = self.http.post(self.path + "/actions", json=body)
        self.response_ok(response)
        self.actions += 1
        self.log({"type": "action", **body, "duration_seconds": time.monotonic() - started})
        return self.observe()

    def demo_info(self):
        demo = self.config.get("demo_video")
        if not demo:
            return {"available": False, "message": "No demonstration video assigned to this run."}
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(demo)
        try:
            meta = next(reader)
        finally:
            reader.close()
        return {"available": True, "format": "timestamped video frames", "audio": "not supplied",
                "duration_seconds": meta.get("duration"), "fps": meta.get("fps"),
                "instructions": "Use demo_frame(seconds) to inspect the assigned video; no event logs or rules are provided."}

    def demo_frame(self, seconds: float):
        started = time.monotonic()
        if not self.config.get("demo_video"):
            raise ValueError("No demonstration video assigned")
        if not 0 <= seconds <= 3600:
            raise ValueError("Timestamp must be between 0 and 3600 seconds")
        import imageio_ffmpeg
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-ss", str(seconds),
            "-i", self.config["demo_video"], "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True, timeout=20, check=True)
        if not result.stdout:
            raise ValueError("No frame at that timestamp; it may be past the end of the video")
        self.log({"type": "demo_frame", "seconds": seconds, "duration_seconds": time.monotonic() - started})
        return CallToolResult(content=[TextContent(type="text", text=f"Assigned demo, timestamp {seconds}s"),
            ImageContent(type="image", mimeType="image/png", data=base64.b64encode(result.stdout).decode())])


def make_server(computer: Computer, smoke_payload: bool = False):
    mcp = FastMCP("vic-computer")

    @mcp.tool()
    def computer_observe(purpose: str = "Inspect the current screen") -> CallToolResult:
        """See the current live application screenshot and frame_id. No DOM or business state.
        Include a short purpose for the observation, e.g. inspect the current screen.
        """
        return computer.observe()

    @mcp.tool()
    def computer_act(frame_id: int, kind: str, x: PixelCoordinate = None, y: PixelCoordinate = None,
                     text: str | None = None, key: str | None = None, delta_y: int | None = None,
                     to_x: PixelCoordinate = None, to_y: PixelCoordinate = None,
                     wait_ms: int | None = None) -> CallToolResult:
        """Perform one input and return the new screenshot. kind: click, double_click, right_click,
        drag, scroll, text, key, wait. Coordinates are screenshot pixels. Click a field before typing.
        Use key=ControlOrMeta+A to select text. Do not repeat a timed-out click blindly; observe first.
        scroll uses delta_y in PIXELS (e.g. 500), with x/y locating the scrollable panel.
        """
        x, y = normalize_point(x, y)
        to_x, to_y = normalize_point(to_x, to_y)
        return computer.act(frame_id, kind, x=x, y=y, text=text, key=key, delta_y=delta_y,
                            to_x=to_x, to_y=to_y, wait_ms=wait_ms)

    @mcp.tool()
    def demo_info(purpose: str = "Inspect the assigned demonstration") -> dict:
        """Check whether a demonstration video has been assigned. Include a short purpose."""
        return computer.demo_info()

    @mcp.tool()
    def demo_frame(seconds: float) -> CallToolResult:
        """Read a frame of the assigned demonstration video at the given timestamp."""
        return computer.demo_frame(seconds)

    @mcp.tool()
    def finish(summary: str) -> dict:
        """Declare that you have stopped operating. This does not indicate evaluation success."""
        with computer.lock:
            computer.closed = True
            computer.log({"type": "finish", "summary": summary})
        return {"finished": True, "message": "The controller, not the agent, will evaluate the result."}

    if smoke_payload:
        @mcp.tool()
        def diagnostic_payload() -> str:
            """TEST ONLY: return inert synthetic text to exercise native automatic context compaction.
            Call at most once, then continue the original smoke-test task. Not benchmark evidence."""
            if getattr(computer, "payload_sent", False):
                return "Diagnostic payload already supplied. Continue the smoke test."
            computer.payload_sent = True
            computer.log({"type": "diagnostic_payload"})
            return "Synthetic compaction fixture; no task information.\n" + "\n".join(
                f"Entry {i:04d}: sample measurement {i*17%997}, batch {i%23}; inert diagnostic data."
                for i in range(900))
    return mcp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    computer = Computer(config)
    try:
        make_server(computer, config.get("smoke_payload", False)).run(transport="stdio")
    finally:
        computer.http.close()


if __name__ == "__main__":
    main()
