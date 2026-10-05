"""The published difficulty table describes the runnable task contracts."""
from collections import Counter
from copy import deepcopy
import base64
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from vic import business, v2
from vic.identity_context import contextualize
from vic.v2_atomic import TASKS as LOW_TASKS, FOUR_OBJECTS
from vic_apps.domain import initialize
from vic_apps import workset_delivery


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "tasks/v2/catalog.json").read_text())
TASKS = {task["id"]: task for task in CATALOG["tasks"]}
MEDIUM = [key for key, task in TASKS.items() if task["difficulty"] == "medium"]
HARD = [key for key, task in TASKS.items() if task["difficulty"] == "hard"]


@pytest.fixture(scope="module")
def inference_states():
    return {key: v2.generate(key, 10001, "eval") for key in TASKS}


def runtime_platforms(state):
    return {state["app"], *state.get("linked_apps", [])}


def catalog_platforms(task):
    games = {"2048", "Sudoku", "Minesweeper", "Reversi"}
    return {"games" if name in games else name.lower() for name in task["platforms"]}


def test_catalog_covers_every_task_once_and_has_equal_difficulty_groups():
    assert len(CATALOG["tasks"]) == 75
    assert set(TASKS) == set(range(1, 76))
    assert Counter(t["difficulty"] for t in TASKS.values()) == {"low": 25, "medium": 25, "hard": 25}
    assert {key for key, task in TASKS.items() if task["difficulty"] == "low"} == LOW_TASKS
    for key in LOW_TASKS:
        # Recorder guidance can describe a single demonstration. The execution
        # assignment must not instruct users to use the retired one-target flow.
        visible = json.dumps(TASKS[key]["inference"], ensure_ascii=False)
        assert "确认本条核验" not in visible and "单目标核验" not in visible


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_documented_platforms_exist_and_initial_state_cannot_pass(task_id, inference_states):
    initial = inference_states[task_id]
    assert catalog_platforms(TASKS[task_id]) == runtime_platforms(initial)
    for variant in "ABC":
        result = v2.evaluate(initial, deepcopy(initial), variant, [])
        assert not result["success"], (task_id, variant)
        assert any(not check["passed"] for check in result["checks"])


@pytest.mark.parametrize("task_id", sorted(LOW_TASKS))
def test_low_tasks_repeat_rule_on_independent_work(task_id, inference_states):
    state = inference_states[task_id]
    assert "rule_target" not in json.dumps(state)
    minimum = TASKS[task_id]["execution_profile"]["minimum_objects"]
    if task_id in FOUR_OBJECTS:
        assert len(state["items"]) >= max(4, minimum)
        assert len({row["id"] for row in state["items"]}) == len(state["items"])
    else:
        units = state["work_batch"]["units"]
        assert len(units) >= max(3, minimum)
        assert len({unit["id"] for unit in units}) == len(units)
        assert len({unit["state"]["seed"] for unit in units}) == len(units)
        inputs = [unit["state"]["board"] if task_id >= 66 else unit["state"]["source"] for unit in units]
        assert len({json.dumps(value, sort_keys=True) for value in inputs}) == len(units)


@pytest.mark.parametrize("task_id", MEDIUM)
def test_medium_documents_depend_on_real_independent_source_records(task_id, inference_states):
    state = inference_states[task_id]
    delivery = state["workset_delivery"]
    requests = delivery["requests"]
    current = max(requests, key=lambda row: row["revision"])
    assert len({request["revision"] for request in requests}) >= 2
    assert current["body"] and current["scope_ids"] and current["deadline"]
    recipient = next(row for row in delivery["directory"] if row["id"] == current["recipient"])
    assert recipient["address"] and recipient["name"]
    refs = delivery["references"]
    assert refs and len({row["id"] for row in refs}) == len(refs)
    assert len({row["object"] for row in refs}) == len(refs)
    for row in refs:
        assert row["detail"] and row["object_code"] and row["name"]
        if task_id in (69, 74):
            assert row["object"] == "practice-result"
            assert delivery["training_opening"] == state["board"]
        else:
            assert row["object"] in state["domain"]["objects"]
            assert row["scope"] in {scope["id"] for scope in state["scopes"]}
    assert delivery["draft"] is None and not delivery["publications"]
    # An empty document cannot stand in for business delivery, independently
    # of whether a task's native rule operation happens to leave no changes.
    checks = workset_delivery.checks(state, deepcopy(state), [])
    assert any(check["id"] == "delivery:published" and not check["passed"] for check in checks)


@pytest.mark.parametrize("task_id", HARD)
def test_hard_tasks_have_multiple_apps_and_real_source_data(task_id, inference_states):
    state = inference_states[task_id]
    assert len(runtime_platforms(state)) >= 2
    assert state["workflow"] and state["world"]["brief"]
    extension = state.get("cross_platform")
    if extension:
        assert extension["primary_app"] in runtime_platforms(state)
        assert "im" in runtime_platforms(state)
        assert not extension["receipts"] and not extension["messages"]
        people = {person["id"] for person in extension["people"]}
        for request in extension["requests"]:
            assert request["recipient"] in people
            assert request["body"] and request["scope"]
            file = request["attachment"]
            content = base64.b64decode(file["content"], validate=True)
            assert content and len(content) == file["size"]


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_demo_remains_original_rule_lesson_without_execution_plugins(task_id):
    from vic.lessons import episode_count
    spec = TASKS[task_id]
    assert spec['demo']['scope'] == 'rule_demonstration_only'
    assert spec['demo']['episode_count'] == episode_count(task_id)
    assert spec['demo']['objective'] != spec['assignment']
    assert spec['demo']['title'].startswith('规则示范：')
    assert spec['demo']['completion_checks']
    demo = v2.generate(task_id, 0, "demo")
    original_lesson = contextualize(initialize(business.generate(task_id, 0)), "demo")
    assert demo == original_lesson
    for field in ("work_batch", "workset_delivery", "cross_platform", "v2_atomic", "v2_worksets", "workflow"):
        assert field not in demo


def test_table_exactly_matches_catalog_without_rewriting_real_document(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tasks/v2").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/render_v2_catalog.py", tmp_path / "scripts/render_v2_catalog.py")
    shutil.copy2(ROOT / "tasks/v2/catalog.json", tmp_path / "tasks/v2/catalog.json")
    subprocess.run([sys.executable, str(tmp_path / "scripts/render_v2_catalog.py")], check=True)
    expected = (tmp_path / "VideoICL_75_web_tasks.md").read_text()
    actual = (ROOT / "VideoICL_75_web_tasks.md").read_text()
    assert actual == expected
    rows = re.findall(r"^\| (\d{3}) ", actual, flags=re.MULTILINE)
    assert len(rows) == 75 and {int(row) for row in rows} == set(TASKS)
