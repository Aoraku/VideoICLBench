import copy
import json
import pytest
from vic.business import generate, expected_effect, apply_mutation, evaluate
from vic.catalog import catalog


def perform(initial, variant):
    state = copy.deepcopy(initial)
    effect = expected_effect(initial["task_id"], variant, initial)
    events = []

    def action(op, target="", value="", ids=None):
        nonlocal state
        e = dict(op=op, target=target, value=value, ids=ids or [])
        state = apply_mutation(state, **e)
        events.append(e)

    key = next(iter(effect))
    wanted = effect[key]
    if key == "outputs":
        action("save", "target", wanted["target"])
    elif key == "labels":
        for i, label in wanted.items():
            if label:
                action("label", i, label)
    elif key == "selection":
        action("select", ids=wanted)
    elif key == "members":
        action("invite", ids=wanted)
    elif key == "order":
        action("order", ids=wanted)
    else:
        for i, op in wanted:
            if initial["task_id"] == 43:
                action("action", i, "检查")
            if initial["task_id"] == 65 and variant == "A":
                action("action", i, "本地检查")
            action("action", i, op)
    return state, events


def test_inventory():
    tasks = catalog()["tasks"]
    assert len(tasks) == 100
    assert {t["id"] for t in tasks} == set(range(1, 101))
    assert all(set(t["variants"]) == set("ABC") for t in tasks)


@pytest.mark.parametrize("task_id", range(1, 66))
@pytest.mark.parametrize("seed", [0, 11, 1000, 10001, 98412])
def test_counterfactuals_and_seed_reproducibility(task_id, seed):
    state = generate(task_id, seed)
    assert state == generate(task_id, seed)
    assert "variant" not in state and "rules" not in state
    expected = [
        json.dumps(expected_effect(task_id, v, state), sort_keys=True) for v in "ABC"
    ]
    assert len(set(expected)) == 3
    for v in "ABC":
        final, events = perform(state, v)
        assert evaluate(state, final, v, events)["success"]
        for wrong in set("ABC") - {v}:
            assert not evaluate(state, final, wrong, events)["success"]
    assert not evaluate(state, state, "A", [])["success"]


def test_fixed_expected_examples_not_derived_from_oracle():
    s = generate(1, 1000)
    final = apply_mutation(s, "save", "target", s["source"]["text"].lower())
    assert not evaluate(s, final, "A", [dict(op="save")])["success"]
    s["source"]["text"] = "hELLO wORLD"
    assert expected_effect(1, "A", s) == {"outputs": {"target": "hELLO WORLD"}}
    assert expected_effect(1, "B", s) == {"outputs": {"target": "Hello world"}}
    assert expected_effect(1, "C", s) == {"outputs": {"target": "Hello World"}}


def test_extra_action_and_order_violation():
    s = generate(43, 1000)
    state, events = perform(s, "A")
    assert evaluate(s, state, "A", events)["success"]
    assert not evaluate(s, state, "A", [e for e in events if e["value"] != "检查"])[
        "success"
    ]
    state = apply_mutation(state, "action", events[-1]["target"], "保存")
    assert not evaluate(s, state, "A", events)["success"]


def test_invalid_object_and_duplicate_order():
    s = generate(12, 1000)
    with pytest.raises(ValueError):
        apply_mutation(s, "order", ids=[s["items"][0]["id"]] * 6)
    with pytest.raises(ValueError):
        apply_mutation(generate(5, 1000), "label", "not-an-object", "蓝色")


def test_template_variables_preserve_semantics():
    s = generate(60, 1000)
    for v in "ABC":
        namespace = {}
        exec(expected_effect(60, v, s)["outputs"]["target"], namespace)
        name = {"A": "x_total", "B": "total_v", "C": "TOTAL"}[v]
        assert namespace[name] == 1008


@pytest.mark.parametrize(
    "task_id", [1, 2, 3, 4, 17, 18, 19, 20, 21, 36, 37, 44, 45, 46, 58, 59, 60]
)
def test_demonstration_answers_do_not_copy_to_eval(task_id):
    demo = generate(task_id, 0)
    query = generate(task_id, 1000)
    for v in "ABC":
        assert expected_effect(task_id, v, demo) != expected_effect(task_id, v, query)
