"""Framed RGB/robot MCP for native CLIs; no scoring or private-state tools."""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
from pathlib import Path
import threading
import time
import uuid

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image

from .computer_mcp import Computer

CAMERAS = ("head", "left_wrist", "right_wrist")
PUBLIC_STATE = ("title", "instruction", "condition", "action_schema", "steps", "max_actions", "rule_reported")


class Robot(Computer):
    def __init__(self, config: dict, *, http=None):
        super().__init__(config)
        self.http.close()
        self.http = http or httpx.Client(base_url=config["control_url"], timeout=120, trust_env=False,
            headers={"Authorization": "Bearer " + config["actor_token"]})
        self.frame = None
        self.diagnosed = not config.get("rule_diagnostic", True)
        self.state = {}
        self.condition = config["condition"]
        if self.condition not in {"real", "sim", "text_rule"}:
            raise ValueError("Unknown input condition")
        if self.condition == "text_rule" and config.get("demo_video"):
            raise ValueError("Text condition must not receive a video")

    def _unavailable(self, reason, **details):
        self.closed = True
        self.frame = None
        (self.output / "environment-error.json").write_text(json.dumps({
            "type": reason, "message": "Environment unavailable; stop, do not retry actions.", **details}))

    def request(self, method, path, body=None):
        try:
            response = self.http.request(method, path, json=body)
        except httpx.RequestError as exc:
            self._unavailable("transport_error", error_class=type(exc).__name__)
            raise RuntimeError("Environment transport failed; action execution may be uncertain") from None
        if response.status_code in {401, 403, 404, 410, 429} or response.status_code >= 500:
            self._unavailable("http_error", http_status=response.status_code)
            raise RuntimeError("Environment unavailable; stop this trial")
        if not response.is_success:
            # A rejected/stale frame has not executed another physical action.
            raise ValueError("Controller rejected input (HTTP " + str(response.status_code) + "); observe again")
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except ValueError:
            self._unavailable("invalid_response")
            raise RuntimeError("Invalid controller response") from None

    def picture(self, packet):
        try:
            frame = packet["frame_id"]
            if not isinstance(frame, str) or not frame or len(frame) > 256:
                raise ValueError("Invalid frame identity")
            images = packet["images"]
            if set(images) != set(CAMERAS):
                raise ValueError("Missing RGB camera")
            raw_state = packet["state"]
            if not isinstance(raw_state, dict):
                raise ValueError("Invalid public state")
            state = {k: raw_state[k] for k in PUBLIC_STATE if k in raw_state}
            if self.condition == "text_rule" and "text_rule" in raw_state:
                state["text_rule"] = raw_state["text_rule"]
            decoded = []
            for camera in CAMERAS:
                encoded = images[camera]
                if not isinstance(encoded, str) or len(encoded) > 24_000_000:
                    raise ValueError("Invalid image size")
                encoded = encoded.split(",", 1)[1] if encoded.startswith("data:image/") else encoded
                data = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(data)) as im:
                    im.verify()
                with Image.open(io.BytesIO(data)) as im:
                    size, mime = list(im.size), Image.MIME[im.format]
                if mime not in {"image/jpeg", "image/png"}:
                    raise ValueError("Unsupported image format")
                decoded.append((camera, encoded, data, size, mime))
        except (KeyError, TypeError, ValueError, OSError):
            self._unavailable("invalid_rgb_observation")
            raise RuntimeError("Invalid RGB observation; stop this trial") from None
        self.frame, self.state = frame, state
        if state.get("rule_reported") is True:
            self.diagnosed = True
        metadata = {"frame_id": frame, "state": state,
                    "remaining_seconds": self.remaining_seconds(),
                    "remaining_actions": max(0, self.config["max_actions"] - self.actions),
                    "cameras": {n: {"width": size[0], "height": size[1]} for n, _, _, size, _ in decoded}}
        content = [TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False))]
        files = {}
        for camera, encoded, data, _, mime in decoded:
            name = "frame-" + uuid.uuid4().hex + "-" + camera + (".png" if mime == "image/png" else ".jpg")
            (self.output / name).write_bytes(data)
            files[camera] = name
            content.extend([TextContent(type="text", text="Live camera: " + camera),
                            ImageContent(type="image", mimeType=mime, data=encoded)])
        self.log({"type": "observation", "frame_id": frame, "files": files})
        return CallToolResult(content=content)

    def observe(self):
        with self.lock:
            self.check()
            return self.picture(self.request("GET", "/api/observe"))

    def act(self, frame_id: str, left: str = "STILL", right: str = "STILL",
            step_mm: float = 20., rotation_deg: float = 10.):
        with self.lock:
            self.check()
            if not isinstance(frame_id, str) or frame_id != self.frame:
                raise ValueError("Observe first; action must reference the latest frame_id")
            if self.actions >= self.config["max_actions"]:
                raise ValueError("Action budget exhausted")
            if not self.diagnosed:
                raise ValueError("Report the inferred relation before the first robot action")
            if not all(type(x) in (float, int) and math.isfinite(x) for x in (step_mm, rotation_deg)):
                raise ValueError("Action units must be finite numbers")
            if not all(isinstance(x, str) for x in (left, right)):
                raise ValueError("Each hand requires one action token")
            body = dict(frame_id=frame_id, left=left, right=right, step_mm=step_mm, rotation_deg=rotation_deg)
            self.frame = None  # Never replay an ambiguous physical request.
            started = time.monotonic()
            reply = self.request("POST", "/api/action", body)
            self.actions += 1
            self.log({"type": "action", **body, "duration_seconds": time.monotonic() - started})
            return self.picture(reply)

    def sequence(self, frame_id: str, actions: list[dict]):
        if not 1 <= len(actions) <= 6:
            raise ValueError("One to six robot actions required")
        allowed = {"left", "right", "step_mm", "rotation_deg"}
        if any(not isinstance(a, dict) or set(a) - allowed for a in actions):
            raise ValueError("Invalid robot action fields")
        with self.lock:
            result = None
            for action in actions:
                result = self.act(frame_id, **action)
                frame_id = self.frame
            return result

    def report_rule(self, relation: str, evidence_timestamps: list[float], uncertainty: str = ""):
        with self.lock:
            self.check()
            if self.actions:
                raise ValueError("Rule diagnosis must precede acting")
            if not isinstance(relation, str) or not relation.strip() or len(relation) > 16000:
                raise ValueError("Describe the inferred relation")
            if not 1 <= len(evidence_timestamps) <= 12 or any(
                    type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= 3600
                    for t in evidence_timestamps):
                raise ValueError("Supply one to twelve finite video timestamps")
            body = dict(relation=relation, evidence_timestamps=evidence_timestamps, uncertainty=uncertainty)
            self.request("POST", "/api/report-inferred-rule", {"rule": relation, "evidence_seconds": evidence_timestamps})
            self.diagnosed = True
            self.log({"type": "rule_diagnostic", **body})
            return {"recorded": True, "feedback": "No correctness feedback. Continue the task."}

    def finish(self, summary: str):
        with self.lock:
            if not isinstance(summary, str) or len(summary) > 16000:
                raise ValueError("Invalid finish summary")
            if not self.closed:
                self.request("POST", "/api/finish", {"summary": summary})
                self.log({"type": "finish", "summary": summary})
                self.closed = True
            return {"finished": True, "message": "The controller independently evaluates the sealed state."}


def make_server(robot: Robot):
    server = FastMCP("vic-robot")

    @server.tool()
    def robot_observe() -> CallToolResult:
        """Observe head and two wrist RGB views and an opaque frame_id. No hidden object state."""
        return robot.observe()

    @server.tool()
    def robot_act(frame_id: str, left: str = "STILL", right: str = "STILL",
                  step_mm: float = 20., rotation_deg: float = 10.) -> CallToolResult:
        """Execute one pair of native robot actions, using the latest frame_id.

        Choose hand tokens and parameter limits from the public action_schema.
        Translation is millimetres and rotation is degrees in the published task frame.
        Both hands execute together. This counts as one action and returns new RGB views.
        """
        return robot.act(frame_id, left, right, step_mm, rotation_deg)

    @server.tool()
    def robot_sequence(frame_id: str, actions: list[dict]) -> CallToolResult:
        """Execute one to six already planned robot_act inputs serially; stop on any error.

        Every pair counts toward the action budget. All intermediate RGB observations are logged.
        Avoid batching actions whose targets depend on an unknown later observation.
        """
        return robot.sequence(frame_id, actions)

    @server.tool()
    def finish(summary: str) -> dict:
        """Stop operating; this declares no success and returns no score."""
        return robot.finish(summary)

    if robot.condition != "text_rule":
        @server.tool()
        def demo_info() -> dict:
            """Inspect basic information for this trial's assigned video; no rule annotation or audio."""
            robot.check()
            return robot.demo_info()

        @server.tool()
        def demo_frame(seconds: float) -> CallToolResult:
            """Read one original-resolution frame of the assigned demo at the chosen timestamp."""
            robot.check()
            return robot.demo_frame(seconds)

        @server.tool()
        def demo_frames(seconds: list[float]) -> CallToolResult:
            """Read one to twelve chronological timestamped demo frames, without rule overlays."""
            robot.check()
            if not 1 <= len(seconds) <= 12:
                raise ValueError("Choose one to twelve timestamps")
            content = []
            for second in sorted(seconds):
                content.extend(robot.demo_frame(second).content)
            return CallToolResult(content=content)

        @server.tool()
        def report_inferred_rule(relation: str, evidence_timestamps: list[float], uncertainty: str = "") -> dict:
            """Before acting, record the inferred mapping/order/stop rule and video evidence; no correctness feedback."""
            return robot.report_rule(relation, evidence_timestamps, uncertainty)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    robot = Robot(json.loads(args.config.read_text()))
    try:
        make_server(robot).run(transport="stdio")
    finally:
        robot.http.close()


if __name__ == "__main__":
    main()
