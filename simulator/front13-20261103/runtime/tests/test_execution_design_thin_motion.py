from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_thin_motion import checked_move
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def policy_for(displace):
    pos = np.zeros(3); calls = []
    def act(side, token, mm):
        calls.append((token, mm)); pos[:] += displace(token, mm, len(calls))
    return SimpleNamespace(a=SimpleNamespace(), tip=lambda side: pos.copy(),
        act=act, max_mm=12.), calls


def test_sideways_contact_deflection_stops_after_one_accepted_action():
    p, calls = policy_for(lambda token, mm, n: np.array([.003, 0., 0.]))
    with pytest.raises(ToolExecutionError, match='sideways'):
        checked_move(p, 'right', [0., 0., -.05])
    assert len(calls) == 1


def test_contact_jitter_cannot_hide_zero_net_approach_progress():
    p, calls = policy_for(lambda token, mm, n: np.array([.0005 * (-1) ** n, 0., 0.]))
    with pytest.raises(ToolExecutionError, match='target progress'):
        checked_move(p, 'right', [0., 0., -.05])
    assert len(calls) == 12


def test_slow_actual_approach_retains_guard_and_reaches_waypoint():
    p, calls = policy_for(lambda token, mm, n: np.array([0., 0., -.0005]))
    checked = []
    checked_move(p, 'right', [0., 0., -.010], lambda: checked.append(True), tolerance=.0006)
    assert len(calls) == 19
    assert len(checked) == len(calls) * 2 + 1
