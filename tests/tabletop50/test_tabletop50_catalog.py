import pytest
from simulator.tabletop50.catalog import IMPLEMENTED, task_spec, visible_world, world_sha256
from simulator.tabletop50.families import BY_ID, FAMILIES


def test_all_families_have_recording_cards_and_distinct_rules():
    assert list(BY_ID) == [f"F{i:02d}" for i in range(1, 51)]
    for f in FAMILIES:
        assert set(f["rules"]) == set("ABC")
        assert len(set(f["rules"].values())) == 3
        assert f["props"] and f["reset"] and f["camera_note"]
        assert f["human_recording_status"] == "not-recorded-not-user-validated"


@pytest.mark.parametrize("task", IMPLEMENTED)
@pytest.mark.parametrize("seed", [0, 1, 19, 101])
def test_rule_never_changes_visible_initial_world(task, seed):
    specs = [task_spec(task, rule, seed) for rule in "ABC"]
    assert visible_world(specs[0]) == visible_world(specs[1]) == visible_world(specs[2])
    assert len({world_sha256(s) for s in specs}) == 1
    assert len({str(s["goals"]) for s in specs}) == 3
    names = {o["id"] for o in specs[0]["objects"]}
    for s in specs:
        assert all(p["object"] in names for p in s["author_plan"])


def test_pending_design_is_not_silently_replaced_with_generic_pick_place():
    with pytest.raises(NotImplementedError): task_spec("F43")


@pytest.mark.parametrize("task", IMPLEMENTED)
def test_demo_and_inference_can_use_different_worlds(task):
    assert world_sha256(task_spec(task, "A", 0)) != world_sha256(task_spec(task, "A", 101))
