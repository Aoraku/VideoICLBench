"""Versioned scene contracts for the complete 48-task taxonomy.

The taxonomy and ``configs/task_registry.json`` are the public registry.  The
eight native anchors retain their audited scene files; the remaining tasks
use deterministic generated templates until their task-specific USD adapter
is installed.  Both kinds of scene have the same loader contract, so worker
and evaluator code does not need task-specific path logic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .profiles import revise_scene

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "task_registry.json"
REGISTRY = json.loads(REGISTRY_PATH.read_text())
TASKS = tuple(task["id"] for task in REGISTRY["tasks"])
VARIANTS = tuple(REGISTRY.get("variants", ["A", "B", "C"]))
SEEDS = tuple(int(seed) for seed in REGISTRY.get("seeds", [0, 7]))

_BY_ID = {task["id"]: task for task in REGISTRY["tasks"]}
_RELEASED_MANIFEST = json.loads((ROOT / "scenes" / "manifest.private.json").read_text())
_RELEASED_BY_FILE = {record["file"]: record for record in _RELEASED_MANIFEST["scenes"]}
_GENERATED_MANIFEST_PATH = ROOT / "scenes" / "generated" / "manifest.json"
_GENERATED_MANIFEST = json.loads(_GENERATED_MANIFEST_PATH.read_text()) if _GENERATED_MANIFEST_PATH.exists() else {"scenes": []}
_GENERATED_BY_FILE = {record["file"]: record for record in _GENERATED_MANIFEST.get("scenes", [])}


def _entry(task: str, variant: str) -> dict[str, Any]:
    try:
        item = _BY_ID[task]
    except KeyError as exc:
        raise ValueError(f"Unknown task {task!r}; expected one of {TASKS}") from exc
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}; expected one of {VARIANTS}")
    return item["variants_manifest"][VARIANTS.index(variant)]


def scene_path(task: str, variant: str = "A", seed: int = 7) -> Path:
    """Return the immutable scene file for a task/variant/seed tuple."""
    if int(seed) not in SEEDS:
        raise ValueError(f"Use an exported seed from {SEEDS}")
    path = ROOT / _entry(task, variant)["scene_paths"][str(int(seed))]
    if not path.is_file():
        raise FileNotFoundError(f"Missing scene contract {path}")
    return path


def _verify(path: Path) -> None:
    rel = str(path.relative_to(ROOT))
    record = _RELEASED_BY_FILE.get(path.name) or _GENERATED_BY_FILE.get(rel)
    if record is None:
        raise ValueError(f"Scene is not listed in a manifest: {rel}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != record["sha256"]:
        raise ValueError(f"Scene checksum mismatch: {rel}")


def load(task: str, variant: str = "A", seed: int = 7) -> dict[str, Any]:
    """Load and verify a scene contract, then apply calibrated revisions."""
    path = scene_path(task, variant, seed)
    _verify(path)
    spec = json.loads(path.read_text())
    # Older anchors predate the explicit field; generated templates already
    # include it. Keep this normalization at the loader boundary so every
    # Isaac scene sees the same shape.
    spec.setdefault("fixtures", [])
    spec.setdefault("variant", variant)
    spec.setdefault("seed", int(seed))
    spec.setdefault("embodiment", _BY_ID[task]["embodiment"])
    spec.setdefault("scene_template", _BY_ID[task].get("scene_template", {}))
    spec.setdefault("instruction", _BY_ID[task]["variants_manifest"][VARIANTS.index(variant)]["instruction"])
    return revise_scene(spec)


def metadata(task: str) -> dict[str, Any]:
    """Return registry metadata without loading private physical state."""
    if task not in _BY_ID:
        raise ValueError(f"Unknown task {task!r}")
    return dict(_BY_ID[task])


def visible_world(spec: dict[str, Any]) -> dict[str, Any]:
    """Extract the rule-independent initial world shown to the agent."""
    return {k: spec.get(k, []) for k in ("objects", "zones", "fixtures")}


def public_assignment() -> str:
    return "观察分配到的演示并在新场景中复现其规则；只使用可见场景与公开控制。"


__all__ = ["TASKS", "VARIANTS", "SEEDS", "load", "scene_path", "metadata", "visible_world", "public_assignment"]
