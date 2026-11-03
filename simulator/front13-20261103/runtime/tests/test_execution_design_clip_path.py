import json
from pathlib import Path

import numpy as np

from videoicl_isaaclab.execution_design_clip_handover import public_rotation_poses, public_route_poses, rotation_clear
from videoicl_isaaclab.execution_design_local_pose_path import solve_local_pose_path


def test_native_endpoint_solution_cannot_certify_public_turn_at_joint_limit():
    fixture = json.loads((Path(__file__).parent / 'fixtures/e40_native_v9_ik_path.json').read_text())
    measured = fixture['native_context']
    failed = fixture['endpoint_only_failed_native_plan']
    assert all(r['kinematically_reachable'] for r in failed['ik'])
    assert min(r['minimum_joint_margin_rad'] for r in failed['ik']) > .05
    args = [measured[k] for k in ('position', 'rotation_task', 'jacobian', 'q', 'limits')]
    turn = public_rotation_poses(measured['position'], measured['rotation_task'], failed['rotation'])
    rejected = solve_local_pose_path(*args, turn)
    assert not rejected['feasible']
    assert rejected['rows'][-1]['reason'] == 'joint_margin'

    # The opposite real finger assignment has a continuous local branch.
    candidate = fixture['continuous_candidate']
    path = public_route_poses(measured['position'], measured['rotation_task'], candidate)
    accepted = solve_local_pose_path(*args, path)
    assert accepted['feasible'] and len(accepted['rows']) > 100
    assert min(r['minimum_joint_margin_rad'] for r in accepted['rows']) > .4
    assert max(r['maximum_joint_step_rad'] for r in accepted['rows']) <= .18 + 1e-8
    assert accepted['actuation_performed'] is False
    assert np.allclose(path[-1]['position'], candidate['position'], atol=.002)


def test_turn_endpoints_above_table_do_not_certify_the_intermediate_arc():
    from itertools import product
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    mesh = np.asarray(list(product((.18, .20), (-.01, .01), (-.01, .01))))
    position = np.array([0., 0., .9])
    target = _axis_rotation([0, 1, 0], np.pi)
    assert (mesh + position)[:, 2].min() > .8
    assert (mesh @ target.T + position)[:, 2].min() > .8
    assert not rotation_clear([mesh], position, np.eye(3),
                              [dict(rotation=target.tolist())], [], .8)
    assert rotation_clear([mesh], position + [0, 0, .2], np.eye(3),
                          [dict(rotation=target.tolist())], [], .8)


def test_open_finger_cannot_cross_the_target_before_the_grasp_closes():
    from itertools import product
    from videoicl_isaaclab.execution_design_clip_handover import route_clear
    box = np.asarray(list(product((-.005, .005), repeat=3)))
    meshes = [box + [0, 0, .04], box + [0, .03, 0], box + [0, -.03, 0]]
    target = np.array([0., 0., .9])
    clip = box * 2 + target
    args = (meshes, np.array([0., 1., 0.]), target, .020,
            np.array([0., .08, .9]), .9, [], .8)
    assert route_clear(*args)
    assert not route_clear(*args, contact_obstacles=[clip])
    # A vertical entry goes around the clip; the intended closing contact is
    # allowed only after the clip is physically between the open fingers.
    assert route_clear(meshes, np.array([0., 1., 0.]), target, .020,
                       np.array([0., 0., .98]), .98, [], .8,
                       contact_obstacles=[clip])


def test_handover_selects_actual_upper_wire_not_the_low_mouth_lip():
    from videoicl_isaaclab.execution_design_clip_handover import upper_handle_end_points, single_wall_end_points
    fixture = json.loads((Path(__file__).parent / 'fixtures/e40_native_settled_clip.json').read_text())
    geometry, mechanism = fixture['geometry'], fixture['mechanism']
    body, local, points = upper_handle_end_points(mechanism, geometry, .01712)
    assert body == 'JawNegative'
    assert np.allclose(local, geometry[body]['handle_point_body_local'])
    assert points[:, 2].min() > single_wall_end_points(mechanism, geometry, .01712)[:, 2].max() + .03
    # Both points remain on the source extrusion, ten millimetres either side
    # of its actual crossbar centre, rather than a made-up external grasp.
    recovered = (points - mechanism['body_pos_task'][body]) @ np.asarray(mechanism['body_mat_task'][body])
    assert np.allclose(recovered[:, 0], [-.010, .010], atol=1e-8)
    assert np.allclose(recovered[:, 1:], np.tile(local[1:], (2, 1)), atol=1e-8)
    # Selection follows the actual world frame, never a fixed jaw label.
    flipped = dict(mechanism, body_pos_task={k: [-v[0], v[1], -v[2]]
                   for k, v in mechanism['body_pos_task'].items()},
                   body_mat_task={k: (np.diag([-1., 1., -1.]) @ np.asarray(v)).tolist()
                   for k, v in mechanism['body_mat_task'].items()})
    assert upper_handle_end_points(flipped, geometry, .01712)[0] == 'JawPositive'


def test_failed_direction_tracking_stops_after_the_accepted_action():
    import pytest
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_clip_handover import checked_approach_move
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    position = np.array([-.1677, -.1342, .95]); actions = []
    def action(side, token, mm):
        actions.append((token, mm))
        position[:] += [-.0004, -.0034, -.000018]
    policy = SimpleNamespace(max_mm=12., tip=lambda side: position, act=action)
    with pytest.raises(ToolExecutionError, match='sideways'):
        checked_approach_move(policy, 'left', [-.1677, -.1342, .908], lambda: None)
    assert len(actions) == 1 and actions[0][0] == 'DOWN'


def test_native_contact_flags_do_not_certify_a_stable_handover(monkeypatch):
    import pytest
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_clip_handover as handover
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    # Native v14 retained both jaw contacts, but the free clip rotated 117.43
    # degrees after releasing the original hand. Stop at that first release.
    before = np.array([[-.00534916762, -.528381586, .848990083],
                       [.999985456, -.00243348442, .00478601828],
                       [-.000462840428, .849003434, .528387070]])
    after = np.array([[.09850737, .99153601, .08457323],
                      [.99107631, -.10541964, .08157475],
                      [.08979998, .07578281, -.99307247]])
    actions = []
    policy = SimpleNamespace(
        c=SimpleNamespace(),
        spec={'mechanisms': [{'id': 'clip1', 'mechanical_asset': {
            'physical_affordances': {'body_geometry': {}},
            'bounds': [[-.01712, -.02, 0.], [.01712, .02, .046]]}}]},
        mechanisms=lambda: {'clip1': {}},
        frame=lambda ref: (np.zeros(3), after if actions else before),
        act=lambda side, token: actions.append(token),
        held=lambda *args: True,
        require_held=lambda *args: None)
    monkeypatch.setattr(handover, 'single_wall_end_points', lambda *args: np.zeros((2, 3)))
    monkeypatch.setattr(handover, 'plan_pair', lambda *args: {})
    monkeypatch.setattr(handover, 'follow_pair', lambda *args: None)
    with pytest.raises(ToolExecutionError, match='rotated inside'):
        clip = {'mechanism': 'clip1', 'left': {'body': 'JawPositive', 'contact_body': 'clip1/positive_jaw'}}
        handover.handover_supported_clip(policy, clip, {}, 'right', 'left', {})
    assert actions == ['RELEASE']


def test_real_handle_opening_is_not_rejected_for_normal_articulated_motion(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_clip_handover as handover
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    actions=[];tcp=np.array([0.,0.,1.])
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=np.array([[.04,.04]])))
    policy=SimpleNamespace(a=SimpleNamespace(tcp_rotation_task=lambda side:np.eye(3),
        scene=SimpleNamespace(robots={'right':robot})),
        c=SimpleNamespace(ids={'right':(None,[0,1])}),
        frame=lambda ref:(np.zeros(3),_axis_rotation([1,0,0],np.deg2rad(30.)) if actions else np.eye(3)),
        tip=lambda side:tcp,stage=lambda name:None,max_mm=12.,
        require_held=lambda *args:None,held=lambda *args:bool(actions),
        clip_gap=lambda clip:(.022,np.zeros(3)),act=lambda side,token:actions.append(token))
    monkeypatch.setattr(handover,'refine_current_handle_grasp',lambda *args:dict(closure_m=.02))
    plan=dict(position=tcp,pregrasp=tcp,height=1.,orientation_height=1.,rotation=np.eye(3))
    handover.follow_pair(policy,{'expert':{'open_gap_m':.018}}, {},'right','left',{},np.zeros((2,3)),plan,'handle-squeeze')
    assert actions==['GRASP']


def test_partial_motion_reuses_same_public_goal_before_a_new_direction():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_clip_handover import finish_partial_translation
    waits=[];guards=[]
    controller=SimpleNamespace(action_feedback=lambda:dict(control_feedback={'right':
        dict(status='partial'if not waits else'reached',position_error_m=.006 if not waits else .001)}))
    policy=SimpleNamespace(_e40_table_supported_reference=True,c=controller,wait=lambda n:waits.append(n))
    finish_partial_translation(policy,'right',lambda:guards.append(True))
    assert waits==[1] and len(guards)==2
