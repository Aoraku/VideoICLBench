"""MCP transport for native agents. No model calls or conversation management."""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import threading
import uuid
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent


class Computer:
    def __init__(self, config: dict):
        self.config = config
        self.http = httpx.Client(base_url=config["control_url"], timeout=90,
            headers={"Authorization": "Bearer " + config["actor_token"]})
        self.path = "/v1/runs/" + config["run_id"]
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
        if time.monotonic() - self.started > self.config.get("timeout_seconds", 600):
            raise ValueError("Session time budget exhausted")

    def observe(self):
        with self.lock:
            return self._observe()

    def _observe(self):
        self.check()
        response = self.http.get(self.path + "/observation")
        response.raise_for_status()
        observation = response.json()
        self.frame, self.epoch = observation["frame"], observation["epoch"]
        encoded = observation["image"].split(",", 1)[1]
        filename = f"frame-{self.epoch}-{self.frame:05d}.png"
        (self.output / filename).write_bytes(base64.b64decode(encoded))
        self.log({"type": "observation", "frame_id": self.frame, "file": filename})
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
            "frame_id": self.frame, "width": observation["width"], "height": observation["height"],
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
        response = self.http.post(self.path + "/actions", json=body)
        response.raise_for_status()
        self.actions += 1
        self.log({"type": "action", **body})
        return self.observe()

    def demo_info(self):
        demo = self.config.get("demo_video")
        if not demo:
            return {"available": False, "message": "No demonstration video assigned to this run."}
        return {"available": True, "format": "timestamped video frames", "audio": "not supplied",
                "instructions": "Use demo_frame(seconds) to inspect the assigned video; no event logs or rules are provided."}

    def demo_frame(self, seconds: float):
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
        self.log({"type": "demo_frame", "seconds": seconds})
        return CallToolResult(content=[TextContent(type="text", text=f"Assigned demo, timestamp {seconds}s"),
            ImageContent(type="image", mimeType="image/png", data=base64.b64encode(result.stdout).decode())])


def make_server(computer: Computer, smoke_payload: bool = False):
    mcp = FastMCP("vic-computer")

    @mcp.tool()
    def computer_observe() -> CallToolResult:
        """See the current live application screenshot and frame_id. No DOM or business state."""
        return computer.observe()

    @mcp.tool()
    def computer_act(frame_id: int, kind: str, x: int | None = None, y: int | None = None,
                     text: str | None = None, key: str | None = None, delta_y: int | None = None,
                     to_x: int | None = None, to_y: int | None = None,
                     wait_ms: int | None = None) -> CallToolResult:
        """Perform one input and return the new screenshot. kind: click, double_click, right_click,
        drag, scroll, text, key, wait. Coordinates are screenshot pixels. Click a field before typing.
        Use key=ControlOrMeta+A to select text. Do not repeat a timed-out click blindly; observe first.
        """
        return computer.act(frame_id, kind, x=x, y=y, text=text, key=key, delta_y=delta_y,
                            to_x=to_x, to_y=to_y, wait_ms=wait_ms)

    @mcp.tool()
    def demo_info() -> dict:
        """Check whether a demonstration video has been assigned."""
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
