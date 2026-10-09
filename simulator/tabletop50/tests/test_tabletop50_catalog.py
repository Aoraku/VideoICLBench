import pytest
from simulator.tabletop50.catalog import IMPLEMENTED, task_spec, visible_world, world_sha256
from simulator.tabletop50.families import BY_ID, FAMILIES


def test_size_kits_use_real_shapes_without_fixed_colour_size_mapping():
    colour_mappings = set()
    for seed in range(8):
        spec = task_spec("F26", "A", seed)
        objects = {o["id"]: o for o in spec["objects"]}
        assert len(spec["zones"]) == 3
        assert all(g["type"] == "on_mat" for g in spec["goals"])
        for rank in range(3):
            bar = objects[f"part1_{rank}"]
            cylinder = objects[f"part2_{rank}"]
            assert bar["size"][0] > 3 * bar["size"][1]
            assert cylinder["size"][2] > cylinder["size"][0]
        colour_mappings.add(tuple(tuple(objects[f"part{group}_{rank}"]["rgba"])
                                  for group in range(3) for rank in range(3)))
    assert len(colour_mappings) > 1


def test_top_up_has_ten_visible_four_centimetre_blocks_and_only_count_goals():
    for variant, expected in zip("ABC", [[3, 4, 3], [4, 3, 3], [3, 3, 4]]):
        spec = task_spec("F27", variant)
        blocks = [o for o in spec["objects"] if o["id"].startswith(("initial", "spare"))]
        assert len(blocks) == 10
        assert all(o["size"] == [.02, .02, .02] for o in blocks)
        assert [g["count"] for g in spec["goals"]] == expected
        assert all(g["type"] == "count_in" for g in spec["goals"])


def test_all_families_have_recording_cards_and_distinct_rules():
    assert list(BY_ID) == [f"F{i:02d}" for i in range(1, 51)]
    for f in FAMILIES:
        assert set(f["rules"]) == set("ABC")
        assert len(set(f["rules"].values())) == 3
        assert f["props"] and f["reset"] and f["camera_note"]
        assert f["human_recording_status"] == "not-recorded-not-user-validated"


def test_contents_exchange_is_judged_by_container_membership():
    for variant in "ABC":
        spec = task_spec("F18", variant)
        assert len(spec["goals"]) == 4
        assert all(g["type"] == "nest" for g in spec["goals"])
        expected = {f"piece{i}_{shape}": f"bin{1-i if variant == 'A' or shape == 'ABC'.index(variant)-1 else i}"
                    for i in range(2) for shape in range(2)}
        assert {g["object"]: g["target"] for g in spec["goals"]} == expected
        assert len(spec["zones"]) == 4  # Visible staging pads, not a forced route.


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


@pytest.mark.parametrize("task", ["F42"])
def test_missing_recipe_is_not_silently_replaced_with_generic_pick_place(task, monkeypatch):
    # All 50 now have recipes. Simulate a missing future implementation to
    # preserve the explicit refusal policy rather than a generic fallback.
    monkeypatch.setitem(BY_ID[task], "runtime_recipe", None)
    with pytest.raises(NotImplementedError): task_spec(task)


@pytest.mark.parametrize("task", IMPLEMENTED)
def test_demo_and_inference_can_use_different_worlds(task):
    assert world_sha256(task_spec(task, "A", 0)) != world_sha256(task_spec(task, "A", 101))


def test_layout_randomisation_does_not_translate_container_local_goals():
    specs = [task_spec("F35", "A", seed) for seed in [0, 19, 101]]
    local = [[g["xy"] for g in s["goals"] if g["type"] == "local_position"] for s in specs]
    assert local == [[[0., -.075], [0., 0.], [0., .075]]]*3


def test_prop_colours_do_not_share_mutable_catalogue_state():
    first = task_spec("F02")
    expected = visible_world(task_spec("F02"))
    first["objects"][0]["rgba"][0] = 0.
    task_spec("F40")  # Its transparent cup must not turn all white props transparent.
    assert visible_world(task_spec("F02")) == expected
    assert all(o["rgba"][3] == 1. for o in task_spec("F40")["objects"] if o["id"].startswith("bin"))


def test_mosaic_rules_are_rigid_transforms_of_a_square_reference():
    import numpy as np
    transforms = {"A": np.eye(2), "B": np.array([[0., 1.], [-1., 0.]]),
                  "C": np.array([[1., 0.], [0., -1.]])}
    for seed in [0, 19, 37]:
        for variant, transform in transforms.items():
            spec = task_spec("F10", variant, seed)
            refs = [o for o in spec["objects"] if o["id"].startswith("ref")]
            pieces = {o["id"]: o for o in spec["objects"] if o["id"].startswith("piece")}
            ref_center = np.mean([o["xy"] for o in refs], axis=0)
            targets = [g for g in spec["goals"] if g["object"].startswith("piece")]
            zones = {z["id"]: z for z in spec["zones"]}
            target_center = np.mean([zones[g["target"]]["xy"] for g in targets], axis=0)
            assert len({round(o["xy"][0], 6) for o in refs}) == 2
            assert len({round(o["xy"][1], 6) for o in refs}) == 2
            for goal in targets:
                reference = next(o for o in refs if o["rgba"] == pieces[goal["object"]]["rgba"])
                expected = target_center+transform@(np.array(reference["xy"])-ref_center)
                assert np.allclose(zones[goal["target"]]["xy"], expected)
            assert len(spec["fixtures"]) == 14


def test_vacancy_rule_labels_follow_first_person_left_and_right():
    # The fixed FPV camera faces +X: increasing world Y is screen left.
    for seed in [0, 19, 37]:
        for variant in "ABC":
            spec = task_spec("F16", variant, seed)
            objects = {o["id"]: o for o in spec["objects"]}
            initial = [o["id"] for o in sorted(objects.values(), key=lambda o: -o["xy"][1])]
            final = [g["object"] for g in sorted(spec["goals"], key=lambda g: -g["xy"][1])]
            expected = {"A": initial[-1:]+initial[:-1], "B": initial[1:]+initial[:1], "C": initial[::-1]}
            assert final == expected[variant]


def test_reference_row_and_extraction_labels_follow_first_person_direction():
    for seed in [0, 19, 37]:
        for variant in "ABC":
            spec = task_spec("F28", variant, seed)
            objects = {o["id"]: o for o in spec["objects"]}
            refs = sorted((o for o in objects.values() if o["id"].startswith("ref")), key=lambda o: -o["xy"][1])
            initial = [o["rgba"] for o in refs]
            goals = sorted((g for g in spec["goals"] if g["object"].startswith("piece")), key=lambda g: -g["xy"][1])
            final = [objects[g["object"]]["rgba"] for g in goals]
            expected = {"A": initial, "B": initial[::-1], "C": initial[-1:]+initial[:-1]}
            assert final == expected[variant]
            spec = task_spec("F24", variant, seed)
            selected = next(p["object"] for p in spec["author_plan"] if p["object"].startswith("piece"))
            pieces = sorted((o for o in spec["objects"] if o["id"].startswith("piece")), key=lambda o: -o["xy"][1])
            assert selected == pieces[{"A": 2, "B": 1, "C": 0}[variant]]["id"]
