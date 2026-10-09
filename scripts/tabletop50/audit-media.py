#!/usr/bin/env python3
"""Decode videos, verify endings and same-world rule groups before publication."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from simulator.tabletop50.catalog import task_spec, world_sha256


def audit(folder):
    proof = json.loads((folder/"result.private.json").read_text())
    visual = proof.get("visual_environment")
    if visual is None:
        spec = task_spec(proof["task"], proof["variant"], proof["seed"])
        assert world_sha256(spec) == proof["world_sha256"] and not spec["fixtures"], "Legacy fixture visibility is unverified"
        visual = dict(fixture_count=0, fixtures_visible=True, evidence="matching-world-without-fixtures")
    assert visual["fixtures_visible"], "Physical fixtures are invisible in the actor camera"
    cross = proof.get("cross_rule_predicates", {})
    assert proof["score"]["success"] and not proof["error"], "Failed author execution"
    assert proof["source_unchanged"], "Source changed during execution"
    assert proof["independent_agent"] is False and proof["human_recorded"] is False
    assert sum(cross.values()) == 1 and cross[proof["variant"]], "Ambiguous or wrong rule result"
    video = folder/"video.mp4"
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    assert digest == proof["video"]["sha256"], "Video checksum mismatch"
    decoder = imageio_ffmpeg.read_frames(str(video), pix_fmt="rgb24")
    meta = next(decoder)
    count = 0; last = None
    for frame in decoder:
        last = frame; count += 1
    assert count == proof["video"]["frames"], "Truncated video"
    assert abs(meta["fps"]-proof["video"]["fps"]) < .01
    assert proof["video"]["full_episode"] and proof["video"]["final_success"]
    width, height = meta["size"]
    pixels = np.frombuffer(last, np.uint8).reshape(height, width, 3)
    final = np.asarray(Image.open(folder/"final.jpg").convert("RGB"), dtype=np.float32)
    mae = float(np.abs(pixels.astype(np.float32)-final).mean())
    assert mae < 20, "Decoded video ending does not match saved terminal frame"
    return dict(task=proof["task"], variant=proof["variant"], seed=proof["seed"],
                source_sha256=proof["source_sha256"], world_sha256=proof["world_sha256"],
                video_sha256=digest, decoded_frames=count, fps=meta["fps"],
                duration_seconds=count/meta["fps"], ending_image_mae=mae,
                initial_positions=proof["initial_positions"], cross_rule_predicates=cross,
                initial_joint_angles=proof.get("initial_joint_angles", {}),
                visual_environment=visual,
                usable_for_agent_demo=True,
                independent_agent=False, human_recorded=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--recordings", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    rows, rejected = [], []
    for proof in sorted(a.recordings.glob("*/result.private.json")):
        try:
            row = audit(proof.parent)
        except (AssertionError, KeyError, OSError, ValueError, StopIteration) as error:
            rejected.append(dict(case=proof.parent.name, error=str(error))); continue
        target = a.output/proof.parent.name
        target.mkdir(exist_ok=True)
        for name in ("video.mp4", "initial.jpg", "final.jpg", "actions.json", "result.private.json"):
            shutil.copy2(proof.parent/name, target/name)
        row["folder"] = target.name; rows.append(row)
        (target/"media-audit.private.json").write_text(json.dumps(row, indent=2)+"\n")
    groups = {}
    for row in rows: groups.setdefault((row["task"], row["seed"], row["source_sha256"]), []).append(row)
    complete = []
    for (task, seed, source), group in groups.items():
        if {r["variant"] for r in group} != set("ABC"): continue
        assert len({r["world_sha256"] for r in group}) == 1, f"{task}: world depends on rule"
        initial = [r["initial_positions"] for r in group]
        assert initial[0] == initial[1] == initial[2], f"{task}: physical initial state differs"
        joints = [r["initial_joint_angles"] for r in group]
        assert joints[0] == joints[1] == joints[2], f"{task}: initial articulation differs"
        complete.append(dict(task=task, seed=seed, source_sha256=source))
    manifest = dict(status="engineering-author-demonstrations", expected_families=50,
                    expected_rule_conditions=150, verified_videos=len(rows),
                    complete_three_rule_families=len(complete), complete_groups=complete,
                    usable_videos=len(rows), usable_complete_three_rule_families=len(complete),
                    human_videos=0, independent_agent_trials=0, cases=rows, rejected=rejected)
    (a.output/"manifest.private.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    cards = ["<!doctype html><meta charset='utf-8'><title>Tabletop50 author previews</title>",
             "<style>body{font:16px system-ui;background:#f5f5f5;color:#222;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}article{background:white;padding:16px;border-radius:12px}video{width:100%}</style>",
             f"<h1>桌面第一人称仿真预览</h1><p>已解码验收 {len(rows)}/150 段；完整三规则任务 {len(complete)}/50。作者控制器示范，非真人录像、非独立 agent 成绩。</p><main>"]
    for row in rows:
        folder = row["folder"]
        cards.append(f"<article><h2>{folder}</h2><video controls preload='none' poster='{folder}/final.jpg' src='{folder}/video.mp4'></video><p>{row['duration_seconds']:.1f} 秒 · {row['fps']} fps</p></article>")
    cards.append("</main>")
    (a.output/"index.html").write_text("\n".join(cards))
    print(json.dumps({k:v for k,v in manifest.items() if k not in ("cases", "rejected", "complete_groups")}))


if __name__ == "__main__": main()
