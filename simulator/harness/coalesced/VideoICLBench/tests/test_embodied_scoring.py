import json
from pathlib import Path
import importlib.util
import sys

import unittest

# The private scorer has no SDK/network dependencies. Load it in isolation so
# these protocol checks also run on a machine without the SDK's HTTP clients.
_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location('embodied_private_scoring',
    _ROOT / 'packages/sdk/vic_sdk/embodied_environment/scoring.py')
_SCORING = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCORING
_SPEC.loader.exec_module(_SCORING)
ProgressAccumulator, ScoreContract = _SCORING.ProgressAccumulator, _SCORING.ScoreContract
score_native_terminal = _SCORING.score_native_terminal


def test_formal_score_is_native_success_not_terminal_predicate_fraction():
    result = score_native_terminal(dict(success=False, history_valid=True,
        conditions=[dict(passed=True), dict(passed=False)], score=.99,
        process_score=.99, progress_score=.99))
    assert result['score'] == result['success_score'] == 0.
    assert result['terminal_success_100'] == 0.
    assert result['task_score'] is None and result['task_score_100'] is None
    assert result['progress_score'] is None and result['process_score'] is None
    assert result['condition_pass_fraction_diagnostic'] == .5
    assert result['progress_unavailable_reason'] == 'verified_native_task_ladder_not_implemented'


def test_formal_native_success_gets_one_without_inventing_progress():
    result = score_native_terminal(dict(success=True, conditions=[dict(passed=True)]))
    assert result['score'] == 1. and result['task_score_100'] == 100.
    assert result['progress_score'] is None


def test_passing_terminal_conditions_are_not_sufficient_for_native_success():
    result = score_native_terminal(dict(success=False, conditions=[dict(passed=True)]))
    assert result['score'] == 0. and result['condition_pass_fraction_diagnostic'] == 1.


def test_formal_malformed_or_invalid_history_never_becomes_zero():
    invalid_results = [dict(success=True, conditions=[]),
        dict(success=False, conditions=[dict(passed=True)], history_valid=False),
        dict(success=True, conditions=[dict(passed=False)]),
        dict(success=False, conditions=[dict(passed=0)]),
        dict(success=False, conditions=[dict(passed=True)], errors=['missing physical evidence'])]
    for native in invalid_results:
        try:
            score_native_terminal(native)
        except ValueError:
            continue
        raise AssertionError('Malformed native evidence must stay unscored')


def contract(mode='paired'):
    return ScoreContract('E05', 'A', mode, ('one', 'two', 'three'),
                         (30., 30., 30.) if mode == 'paired' else (25., 55., 90.))


def observe(acc, step, values=(False, False, False), success=False):
    return acc.observe(step, native_success=success, native_valid=True,
                       milestones=dict(zip(acc.contract.milestone_ids, values)))


def test_model_done_does_not_replace_native_success_or_reveal_it_early():
    acc = ProgressAccumulator(contract())
    running = observe(acc, 0, (True, True, True), success=True)
    assert running['termination_reason'] == 'running'
    assert running['native_success'] is None
    result = acc.finish('done')
    assert result['model_declared_success'] is True
    assert result['native_success'] is True
    assert result['task_score_100'] == 100.


def test_current_native_success_at_done_not_ever_success():
    acc = ProgressAccumulator(contract())
    observe(acc, 4, (True, True, True), success=True)
    observe(acc, 5, (True, True, False), success=False)
    result = acc.finish('done')
    assert result['native_success'] is False
    assert result['first_native_success_step'] == 4
    assert result['native_success_lost_after_first'] is True
    assert result['task_score_100'] == 90.


def test_give_up_records_model_and_native_decisions_independently():
    acc = ProgressAccumulator(contract())
    observe(acc, 0, success=True)
    result = acc.finish('give_up')
    assert result['model_declared_success'] is False
    assert result['native_success'] is True
    assert result['score'] == 1.


def test_independent_native_milestones_latch_across_ticks():
    acc = ProgressAccumulator(contract())
    observe(acc, 0, (True, False, False))
    observe(acc, 1, (False, True, False))
    result = acc.finish('action_budget')
    assert result['native_success'] is False
    assert result['task_score_100'] == 60.
    assert len(result['milestone_witnesses']) == 2


def test_transition_advances_one_stage_per_physics_tick():
    acc = ProgressAccumulator(contract('transition'))
    for step, score in enumerate((25., 55., 90.)):
        assert observe(acc, step, (True, True, True))['process_score_100'] == score
    assert acc.finish()['score'] == .9


def test_count_mode_keeps_maximum_measured_count():
    acc = ProgressAccumulator(contract('by_count'))
    observe(acc, 0, (True, False, True))
    observe(acc, 1)
    assert acc.finish()['task_score_100'] == 55.


def test_missing_atoms_are_unknown_while_explicit_complete_failure_is_zero():
    missing = ProgressAccumulator(contract())
    missing.observe(0, native_success=False, native_valid=True)
    assert missing.finish()['score'] is None
    explicit = ProgressAccumulator(contract())
    observe(explicit, 0)
    assert explicit.finish()['score'] == 0.


def test_terminal_before_native_evidence_is_unknown():
    result = ProgressAccumulator(contract()).finish()
    assert result['native_success'] is None
    assert result['score'] is None
    assert result['termination_reason'] == 'no_native_evidence'


def test_incomplete_or_invalid_native_history_has_no_score():
    for invalidity in ('gap', 'native_invalid'):
        acc = ProgressAccumulator(contract())
        observe(acc, 0, (True, False, False))
        acc.observe(2 if invalidity == 'gap' else 1, native_success=True,
                    native_valid=invalidity != 'native_invalid', milestones={})
        assert acc.finish()['native_success'] is None
        assert acc.finish()['score'] is None


def test_terminal_snapshot_is_immutable_even_if_room_physics_continues():
    acc = ProgressAccumulator(contract())
    observe(acc, 0, (True, False, False))
    result = acc.finish('give_up')
    result['milestone_witnesses'].append({'forged': True})
    assert observe(acc, 1, (True, True, True), success=True)['score'] == .3
    assert len(acc.finish()['milestone_witnesses']) == 1


def test_native_auto_success_requires_explicit_alternative_protocol():
    acc = ProgressAccumulator(contract(), termination_mode='native_auto_success')
    assert observe(acc, 0, success=True)['termination_reason'] == 'native_success'


def test_full_success_can_be_known_when_partial_adapter_is_missing():
    acc = ProgressAccumulator(contract())
    acc.observe(0, native_success=True, native_valid=True)
    result = acc.finish()
    assert result['score'] == 1.
    assert result['process_score_100'] is None


def test_all_150_draft_contracts_are_explicit_and_unvalidated():
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / 'docs/evaluation/realworld50-progress-proposed-v1.json').read_text())
    assert registry['release_status'] == 'proposal_requires_native_positive_negative_controls'
    assert [row['task_id'] for row in registry['tasks']] == [f'E{i:02d}' for i in range(1, 51)]
    for task in registry['tasks']:
        assert task['native_controls_verified'] is False
        for variant in 'ABC':
            parsed = ScoreContract.from_task_spec(task, variant)
            assert parsed.process_ceiling == 90.
            assert parsed.milestone_ids


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(fn) for name, fn in globals().items()
                              if name.startswith('test_') and callable(fn))


if __name__ == '__main__':
    unittest.main()


def bound_progress_native(raw=50, cap=75, success=False, task='E05', variant='A'):
    """Private runtime fixture, not an actor or physical-evidence assertion."""
    from fractions import Fraction
    import hashlib
    evidence=dict(schema='videoicl-native-progress-evidence-v2',task=task,variant=variant,
        history_valid=True,physics_step=100,observation=dict(private_native_fixture=True),
        object_status={})
    r,c=Fraction(raw),Fraction(cap)
    progress=dict(protocol='videoicl-realworld50-task-score-v2',task=task,variant=variant,
        task_score_100=float(r),failure_ceiling_100=float(c),progress_available=True,
        score_is_raw_before_native_gate=True,raw_score_numerator=r.numerator,
        raw_score_denominator=r.denominator,failure_ceiling_numerator=c.numerator,
        failure_ceiling_denominator=c.denominator,units=[dict(id='measured-unit',score=float(r))],
        missing_evidence=[],native_physics_verified=False)
    progress['evidence_sha256']=hashlib.sha256(json.dumps(evidence,sort_keys=True,
        separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return dict(success=success,history_valid=True,conditions=[dict(passed=success)],
        progress_evidence=evidence,progress_result=progress)


def test_v2_partial_is_separate_from_binary_native_success_and_capped():
    native=bound_progress_native(raw=100,cap=75)
    result=score_native_terminal(native,task_id='E05',variant='A')
    assert result['score']==result['success_score']==0.
    assert result['task_score_100']==75 and result['task_score']==.75
    assert result['progress_raw_score_100']==100
    assert result['progress_score_available'] is True
    assert result['task_score_native_physics_verified'] is False
    assert result['progress_units']==native['progress_result']['units']
    result['progress_units'][0]['score']=999
    assert native['progress_result']['units'][0]['score']==100


def test_v2_declared_terminal_gates_require_boolean_measurements():
    import hashlib
    for gate in ('released', 'stable'):
        for value in ('missing', None, 0, 1, 'false', [], {}):
            native=bound_progress_native(raw=100)
            native['conditions']=[dict(type=gate,passed=False)]
            if value != 'missing':
                native['progress_evidence']['observation'][gate]=value
            native['progress_result']['evidence_sha256']=hashlib.sha256(json.dumps(
                native['progress_evidence'],sort_keys=True,separators=(',',':'),
                ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            result=score_native_terminal(native,task_id='E05',variant='A')
            assert result['task_score_100'] is None
            assert result['progress_unavailable_reason']=='native_terminal_gate_evidence_missing'
            assert result['progress_missing_evidence']==['observation.'+gate]


def test_v2_measured_terminal_gate_failure_remains_scoreable():
    import hashlib
    for gate in ('released', 'stable'):
        native=bound_progress_native(raw=100)
        native['conditions']=[dict(type=gate,passed=False)]
        native['progress_evidence']['observation'][gate]=False
        native['progress_result']['evidence_sha256']=hashlib.sha256(json.dumps(
            native['progress_evidence'],sort_keys=True,separators=(',',':'),
            ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        result=score_native_terminal(native,task_id='E05',variant='A')
        assert result['task_score_100']==75
        assert result['progress_score_available'] is True


def test_v2_complete_score_requires_raw_and_native_agreement():
    result=score_native_terminal(bound_progress_native(raw=100,success=True),task_id='E05',variant='A')
    assert result['score']==1 and result['task_score_100']==100
    result=score_native_terminal(bound_progress_native(raw=50,success=True),task_id='E05',variant='A')
    assert result['score']==1 and result['task_score_100'] is None
    assert result['progress_unavailable_reason']=='native_success_progress_contract_mismatch'


def test_v2_identity_unknown_protocol_and_unbound_call_fail_closed():
    native=bound_progress_native()
    result=score_native_terminal(native)
    assert result['task_score_100'] is None
    for key,value in [('task','E06'),('variant','B'),('protocol','unreviewed-v3')]:
        changed=json.loads(json.dumps(native));changed['progress_result'][key]=value
        result=score_native_terminal(changed,task_id='E05',variant='A')
        assert result['score']==0 and result['task_score_100'] is None


def test_v2_evidence_digest_detects_changed_terminal_snapshot():
    native=bound_progress_native();native['progress_evidence']['physics_step']=101
    result=score_native_terminal(native,task_id='E05',variant='A')
    assert result['task_score_100'] is None
    assert result['progress_unavailable_reason']=='native_progress_evidence_hash_mismatch'


def test_v2_numeric_and_gate_contract_cannot_be_bypassed():
    changes=[('raw_score_denominator',0),('raw_score_numerator',True),
        ('raw_score_numerator',101),('task_score_100',float('nan')),
        ('task_score_100',99),('failure_ceiling_numerator',100),
        ('score_is_raw_before_native_gate',False),('units',None)]
    for key,value in changes:
        native=bound_progress_native();native['progress_result'][key]=value
        result=score_native_terminal(native,task_id='E05',variant='A')
        assert result['score']==0 and result['task_score_100'] is None,(key,result)


def test_v2_missing_atoms_stay_null_while_explicit_zero_is_available():
    native=bound_progress_native(raw=0)
    result=score_native_terminal(native,task_id='E05',variant='A')
    assert result['task_score_100']==0 and result['progress_score_available']
    native['progress_result'].update(progress_available=False,task_score_100=None,missing_evidence=['delivery_chain_valid'])
    result=score_native_terminal(native,task_id='E05',variant='A')
    assert result['task_score_100'] is None and not result['progress_score_available']
    assert result['progress_missing_evidence']==['delivery_chain_valid']


def test_v2_exact_fraction_is_not_replaced_by_rounded_display():
    from fractions import Fraction
    native=bound_progress_native(raw=Fraction(200,3),cap=Fraction(200,3))
    result=score_native_terminal(native,task_id='E05',variant='A')
    assert (result['task_score_numerator'],result['task_score_denominator'])==(200,3)
    assert result['task_score_100']==float(Fraction(200,3))
