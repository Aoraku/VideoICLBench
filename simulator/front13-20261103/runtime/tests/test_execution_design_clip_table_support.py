import numpy as np
import pytest

from videoicl_isaaclab.execution_design_clip_table_support import horizontal_handle_turn, horizontal_handle_turns


def test_one_analytic_turn_lays_native_handle_pair_horizontal():
    # Measured native E40 after robust body hold. The wire gap stays exact;
    # this is a rigid planning turn, never a position assignment.
    points = np.array([[-.1206848, -.1411570, .9811048],
                       [-.1525858, -.1411788, 1.0241914]])
    delta = points[1] - points[0]
    rotation = horizontal_handle_turn(points)
    assert abs((rotation @ delta)[2]) < 1e-12
    assert np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-12)
    assert abs(np.linalg.det(rotation) - 1) < 1e-12
    assert np.isclose(np.linalg.norm(rotation @ delta), np.linalg.norm(delta))
    # A roughly horizontal pair should not get an unnecessary extra turn.
    assert np.allclose(horizontal_handle_turn(points @ rotation.T), np.eye(3), atol=1e-10)
    alternatives = horizontal_handle_turns(points)
    assert len(alternatives) == 2
    assert all(abs((r @ delta)[2]) < 1e-12 for r in alternatives)
    # The alternative inverts the horizontal direction; it is not another
    # source pose or a relaxed joint limit.
    assert np.allclose(alternatives[0] @ delta, -alternatives[1] @ delta, atol=1e-12)


def test_invalid_handle_geometry_is_rejected_before_planning():
    for points in (np.zeros((2, 3)), [[0, 0, 0], [0, np.nan, 1]], np.zeros((3, 3))):
        with pytest.raises(ValueError):
            horizontal_handle_turn(points)
