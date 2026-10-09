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


def test_tray_handle_does_not_count_as_container_interior():
    e = TabletopDual(task_spec("F35"), render=False)
    try:
        state = e.snapshot()
        tray = state["carrier"]
        # Enlarged bounding box includes grip tabs; the usable cavity does not.
        state["part0_0"]["pos"] = tray["pos"]+tray["mat"]@np.array([0., .135, 0.])
        assert not e.predicate(dict(type="nest", object="part0_0", target="carrier"), state)
    finally: e.close()


def test_drop_is_caught_by_box_but_does_not_count_as_pouring():
    e = TabletopDual(task_spec("F40"), render=False)
    try:
        xy = e.snapshot()["bin0"]["pos"][:2].tolist()
        # Initialise a negative episode with one piece released above the box.
        # This setup is test-only, never part of an author execution.
        e.sim.data.set_joint_qpos(e.items["wood0"].joints[0], xy+[.91, 1., 0., 0., 0.])
        e.sim.forward()
        for _ in range(20): e.action()
        state = e.snapshot()
        assert state["wood0"]["pos"][2] > .82
        assert e.predicate(dict(type="nest", object="wood0", target="bin0"), state)
        assert not e.predicate(dict(type="poured", object="wood0", target="cup"), state)
    finally: e.close()


def test_classification_follows_marked_boxes_after_boxes_move():
    e = TabletopDual(task_spec("F07", "A"), render=False)
    try:
        state = e.snapshot()
        centers = {}
        for i in range(2):
            centers[i] = state[f"bin{i}"]["pos"][:2]+[.035, 0.]
            e.sim.data.set_joint_qpos(e.items[f"bin{i}"].joints[0],
                centers[i].tolist()+[.825, 1., 0., 0., 0.])
        for shape in range(2):
            for color in range(2):
                name = f"part{shape}_{color}"
                xy = centers[color]+[0., -.032+shape*.064]
                z = .808+e.by_spec[name]["size"][2]
                e.sim.data.set_joint_qpos(e.items[name].joints[0], xy.tolist()+[z, 1., 0., 0., 0.])
        e.sim.forward()
        for _ in range(20): e.action()
        assert e.score()["success"]
        # Correct box identity still matters after dropping coordinate quotas.
        e.sim.data.set_joint_qpos(e.items["part0_0"].joints[0],
            (centers[1]+[0., -.032]).tolist()+[.832, 1., 0., 0., 0.])
        e.sim.forward()
        for _ in range(20): e.action()
        assert not e.score()["success"]
    finally: e.close()


def test_double_hole_accepts_varied_depth_but_rejects_partial_threading():
    e = TabletopDual(task_spec("F13"), render=False)
    try:
        state = e.snapshot()
        goal = e.spec["goals"][0]
        dx = goal["apertures"][0][0]-.07
        y = goal["apertures"][0][1]
        rod = state[goal["object"]]
        rod["mat"] = np.eye(3)
        for x in [.10, .16, .22]:
            rod["pos"] = np.array([x+dx, y, .89])
            assert e.predicate(goal, state)
        rod["pos"] = np.array([.05+dx, y, .89])
        assert not e.predicate(goal, state)
        rod["pos"] = np.array([.16+dx, y, .94])
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
