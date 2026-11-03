#!/usr/bin/env python3
"""Export RealWorld50 as 150 native-consumer Harbor task directories.

Three input conditions produce a 450-episode plan, not 450 task directories.
Media verification here proves file identity only. Every exported environment
remains unavailable until native interaction and independent grading acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
TASKS = tuple(f"E{i:02d}" for i in range(1, 51))
VARIANTS = ("A", "B", "C")
CONDITIONS = ("real", "sim", "text_rule")
READINESS = "requires_native_interaction_validation"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("A complete lowercase SHA256 is required")
    return value


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or str(path) == "." or "\\" in value or path.is_absolute() or ".." in path.parts:
        raise ValueError("Media path must be a nonempty relative path inside its explicit root")
    return str(path)


def read_catalog(path: Path) -> dict:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    data["_catalog_sha256"] = hashlib.sha256(raw).hexdigest()
    rows = data.get("tasks", [])
    if tuple(row.get("id") for row in rows) != TASKS:
        raise ValueError("Canonical catalog must contain E01-E50 exactly once in order")
    for row in rows:
        if not isinstance(row.get("inference_prompt"), str) or not row["inference_prompt"].strip():
            raise ValueError("Missing public inference prompt")
        variants = row.get("variants", [])
        if tuple(v.get("variant") for v in variants) != VARIANTS:
            raise ValueError("Each canonical task requires exactly A/B/C in order")
        for variant in variants:
            if variant.get("task_id") != row["id"]:
                raise ValueError("Catalog video task identity mismatch")
            _relative(variant["relative_path"])
            _hash(variant["sha256"])
            if not isinstance(variant.get("observed_demo"), str) or not variant["observed_demo"].strip():
                raise ValueError("Missing private variant method")
    return data


def read_media_maps(maps: list[tuple[Path, Path]], catalog: dict, verify_local: bool) -> dict:
    """Consume explicit workbench task/variant mappings; never guess by name."""
    expected = {(task["id"], v["variant"]): v for task in catalog["tasks"] for v in task["variants"]}
    result = {}
    for manifest_path, media_root in maps:
        manifest_raw = Path(manifest_path).read_bytes()
        manifest = json.loads(manifest_raw)
        if manifest.get("dataset_revision") != catalog.get("dataset_revision"):
            raise ValueError("Media map dataset revision differs from canonical catalog")
        root = Path(media_root).resolve()
        for task in manifest.get("tasks", []):
            for variant, row in task.get("variants", {}).items():
                key = (task["id"], variant)
                if key not in expected or row.get("task", task["id"]) != key[0] or row.get("variant", variant) != key[1]:
                    raise ValueError("Media map task/variant outside canonical panel")
                if key in result:
                    raise ValueError("Duplicate media mapping: " + "-".join(key))
                if row.get("source_video_sha256") != expected[key]["sha256"]:
                    raise ValueError("Media mapping source video SHA differs from canonical variant")
                mapped = {"source_video_sha256": row["source_video_sha256"],
                          "manifest_path": str(Path(manifest_path).resolve()),
                          "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest()}
                streams = {"real": row.get("human"), "sim": row.get("simulation", {}).get("head")}
                for kind, record in streams.items():
                    if not record:
                        continue
                    file = (root / _relative(record["file"])).resolve()
                    if not file.is_relative_to(root):
                        raise ValueError("Media symlink escapes explicit media root")
                    digest = _hash(record["sha256"])
                    if verify_local:
                        if not file.is_file() or sha256(file) != digest:
                            raise ValueError("Mapped media file missing or SHA256 mismatch: " + str(file))
                        if "bytes" in record and file.stat().st_size != record["bytes"]:
                            raise ValueError("Mapped media byte count mismatch")
                    mapped[kind] = {"path": str(file), "sha256": digest,
                                    "verification": "file_sha256_verified" if verify_local else "metadata_only"}
                # Recording verification is descriptive provenance, never runtime readiness.
                mapped["recording_acceptance"] = {name: row.get(name) is True for name in
                    ("native_verified", "camera_clock_verified", "source_visual_reviewed")}
                result[key] = mapped
    return result


def validate_budget(budget: dict) -> dict:
    required = {"timeout_sec", "max_actions", "action_interface", "status"}
    if not isinstance(budget, dict) or not required <= budget.keys():
        raise ValueError("Explicit budget requires timeout_sec, max_actions, action_interface, status")
    if type(budget["timeout_sec"]) not in (int, float) or not math.isfinite(budget["timeout_sec"]) or budget["timeout_sec"] <= 0:
        raise ValueError("timeout_sec must be finite and positive")
    if type(budget["max_actions"]) is not int or budget["max_actions"] < 1:
        raise ValueError("max_actions must be a positive integer")
    if not all(isinstance(budget[key], str) and budget[key].strip() for key in ("action_interface", "status")):
        raise ValueError("Explicit action_interface and budget status required")
    return dict(budget)


def export(catalog_path: Path, output: Path, *, budget: dict, seed: int,
           human_root: str, source_root: str, media_maps=None, verify_local_media=False) -> dict:
    catalog_path, output = Path(catalog_path), Path(output)
    catalog = read_catalog(catalog_path)
    budget = validate_budget(budget)
    if type(seed) is not int or seed < 0:
        raise ValueError("Explicit seed must be a nonnegative integer")
    if not human_root or not source_root:
        raise ValueError("Explicit human data root and native source root required")
    mappings = read_media_maps(media_maps or [], catalog, verify_local_media)
    if output.exists():
        raise FileExistsError("Export output must be new; frozen task packages are never overwritten")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".embodied-harbor-", dir=output.parent))
    index, episodes = [], []
    counts = Counter()
    try:
        for task in catalog["tasks"]:
            for variant in task["variants"]:
                tid, var = task["id"], variant["variant"]
                name = f"embodied-{tid.lower()}-{var.lower()}"
                directory = staging / name
                (directory / "environment").mkdir(parents=True)
                (directory / "tests").mkdir()
                instruction = task["inference_prompt"].rstrip("\n") + "\n"
                instruction_bytes = instruction.encode("utf-8")
                (directory / "instruction.md").write_bytes(instruction_bytes)
                controls = (HERE / "gui-controls.md").read_bytes()
                (directory / "environment/gui-controls.md").write_bytes(controls)
                mapped = mappings.get((tid, var), {})
                original = {"path": human_root.rstrip("/") + "/" + _relative(variant["relative_path"]),
                            "sha256": variant["sha256"], "verification": "metadata_only"}
                demo = mapped.get("real", original)
                spec = {"schema_version": 1, "backend": "videoicl-native-slurm", "kind": "embodied",
                    "task_id": tid, "variant": var, "seed": seed, "demo": demo,
                    "readiness": READINESS, "source_root": source_root,
                    "instruction_sha256": hashlib.sha256(instruction_bytes).hexdigest(),
                    "instruction_hash_scheme": "sha256_utf8_exact_file_bytes",
                    "dataset_revision": catalog["dataset_revision"], "catalog_sha256": catalog["_catalog_sha256"],
                    "source_video": original, "action_interface": budget["action_interface"],
                    "agent_interaction": "gui_only", "agent_protocol": "roboprobe_gui_v1",
                    "gui_controls": {"path": "gui-controls.md", "sha256": hashlib.sha256(controls).hexdigest()},
                    "budget": budget, "input_conditions": list(CONDITIONS),
                    "native_interaction_validated": False,
                    "media_acceptance_scope": "demonstration_files_only_not_native_evaluation"}
                if "sim" in mapped:
                    spec["demo_sim"] = dict(mapped["sim"], kind="engineering_simulated_demonstration")
                if mapped:
                    spec["media_provenance"] = {k: v for k, v in mapped.items() if k not in {"real", "sim"}}
                (directory / "environment/native.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
                difficulty = task.get("difficulty", "unassigned")
                difficulty = {"low": "easy", "normal": "medium", "high": "hard"}.get(difficulty, difficulty)
                if difficulty not in {"easy", "medium", "hard", "unassigned"}:
                    raise ValueError("Unknown execution difficulty: " + str(difficulty))
                (directory / "task.toml").write_text(f'''schema_version = "1.3"
[task]
name = "videoicl/{name}"
authors = [{{ name = "VideoICLBench team" }}]
[metadata]
category = "embodied"
difficulty = "{difficulty}"
variant = "{var}"
readiness = "{READINESS}"
[agent]
timeout_sec = {float(budget['timeout_sec'])}
[verifier]
timeout_sec = 120.0
[environment]
cpus = 8
memory_mb = 32768
storage_mb = 20480
''')
                rule = {"rule": variant["observed_demo"], "evaluation_scope": task.get("evaluation_scope"),
                        "scope_note": task.get("scope_note"), "source_video_sha256": variant["sha256"]}
                (directory / "tests/rule.json").write_text(json.dumps(rule, ensure_ascii=False, indent=2) + "\n")
                shutil.copyfile(HERE / "verify_embodied.py", directory / "tests/verify.py")
                test = directory / "tests/test.sh"
                test.write_text('#!/bin/sh\nset -eu\nexec "${VIDEOICL_PYTHON:-python3}" "$(dirname "$0")/verify.py"\n')
                test.chmod(0o755)
                real_verified = demo["verification"] == "file_sha256_verified"
                sim_referenced = "demo_sim" in spec
                sim_verified = sim_referenced and spec["demo_sim"]["verification"] == "file_sha256_verified"
                counts["real_demo_file_verified_cases"] += real_verified
                counts["sim_demo_file_verified_cases"] += sim_verified
                counts["sim_demo_referenced_cases"] += sim_referenced
                index.append({"name": name, "kind": "embodied", "task_id": tid, "variant": var,
                              "readiness": READINESS, "demo_file_verified": real_verified,
                              "demo_sim_file_verified": bool(sim_verified)})
                for condition in CONDITIONS:
                    episodes.append({"episode_key": f"{name}--{condition}--seed{seed}", "task_directory": name,
                        "task_id": tid, "variant": var, "seed": seed, "input_condition": condition,
                        "readiness": READINESS, "video_enabled": condition != "text_rule",
                        "demo_field": "demo" if condition == "real" else "demo_sim" if condition == "sim" else None,
                        "media_mapping_present": condition != "sim" or sim_referenced,
                        "fresh_environment_required": True, "fresh_agent_session_required": True})
        summary = {"schema": "videoicl-realworld50-harbor-export-v1", "task_families": 50,
            "task_directories": len(index), "planned_episodes": len(episodes),
            "input_conditions": list(CONDITIONS), "seed": seed, "budget": budget,
            "native_evaluation_ready_cases": 0, "catalog_sha256": catalog["_catalog_sha256"], **dict(counts),
            "real_demo_metadata_only_cases": 150 - counts["real_demo_file_verified_cases"],
            "sim_demo_missing_cases": 150 - counts["sim_demo_referenced_cases"]}
        (staging / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        (staging / "episode-plan.json").write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + "\n")
        (staging / "export-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        staging.rename(output)
        return summary
    except BaseException:
        shutil.rmtree(staging)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True, help="Explicit JSON with timeout_sec, max_actions, action_interface, status")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--human-root", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--media-map", nargs=2, action="append", default=[], metavar=("MANIFEST", "MEDIA_ROOT"))
    parser.add_argument("--verify-local-media", action="store_true")
    args = parser.parse_args()
    summary = export(args.catalog, args.output, budget=json.loads(args.budget.read_text()), seed=args.seed,
        human_root=args.human_root, source_root=args.source_root,
        media_maps=[(Path(a), Path(b)) for a, b in args.media_map], verify_local_media=args.verify_local_media)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
