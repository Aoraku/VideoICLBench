import json
from pathlib import Path

import numpy as np
from types import SimpleNamespace
from scipy.spatial import ConvexHull

from videoicl_isaaclab.execution_design_clip_grasp import actual_handles, solve_finger_placement


def test_identical_pose_is_not_rejected_by_repeated_random_seed_order(monkeypatch):
    from videoicl_isaaclab import execution_design_drawer_ik_probe as probe
    from videoicl_isaaclab.execution_design_clip_handover import inspect_unique_poses
    calls = []
    def inspect(a, c, side, targets):
        assert len(targets) == 1
        calls.append(targets[0]['position'])
        return [dict(kinematically_reachable=True, minimum_joint_margin_rad=.128)]
    monkeypatch.setattr(probe, 'inspect', inspect)
    policy = SimpleNamespace(a=SimpleNamespace(c=object()))
    cache = {}
    result = inspect_unique_poses(policy, 'left', [[0, 0, .9], [0, 0, .9], [.1, 0, .9]], np.eye(3).tolist(), cache)
    assert len(calls) == 2 and result[0] is result[1]
    assert all(r['minimum_joint_margin_rad'] >= .05 for r in result)
    inspect_unique_poses(policy, 'left', [[0, 0, .9]], np.eye(3).tolist(), cache)
    assert len(calls) == 2


def test_support_hand_filter_rejects_overlap_and_intervening_finger():
    from itertools import product
    from videoicl_isaaclab.execution_design_clip_grasp import convex_meshes_clear, hand_approach_clear
    box = np.array(list(product((-.005, .005), repeat=3)))
    assert not convex_meshes_clear(box, box + [.004, 0, 0])
    assert not convex_meshes_clear(box, box + [.011, 0, 0])
    assert convex_meshes_clear(box, box + [.02, 0, 0])
    meshes = [box, box + [.03, 0, 0], box + [-.03, 0, 0]]
    plan = dict(position=[0, 0, 0], closure_m=.005)
    middle_obstacle = box + [0, 0, .04]
    # Both vertical endpoints are clear; the full sweep intersects a support pad.
    assert convex_meshes_clear(box, middle_obstacle)
    assert convex_meshes_clear(box + [0, 0, .08], middle_obstacle)
    assert not hand_approach_clear(meshes, np.array([1., 0, 0]), plan, [middle_obstacle], .08)
    assert hand_approach_clear(meshes, np.array([1., 0, 0]), plan, [box + [.15, 0, 0]], .08)


def test_side_entry_checks_whole_sweep_and_table_floor():
    from itertools import product
    from videoicl_isaaclab.execution_design_clip_handover import route_clear
    box = np.array(list(product((-.005, .005), repeat=3)))
    meshes = [box, box + [0, .025, 0], box + [0, -.025, 0]]
    args = (meshes, np.array([0., 1., 0.]), np.array([0., 0., .9]), .005,
            np.array([.08, 0., .9]), 1.05)
    assert route_clear(*args, [box + [.3, .3, .9]], .8)
    assert not route_clear(*args, [box + [.04, 0, .9]], .8)
    assert not route_clear(*args, [], .898)


def test_jaw_end_handover_points_use_each_measured_body_and_source_width():
    from videoicl_isaaclab.execution_design_clip_handover import jaw_end_points
    fixture = Path(__file__).parent / 'fixtures/e40_native_settled_clip.json'
    x = json.loads(fixture.read_text())
    points = jaw_end_points(x['mechanism'], x['geometry'], .01712)
    for point, name, sign in zip(points, ('JawPositive', 'JawNegative'), (1, -1)):
        p = np.array(x['mechanism']['body_pos_task'][name])
        r = np.array(x['mechanism']['body_mat_task'][name])
        local = r.T @ (point - p)
        assert abs(local[0] - sign * .01712 * .7) < 1e-7
        assert np.allclose(local[1:], x['geometry'][name]['jaw_point_body_local'][1:], atol=1e-7)


def test_preparatory_lift_requires_distinct_jaw_contacts_and_actual_spine_motion():
    import pytest
    from videoicl_isaaclab.execution_design_clip_grasp import lift_supported_clip
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor, ToolExecutionError
    policy = ToolAuthor.__new__(ToolAuthor)
    bodies = ['clip1/positive_jaw', 'clip1/negative_jaw']
    contacts = {frozenset((bodies[0], 'right_finger2')),
                frozenset((bodies[1], 'right_finger1'))}
    policy.snapshot = lambda: ({}, contacts)
    spine = np.array([0., 0., .805])
    source = dict(mechanism='clip1', body='Spine', contact_body='clip1/back',
                  local=[0., 0., .022], jaw_axis_local=[1., 0., 0.])
    policy.clip_ref = lambda *args: source
    policy.acquire = lambda ref, side: policy.require_held(ref, side)
    policy.frame = lambda ref: (spine.copy(), np.eye(3))
    policy.stage = lambda stage: None
    policy.tip = lambda side: np.array([0., 0., .827])
    def lift(side, target, guard):
        guard()
        spine[2] += .098
    policy.move = lift
    assert not policy.held(source, 'right')  # No native spine contacts.
    result = lift_supported_clip(policy, {}, dict(grasp_contacts=bodies), 'right')
    assert result['grasp_contacts'] == bodies and 'grasp_contacts' not in source
    # Strong jaw contacts alone cannot certify transport of the actual clip.
    policy.move = lambda side, target, guard: guard()
    with pytest.raises(ToolExecutionError, match='spine did not follow'):
        lift_supported_clip(policy, {}, dict(grasp_contacts=bodies), 'right')
    contacts.clear()
    contacts.update(frozenset((bodies[0], f'right_finger{i}')) for i in (1, 2))
    with pytest.raises(ToolExecutionError, match='Actual grip lost'):
        lift_supported_clip(policy, {}, dict(grasp_contacts=bodies), 'right')


def test_real_engineering_dispatch_reaches_supported_clip_grasp(monkeypatch):
    from videoicl_isaaclab import execution_design_reference as route
    from videoicl_isaaclab import execution_design_clip_grasp as grasp
    from videoicl_isaaclab.execution_design import REVISION_V3, source_sha256
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor
    spec = dict(id='E40', variant='A', execution_design=dict(
        revision=REVISION_V3, source_sha256=source_sha256(REVISION_V3)))
    author = SimpleNamespace(scene=SimpleNamespace(spec=spec), control_report={},
                             c=SimpleNamespace(steps=0), smooth=False)
    seen = []
    def supported(policy, clip, ref, side):
        assert policy.a.control_report['engineering_reference_only']
        assert not getattr(policy.a, '_execution_design_reference_authorized', False)
        seen.append(side)
    monkeypatch.setattr(grasp, 'squeeze_supported', supported)
    def tool(a):
        policy = ToolAuthor.__new__(ToolAuthor)
        policy.a, policy.spec, policy.task = a, spec, 'E40'
        policy.squeeze({}, {}, 'left')
        return {'attempt_only': True}
    monkeypatch.setattr(route, 'solve_tool', tool)
    result = route.solve_execution_reference(author)
    assert seen == ['left'] and result['physics_success_not_asserted']


def test_formal_clip_does_not_enter_engineering_two_hand_route(monkeypatch):
    from videoicl_isaaclab import execution_design_clip_grasp as grasp
    from videoicl_isaaclab.execution_design import REVISION_V3
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor
    import pytest
    monkeypatch.setattr(grasp, 'squeeze_supported', lambda *a: pytest.fail('Formal route changed'))
    policy = ToolAuthor.__new__(ToolAuthor)
    policy.a = SimpleNamespace(control_report={})
    policy.task, policy.spec = 'E40', dict(execution_design=dict(revision=REVISION_V3))
    acquired = []
    policy.acquire = lambda ref, side: acquired.append(side)
    policy.clip_gap = lambda clip: (.03, None)
    policy.squeeze({'expert': {'open_gap_m': .018}}, {}, 'right')
    assert acquired == ['right']


def test_clip_edges_uses_actual_handover_gripper_for_transport_and_release():
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor
    from videoicl_isaaclab.execution_design import REVISION_V3
    policy = ToolAuthor.__new__(ToolAuthor)
    policy.index = 0
    policy.a = SimpleNamespace(control_report={'engineering_reference_only': True})
    policy.s = {'clips': {n: {'expert': {'insert_direction_task': [0, 0, -1]}} for n in ('one', 'two')}}
    policy.spec = dict(execution_design=dict(revision=REVISION_V3), zones=[
        dict(id=n, edge_point=[0, 0, .8], support='paper') for n in ('circle', 'cross')])
    policy.stage = lambda *args: None
    policy.clip_ref = lambda clip, key: {'contact_body': 'clip/back'}
    policy.point = lambda ref: np.array([0., 0., .8])
    policy.tip = lambda side: np.array([0., 0., .8 if side == 'right' else 1.])
    requests, transports, releases = [], [], []
    def squeeze(clip, ref, side):
        requests.append(side)
        return 'right'  # Actual hand after the second handover.
    policy.squeeze = squeeze
    policy.clip_move = lambda clip, ref, side, point: transports.append(side)
    policy.release = lambda ref, side: releases.append(side)
    policy.wait = lambda *args: None
    policy.clip_contact = lambda *args: True
    policy.move = lambda *args: None
    policy.clip_edges()
    assert requests == ['left', 'left']
    assert transports == ['right'] * 4 and releases == ['right'] * 2


def recorded_geometry():
    base = Path(__file__).parent / 'fixtures'
    clip = json.loads((base / 'e40_native_settled_clip.json').read_text())
    fingers = json.loads((base / 'cutlery_native_finger_section.json').read_text())
    points, center, jaw = actual_handles(clip['mechanism'], clip['geometry'])
    tcp, rotation = np.array(fingers['tcp']), np.array(fingers['rotation'])
    meshes = [(np.array(m) - tcp) @ rotation for m in [fingers['palm'], *fingers['fingers']]]
    local_jaw = meshes[1].mean(0) - meshes[2].mean(0)
    local_jaw /= np.linalg.norm(local_jaw)
    forward = (meshes[1].mean(0) + meshes[2].mean(0)) / 2 - meshes[0].mean(0)
    forward -= local_jaw * (forward @ local_jaw)
    forward /= np.linalg.norm(forward)
    source = np.column_stack((local_jaw, forward, np.cross(local_jaw, forward)))
    up = np.array([0., 0., 1.])
    v = up - jaw * (up @ jaw)
    v /= np.linalg.norm(v)
    u = np.cross(jaw, v)
    candidates = []
    for degrees in range(0, 360, 15):
        direction = np.cos(np.deg2rad(degrees)) * v + np.sin(np.deg2rad(degrees)) * u
        target = np.column_stack((jaw, direction, np.cross(jaw, direction))) @ source.T
        candidates.append([mesh @ target.T for mesh in meshes])
    return points, center, jaw, candidates


def test_actual_pair_uses_both_articulated_body_frames():
    points, center, jaw, _ = recorded_geometry()
    assert np.isclose(points[0, 2], .80300003, atol=1e-6)
    assert np.isclose(points[1, 2], .84551486, atol=1e-6)
    assert np.allclose(center, points.mean(0))
    assert np.isclose(jaw[2], .79765009, atol=1e-6)


def test_recorded_tabletop_handle_centers_have_no_table_clear_pad_candidate():
    points, _, jaw, rotations = recorded_geometry()
    assert not any(solve_finger_placement(points, m[0], m[1:], jaw, .8)
                   for m in rotations)


def test_lifted_candidate_satisfies_each_pad_hull_and_floor_independently():
    # Hypothetical lift only tests geometry. It neither moves the native clip
    # nor establishes that a robot can perform the required preparatory lift.
    points, _, jaw, rotations = recorded_geometry()
    found = 0
    for meshes in rotations:
        for row in solve_finger_placement(points + [0, 0, .03], meshes[0], meshes[1:], jaw, .8):
            found += 1
            shift = np.array(row['tcp_translation'])
            c = row['closure_m']
            assert meshes[0][:, 2].min() + shift[2] >= .8002 - 1e-9
            for point, mesh, sign in zip(row['ordered_handles'], meshes[1:], (-1., 1.)):
                assert mesh[:, 2].min() + shift[2] >= .8002 - 1e-9
                actual = mesh + shift + sign * c * jaw
                assert actual[:, 2].min() >= .8002 - 1e-9
                planes = ConvexHull(actual).equations
                assert np.max(planes[:, :3] @ np.array(point) + planes[:, 3]) <= -.0002 + 1e-9
            assert row['native_grasp_verified'] is False
    assert found > 0


def test_feasible_measured_grasp_does_not_jump_to_another_lp_extreme():
    points, _, jaw, rotations = recorded_geometry()
    points = points + [0, 0, .03]
    for meshes in rotations:
        rows = solve_finger_placement(points, meshes[0], meshes[1:], jaw, .8)
        if not rows:
            continue
        preferred = np.asarray(rows[0]['tcp_translation'])
        refined = solve_finger_placement(points, meshes[0], meshes[1:], jaw, .8,
                                         preferred_translation=preferred)
        assert refined
        assert min(np.linalg.norm(np.asarray(r['tcp_translation'])-preferred) for r in refined) < 1e-8
        return
    raise AssertionError('Recorded lifted clip must contain a feasible measured candidate')


def test_handle_candidate_uses_inward_pad_not_deep_toe_or_back():
    from itertools import product
    box = np.array(list(product((-.005, .005), repeat=3)))
    fingers = [box + [0., .035, 0.], box + [0., -.035, 0.]]
    points = np.array([[0., .01, .9], [0., -.01, .9]])
    jaw = np.array([0., 1., 0.])
    rows = solve_finger_placement(points, box, fingers, jaw, .8, pad_depth_m=.001)
    assert rows
    for row in rows:
        for point, mesh, sign in zip(row['ordered_handles'], fingers, (-1., 1.)):
            moved = mesh + row['tcp_translation'] + sign * row['closure_m'] * jaw
            planes = ConvexHull(moved).equations
            plane = planes[np.argmax(planes[:, :3] @ (sign * jaw))]
            depth = -(plane[:3] @ point + plane[3])
            assert .0002 - 1e-9 <= depth <= .001 + 1e-9
    # A slanted toe can contain the points but supplies no inward pad face.
    angle = np.deg2rad(30.)
    rotation = np.array([[1., 0., 0.], [0., np.cos(angle), -np.sin(angle)],
                         [0., np.sin(angle), np.cos(angle)]])
    assert not solve_finger_placement(points, box, [m @ rotation.T for m in fingers],
                                      jaw, .8, pad_depth_m=.001)


def test_articulated_support_can_change_contact_pair_but_cannot_lose_a_finger():
    import pytest
    from videoicl_isaaclab.execution_design_clip_handover import require_supported_clip
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor, ToolExecutionError
    policy = ToolAuthor.__new__(ToolAuthor)
    positive, negative = 'clip1/positive_jaw', 'clip1/negative_jaw'
    contacts = {frozenset((positive, 'left_finger2')), frozenset((negative, 'left_finger1'))}
    policy.snapshot = lambda: ({}, contacts)
    wall = dict(contact_body=positive)
    handles = dict(grasp_contacts=[positive, negative])
    assert not policy.held(wall, 'left')
    require_supported_clip(policy, wall, handles, 'left')
    contacts.remove(frozenset((negative, 'left_finger1')))
    with pytest.raises(ToolExecutionError, match='Actual grip lost'):
        require_supported_clip(policy, wall, handles, 'left')


def test_closing_readiness_checks_actual_pose_instead_of_nearby_feasible_pose():
    from itertools import product
    box = np.array(list(product((-.005, .005), repeat=3)))
    fingers = [box + [0., .035, 0.], box + [0., -.035, 0.]]
    points = np.array([[0., .01, .9], [0., -.01, .9]])
    jaw = np.array([0., 1., 0.])
    candidate = solve_finger_placement(points, box, fingers, jaw, .8, pad_depth_m=.001)[0]
    position = np.asarray(candidate['tcp_translation'])
    rows = solve_finger_placement(points, box, fingers, jaw, .8,
                                  pad_depth_m=.001, fixed_translation=position)
    assert rows and all(np.array_equal(r['tcp_translation'], position) for r in rows)
    # Sub-millimetre TCP distance alone cannot certify an edge-of-pad grip.
    shifted = position + [.0008, 0., 0.]
    edge_points = points + [.0047, 0., 0.]
    assert solve_finger_placement(edge_points, box, fingers, jaw, .8, pad_depth_m=.001)
    assert not solve_finger_placement(edge_points, box, fingers, jaw, .8,
                                      pad_depth_m=.001, fixed_translation=shifted - [.0016, 0., 0.])


def test_clip_motion_uses_actual_material_feedback_without_extra_tcp_waypoints():
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor
    policy=ToolAuthor.__new__(ToolAuthor);policy._e40_table_supported_reference=True
    position=np.array([0.,0.,.84]);commands=[]
    policy.clip_gap=lambda clip:(.02,position.copy())
    policy.require_held=lambda *args:None
    def act(side,token,mm):
        commands.append((token,mm));i={'FWD':0,'BACK':0,'LEFT':1,'RIGHT':1,'UP':2,'DOWN':2}[token]
        position[i]+=(1 if token in('FWD','LEFT','UP')else -1)*mm/1000.*.95
    policy.act=act
    policy.move=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('Extra TCP waypoint'))
    goal=np.array([.025,.013,.84]);policy.clip_move({}, {}, 'left',goal)
    assert max(abs(goal-position))<.002 and len(commands)<=8


def test_clip_actual_stall_ends_without_hundreds_of_empty_tcp_actions():
    import pytest
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor,ToolExecutionError
    policy=ToolAuthor.__new__(ToolAuthor);policy._e40_table_supported_reference=True
    commands=[];policy.clip_gap=lambda clip:(.02,np.array([0.,0.,.84]))
    policy.require_held=lambda *args:None;policy.act=lambda *args,**kwargs:commands.append((args,kwargs))
    with pytest.raises(ToolExecutionError,match='no net physical progress'):
        policy.clip_move({}, {}, 'left',[.025,.013,.84])
    assert len(commands)<=8
