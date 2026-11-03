import numpy as np
import pytest

from videoicl_isaaclab.execution_design_ring_reference import release_target, track_center


def test_recorded_ring_cannot_hit_post_tip_at_release_height():
    # Source I4201 ring and board geometry, with recorded thin-rim grasp offset.
    tip = np.array([.14000034, -.12, .86401002])
    goal, radial = release_target(tip, .00321, .00672, .887, .005136, .0026)
    assert np.allclose(goal[:2], tip[:2])
    assert goal[2] - .00321 >= tip[2] + .004
    assert goal[2] + .00672 >= .887
    assert radial < .005136 - .0026


def test_material_center_feedback_corrects_recorded_seven_mm_bias():
    target = np.array([.14, -.12, .88])
    center = np.array([.1329, -.1228, .90])
    moves = []
    labels = {'FWD':(0,1), 'BACK':(0,-1), 'LEFT':(1,1),
              'RIGHT':(1,-1), 'UP':(2,1), 'DOWN':(2,-1)}
    def act(token, mm):
        axis, sign = labels[token]
        center[axis] += sign * mm / 1000.
        if axis == 2:
            center[0] += .00015  # Re-measure real grasp drift after lowering.
        moves.append((token, mm))
    track_center(lambda: (center.copy(), True, 1.), act, target, .0008)
    assert np.linalg.norm(center[:2] - target[:2]) <= .0008
    assert abs(center[2] - target[2]) <= .001
    assert moves and all(mm <= 2. for _, mm in moves)


@pytest.mark.parametrize('held,up,message', [(False, 1., 'grip lost'), (True, .74, 'tilted')])
def test_grip_and_orientation_are_checked_even_at_target(held, up, message):
    with pytest.raises(RuntimeError, match=message):
        track_center(lambda: (np.zeros(3), held, up),
                     lambda *_: pytest.fail('Invalid grip must never move'), np.zeros(3), .0008)


def test_measured_nonprogress_stops_before_action_budget():
    moves = []
    with pytest.raises(RuntimeError, match='stalled'):
        track_center(lambda: (np.zeros(3), True, 1.), lambda *x: moves.append(x),
                     np.array([.01, 0, 0]), .0008)
    assert len(moves) == 24


def test_nonfitting_hole_rejected():
    with pytest.raises(ValueError, match='clear the post'):
        release_target([0, 0, .86], .003, .007, .88, .002, .0026)
