"""Sample the remote workspace itself and encode a portable MP4 artifact."""

import asyncio
import json
import subprocess
import time
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from .config import ROOT


class Recorder:
    def __init__(self, directory, runtime):
        self.directory = Path(directory)
        self.runtime = runtime
        self.active = {}

    async def start(self, run_id, url, rule, epoch=0):
        if run_id in self.active:
            raise ValueError("Recording already active")
        dest = self.directory / run_id
        if (dest / "tutorial.mp4").exists():
            raise ValueError("A recording already exists; create a new demo run")
        dest.mkdir(parents=True, exist_ok=True)
        record = dict(
            stop=False,
            error=None,
            started=time.monotonic(),
            frames=0,
            directory=dest,
            epoch=epoch,
            url=url,
        )
        self.active[run_id] = record

        async def sample():
            try:
                while not record["stop"] and record["frames"] < 180:
                    tick = time.monotonic()
                    raw = await self.runtime.capture(run_id, url)
                    img = Image.open(BytesIO(raw)).convert("RGB")
                    # Recording-only overlay. The application receives no rule.
                    if time.monotonic() - record["started"] < 4:
                        draw = ImageDraw.Draw(img)
                        draw.rectangle((0, 0, 1280, 112), fill="#102338")
                        candidates = [
                            str(ROOT / "apps/gomoku/simhei.ttf"),
                            "/System/Library/Fonts/PingFang.ttc",
                            "/System/Library/Fonts/STHeiti Medium.ttc",
                            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                        ]
                        path = next((p for p in candidates if Path(p).exists()), None)
                        if not path:
                            raise RuntimeError(
                                "CJK font required for recording rule subtitles"
                            )
                        font = ImageFont.truetype(path, 26)
                        for i, line in enumerate(
                            [rule[j : j + 40] for j in range(0, len(rule), 40)][:3]
                        ):
                            draw.text((28, 12 + i * 32), line, font=font, fill="white")
                    img.save(dest / f"{record['frames']:05d}.png")
                    record["frames"] += 1
                    await asyncio.sleep(max(0, 0.2 - (time.monotonic() - tick)))
                if not record["stop"]:
                    record["error"] = (
                        "Recording frame budget exceeded; create a shorter demonstration"
                    )
            except Exception as exc:
                record["error"] = str(exc)

        record["task"] = asyncio.create_task(sample())

    async def stop(self, run_id):
        record = self.active.get(run_id)
        if not record:
            raise ValueError("Recording is not active")
        record["stop"] = True
        await record["task"]
        self.active.pop(run_id, None)
        if record["error"]:
            raise RuntimeError(record["error"])
        if record["frames"] < 2:
            raise ValueError("Recording too short")
        dest = record["directory"]
        raw = await self.runtime.capture(run_id, record["url"])
        Image.open(BytesIO(raw)).convert("RGB").save(
            dest / f"{record['frames']:05d}.png"
        )
        record["frames"] += 1
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            "5",
            "-i",
            str(dest / "%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest / "tutorial.mp4"),
        ]
        result = await asyncio.to_thread(
            subprocess.run, command, capture_output=True, timeout=120
        )
        if result.returncode:
            raise RuntimeError("Video encoding failed")
        meta = dict(
            frames=record["frames"],
            fps=5,
            duration=record["frames"] / 5,
            epoch=record["epoch"],
            status="pending_review",
            official=False,
        )
        (dest / "recording.json").write_text(json.dumps(meta, indent=2))
        return meta

    async def close(self):
        for record in self.active.values():
            record["stop"] = True
        await asyncio.gather(
            *(record["task"] for record in self.active.values()), return_exceptions=True
        )
        self.active.clear()
