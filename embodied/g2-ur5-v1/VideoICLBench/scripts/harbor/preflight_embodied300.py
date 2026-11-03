#!/usr/bin/env python3
"""Read-only identity/media checks for the real-video + text 300 panel. No GPU/API."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def validate_panel(plan):
    if 'panel_contract' in plan:
        from panel_contract import validate_frozen_panel
        return validate_frozen_panel(plan)
    rows = plan.get('episodes', [])
    expected = {(f'E{i:02d}', v, c) for i in range(1, 51) for v in 'ABC' for c in ('real', 'text_rule')}
    actual = [(r.get('task_id'), r.get('variant'), r.get('input_condition')) for r in rows]
    if len(rows) != 300 or len(set(actual)) != 300 or set(actual) != expected:
        raise ValueError('Require exactly 50 x ABC x real/text_rule, with no sim or duplicate identities')
    keys = {r['episode_key'] for r in rows}
    if len(keys) != 300:
        raise ValueError('Require 300 unique episode keys')
    paired = defaultdict(list)
    for r in rows:
        if type(r.get('seed')) is not int or r['seed'] < 0:
            raise ValueError('Explicit nonnegative seed required')
        if r['episode_key'] != f"embodied-{r['task_id'].lower()}-{r['variant'].lower()}--{r['input_condition']}--seed{r['seed']}":
            raise ValueError('Episode key and identity disagree')
        if r['task_directory'] != f"embodied-{r['task_id'].lower()}-{r['variant'].lower()}":
            raise ValueError('Task directory and identity disagree')
        paired[(r['task_id'], r['variant'])].append(r)
    for pair in paired.values():
        if len({r['seed'] for r in pair}) != 1 or len({r['comparison_contract_sha256'] for r in pair}) != 1:
            raise ValueError('Real/text must share task, variant, seed and comparison contract')
    pools = plan.get('pools', [])
    if len({p['pool_id'] for p in pools}) != len(pools):
        raise ValueError('Duplicate pool ID')
    memberships = []
    by_key = {r['episode_key']: r for r in rows}
    for p in pools:
        if not re.fullmatch(r'gpu-\d{2}-pool-\d{2}', p['pool_id']):
            raise ValueError('Invalid pool ID')
        if p['pool_index'] not in (0, 1) or not 0 <= p['logical_gpu_index'] < 24:
            raise ValueError('300 plan requires 24 logical cards and at most two pools per card')
        if len(p['episode_keys']) != p['planned_occupied_rooms'] or not 5 <= len(p['episode_keys']) <= 8:
            raise ValueError('Each assigned pool must contain 5 to 8 episodes')
        members = [by_key[k] for k in p['episode_keys']]
        tasks = {r['task_id'] for r in members}
        if tasks & {'E42', 'E43', 'E45'} and len(tasks) != 1:
            raise ValueError('E42/E43/E45 require separate same-task pools')
        if len({r['global_fingerprint'] for r in members}) != 1:
            raise ValueError('Incompatible global profiles in one pool')
        if any(r['pool_id'] != p['pool_id'] or r['logical_gpu_index'] != p['logical_gpu_index'] for r in members):
            raise ValueError('Pool and episode assignment disagree')
        if sorted(r['room_slot'] for r in members) != list(range(len(members))):
            raise ValueError('Room slots must be unique and contiguous')
        memberships.extend(p['episode_keys'])
    if Counter(memberships) != Counter(keys):
        raise ValueError('Pool memberships lost or duplicated an episode')
    counts = Counter(p['logical_gpu_index'] for p in pools)
    if counts != {i: 2 for i in range(24)}:
        raise ValueError('Require exactly two pools on each of 24 logical cards')
    return rows


def preflight(plan, task_root, *, logical_gpu=None, verify_media=True, path_mappings=(), pool_ids=None):
    rows = validate_panel(plan)
    if logical_gpu is not None:
        if type(logical_gpu) is not int or logical_gpu not in {r['logical_gpu_index'] for r in rows}:
            raise ValueError('logical_gpu must be assigned in the frozen panel')
        rows = [r for r in rows if r['logical_gpu_index'] == logical_gpu]
    if pool_ids is not None:
        if not isinstance(pool_ids,list) or not pool_ids or len(pool_ids)!=len(set(pool_ids)):
            raise ValueError('Explicit nonempty unique pool selection required')
        known={p['pool_id']for p in plan['pools'] if logical_gpu is None or p['logical_gpu_index']==logical_gpu}
        if not set(pool_ids)<=known:raise ValueError('Selected pool is not on this card')
        rows=[r for r in rows if r.get('pool_id')in pool_ids]
    task_root = Path(task_root).resolve()
    reports, sha_cache = [], {}
    for r in rows:
        errors = []
        folder = task_root / r['task_directory']
        try:
            manifest = folder / 'environment/native.json'
            if file_sha(manifest) != r['task_manifest_sha256']:
                errors.append('task_manifest_changed_rebuild_plan_after_reviewed_relocation')
            spec = json.loads(manifest.read_text())
            if (spec.get('task_id'), spec.get('variant'), spec.get('seed')) != (r['task_id'], r['variant'], r['seed']):
                errors.append('task_identity_mismatch')
            instruction = folder / 'instruction.md'
            if not instruction.read_text().strip() or file_sha(instruction) != spec.get('instruction_sha256'):
                errors.append('instruction_missing_or_hash_mismatch')
            rule_path = folder / 'tests/rule.json'
            if file_sha(rule_path) != r.get('rule_file_sha256'):
                errors.append('text_rule_hash_mismatch')
            rule = json.loads(rule_path.read_text()).get('rule')
            if not isinstance(rule, str) or not rule.strip():
                errors.append('text_rule_missing')
            if r['input_condition'] in ('real', 'sim'):
                condition = r['input_condition']
                field = 'demo' if condition == 'real' else 'demo_sim'
                demo = spec.get(field)
                if 'panel_contract' in plan and isinstance(demo, dict):
                    material = r.get('input_material') or {}
                    if material.get('field') != field or any(material.get(k) != demo.get(k) for k in ('path','sha256')):
                        errors.append('frozen_input_material_mismatch')
                if not isinstance(demo, dict) or not isinstance(demo.get('path'), str) or not re.fullmatch(r'[0-9a-f]{64}', demo.get('sha256', '')):
                    errors.append(f'assigned_{condition}_demo_missing')
                elif verify_media:
                    path = Path(demo['path'])
                    path = path if path.is_absolute() else folder / path
                    for remote_prefix, local_prefix in path_mappings:
                        if path.is_relative_to(Path(remote_prefix)):
                            path = Path(local_prefix) / path.relative_to(Path(remote_prefix))
                            break
                    if '${' in str(path) or not path.is_file():
                        errors.append(f'assigned_{condition}_demo_not_local')
                    else:
                        path = path.resolve()
                        if path not in sha_cache:
                            sha_cache[path] = file_sha(path)
                        if sha_cache[path] != demo['sha256']:
                            errors.append(f'assigned_{condition}_demo_hash_mismatch')
                        elif path.stat().st_size == 0:
                            errors.append(f'assigned_{condition}_demo_empty')
            reports.append(dict(episode_key=r['episode_key'], input_condition=r['input_condition'], errors=errors, ok=not errors))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            reports.append(dict(episode_key=r['episode_key'], input_condition=r['input_condition'], errors=errors + ['task_input_error:' + type(exc).__name__], ok=False))
    return dict(schema='videoicl-real-text300-input-preflight-v1', campaign_id=plan['campaign_id'],
        logical_gpu_index=logical_gpu, planned_panel_episodes=len(plan['episodes']), checked_episodes=len(rows),
        input_counts=dict(Counter(r['input_condition'] for r in rows)), media_bytes_verified=verify_media,
        path_mappings=[list(pair) for pair in path_mappings], remote_paths_verified=not bool(path_mappings),
        ready=verify_media and all(r['ok'] for r in reports),
        passed=sum(r['ok'] for r in reports), failed=sum(not r['ok'] for r in reports),
        actual_model_requests=0, gpu_processes_started=0, checks=reports,
        note='Input preflight only; no mixed-pool compatibility, physics, cameras or model acceptance implied.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--task-root', type=Path, required=True)
    p.add_argument('--logical-gpu', type=int)
    p.add_argument('--output', type=Path)
    p.add_argument('--material-path-map', nargs=2, action='append', default=[], metavar=('REMOTE_PREFIX','LOCAL_PREFIX'), help='Local staging byte verification only; does not prove remote file presence')
    p.add_argument('--manifest-only', action='store_true', help='Never returns ready; skips video byte hashing')
    a = p.parse_args()
    report = preflight(json.loads(a.plan.read_text()), a.task_root, logical_gpu=a.logical_gpu, verify_media=not a.manifest_only, path_mappings=a.material_path_map)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open('x') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False))
    return 0 if report['ready'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
