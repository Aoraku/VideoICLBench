"""Measured C regression: endpoint-only IK chose a different winding."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from videoicl_isaaclab.execution_design_e15_path import solve_path


def fixture():
    return json.loads((Path(__file__).parent/'data/e15c-native-halfturn-start.json').read_text())


def test_native_measured_halfturn_keeps_the_actual_continuous_wrist_branch():
    d=fixture();before=deepcopy(d)
    rows=solve_path(d['measured'],d['targets'])
    assert len(rows)==17 and all(r['kinematically_reachable']for r in rows)
    # Source pickup previously selected q7=-2.895, only1.88mrad from its limit.
    # Continuation from the checked empty-turn arc stays on positive q7.
    assert 2.3<rows[7]['candidate_joints_rad'][6]<2.7
    # A robust reserve well above the unchanged20mrad rejection threshold.
    assert rows[7]['minimum_joint_margin_rad']>.2
    assert all(r['maximum_nearby_joint_increment_rad']<.35 for r in rows)
    assert d==before


def test_invalid_measured_model_is_rejected_before_path_work():
    d=fixture();d['measured']['jacobian'][0][0]=float('nan')
    with pytest.raises(ValueError,match='measured'):solve_path(d['measured'],d['targets'])


def test_existing_joint_limit_is_not_waived_for_continuation():
    d=fixture();d['measured']['q'][0]=d['measured']['limits'][0][0]
    with pytest.raises(ValueError,match='limit'):solve_path(d['measured'],d['targets'])


def test_native_e18_staging_redundancy_does_not_jump_between_nearby_samples():
    d=json.loads((Path(__file__).parent/'data/e18-native-continuous-start.json').read_text())
    rows=solve_path(d['measured'],d['targets'])
    assert len(rows)==5 and all(r['kinematically_reachable']for r in rows)
    assert min(r['minimum_joint_margin_rad']for r in rows)>.08
    assert max(r['maximum_nearby_joint_increment_rad']for r in rows)<.35


def test_e18_array_targets_are_recorded_without_changing_the_solved_path(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import numpy as np
    from videoicl_isaaclab import execution_design_jacobian_reference as capture_module
    from videoicl_isaaclab.execution_design_e15_path import inspect_path
    d=json.loads((Path(__file__).parent/'data/e18-native-continuous-start.json').read_text())
    targets=[dict(position=np.asarray(t['position']),rotation=np.asarray(t['rotation']))for t in d['targets']]
    before=deepcopy(targets)
    monkeypatch.setattr(capture_module,'capture',lambda *_:d['measured'])
    rows=inspect_path(SimpleNamespace(out=tmp_path),SimpleNamespace(steps=1),'left',targets)
    record=json.loads((tmp_path/'e15-continuous-winding.private.jsonl').read_text())
    assert rows==solve_path(d['measured'],d['targets'])
    assert record['targets']==d['targets']
    assert record['candidates']==rows and record['actuation_performed'] is False
    for actual,original in zip(targets,before):
        for key in ('position','rotation'):np.testing.assert_array_equal(actual[key],original[key])


def test_private_diagnostic_encoder_does_not_hide_unknown_types():
    import numpy as np
    from videoicl_isaaclab.execution_design_e15_path import _diagnostic_json
    assert _diagnostic_json(np.float64(.125))==.125
    with pytest.raises(TypeError,match='Unsupported'):_diagnostic_json(object())


@pytest.mark.parametrize('name',['e15b-native-empty-finger-118.json','e15c-native-red-halfturn-716.json'])
def test_native_red_halfturn_finds_candidates_inside_original_acceptance_gates(name):
    d=json.loads((Path(__file__).parent/'data'/name).read_text());before=deepcopy(d)
    rows=solve_path(d['measured'],d['targets'])
    assert len(rows)==17 and all(r['kinematically_reachable']for r in rows)
    assert min(r['minimum_joint_margin_rad']for r in rows)>.02
    assert max(r['position_error_m']for r in rows)<.001
    import math
    assert max(r['orientation_error_rad']for r in rows)<math.radians(1.5)
    assert max(r['maximum_nearby_joint_increment_rad']for r in rows)<.35
    assert d==before


def test_measured_start_inside_new_optimizer_reserve_is_rejected_without_clipping():
    d=fixture();d['measured']['q'][0]=d['measured']['limits'][0][0]+.01;before=deepcopy(d)
    with pytest.raises(ValueError,match='measured q not clipped'):solve_path(d['measured'],d['targets'])
    assert d==before
