"""Frozen RealWorld50 labels and private pilot semantic checks.

This module has no simulator dependency. ``metadata`` and ``provenance`` are
maintainer-only; only ``public_assignment`` is suitable for the policy prompt.
E task IDs never fall back to an old F/B task or inherit its ABC meaning.

``check_pilot`` consumes evidence derived by the simulator adapter. It does not
infer contacts, stable support, or release from a picture or commanded pose.
All pilots require literal ``released=True`` and ``stable=True`` after the
adapter's calibrated stability interval. Missing evidence fails closed.

Observation contracts (JSON-compatible):
* E02: ``bottom_to_top`` color list; directed ``support_edges`` [lower, upper],
  including [table, bottom]. Each edge needs measured contact AND support.
* E05: ``placements`` maps cube/sphere/triangle to square/circle/triangle;
  ``supported`` lists the three physically supported object IDs.
* E06: ``ball_to_cell`` maps exactly three distinct IDs to left_far,
  left_middle, left_near, right_far, right_middle, right_near; ``seated`` lists
  physically seated IDs. The holder stays in the defined operator frame.
* E18: ``delivered`` lists ball colors on the white target; ``in_drawer`` lists
  ball colors still inside; ``drawer_closed`` is a measured joint predicate.
* E26: ``bell_events`` is a chronological list of {side, event, step, contact}.
  side is left/right, event is press/release, and step is a nonnegative physics
  step. A press requires contact=True; it counts only upon a later release.
  The adapter retains the event history across actions. Camera frames and
  commands alone cannot generate these events. Pilot cards are fixed to 9,1.
* E32: ``delivered`` and ``moved_objects`` list object identities, using
  sprite_bottle/pink_cube/cola_bottle for the three candidates. The latter
  uses calibrated movement tolerance, not exact initial-pose equality.

The result proves only these semantic predicates on the supplied evidence.
Asset fidelity and native-physics verification are separate release gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).resolve().parents[1] / "configs" / "realworld50_catalog.json"
_CATALOG_BYTES = CATALOG_PATH.read_bytes()
_CATALOG = json.loads(_CATALOG_BYTES)
DATASET_REPOSITORY = "Aoraku/VideoICL-Embodied-RealWorld50"
DATASET_REVISION = _CATALOG["dataset_revision"]
CATALOG_SHA256 = hashlib.sha256(_CATALOG_BYTES).hexdigest()
TASKS = tuple(item["id"] for item in _CATALOG["tasks"])
VARIANTS = ("A", "B", "C")
PILOT_TASKS = ("E02", "E05", "E06", "E18", "E26", "E32")
_BY_ID = {item["id"]: item for item in _CATALOG["tasks"]}

if TASKS != tuple(f"E{i:02d}" for i in range(1, 51)):
    raise ValueError("RealWorld50 catalog must contain E01–E50 exactly once in order")
if any(tuple(v["variant"] for v in task["variants"]) != VARIANTS
       for task in _CATALOG["tasks"]):
    raise ValueError("Every RealWorld50 task must preserve source A/B/C labels")


def _task(task: str) -> dict[str, Any]:
    try:
        return _BY_ID[task]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Unknown RealWorld50 task: {task!r}") from exc


def _variant(task: str, variant: str) -> dict[str, Any]:
    item = _task(task)
    if variant not in VARIANTS:
        raise ValueError(f"Unknown RealWorld50 variant: {variant!r}")
    return item["variants"][VARIANTS.index(variant)]


def metadata(task: str) -> dict[str, Any]:
    """Return the full, unmodified private source task, detached from storage."""
    return deepcopy(_task(task))


def variant_rule(task: str, variant: str) -> str:
    """Return the exact private source annotation, not an old F-task rule."""
    return _variant(task, variant)["observed_demo"]


def public_assignment(task: str) -> str:
    """Return only the source's neutral execution prompt; never append ABC."""
    return _task(task)["inference_prompt"]


def provenance(task: str, variant: str | None = None) -> dict[str, Any]:
    """Bind a task or variant to the frozen dataset and original video hashes."""
    item = _task(task)
    videos = item["variants"] if variant is None else [_variant(task, variant)]
    fields = ("video_id", "variant", "relative_path", "sha256", "sheet",
              "source_kind", "source_commit", "source_date", "supersedes_filename")
    return {
        "dataset_repository": DATASET_REPOSITORY,
        "dataset_revision": DATASET_REVISION,
        "catalog_sha256": CATALOG_SHA256,
        "task_id": task,
        "videos": [{k: deepcopy(v[k]) for k in fields if k in v} for v in videos],
    }


def _same_members(value: Any, expected: set[str]) -> bool:
    # Reject duplicates and strings; a duplicated item cannot stand for another.
    return (isinstance(value, (list, tuple))
            and all(isinstance(x, str) for x in value)
            and len(value) == len(expected) and set(value) == expected)


def _support_edges(value: Any) -> set[tuple[str, str]] | None:
    if not isinstance(value, (list, tuple)):
        return None
    edges = set()
    for pair in value:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not all(isinstance(x, str) for x in pair)):
            return None
        edges.add(tuple(pair))
    return edges


def _bell_counts(events: Any) -> tuple[bool, dict[str, int]]:
    """Count completed physical press-release cycles; reject broken histories."""
    counts = {"left": 0, "right": 0}
    if not isinstance(events, (list, tuple)):
        return False, counts
    pressed_at: dict[str, int | None] = {"left": None, "right": None}
    previous_step = -1
    for event in events:
        if not isinstance(event, Mapping):
            return False, counts
        side, kind, step = event.get("side"), event.get("event"), event.get("step")
        if (not isinstance(side, str) or side not in counts or kind not in ("press", "release")
                or type(step) is not int or step < 0 or step < previous_step):
            return False, counts
        previous_step = step
        if kind == "press":
            if pressed_at[side] is not None or event.get("contact") is not True:
                return False, counts
            pressed_at[side] = step
        else:
            if pressed_at[side] is None or step <= pressed_at[side]:
                return False, counts
            counts[side] += 1
            pressed_at[side] = None
    return all(step is None for step in pressed_at.values()), counts


def check_pilot(task: str, variant: str, observation: Mapping[str, Any]) -> dict[str, Any]:
    """Check one private pilot outcome; unsupported tasks never pass by default.

    Missing or malformed observation evidence returns success=False. Unknown
    identities/variants raise ValueError; known non-pilot E tasks raise
    NotImplementedError, so callers must report them as unimplemented.
    """
    _variant(task, variant)
    if task not in PILOT_TASKS:
        raise NotImplementedError(f"RealWorld50 semantics not implemented for {task}")
    obs = observation if isinstance(observation, Mapping) else {}
    checks = {
        "released": obs.get("released") is True,
        "stable": obs.get("stable") is True,
    }
    index = VARIANTS.index(variant)

    if task == "E02":
        order = (("red", "green", "blue"), ("green", "blue", "red"),
                 ("blue", "red", "green"))[index]
        actual_order = obs.get("bottom_to_top")
        checks["color_layer_order"] = (isinstance(actual_order, (list, tuple))
                                       and tuple(actual_order) == order)
        edges = _support_edges(obs.get("support_edges"))
        required = {("table", order[0]), (order[0], order[1]), (order[1], order[2])}
        checks["physical_support_chain"] = edges is not None and required <= edges

    elif task == "E05":
        targets = (("square", "circle", "triangle"), ("circle", "triangle", "square"),
                   ("triangle", "square", "circle"))[index]
        expected = dict(zip(("cube", "sphere", "triangle"), targets))
        checks["shape_marker_mapping"] = obs.get("placements") == expected
        checks["physical_support"] = _same_members(obs.get("supported"), set(expected))

    elif task == "E06":
        targets = ({"left_far", "left_middle", "left_near"},
                   {"right_far", "right_middle", "right_near"},
                   {"left_far", "left_near", "right_middle"})[index]
        assignment = obs.get("ball_to_cell")
        valid = (isinstance(assignment, Mapping) and len(assignment) == 3
                 and all(isinstance(k, str) and isinstance(v, str)
                         for k, v in assignment.items()))
        checks["occupied_hole_set"] = valid and set(assignment.values()) == targets
        checks["three_balls_physically_seated"] = (
            valid and _same_members(obs.get("seated"), set(assignment)))

    elif task == "E18":
        target = ("red", "green", "blue")[index]
        checks["selected_ball_delivered"] = _same_members(obs.get("delivered"), {target})
        checks["other_balls_in_drawer"] = _same_members(
            obs.get("in_drawer"), {"red", "green", "blue"} - {target})
        checks["drawer_closed"] = obs.get("drawer_closed") is True

    elif task == "E26":
        valid, counts = _bell_counts(obs.get("bell_events"))
        expected = ((9, 1), (1, 9), (10, 0))[index]
        checks["complete_contact_press_release_history"] = valid
        checks["exact_bell_counts"] = (counts["left"], counts["right"]) == expected

    elif task == "E32":
        target = ("sprite_bottle", "pink_cube", "cola_bottle")[index]
        checks["selected_identity_delivered"] = _same_members(obs.get("delivered"), {target})
        checks["only_selected_object_moved"] = _same_members(obs.get("moved_objects"), {target})

    return {
        "task": task,
        "variant": variant,
        "success": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "dataset_revision": DATASET_REVISION,
    }


__all__ = ["TASKS", "VARIANTS", "PILOT_TASKS", "DATASET_REPOSITORY",
           "DATASET_REVISION", "CATALOG_SHA256", "metadata", "variant_rule",
           "public_assignment", "provenance", "check_pilot"]
