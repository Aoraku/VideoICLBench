"""E39 source ABC must warm the renderer without advancing the world."""
from types import SimpleNamespace

import pytest

from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_render_retry import capture


def test_e39_gray_warmup_preserves_three_room_initial_boundary(tmp_path):
    pool = SimpleNamespace(physics_ticks=840)
    controllers = {
        variant: SimpleNamespace(physics_ticks=840, steps=0, scene=SimpleNamespace(
            spec={'id': 'E39', 'execution_design': {'revision': REVISION_V3}}))
        for variant in 'ABC'
    }
    calls = []
    counts = {}

    def render(room, passes, capture):
        calls.append((room, passes))
        counts[room] = counts.get(room, 0) + 1
        if room in 'AB' and counts[room] < 3:
            raise RuntimeError('Initial camera evidence rejected: All three native views are near-uniform gray; task visibility not established')
        return capture()

    pool.render_room = render
    for room, controller in controllers.items():
        assert capture(pool, room, controller, passes=3, callback=lambda: 'native_rgb',
                       log_path=tmp_path/(room+'-render-attempts.private.json')) == 'native_rgb'
        assert (pool.physics_ticks, controller.physics_ticks, controller.steps) == (840, 840, 0)
    assert calls == [('A', 3), ('A', 12), ('A', 24), ('B', 3), ('B', 12), ('B', 24), ('C', 3)]


@pytest.mark.parametrize('error,expected_passes', [
    ('All three native views are near-uniform gray; task visibility not established', [3, 12, 24]),
    ('Actual head camera differs from declared task view', [3]),
    ('Initial camera evidence rejected: All three native views are near-uniform gray; Actual head camera differs from declared task view', [3]),
])
def test_e39_still_rejects_unusable_camera_evidence(tmp_path, error, expected_passes):
    pool = SimpleNamespace(physics_ticks=840)
    controller = SimpleNamespace(physics_ticks=840, steps=0, scene=SimpleNamespace(
        spec={'id': 'E39', 'execution_design': {'revision': REVISION_V3}}))
    calls = []

    def render(room, passes, capture):
        calls.append(passes)
        raise RuntimeError(error)

    pool.render_room = render
    with pytest.raises(RuntimeError, match=error):
        capture(pool, 'A', controller, passes=3, callback=lambda: None,
                log_path=tmp_path/'initial-render-attempts.private.json')
    assert calls == expected_passes
    assert (pool.physics_ticks, controller.physics_ticks, controller.steps) == (840, 840, 0)
