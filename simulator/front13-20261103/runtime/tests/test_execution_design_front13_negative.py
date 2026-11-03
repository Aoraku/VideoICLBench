from copy import deepcopy
from pathlib import Path

import pytest

from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design_front13_negative import (
    CAPABILITIES, Front13NegativeAuthor, negative_plan,
)
from videoicl_isaaclab.realworld_scenes import load
from test_execution_design_back25_negative import FakeAuthor


def spec(task, variant='A', seed=4201, condition='I'):
    base = load(task, variant, 0, Path(__file__).parents[1] /
                'configs/realworld_full50_bindings.json', verify_files=False)
    return apply_execution_inputs(base, condition=condition, seed=seed, revision=REVISION_V3)


@pytest.mark.parametrize('task', ['E04', 'E06'])
@pytest.mark.parametrize('variant', 'ABC')
@pytest.mark.parametrize('seed', [4201, 4202, 4203])
@pytest.mark.parametrize('condition', 'RIE')
def test_all_legal_cells_keep_original_world_and_change_only_reference(task, variant, seed, condition):
    original = spec(task, variant, seed, condition)
    before = deepcopy(original)
    for control in CAPABILITIES[task]:
        plan, delta = negative_plan(original, control)
        assert original == before
        assert plan['objects'] == original['objects']
        assert plan['semantic'] == original['semantic']
        assert plan['execution_design'] == original['execution_design']
        assert delta['negative_condition_observed'] is None
        goals = plan['goals']
        if control == 'wrong_members':
            assert len(goals) == 2
            assert delta['omitted_member'] not in [g['object'] for g in goals]
        elif control == 'wrong_destination':
            assert len(goals) == 3
            assert goals[-1]['required_support'] == 'table'
            assert goals[-1]['target'] not in {g['target'] for g in original['goals']}
        elif control == 'wrong_rule':
            assert {g['object'] for g in goals} == {g['object'] for g in original['goals']}
            assert all(a['target'] != b['target'] for a, b in zip(goals, original['goals']))
            if task == 'E06':
                assert {g['target'] for g in goals}.isdisjoint(g['target'] for g in original['goals'])
                assert all(g['required_support'] == 'eggtray' for g in goals)
        else:
            assert goals == original['goals']
            assert delta['held_member'] == goals[-1]['object']


@pytest.mark.parametrize('task', ['E04', 'E06'])
@pytest.mark.parametrize('control', sorted(CAPABILITIES['E04']))
def test_actual_runner_restores_scene_even_after_physical_failure(task, control):
    source = spec(task)
    author = FakeAuthor(source)
    original = author.scene
    result = Front13NegativeAuthor(author, control).solve_negative()
    assert author.scene is original and author.c.scene is original
    assert 'release_generated' not in author.__dict__
    assert result['native_validation_required'] and result['negative_condition_observed'] is None
    broken = FakeAuthor(source, fail=True)
    with pytest.raises(RuntimeError, match='physical failure'):
        Front13NegativeAuthor(broken, control).solve_negative()
    assert broken.scene is broken.c.scene
    assert 'release_generated' not in broken.__dict__


@pytest.mark.parametrize('task', ['E04', 'E06'])
def test_missing_grasp_does_not_count_as_held_counterexample(task):
    author = FakeAuthor(spec(task), grasp=False)
    with pytest.raises(RuntimeError, match='physically held'):
        Front13NegativeAuthor(author, 'not_released').solve_negative()
    assert author.scene is author.c.scene


def test_legacy_unreviewed_and_smooth_routes_rejected():
    s = spec('E04')
    s['execution_design']['revision'] = 'legacy'
    with pytest.raises(ValueError):
        negative_plan(s, 'wrong_rule')
    s = spec('E04')
    s['id'] = 'E05'
    with pytest.raises(ValueError):
        negative_plan(s, 'wrong_rule')
    author = FakeAuthor(spec('E04'))
    author.smooth = True
    with pytest.raises(ValueError, match='public actions'):
        Front13NegativeAuthor(author, 'wrong_rule')


@pytest.mark.parametrize('task', ['E04', 'E06'])
@pytest.mark.parametrize('control', sorted(CAPABILITIES['E04']))
def test_probe_gate_preserves_native_pending_and_blocks_old_revision(tmp_path, task, control):
    import json
    from videoicl_isaaclab.execution_design import REVISION_V2
    from videoicl_isaaclab.execution_design_probe import validate_execution_cases
    from videoicl_isaaclab.execution_design_reference import reference_capability
    binding = json.loads((Path(__file__).parents[1] /
                          'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design'] = dict(revision=REVISION_V3, condition='I')
    path = tmp_path / 'binding.json'
    path.write_text(json.dumps(binding))
    case = dict(episode_id='candidate', task=task, variant='B', seed=4202,
                bindings=str(path), robot='franka')
    result = validate_execution_cases([case], control)[0]
    assert result['native_acceptance'] == 'not_run'
    assert result['native_assets_verified'] is False
    assert reference_capability(task, control)['native_validated'] is False
    binding['execution_design'] = dict(revision=REVISION_V2, condition='R')
    path.write_text(json.dumps(binding))
    with pytest.raises(ValueError, match='explicit v3'):
        validate_execution_cases([case], control)


@pytest.mark.parametrize('variant', 'ABC')
@pytest.mark.parametrize('condition', 'RIE')
@pytest.mark.parametrize('seed', [4201, 4202, 4203])
def test_e07_keeps_original_sizes_and_physical_relay_goals(variant, condition, seed):
    original = spec('E07', variant, seed, condition)
    before = deepcopy(original)
    for control in CAPABILITIES['E07']:
        plan, delta = negative_plan(original, control)
        assert original == before and plan['objects'] == original['objects']
        assert plan['semantic'] == original['semantic']
        assert delta['negative_condition_observed'] is None
        if control == 'wrong_rule':
            assert len(plan['goals']) == 5
            assert plan['goals'][0]['target'] == original['goals'][1]['target']
            assert plan['goals'][1]['target'] == original['goals'][0]['target']
            assert plan['zones'] == original['zones']
        elif control == 'wrong_members':
            assert len(plan['goals']) == 4
        else:
            assert plan['goals'][-1]['required_support'] == 'table'
    # E07 may release at a real relay before its final placement. The generic
    # last-release counter must not advertise an unreviewed held witness.
    with pytest.raises(ValueError):
        negative_plan(original, 'not_released')


def test_final_hold_does_not_intercept_actual_table_handoffs():
    class RelayAuthor(FakeAuthor):
        def __init__(self, source):
            super().__init__(source)
            self.actual_releases = []
        def release_generated(self, side):
            self.actual_releases.append((self.current_object, self._engineering_release_is_relay))
            self.act()
        def solve_generated(self):
            for goal in self.scene.spec['goals']:
                self.current_object = goal['object']
                for temporary in (True, False):
                    self._engineering_release_is_relay = temporary
                    try:
                        self.release_generated('left')
                    finally:
                        del self._engineering_release_is_relay
    source = spec('E04')
    a = RelayAuthor(source)
    result = Front13NegativeAuthor(a, 'not_released').solve_negative()
    assert [name for name,temporary in a.actual_releases if temporary] == [g['object'] for g in source['goals']]
    assert [name for name,temporary in a.actual_releases if not temporary] == [g['object'] for g in source['goals'][:-1]]
    assert a.current_object == source['goals'][-1]['object']
    assert a.c.steps == 8  # Five real releases, three actual held ticks.
    assert not hasattr(a, '_engineering_release_is_relay')
    assert result['negative_condition_observed'] is None
