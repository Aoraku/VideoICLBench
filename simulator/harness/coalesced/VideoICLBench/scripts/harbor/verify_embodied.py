#!/usr/bin/env python3
"""Private controller-side Harbor verifier for sealed embodied evaluations.

This file is copied into each task's tests directory. The agent never receives
the verifier configuration, expected run identity, or authoritative result file.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

IDENTITY = ("run_id", "task_id", "variant", "seed", "suite", "epoch")
UNSCORED = {"infrastructure_error", "unscored", "error", "failed_to_start", "initialization_failed"}


def validate_evaluation(result: dict, expected: dict) -> float:
    if not isinstance(result, dict) or not isinstance(expected, dict):
        raise ValueError("Result and expected_identity must be JSON objects")
    if any(key not in expected for key in IDENTITY):
        raise ValueError("expected_identity requires all six fields: " + ", ".join(IDENTITY))
    for key in IDENTITY:
        value = expected[key]
        if key == "seed":
            valid = type(value) is int and value >= 0
        elif key == "epoch":
            valid = (type(value) is int and value >= 0) or (isinstance(value, str) and bool(value.strip()))
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            raise ValueError("Invalid expected identity: " + key)
        if key not in result or type(result[key]) is not type(value) or result[key] != value:
            raise ValueError("Evaluation identity mismatch: " + key)
    if expected["variant"] not in {"A", "B", "C"}:
        raise ValueError("Invalid embodied variant")
    if expected["task_id"] not in {f"E{i:02d}" for i in range(1, 51)}:
        raise ValueError("Task outside frozen E01-E50 panel")
    if result.get("status") in UNSCORED or result.get("scored") is False:
        raise ValueError("Infrastructure or unscored result has no Harbor reward")
    if result.get("infrastructure_error"):
        raise ValueError("Infrastructure error has no Harbor reward")
    if type(result.get("success")) is not bool:
        raise ValueError("Missing authoritative boolean success")
    score = next((result[key] for key in ("score", "completion", "partial_credit") if key in result), None)
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Missing or invalid explicit normalized score")
    return float(score)


def verify(config_path: Path, output: Path) -> dict:
    cfg = json.loads(Path(config_path).read_text())
    if not isinstance(cfg, dict) or not cfg.get("result_path"):
        raise ValueError("Private controller config requires result_path")
    result_path = Path(cfg["result_path"])
    raw = result_path.read_bytes()
    if "result_sha256" in cfg and hashlib.sha256(raw).hexdigest() != cfg["result_sha256"]:
        raise ValueError("Sealed authoritative result SHA256 mismatch")
    result = json.loads(raw)
    score = validate_evaluation(result, cfg.get("expected_identity"))
    # No reward directory or reward file is created before full validation.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reward = {"success": float(result["success"]), "score": score}
    for name, value in (("evaluation.json", result), ("reward.json", reward)):
        temporary = output / (name + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        temporary.replace(output / name)
    return reward


def main() -> int:
    path = os.environ.get("VIDEOICL_VERIFIER_CONFIG")
    if not path:
        raise ValueError("VIDEOICL_VERIFIER_CONFIG must point to controller-private configuration")
    reward = verify(Path(path), Path(os.environ.get("HARBOR_VERIFIER_LOG_DIR", "/logs/verifier")))
    print(json.dumps(reward))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
