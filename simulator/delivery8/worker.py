"""JSON-lines worker. Imports only the selected frozen scene plus motion adapter."""
import contextlib
import json
from pathlib import Path
import sys
import traceback

# Invoked as an absolute script with cwd set to a verified historical runtime.
# Do not import current simulator.tabletop50 into this process.
sys.path.insert(0, str(Path.cwd()))
from motion import move


def main():
    env = writer = None
    frames = steps = 0
    try:
        for line in sys.stdin:
            try:
                req = json.loads(line)
                with contextlib.redirect_stdout(sys.stderr):
                    if req["op"] == "init":
                        import imageio_ffmpeg
                        import numpy as np
                        from PIL import Image
                        from simulator.tabletop50.catalog import task_spec, world_sha256
                        from simulator.tabletop50.environment import TabletopDual
                        spec = task_spec(req["task"], req["variant"], req["seed"])
                        env = TabletopDual(spec, seed=req["seed"])
                        folder = Path(req["folder"])
                        writer = imageio_ffmpeg.write_frames(str(folder/"execution.mp4"), (512, 384),
                            fps=10, codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
                            output_params=["-crf", "25", "-preset", "fast"])
                        writer.send(None)
                        def capture():
                            nonlocal frames
                            pixels = np.ascontiguousarray(env.sim.render(width=512, height=384, camera_name="fpv")[::-1])
                            writer.send(pixels); frames += 1
                            return pixels
                        Image.fromarray(capture()).save(folder/"initial.jpg")
                        original_step = env.step
                        def recorded_step(command):
                            nonlocal steps
                            result = original_step(command); steps += 1
                            if steps % 2 == 0: capture()
                            return result
                        env.step = recorded_step
                        result = dict(ready=True, world_sha256=world_sha256(spec))
                    elif req["op"] == "observe": result = dict(images=env.images())
                    elif req["op"] == "action":
                        move(env, req["left"], req["right"], req.get("step_mm"), req.get("rotation_deg"))
                        result = dict(accepted=True)
                    elif req["op"] == "score":
                        # Settle for 0.8s, without moving either gripper.
                        for _ in range(2): move(env)
                        result = env.score()
                        Image.fromarray(capture()).save(folder/"final.jpg")
                    elif req["op"] == "close":
                        if writer: writer.close(); writer = None
                        result = dict(closed=True, video_frames=frames)
                    else: raise ValueError("Unknown operation")
                print(json.dumps(dict(result=result)), flush=True)
                if req["op"] == "close": break
            except Exception:
                traceback.print_exc(file=sys.stderr)
                print(json.dumps(dict(error="Simulation operation failed")), flush=True)
    finally:
        with contextlib.redirect_stdout(sys.stderr):
            if writer: writer.close()
            if env: env.close()


if __name__ == "__main__": main()
