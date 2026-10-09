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


def test_physical_frames_are_visible_with_collision_mesh_rendering_disabled():
    e = TabletopDual(task_spec("F13"), render=False)
    try:
        for i in range(len(e.spec["fixtures"])):
            gid = e.sim.model.geom_name2id(f"fixture{i}")
            assert e.sim.model.geom_group[gid] == 1
            assert e.sim.model.geom_contype[gid] != 0
            assert e.sim.model.geom_conaffinity[gid] != 0
    finally: e.close()


def test_sweep_rejects_manual_delivery_and_sphere_rotation_does_not_change_fit():
    e = TabletopDual(task_spec("F39", "A"), render=False)
    try:
        state = e.snapshot()
        place = next(g for g in e.spec["goals"] if g["type"] == "place")
        swept = next(g for g in e.spec["goals"] if g["type"] == "swept")
        name = place["object"]
        zone = next(z for z in e.spec["zones"] if z["id"] == place["target"])
        radius = e.by_spec[name]["size"][0]
        state[name]["pos"] = np.array(zone["xy"]+[.8+radius])
        state[name]["pos"][0] += zone["half_size"][0]+.008-radius-.001
        assert e.predicate(place, state)
        state[name]["mat"] = np.array([[.70710678, -.70710678, 0.],
                                       [.70710678, .70710678, 0.], [0., 0., 1.]])
        assert e.predicate(place, state)
        assert not e.predicate(swept, state)
        e.events.add(("swept", name))  # Detector fixture, not an execution shortcut.
        assert e.predicate(swept, state)
        e._manually_handled.add(name)
        assert not e.predicate(swept, state)
    finally: e.close()


def test_shovel_requires_airborne_support_and_rejects_manual_delivery():
    e = TabletopDual(task_spec("F38", "A"), render=False)
    try:
        goal = next(g for g in e.spec["goals"] if g["type"] == "scooped")
        name = goal["object"]
        # A stationary coaster and an unheld blade do not establish transport.
        for _ in range(10): e.action()
        assert not e.predicate(goal, e.snapshot())
        # Even prior tool support cannot legitimise subsequent hand delivery.
        e.events.add(("scooped", name))
        assert e.predicate(goal, e.snapshot())
        e._manually_handled.add(name)
        assert not e.predicate(goal, e.snapshot())
        assert not e.score()["success"]
    finally: e.close()


def test_guided_ball_has_real_slope_and_direct_drop_is_not_guidance():
    e = TabletopDual(task_spec("F44", "A"), render=False)
    try:
        gid = e.sim.model.geom_name2id("fixture0")
        rotation = e.sim.data.geom_xmat[gid].reshape(3, 3)
        assert rotation[2, 0] < -.1  # Downhill toward the open-front catch trays.
        assert e.sim.model.geom_group[gid] == 1
        goal = next(g for g in e.spec["goals"] if g["type"] == "guided_roll")
        target = next(g["target"] for g in e.spec["goals"] if g["type"] == "nest")
        xy = e.snapshot()[target]["pos"][:2].tolist()
        # Test-only negative fixture: a dropped ball reaches the correct tray,
        # but never interacts with the ramp or any guide board.
        e.sim.data.set_joint_qpos(e.items["ball"].joints[0], xy+[.9, 1., 0., 0., 0.])
        e.sim.forward()
        for _ in range(15): e.action()
        state = e.snapshot()
        assert e.predicate(dict(type="nest", object="ball", target=target), state)
        assert not e.predicate(goal, state)
        assert not e.score()["success"]
        # Past guide contact cannot legitimise later direct hand transport.
        e.events.add(("guided_roll", "ball"))
        e._manually_handled.add("ball")
        assert not e.predicate(goal, state)
    finally: e.close()


def test_spring_clip_has_passive_hinge_and_direct_delivery_is_rejected():
    e = TabletopDual(task_spec("F43", "A"), render=False)
    try:
        clip = e.items["clip"]
        jid = e.sim.model.joint_name2id(clip.naming_prefix+"hinge")
        assert e.sim.model.jnt_stiffness[jid] > 0
        assert e.sim.model.jnt_limited[jid]
        goal = next(g for g in e.spec["goals"] if g["type"] == "clipped")
        name = goal["object"]
        zone = e.spec["zones"][0]
        # Test-only setup: correct delivery without using the tool is not a
        # successful clip task, even when the plate is stable in the rack.
        e.sim.data.set_joint_qpos(e.items[name].joints[0], zone["xy"]+[.825, 1., 0., 0., 0.])
        e.sim.forward()
        for _ in range(10): e.action()
        assert e.predicate(dict(type="place", object=name, target="rack"), e.snapshot())
        assert not e.predicate(goal, e.snapshot())
        assert not e.score()["success"]
        e.events.add(("clipped", name))
        e._manually_handled.add(name)
        assert not e.predicate(goal, e.snapshot())
    finally: e.close()


def test_real_bolt_blocks_lid_and_removal_allows_it_to_open():
    angles = []
    for removed in [False, True]:
        e = TabletopDual(task_spec("F46", "A"), render=False)
        try:
            latch = next(g for g in e.spec["goals"] if g["type"] == "bolt_engaged")
            assert e.predicate(latch, e.snapshot())
            if removed:
                # Test-only fixture, never used by the author controller.
                e.sim.data.set_joint_qpos(e.items["bolt"].joints[0], [-.25, -.25, .85, 1., 0., 0., 0.])
                e.sim.forward()
                assert not e.predicate(latch, e.snapshot())
            jid = e.sim.model.joint_name2id(e.items["cabinet"].naming_prefix+"hinge")
            # Apply identical test torque to the real hinge in both conditions.
            e.sim.data.qfrc_applied[e.sim.model.jnt_dofadr[jid]] = .3
            for _ in range(15): e.action()
            angles.append(e.snapshot()["cabinet"]["hinge_angle"])
            assert not e.score()["success"]
        finally: e.close()
    assert angles[0] < .06
    assert angles[1] > 1.2


@pytest.mark.parametrize("task", ["F16", "F42", "F43", "F44", "F46"])
def test_real_initial_positions_equal_across_rule_variants(task):
    snapshots = []
    for variant in "ABC":
        e = TabletopDual(task_spec(task, variant, 19), render=False)
        try:
            snapshots.append({k:v["pos"].tolist() for k,v in e.snapshot().items()})
            assert not e.score()["success"]
        finally: e.close()
    assert snapshots[0] == snapshots[1] == snapshots[2]


def test_hinged_display_is_connected_and_needs_a_real_support():
    e = TabletopDual(task_spec("F49", "B"), render=False)
    try:
        panel = e.items["panel1"]
        assert len(panel.joints) == 2  # Free base and attached hinge, not separate rigid tiles.
        joint = panel.naming_prefix+"hinge"
        e.sim.data.set_joint_qpos(joint, 1.15)  # Test fixture, never an author execution.
        e.sim.forward()
        for _ in range(40): e.action()
        state = e.snapshot()
        assert abs(state["panel1"]["hinge_angle"]-1.15) < .01
        angle = next(g for g in e.spec["goals"] if g["object"] == "panel1" and g["type"] == "hinge_angle")
        assert e.predicate(angle, state)
        support = next(g for g in e.spec["goals"] if g["type"] == "leaf_support")
        assert not e.predicate(support, state)
        assert not e.score()["success"]
    finally: e.close()


def test_flying_over_door_does_not_count_as_passing_through_it():
    e = TabletopDual(task_spec("F45"), render=False)
    try:
        goal = next(g for g in e.spec["goals"] if g["type"] == "passed_gate")
        x, y, _ = goal["apertures"][0]
        joint = e.items["long_bar"].joints[0]
        e.sim.data.set_joint_qpos(joint, [x, y, 1.45, 1., 0., 0., 0.])
        e.sim.forward(); e.action()
        assert not e.predicate(dict(goal, type="through_apertures"), e.snapshot())
        e.sim.data.set_joint_qpos(joint, [x+.25, y, 1.4, 1., 0., 0., 0.])
        e.sim.forward(); e.action()
        assert not e.predicate(goal, e.snapshot())
        # Positive detector fixture uses the real aperture before leaving it.
        e.sim.data.set_joint_qvel(joint, [0.]*6)
        e.sim.data.set_joint_qpos(joint, [x, y, .90, 1., 0., 0., 0.])
        e.sim.forward(); e.action()
        e.sim.data.set_joint_qvel(joint, [0.]*6)
        e.sim.data.set_joint_qpos(joint, [x+.25, y, .90, 1., 0., 0., 0.])
        e.sim.forward(); e.action()
        assert e.predicate(goal, e.snapshot())
    finally: e.close()


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


def test_extended_hook_has_separate_free_parts_and_direct_delivery_is_rejected():
    e = TabletopDual(task_spec("F42", "A"), render=False)
    try:
        # Mechanical assembly must be earned by contact; no equality weld.
        assert len(e.items["rod"].joints) == len(e.items["hook"].joints) == 1
        assert e.items["rod"].joints[0] != e.items["hook"].joints[0]
        assert e.sim.model.neq == 0
        goal = next(g for g in e.spec["goals"] if g["type"] == "extended_hook")
        name = goal["object"]
        zone = e.spec["zones"][0]
        # Test-only setup: correct final delivery without assembled-tool load
        # transfer must not earn this tool task.
        e.sim.data.set_joint_qpos(e.items[name].joints[0], zone["xy"]+[.808, 1., 0., 0., 0.])
        e.sim.forward()
        for _ in range(15): e.action()
        state = e.snapshot()
        assert e.predicate(dict(type="place", object=name, target="delivery"), state)
        assert not e.predicate(goal, state)
        assert not e.score()["success"]
    finally: e.close()


def test_author_restores_actual_wrist_even_when_command_counters_are_stale(tmp_path):
    from simulator.tabletop50.author import TabletopAuthor
    e = TabletopDual(task_spec("F46"), render=False)
    try:
        author = TabletopAuthor(e, tmp_path/"author")
        baseline = author.wrist_matrix(0)
        for _ in range(3): author.act(0, "PITCH_POS")
        assert np.linalg.norm(author.wrist_matrix(0)-baseline) > .2
        # A blocked wrist can diverge from accumulated command angles. Reset
        # just the controller's estimates; leave the physical robot untouched.
        author.pitches[0] = author.yaws[0] = 0.
        author.restore_wrist(0)
        assert np.linalg.norm(author.wrist_matrix(0)-baseline) < .055
    finally: e.close()


def test_mosaic_accepts_correct_cell_offsets_but_rejects_wrong_cells_and_hovering():
    e = TabletopDual(task_spec("F10", "B"), render=False)
    try:
        state = e.snapshot()
        goals = [g for g in e.spec["goals"] if g["object"].startswith("piece")]
        zones = {z["id"]: z for z in e.spec["zones"]}
        for g in goals:
            state[g["object"]]["pos"] = np.array(zones[g["target"]]["xy"]+[.812])+[.030, .020, 0.]
        assert all(e.predicate(g, state) for g in goals)
        g = goals[0]; pos = state[g["object"]]["pos"].copy()
        state[g["object"]]["pos"] = pos+[0., .13, 0.]
        assert not e.predicate(g, state)
        center = np.array(zones[g["target"]]["xy"])
        state[g["object"]]["pos"] = np.r_[center+[.060, 0.], .812]
        assert not e.predicate(g, state)
        state[g["object"]]["pos"] = np.r_[center, 1.02]
        assert not e.predicate(g, state)
    finally: e.close()
