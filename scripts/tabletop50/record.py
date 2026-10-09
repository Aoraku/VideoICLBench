#!/usr/bin/env python3
"""Isolated physical author acceptance, with resumable per-condition evidence."""
import argparse
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from simulator.tabletop50.catalog import IMPLEMENTED, task_spec, world_sha256


def source_hash():
    digest = hashlib.sha256()
    files = sorted([*ROOT.glob("simulator/tabletop50/*.py"),
                    *ROOT.glob("scripts/tabletop50/*.py"),
                    ROOT/"simulator/benchmark/environment.py", ROOT/"simulator/benchmark/pilot.py",
                    ROOT/"simulator/benchmark/protocol.py"])
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode()+b"\0"+path.read_bytes()+b"\0")
    return digest.hexdigest()


def record(task, variant, seed, output, render):
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image
    from simulator.tabletop50.environment import TabletopDual
    from simulator.tabletop50.author import TabletopAuthor

    spec = task_spec(task, variant, seed)
    digest = source_hash()
    folder = output/f"{task}-{variant}-{seed}"
    env = TabletopDual(spec, seed=seed, render=render)
    fixture_groups = [int(env.sim.model.geom_group[env.sim.model.geom_name2id(f"fixture{i}")])
                      for i in range(len(spec.get("fixtures", [])))]
    visual_environment = dict(fixture_count=len(fixture_groups), fixtures_visible=all(g == 1 for g in fixture_groups))
    author = TabletopAuthor(env, folder, seed)
    writer = None
    frame_count = 0
    steps = 0
    initial = env.snapshot()
    error = None
    try:
        if render:
            writer = imageio_ffmpeg.write_frames(str(folder/"video.mp4"), (512, 384), fps=10,
                codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
                output_params=["-crf", "25", "-preset", "fast"])
            writer.send(None)
            def capture():
                nonlocal frame_count
                pixels = np.ascontiguousarray(env.sim.render(width=512, height=384, camera_name="fpv")[::-1])
                writer.send(pixels); frame_count += 1
                return pixels
            Image.fromarray(capture()).save(folder/"initial.jpg")
            step = env.step
            def recorded_step(action):
                nonlocal steps
                result = step(action); steps += 1
                if steps % 2 == 0: capture()
                return result
            env.step = recorded_step
        author.solve()
        # Keep the complete ending; do not stop on transient mid-episode success.
        author.wait(5)
    except Exception:
        error = traceback.format_exc()
    finally:
        score = env.score()
        final = env.snapshot()
        cross = {}
        for rule in "ABC":
            target = task_spec(task, rule, seed)
            cross[rule] = bool(all(env.predicate(g, final) for g in target["goals"]))
        if render and writer:
            Image.fromarray(capture()).save(folder/"final.jpg")
            writer.close()
        actions = folder/"actions.json"
        actions.write_text(json.dumps(author.actions, separators=(",", ":")))
        result = dict(task=task, variant=variant, seed=seed,
            kind="privileged-author-physical-acceptance", independent_agent=False,
            human_recorded=False, source_sha256=digest, source_unchanged=source_hash() == digest,
            world_sha256=world_sha256(spec), initial_positions={k:v["pos"].tolist() for k,v in initial.items()},
            initial_joint_angles={k:v["hinge_angle"] for k,v in initial.items() if "hinge_angle" in v},
            visual_environment=visual_environment,
            score=score, cross_rule_predicates=cross, actions=len(author.actions),
            actions_sha256=hashlib.sha256(actions.read_bytes()).hexdigest(), error=error,
            video=dict(recorded=render, camera="fpv", fps=10, frames=frame_count,
                       duration_seconds=frame_count/10, full_episode=True, final_success=bool(score["success"])))
        if render:
            result["video"]["sha256"] = hashlib.sha256((folder/"video.mp4").read_bytes()).hexdigest()
        (folder/"result.private.json").write_text(json.dumps(result, indent=2)+"\n")
        env.close()
    print(json.dumps(result), flush=True)
    return not error and score["success"] and result["source_unchanged"] and sum(cross.values()) == 1 and cross[variant]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", choices=IMPLEMENTED, required=True)
    p.add_argument("--variant", choices=list("ABC"), default="A")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--record", action="store_true")
    a = p.parse_args()
    if not record(a.task, a.variant, a.seed, a.output, a.record): raise SystemExit(1)


if __name__ == "__main__": main()
