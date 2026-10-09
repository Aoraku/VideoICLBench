import numpy as np
import pytest

pytest.importorskip("robosuite")
from simulator.tabletop50.catalog import task_spec
from simulator.tabletop50.environment import TabletopDual


def test_triangle_parts_do_not_walk_off_an_idle_table():
    e = TabletopDual(task_spec("F08"), render=False)
    try:
        initial = e.snapshot()
        for _ in range(20): e.action()
        final = e.snapshot()
        for name in ("piece0_2", "piece1_2", "piece2_2"):
            assert np.linalg.norm(final[name]["pos"][:2]-initial[name]["pos"][:2]) < .003
        assert not e.score()["success"]
    finally: e.close()


def test_real_initial_positions_equal_across_rule_variants():
    snapshots = []
    for variant in "ABC":
        e = TabletopDual(task_spec("F16", variant, 19), render=False)
        try:
            snapshots.append({k:v["pos"].tolist() for k,v in e.snapshot().items()})
            assert not e.score()["success"]
        finally: e.close()
    assert snapshots[0] == snapshots[1] == snapshots[2]


def test_cover_cannot_pass_when_held_above_box():
    e = TabletopDual(task_spec("F23"), render=False)
    try:
        state = e.snapshot()
        goal = next(g for g in e.spec["goals"] if g["type"] == "cover")
        assert e.predicate(goal, state)
        state[goal["object"]]["pos"][2] += .05
        assert not e.predicate(goal, state)
    finally: e.close()


def test_length_completion_relations_are_exclusive():
    e = TabletopDual(task_spec("F33"), render=False)
    try:
        state = e.snapshot()
        for row, spare in enumerate([4, 3, 2]):
            ref = state[f"ref{row}"]
            half = e.by_spec[f"ref{row}"]["size"][0]
            spare_half = e.by_spec[f"spare{spare}"]["size"][0]
            state[f"spare{spare}"]["pos"] = ref["pos"]+np.array([half+spare_half, 0., 0.])
        goals = [next(g for g in task_spec("F33", v)["goals"] if g["type"] == "row_lengths") for v in "ABC"]
        assert [e.predicate(g, state) for g in goals] == [True, False, False]
        # A second equal-length solution should also be accepted.
        state = e.snapshot()
        for row, spare in enumerate([2, 1, 0]):
            ref = state[f"ref{row}"]
            half = e.by_spec[f"ref{row}"]["size"][0]+e.by_spec[f"spare{spare}"]["size"][0]
            state[f"spare{spare}"]["pos"] = ref["pos"]+np.array([half, 0., 0.])
        assert e.predicate(goals[0], state)
    finally: e.close()
