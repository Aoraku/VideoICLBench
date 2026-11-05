#!/usr/bin/env python3
"""Build an exact, non-launching resource plan from the fixed 450-trial panel.

A logical slot is not a reserved GPU, a live room, a model request or a scored
episode. Native admission and measured resource validation are separate gates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import re


TASKS = tuple(f"E{i:02d}" for i in range(1, 51))
VARIANTS = ("A", "B", "C")
CONDITIONS = ("real", "sim", "text_rule")
GLOBAL_FIELDS = {"physics_dt_seconds", "physics_device", "gravity", "physx", "renderer", "lighting"}


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def global_fingerprint(profile: dict) -> str:
    if not isinstance(profile, dict) or not isinstance(profile.get("backend"), str) or not profile["backend"]:
        raise ValueError("A named native backend is required")
    settings = profile.get("global_settings")
    if not isinstance(settings, dict) or not GLOBAL_FIELDS <= settings.keys():
        raise ValueError("Explicit global physics/render/lighting settings are required")
    dt = settings["physics_dt_seconds"]
    if type(dt) not in (int, float) or not math.isfinite(dt) or dt <= 0:
        raise ValueError("Physics timestep must be finite and positive")
    if settings["physics_device"] not in {"cpu", "cuda:0"}:
        raise ValueError("Declare the local physical simulation device")
    for field in ("physx", "renderer", "lighting"):
        if not isinstance(settings[field], dict) or not settings[field]:
            raise ValueError("Explicit global section required: " + field)
    # Hash the entire declared global dictionary, not just a subset. Future
    # scene-wide options then cannot silently mix with incompatible pools.
    return digest({"backend": profile["backend"], "global_settings": settings})


def load_episodes(task_root: Path, compatibility: dict) -> list[dict]:
    task_root = Path(task_root).resolve()
    raw_plan = (task_root / "episode-plan.json").read_bytes()
    rows = json.loads(raw_plan)
    if not isinstance(rows, list) or len(rows) != 450:
        raise ValueError("The first panel requires exactly 450 planned episodes")
    wanted = {(t, v, c) for t in TASKS for v in VARIANTS for c in CONDITIONS}
    profiles = compatibility.get("profiles", {})
    task_profiles = compatibility.get("task_profiles", {})
    variant_profiles = compatibility.get("variant_profiles", {})
    if set(task_profiles) != set(TASKS):
        raise ValueError("Compatibility map must cover E01-E50 exactly")
    if not set(variant_profiles) <= {t + "-" + v for t in TASKS for v in VARIANTS}:
        raise ValueError("Unknown task/variant profile override")
    fingerprints = {name: global_fingerprint(value) for name, value in profiles.items()}
    if not profiles or not set(task_profiles.values()) <= profiles.keys() or not set(variant_profiles.values()) <= profiles.keys():
        raise ValueError("All profile assignments must name an explicit profile")
    task_specs = {}
    seen, episode_keys = set(), set()
    result = []
    for item in rows:
        identity = (item.get("task_id"), item.get("variant"), item.get("input_condition"))
        if identity not in wanted or identity in seen:
            raise ValueError("Missing, duplicated or out-of-panel episode identity")
        seen.add(identity)
        task, variant, condition = identity
        seed = item.get("seed")
        if type(seed) is not int or seed < 0:
            raise ValueError("An explicit nonnegative episode seed is required")
        key = item.get("episode_key")
        expected_key = f"embodied-{task.lower()}-{variant.lower()}--{condition}--seed{seed}"
        if not isinstance(key, str) or key != expected_key or key in episode_keys:
            raise ValueError("Unique nonempty episode keys are required")
        episode_keys.add(key)
        if item.get("fresh_environment_required") is not True or item.get("fresh_agent_session_required") is not True:
            raise ValueError("Each condition requires a fresh environment and native agent session")
        if type(item.get("video_enabled")) is not bool or item["video_enabled"] != (condition != "text_rule"):
            raise ValueError("Text-rule trials must disable video")
        relative = Path(item["task_directory"])
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            raise ValueError("A local task directory name is required")
        expected_dir = f"embodied-{task.lower()}-{variant.lower()}"
        if str(relative) != expected_dir:
            raise ValueError("Task directory identity differs from its trial")
        folder = task_root / relative
        if relative not in task_specs:
            raw_spec = (folder / "environment/native.json").read_bytes()
            task_specs[relative] = (json.loads(raw_spec), hashlib.sha256(raw_spec).hexdigest())
        spec, spec_hash = task_specs[relative]
        if type(spec.get('seed')) is not int or (spec.get("kind"), spec.get("task_id"), spec.get("variant"), spec.get("seed")) != ("embodied", task, variant, seed):
            raise ValueError("Harbor package and episode identity differ")
        if spec.get("action_interface") != "bounded_dual_arm_tokens_v1":
            raise ValueError("Unsupported trial action interface")
        if spec.get('agent_interaction') not in (None, 'gui_only') or spec.get('agent_protocol') not in (None, 'roboprobe_gui_v1'):
            raise ValueError('This campaign requires the GUI-only RoboProbe agent protocol')
        budget = spec.get("budget", {})
        if type(budget.get("max_actions")) is not int or budget["max_actions"] <= 0:
            raise ValueError("Explicit action budget required")
        timeout = budget.get("timeout_sec")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Explicit finite time budget required")
        if condition == "text_rule":
            material = None
        else:
            field = "demo" if condition == "real" else "demo_sim"
            record = spec.get(field)
            material = {"field": field, "path": record.get("path"), "sha256": record.get("sha256"),
                        "verification": record.get("verification")} if isinstance(record, dict) else None
        profile_name = variant_profiles.get(task + "-" + variant, task_profiles[task])
        profile = profiles[profile_name]
        comparison = {"task_id": task, "variant": variant, "seed": seed,
            "dataset_revision": spec.get("dataset_revision"), "catalog_sha256": spec.get("catalog_sha256"),
            "instruction_sha256": spec.get("instruction_sha256"), "action_interface": spec["action_interface"],
            "agent_interaction": spec.get('agent_interaction'), "agent_protocol": spec.get('agent_protocol'),
            "budget": budget, "profile_name": profile_name,
            "global_fingerprint": fingerprints[profile_name]}
        result.append({"episode_key": key, "task_directory": str(relative), "task_id": task,
            "variant": variant, "seed": seed, "input_condition": condition,
            "task_manifest_sha256": spec_hash, "input_material": material,
            "video_enabled": condition != "text_rule", "budget": deepcopy(budget),
            "agent_interaction": spec.get('agent_interaction'), "agent_protocol": spec.get('agent_protocol'),
            "paired_comparison_key": f"{task}-{variant}-seed{seed}",
            "comparison_contract_sha256": digest(comparison), "profile_name": profile_name,
            "profile_status": profile.get("status", "unverified"),
            "global_fingerprint": fingerprints[profile_name],
            "task_readiness": spec.get("readiness"),
            "native_interaction_validated": spec.get("native_interaction_validated") is True,
            "fresh_environment_required": True, "fresh_agent_session_required": True,
            "status": "not_started", "native_run_id": None, "native_agent_session_id": None,
            "native_success": None, "score": None, "native_terminal_verified": False})
    if seen != wanted:
        raise ValueError("Incomplete first-panel identity set")
    paired = defaultdict(list)
    for row in result:
        paired[(row["task_id"], row["variant"])].append(row)
    for triple in paired.values():
        if {r["input_condition"] for r in triple} != set(CONDITIONS) or len({r["comparison_contract_sha256"] for r in triple}) != 1:
            raise ValueError("Real/sim/text comparison must use the same scene, seed, action space and budget")
    return result


def _balanced_pool_counts(groups: dict, pool_count: int, capacity: int) -> dict:
    counts = {key: math.ceil(len(rows) / capacity) for key, rows in groups.items()}
    if sum(counts.values()) > pool_count:
        raise ValueError(f"Insufficient pools for compatibility groups: need {sum(counts.values())}, have {pool_count}")
    target = min(pool_count, sum(len(rows) for rows in groups.values()))
    while sum(counts.values()) < target:
        choices = [key for key in groups if counts[key] < len(groups[key])]
        selected = min(choices, key=lambda k: (-len(groups[k]) / counts[k], k))
        counts[selected] += 1
    return counts


def _spread_pools(groups: dict, pool_counts: dict, cards: int, pools_per_card: int, packing_seed: int):
    randomizer = random.Random(packing_seed)
    packed = []
    for group in sorted(groups):
        rows = sorted(groups[group], key=lambda r: r["episode_key"])
        randomizer.shuffle(rows)
        count = pool_counts[group]
        buckets = [[] for _ in range(count)]
        for index, row in enumerate(rows):
            buckets[index % count].append(row)
        packed.extend({"group": group, "rows": bucket} for bucket in buckets)
    # Pair the largest and smallest pools on the same card before adjusting
    # within a compatibility group. Dedicated task groups never receive rows
    # from another task merely to make a utilization chart look full.
    packed.sort(key=lambda p: (-len(p["rows"]), p["group"], p["rows"][0]["episode_key"]))
    by_card = [[] for _ in range(cards)]
    for index, pool in enumerate(packed):
        layer, position = divmod(index, cards)
        card = position if layer % 2 == 0 else cards - position - 1
        pool["card_index"] = card
        pool["pool_index"] = layer
        by_card[card].append(pool)
    return packed, by_card


def _balance_cards(by_card: list, capacity: int):
    while True:
        loads = [sum(len(p["rows"]) for p in card) for card in by_card]
        move = None
        for low in sorted(range(len(loads)), key=lambda i: (loads[i], i)):
            for high in sorted(range(len(loads)), key=lambda i: (-loads[i], i)):
                if loads[high] - loads[low] <= 1:
                    continue
                for receiver in by_card[low]:
                    for donor in by_card[high]:
                        if receiver["group"] == donor["group"] and len(receiver["rows"]) < capacity and len(donor["rows"]) > 1:
                            move = receiver, donor
                            break
                    if move:
                        break
                if move:
                    break
            if move:
                break
        if move is None:
            return
        receiver, donor = move
        receiver["rows"].append(donor["rows"].pop())


def make_plan(task_root: Path, compatibility: dict, *, cards=40, pools_per_card=2,
              rooms_per_pool=8, packing_seed=0, campaign_id="realworld50-first450",
              conditions=CONDITIONS) -> dict:
    for value, name in [(cards, "cards"), (pools_per_card, "pools_per_card"), (rooms_per_pool, "rooms_per_pool")]:
        if type(value) is not int or value <= 0:
            raise ValueError(name + " must be a positive integer")
    if type(packing_seed) is not int or not isinstance(campaign_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', campaign_id):
        raise ValueError("Explicit campaign ID and integer packing seed required")
    if (not isinstance(conditions, (tuple, list)) or not conditions
            or len(set(conditions)) != len(conditions) or not set(conditions) <= set(CONDITIONS)):
        raise ValueError("Select unique known input conditions")
    conditions = tuple(c for c in CONDITIONS if c in conditions)
    # Always validate the entire canonical source before selecting a panel.
    # An excluded malformed row must not silently make a corrupt source valid.
    episodes = [r for r in load_episodes(task_root, compatibility) if r['input_condition'] in conditions]
    expected_count = 150 * len(conditions)
    if conditions == ('real', 'text_rule'):
        # The 300 deployment freezes each full private rule file as well as
        # public instruction/spec bytes. Both paired conditions share its hash.
        rule_hashes = {}
        for row in episodes:
            folder = row['task_directory']
            if folder not in rule_hashes:
                rule_path = Path(task_root) / folder / 'tests/rule.json'
                rule = json.loads(rule_path.read_text()).get('rule')
                if not isinstance(rule, str) or not rule.strip():
                    raise ValueError('The selected 300 panel requires all 150 explicit text rules')
                rule_hashes[folder] = hashlib.sha256(rule_path.read_bytes()).hexdigest()
            row['rule_file_sha256'] = rule_hashes[folder]
            row['comparison_contract_sha256'] = digest(dict(
                base_contract_sha256=row['comparison_contract_sha256'],
                rule_file_sha256=row['rule_file_sha256']))
    same_task = compatibility.get("same_task_validation_groups", ["E42", "E43", "E45"])
    if not isinstance(same_task, list) or len(set(same_task)) != len(same_task) or not set(same_task) <= set(TASKS):
        raise ValueError("Invalid same-task validation grouping")
    groups = defaultdict(list)
    for row in episodes:
        # Joint/mechanism tasks are not excluded from mixed pools. Only the
        # explicitly selected validation groups receive same-task pools.
        dedicated = row["task_id"] if row["task_id"] in same_task else "mixed"
        groups[row["global_fingerprint"] + ":" + dedicated].append(row)
    pool_total = cards * pools_per_card
    counts = _balanced_pool_counts(groups, pool_total, rooms_per_pool)
    packed, by_card = _spread_pools(groups, counts, cards, pools_per_card, packing_seed)
    _balance_cards(by_card, rooms_per_pool)
    pools, assignments, gpu_rows = [], [], []
    for card_index, card in enumerate(by_card):
        for pool_index in range(pools_per_card):
            pool_id = f"gpu-{card_index:02d}-pool-{pool_index:02d}"
            matches = [p for p in card if p["pool_index"] == pool_index]
            packed_pool = matches[0] if matches else None
            rows = sorted(packed_pool["rows"], key=lambda r: r["episode_key"]) if packed_pool else []
            dedicated = packed_pool["group"].split(":", 1)[1] if packed_pool else None
            fingerprint = rows[0]["global_fingerprint"] if rows else None
            pools.append({"pool_id": pool_id, "logical_gpu_index": card_index,
                "pool_index": pool_index, "configured_room_capacity": rooms_per_pool,
                "planned_occupied_rooms": len(rows), "native_live_rooms": 0,
                "global_fingerprint": fingerprint,
                "validation_group": dedicated, "mixed_task_count": len({r["task_id"] for r in rows}),
                "episode_keys": [r["episode_key"] for r in rows], "status": "planned",
                "gpu_uuid": None, "host": None, "process_id": None,
                "capacity_reserved": False, "measured_peak_vram_mib": None,
                "native_admission_validated": False})
            for slot, row in enumerate(rows):
                assignments.append(dict(row, campaign_id=campaign_id, pool_id=pool_id,
                    logical_gpu_index=card_index, room_slot=slot, initial_attempt=1,
                    attempt_status="not_started", runtime_validation_required=True,
                    suite='videoicl-realworld50', epoch=campaign_id,
                    expected_identity_source='native_controller_creation_result'))
        gpu_rows.append({"logical_gpu_index": card_index,
            "selector_hint_only": card_index, "gpu_uuid": None, "host": None,
            "planned_episodes": sum(len(p["rows"]) for p in card),
            "configured_pool_count": pools_per_card, "native_live_pools": 0,
            "allocation_reserved": False})
    assignments.sort(key=lambda r: r["episode_key"])
    if len(assignments) != expected_count or len({r["episode_key"] for r in assignments}) != expected_count:
        raise AssertionError("Packing lost or duplicated a planned episode")
    comparison_counts = Counter(r["input_condition"] for r in assignments)
    if comparison_counts != {c: 150 for c in conditions}:
        raise AssertionError("Packing changed the fixed input panel")
    active = [p for p in pools if p["planned_occupied_rooms"]]
    statistics = {"planned_episodes": expected_count, "logical_gpu_count": cards,
        "configured_pool_count": pool_total, "planned_nonempty_pools": len(active),
        "configured_room_capacity": pool_total * rooms_per_pool,
        "planned_occupied_room_count": expected_count, "planned_unoccupied_room_slots": pool_total * rooms_per_pool - expected_count,
        "min_planned_rooms_per_nonempty_pool": min(p["planned_occupied_rooms"] for p in active),
        "max_planned_rooms_per_pool": max(p["planned_occupied_rooms"] for p in pools),
        "planned_rooms_per_pool_histogram": {str(k): v for k, v in sorted(Counter(p["planned_occupied_rooms"] for p in pools).items())},
        "planned_episodes_per_card_histogram": {str(k): v for k, v in sorted(Counter(g["planned_episodes"] for g in gpu_rows).items())},
        "input_conditions": dict(comparison_counts), "compatibility_groups": len(groups),
        "native_live_episodes": 0, "native_terminal_verified_episodes": 0,
        "actual_model_requests": 0, "resource_validation_status": "unverified"}
    statistics['task_agent_protocol_unverified_cases'] = sum(
        r['agent_interaction'] != 'gui_only' or r['agent_protocol'] != 'roboprobe_gui_v1' for r in assignments)
    for pool in pools:
        if pool["planned_occupied_rooms"] > rooms_per_pool:
            raise AssertionError("Pool capacity exceeded")
    source_plan = Path(task_root) / "episode-plan.json"
    return {"schema": "videoicl-realworld50-campaign-plan-v1", "campaign_id": campaign_id,
        "status": "planned_not_authorized_for_launch", "planning_only": True,
        "source_episode_plan_sha256": hashlib.sha256(source_plan.read_bytes()).hexdigest(),
        "compatibility_manifest_sha256": digest(compatibility),
        "compatibility_manifest_status": compatibility.get("status", "unverified"),
        "packing_seed": packing_seed, "selected_input_conditions": list(conditions), "statistics": statistics,
        "required_agent_capabilities": {'protocol': 'roboprobe_gui_v1', 'surface': 'gui_only',
            'core_verbs': ['observe', 'act', 'done', 'giveup'], 'direct_robot_mcp_exposed': False},
        "provider": {"name": "sub2api" if conditions == CONDITIONS else "explicit_runtime_provider_required", "model_id": "runtime_required", "credentials": "controller_private_file_required",
                     "provider_concurrency_validated": False},
        "attempt_policy": {"initial_scientific_attempts_per_episode": 1,
            "retry_valid_model_failure": False, "retry_valid_zero_score": False,
            "infrastructure_retry_uses_new_attempt_directory": True,
            "preserve_original_infrastructure_evidence": True,
            "unknown_or_infrastructure_result_is_zero": False},
        "runtime_gates": ["exclusive GPU allocation and measured per-card admission",
            "native mixed-task and same-task room startup/step/observation evidence",
            "stable simultaneous one-pool and two-pool memory/CPU/render measurements",
            "room-isolated terminal seal/reset with no cross-room advancement error",
            "identical inference initial-state contract across " + "/".join(conditions),
            "GUI-only native CLI screenshot/click/type and done/giveup acknowledgement through " + ("sub2api" if conditions == CONDITIONS else "the explicitly supplied provider"),
            "complete media mappings and frozen per-task budget/scoring acceptance"],
        "gpus": gpu_rows, "pools": pools, "episodes": assignments}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--compatibility", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cards", type=int, default=40)
    parser.add_argument("--pools-per-card", type=int, default=2)
    parser.add_argument("--rooms-per-pool", type=int, default=8)
    parser.add_argument("--packing-seed", type=int, default=0)
    parser.add_argument("--campaign-id", default="realworld50-first450")
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    args = parser.parse_args()
    plan = make_plan(args.task_root, json.loads(args.compatibility.read_text()), cards=args.cards,
        pools_per_card=args.pools_per_card, rooms_per_pool=args.rooms_per_pool,
        packing_seed=args.packing_seed, campaign_id=args.campaign_id, conditions=args.conditions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(plan["statistics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
