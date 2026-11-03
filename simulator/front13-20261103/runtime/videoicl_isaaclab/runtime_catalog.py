"""Physical construction readiness, independent of formal demo acceptance."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LEGACY_PREVIEW={'F01','F02','F03','F04','F05','F07','F08','F10','F11','F12','F17','F22','F39','F44'}


def recipe_files():
    names=('task_recipes','task_adapters','scene','control','evaluator','profiles','catalog','style','embodiments','layout','rig')
    files=[ROOT/'videoicl_isaaclab'/(n+'.py') for n in names]
    files += [p for p in sorted((ROOT/'configs/embodiments').glob('*.json')) if not p.name.startswith('.')]
    files += [ROOT/'scripts/build_scene.py',ROOT/'scripts/generate_task_specs.py',
              ROOT/'configs/task_registry.json',ROOT/'configs/tasks.json',ROOT/'scenes/generated/manifest.json']
    return files


def recipe_fingerprint():
    h=hashlib.sha256()
    for p in recipe_files():h.update(str(p.relative_to(ROOT)).encode());h.update(p.read_bytes())
    return h.hexdigest()


def ready_tasks():
    try:d=json.loads((ROOT/'configs/workbench_ready.json').read_text())
    except (OSError,ValueError):return set(LEGACY_PREVIEW)
    if d.get('source_sha256')!=recipe_fingerprint():return set(LEGACY_PREVIEW)
    return LEGACY_PREVIEW | {r['task'] for r in d.get('tasks',[]) if r.get('construction_control_checked') and set(r.get('variants',[]))==set('ABC')}
