"""Verify 24 demos, prepare seven frozen runtimes and chronological model inputs."""
import argparse
import json
from pathlib import Path

from .release import TASKS, prepare, verify_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.data/"runtimes")
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image
    for task in TASKS:
        for variant in "ABC":
            demo = verify_demo(task, variant)
            folder = args.data/"demo-frames"/demo.name
            folder.mkdir(parents=True, exist_ok=True)
            count = TASKS[task]["demos"][variant]["frames"]
            indices = set(np.linspace(0, count-1, 12, dtype=int).tolist())
            reader = imageio_ffmpeg.read_frames(str(demo/"video.mp4"), pix_fmt="rgb24")
            meta = next(reader)
            w, h = meta["size"]
            n = selected = 0
            try:
                for n, frame in enumerate(reader, 1):
                    if n-1 in indices:
                        pixels = np.frombuffer(frame, dtype=np.uint8).reshape(h, w, 3)
                        Image.fromarray(pixels).save(folder/f"{selected:02}.jpg", quality=85)
                        selected += 1
            finally: reader.close()
            if n != count or selected != 12: raise ValueError("Unexpected decoded frame count")
            print(json.dumps(dict(demo=demo.name, decoded=n, sampled=selected)), flush=True)


if __name__ == "__main__": main()
