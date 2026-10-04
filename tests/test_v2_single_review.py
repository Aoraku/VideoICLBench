"""Low-tier work means one rule decision, with a saved negative result too."""
from copy import deepcopy

import pytest

from vic import business, games, v2
from vic.schemas import Mutation
from vic.v2_atomic import SINGLE_REVIEW
from vic_apps.store import ApplicationStore
from test_applications import reference


@pytest.mark.parametrize('task_id', sorted(SINGLE_REVIEW))
@pytest.mark.parametrize('variant', list('ABC'))
def test_one_designated_target_requires_review_and_preserves_context(task_id, variant, tmp_path):
    initial = v2.generate(task_id, 10001, 'eval')
    target = initial['rule_target']
    assert initial['review_target_label'] in initial['review_instructions']
    assert not v2.evaluate(initial, initial, variant, [])['success']
    operations = reference(initial, variant)
    assert all(op == 'review.confirm' or key == target for op, key, _, _ in operations)
    assert operations[-1] == ('review.confirm', target, '', [])
    store = ApplicationStore(tmp_path)
    store.initialize('single', initial)
    for index, (op, key, value, ids) in enumerate(operations):
        store.mutate('single', Mutation(epoch=0, action_id=str(index), op=op, target=key, value=value, ids=ids))
    final = ApplicationStore(tmp_path).snapshot('single')
    assert v2.evaluate(initial, final, variant, store.events('single'))['success']
    # Confirmation alone cannot hide an incorrect decision or extra annotation.
    wrong = deepcopy(final)
    if task_id < 66:
        other = next(x['id'] for x in initial['items'] if x['id'] != target)
        wrong['labels'][other] = initial['options'][0]
        wrong['domain']['objects'][other]['label'] = initial['options'][0]
    else:
        other = next(list(p) for p in initial['candidates'] if ','.join(map(str,p)) != target)
        wrong['marks'].append(other)
    assert not v2.evaluate(initial, wrong, variant, store.events('single'))['success']


@pytest.mark.parametrize('task_id', sorted(SINGLE_REVIEW))
def test_rule_versions_distinguishable_over_single_target_instance_bank(task_id):
    signatures = {v: [] for v in 'ABC'}
    for seed in range(1000, 1012):
        initial = v2.generate(task_id, seed, 'eval')
        for variant in 'ABC':
            if task_id < 66:
                decision = business.expected_effect(task_id, variant, initial)['labels'][initial['rule_target']]
            else:
                decision = bool(games.expected(task_id, variant, initial))
            signatures[variant].append(decision)
    assert len({tuple(values) for values in signatures.values()}) == 3


def test_demo_still_teaches_contrasts_instead_of_single_test_item():
    for task_id in SINGLE_REVIEW:
        assert not v2.generate(task_id, 0, 'demo').get('rule_target')
