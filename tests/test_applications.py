import pytest
from vic import business, application_eval
from vic.schemas import Mutation
from vic_apps.domain import initialize
from vic_apps.store import ApplicationStore
from vic.games import expected, stopping_paths


def reference(state, variant):
    t = state["task_id"]
    if t >= 66:
        wanted = expected(t, variant, state)
        if t in (66, 70, 73):
            return [("mark", f"{r},{c}", "", []) for r, c in wanted]
        if t in (67, 72, 74, 75):
            return [("choose", f"{wanted[0]},{wanted[1]}", "", [])]
        if t == 68:
            return [("move", "", wanted, [])]
        if t == 71:
            r, c = state["candidates"][0]
            return [("fill", f"{r},{c}", str(wanted), [])]
        return [
            ("move", "", direction, []) for direction in stopping_paths(state)[variant]
        ] + [("stop", "", "", [])]
    effect = business.expected_effect(t, variant, state)
    if "outputs" in effect:
        return [("save", "target", effect["outputs"]["target"], [])]
    if "labels" in effect:
        return [
            ("label", key, value, [])
            for key, value in effect["labels"].items()
            if value
        ]
    if "order" in effect:
        return [("order", "", "", effect["order"])]
    if "members" in effect:
        return [("invite", "", "", effect["members"])]
    if "selection" in effect:
        return [("select", "", "", effect["selection"])]
    result = []
    for key, value in effect["actions"]:
        if t == 43 or (t == 65 and variant == "A"):
            result.append(("action", key, "检查" if t == 43 else "本地检查", []))
        result.append(("action", key, value, []))
    return result


@pytest.mark.parametrize("task_id", range(1, 76))
@pytest.mark.parametrize("seed", [0, 10001])
def test_application_all_variants(task_id, seed, tmp_path):
    initial = initialize(business.generate(task_id, seed))
    store = ApplicationStore(tmp_path)
    for variant in "ABC":
        store.initialize("run", initial)
        for index, (op, target, value, ids) in enumerate(reference(initial, variant)):
            store.mutate(
                "run",
                Mutation(
                    epoch=0,
                    action_id=str(index),
                    op=op,
                    target=target,
                    value=value,
                    ids=ids,
                ),
            )
        final = store.snapshot("run")
        events = store.events("run")
        clipboard = final.get("domain", {}).get("clipboard_history", [])
        result = application_eval.evaluate(
            initial,
            final,
            variant,
            events,
            clipboard[-1]["text"] if clipboard else None,
        )
        assert result["success"], (
            task_id,
            variant,
            [x for x in result["checks"] if not x["passed"]],
            result["violations"],
        )
        for other in set("ABC") - {variant}:
            assert not application_eval.evaluate(initial, final, other, events)[
                "success"
            ]


def test_bank_ledger_is_double_entry_and_not_only_action_log(tmp_path):
    initial = initialize(business.generate(56, 0))
    store = ApplicationStore(tmp_path)
    store.initialize("run", initial)
    for index, (op, target, value, ids) in enumerate(reference(initial, "A")):
        store.mutate(
            "run",
            Mutation(
                epoch=0,
                action_id=str(index),
                op=op,
                target=target,
                value=value,
                ids=ids,
            ),
        )
    final = store.snapshot("run")
    events = store.events("run")
    assert sum(x["cents"] for x in final["domain"]["ledger"]) == 0
    assert sum(final["domain"]["balances"].values()) == sum(
        initial["domain"]["balances"].values()
    )
    final["domain"]["balances"]["self"] += 1
    assert not application_eval.evaluate(initial, final, "A", events)["success"]


def test_message_wrong_recipient_fails(tmp_path):
    initial = initialize(business.generate(1, 0))
    store = ApplicationStore(tmp_path)
    store.initialize("run", initial)
    store.mutate(
        "run",
        Mutation(
            epoch=0,
            action_id="1",
            op="save",
            target="target",
            value=business.transform(1, 0, initial),
        ),
    )
    final = store.snapshot("run")
    final["domain"]["messages"][-1]["recipient"] = "wrong"
    assert not application_eval.evaluate(initial, final, "A", store.events("run"))[
        "success"
    ]


def test_invalid_code_is_a_normal_failure(tmp_path):
    initial = initialize(business.generate(58, 0))
    store = ApplicationStore(tmp_path)
    store.initialize("run", initial)
    store.mutate(
        "run",
        Mutation(epoch=0, action_id="1", op="save", target="target", value="print("),
    )
    result = application_eval.evaluate(
        initial, store.snapshot("run"), "A", store.events("run")
    )
    assert result["success"] is False and result["completion"] == 0


def test_object_identifiers_cannot_be_reused_from_demo():
    demo = initialize(business.generate(5, 0))
    evaluation = initialize(business.generate(5, 10001))
    assert not {x["id"] for x in demo["items"]} & {x["id"] for x in evaluation["items"]}


def test_title_punctuation_demonstration_contains_a_visible_change():
    state = business.generate(19, 0)
    assert business.transform(19, 0, state) != state["source"]["text"]
    assert all(ch not in business.transform(19, 0, state) for ch in ",!?")
