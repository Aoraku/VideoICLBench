"""Private binary native success and versioned, evidence-bound v2 task scores.

The primary score remains binary. V2 partial scores arrive only from the trusted
native result, bound to the exact private progress evidence and episode identity.
The v1 ProgressAccumulator below remains an unconnected historical proposal.
"""
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math


PROTOCOL = 'videoicl-native-terminal-success-v1'
PROGRESS_PROTOCOL = 'videoicl-realworld50-task-score-v2'
PROGRESS_EVIDENCE_SCHEMA = 'videoicl-native-progress-evidence-v2'
PROPOSAL_PROTOCOL = 'videoicl-realworld50-robodojo-style-proposed-v1'
MODEL_ENDS = frozenset(('done', 'give_up', 'model_finish'))
BUDGET_ENDS = frozenset(('action_budget', 'active_time_budget', 'simulation_time_budget'))
UNSCORED_ENDS = frozenset(('infrastructure_error', 'user_stopped', 'invalid_initial_state', 'invalid_native_history', 'no_native_evidence'))


def score_native_terminal(native, *, task_id=None, variant=None):
    """Score one trusted sealed runtime result without inventing progression.

    The primary score stays binary. Legacy results retain their old semantics.
    V2 task scores require the private versioned native result, its evidence hash
    and the enclosing episode identity. Extra actor-style score fields are ignored.
    """
    if not isinstance(native, dict) or type(native.get('success')) is not bool:
        raise ValueError('A native boolean success result is required')
    if native.get('history_valid') is False or native.get('errors'):
        raise ValueError('Invalid native episode history is unscored')
    conditions = native.get('conditions', [])
    if not isinstance(conditions, list) or not conditions or any(
        not isinstance(c, dict) or type(c.get('passed')) is not bool for c in conditions):
        raise ValueError('Malformed native condition evidence')
    if native['success'] and not all(c['passed'] for c in conditions):
        raise ValueError('Native success contradicts terminal condition evidence')
    success_score = float(native['success'])
    result = dict(scoring_protocol=PROTOCOL, score=success_score,
        success_score=success_score, terminal_success_100=100. * success_score,
        task_score=1. if native['success'] else None,
        task_score_100=100. if native['success'] else None,
        task_score_source='native_success' if native['success'] else None,
        score_definition='terminal_native_success',
        progress_score=None, process_score=None, progress_score_available=False,
        progress_unavailable_reason='verified_native_task_ladder_not_implemented',
        condition_pass_fraction_diagnostic=sum(c['passed'] for c in conditions) / len(conditions),
        condition_pass_fraction_definition='diagnostic_only_not_a_task_score')
    if 'progress_result' in native:
        _apply_native_progress(result, native, task_id=task_id, variant=variant)
    return result


def _apply_native_progress(result, native, *, task_id, variant):
    # This is reached only from the controller's sealed runtime result. Public
    # model declarations are never accepted by this API or read as score fields.
    result.update(task_score=None, task_score_100=None, task_score_source=None,
        task_score_protocol=None, progress_score=None, process_score=None,
        progress_score_available=False, task_score_native_physics_verified=False)

    def unavailable(reason, details=None):
        result['progress_unavailable_reason'] = reason
        if details is not None: result['progress_missing_evidence'] = deepcopy(details)

    progress = native.get('progress_result')
    if not isinstance(progress, dict) or progress.get('protocol') != PROGRESS_PROTOCOL:
        unavailable('unsupported_native_progress_protocol'); return
    result['task_score_protocol'] = PROGRESS_PROTOCOL
    if (task_id not in {f'E{i:02d}' for i in range(1,51)} or variant not in ('A','B','C')
            or progress.get('task') != task_id or progress.get('variant') != variant):
        unavailable('native_progress_identity_mismatch'); return
    evidence = native.get('progress_evidence')
    if (not isinstance(evidence, dict) or evidence.get('schema') != PROGRESS_EVIDENCE_SCHEMA
            or evidence.get('task') != task_id or evidence.get('variant') != variant
            or evidence.get('history_valid') is not True):
        unavailable('invalid_native_progress_evidence'); return
    try:
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
    except (TypeError, ValueError, OverflowError):
        unavailable('invalid_native_progress_evidence_encoding'); return
    if progress.get('evidence_sha256') != digest:
        unavailable('native_progress_evidence_hash_mismatch'); return
    result['progress_evidence_sha256'] = digest
    # Missing terminal measurements are not observed physical failures. Only
    # require gates declared by this native task (event-only tasks omit them).
    observation = evidence.get('observation')
    missing_gates = sorted({c.get('type') for c in native['conditions']
        if c.get('type') in ('released', 'stable') and
        (not isinstance(observation, dict) or type(observation.get(c['type'])) is not bool)})
    if missing_gates:
        unavailable('native_terminal_gate_evidence_missing',
            ['observation.' + gate for gate in missing_gates]); return
    if progress.get('progress_available') is not True:
        missing = progress.get('missing_evidence')
        unavailable('native_progress_missing_evidence', missing if isinstance(missing,list) else []); return
    if progress.get('score_is_raw_before_native_gate') is not True:
        unavailable('native_progress_gate_contract_mismatch'); return
    fields = ('raw_score_numerator','raw_score_denominator',
              'failure_ceiling_numerator','failure_ceiling_denominator')
    if any(type(progress.get(k)) is not int for k in fields):
        unavailable('invalid_native_progress_rational'); return
    if progress['raw_score_denominator'] <= 0 or progress['failure_ceiling_denominator'] <= 0:
        unavailable('invalid_native_progress_rational'); return
    raw = Fraction(progress['raw_score_numerator'], progress['raw_score_denominator'])
    cap = Fraction(progress['failure_ceiling_numerator'], progress['failure_ceiling_denominator'])
    if not 0 <= raw <= 100 or not 0 <= cap < 100:
        unavailable('invalid_native_progress_range'); return
    for key, exact in [('task_score_100',raw),('failure_ceiling_100',cap)]:
        approximate=progress.get(key)
        if (type(approximate) not in (int,float) or not math.isfinite(approximate)
                or not math.isclose(approximate,float(exact),rel_tol=0,abs_tol=1e-9)):
            unavailable('native_progress_numeric_mismatch'); return
    if not isinstance(progress.get('units'),list) or progress.get('missing_evidence') != []:
        unavailable('malformed_native_progress_witnesses'); return
    if native['success'] and raw != 100:
        # Old success checks may not include the new causal/selection guards.
        # Keep the independently measured binary result, but never promote an
        # incompatible v2 raw score to a complete task score.
        unavailable('native_success_progress_contract_mismatch'); return
    final = Fraction(100) if native['success'] else min(raw,cap)
    result.update(task_score=float(final/100), task_score_100=float(final),
        task_score_source='sealed_native_progress_v2',
        task_score_numerator=final.numerator, task_score_denominator=final.denominator,
        progress_score=float(final/100), process_score=float(final/100),
        progress_score_available=True, progress_unavailable_reason=None,
        progress_raw_score_100=float(raw), progress_failure_ceiling_100=float(cap),
        progress_units=deepcopy(progress['units']),
        progress_required_change_count=progress.get('required_change_count'),
        task_score_validation_status='native_positive_negative_controls_pending')


@dataclass(frozen=True)
class ScoreContract:
    task_id: str
    variant: str
    mode: str
    milestone_ids: tuple[str, ...]
    weights: tuple[float, ...]
    process_ceiling: float = 90.

    def __post_init__(self):
        if self.task_id not in {f'E{i:02d}' for i in range(1, 51)} or self.variant not in ('A', 'B', 'C'):
            raise ValueError('Score contract must identify an E01-E50 variant')
        if self.mode not in ('paired', 'by_count', 'transition'):
            raise ValueError('Unknown milestone accumulation mode')
        if not self.milestone_ids or len(set(self.milestone_ids)) != len(self.milestone_ids):
            raise ValueError('Distinct nonempty milestone IDs are required')
        if not all(isinstance(k, str) and k for k in self.milestone_ids):
            raise ValueError('Milestone IDs must be nonempty strings')
        if len(self.weights) != len(self.milestone_ids) or any(
            type(w) not in (int, float) or not math.isfinite(w) or w <= 0 for w in self.weights):
            raise ValueError('An explicit positive finite weight/gradient is required per milestone')
        if type(self.process_ceiling) not in (int, float) or not 0 < self.process_ceiling < 100:
            raise ValueError('Partial process ceiling must be below 100')
        if self.mode == 'paired':
            if not math.isclose(sum(self.weights), self.process_ceiling, rel_tol=0., abs_tol=1e-8):
                raise ValueError('Independent milestone weights must sum to the process ceiling')
        elif tuple(sorted(self.weights)) != self.weights or self.weights[-1] != self.process_ceiling:
            raise ValueError('Count/transition gradients must be nondecreasing and end at the process ceiling')

    @classmethod
    def from_task_spec(cls, task, variant):
        if task.get('adapter_status') != 'requires_native_atom_adapter':
            raise ValueError('Unexpected progress-spec state; review before changing the protocol')
        count = task['unit_count_by_variant'][variant]
        ids = tuple(f'unit_{i:02d}' for i in range(1, count + 1))
        mode = task['score_mode']
        if mode == 'paired':
            weights = tuple(90. / count for _ in ids)
        elif task.get('transition_gradient') is not None:
            weights = tuple(task['transition_gradient'])
        else:
            weights = tuple(90. * i / count for i in range(1, count + 1))
        return cls(task['task_id'], variant, mode, ids, weights)


class ProgressAccumulator:
    """One accumulator per episode; observe every actual physics tick.

    ``milestones`` is a complete bool map produced by the trusted native atom
    adapter. It must not be supplied by the actor or reconstructed from action
    requests. For transition mode at most one stage advances on one physics
    tick, matching RoboDojo's sequential state-machine behavior.
    """
    def __init__(self, contract: ScoreContract, *, termination_mode='model_decision'):
        if termination_mode not in ('model_decision', 'native_auto_success'):
            raise ValueError('Explicit supported termination mode required')
        self.contract = contract
        self.termination_mode = termination_mode
        self.first_step = self.last_step = None
        self.observed_ticks = 0
        self.achieved = set()
        self.completed_count = 0
        self.witnesses = []
        self.partial_evidence_complete = True
        self.partial_unavailable_reason = None
        self.terminal = None
        self.current_native_success = None
        self.first_native_success_step = None
        self._digest = hashlib.sha256()

    def _process_score(self):
        if not self.partial_evidence_complete or self.observed_ticks == 0:
            return None
        if self.contract.mode == 'paired':
            return sum(self.contract.weights[i] for i, key in enumerate(self.contract.milestone_ids) if key in self.achieved)
        return 0. if self.completed_count == 0 else self.contract.weights[self.completed_count - 1]

    def observe(self, physics_step, *, native_success, native_valid, milestones=None):
        if self.terminal is not None:
            return deepcopy(self.terminal)
        if type(physics_step) is not int or physics_step < 0:
            raise ValueError('Actual nonnegative integer physics step required')
        if type(native_success) is not bool or type(native_valid) is not bool:
            raise ValueError('Native validity and success must be literal booleans')
        if self.last_step is not None and physics_step != self.last_step + 1:
            self.partial_evidence_complete = False
            self.partial_unavailable_reason = 'nonconsecutive_physics_evidence'
            return self.finish('invalid_native_history')
        if not native_valid:
            return self.finish('invalid_native_history')
        if self.first_step is None:
            self.first_step = physics_step
        self.last_step = physics_step
        self.observed_ticks += 1
        self.current_native_success = native_success
        if native_success and self.first_native_success_step is None:
            self.first_native_success_step = physics_step
        expected = set(self.contract.milestone_ids)
        valid_atoms = isinstance(milestones, dict) and set(milestones) == expected and all(type(v) is bool for v in milestones.values())
        if not valid_atoms:
            self.partial_evidence_complete = False
            self.partial_unavailable_reason = 'missing_or_malformed_native_atoms'
        else:
            if self.contract.mode == 'paired':
                for key, passed in milestones.items():
                    if passed and key not in self.achieved:
                        self.achieved.add(key)
                        self.witnesses.append(dict(milestone_id=key, physics_step=physics_step))
            elif self.contract.mode == 'by_count':
                count = sum(milestones.values())
                if count > self.completed_count:
                    self.completed_count = count
                    self.witnesses.append(dict(completed_count=count, physics_step=physics_step))
            else:
                if self.completed_count < len(self.contract.milestone_ids):
                    key = self.contract.milestone_ids[self.completed_count]
                    if milestones[key]:
                        self.completed_count += 1
                        self.witnesses.append(dict(milestone_id=key, physics_step=physics_step))
        packet = dict(physics_step=physics_step, native_success=native_success, native_valid=native_valid,
                      milestones=milestones if valid_atoms else None)
        self._digest.update(json.dumps(packet, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())
        if native_success and self.termination_mode == 'native_auto_success':
            self.terminal = self._result('native_success', True, 100.)
            return deepcopy(self.terminal)
        return self.snapshot()

    def snapshot(self):
        if self.terminal is not None:
            return deepcopy(self.terminal)
        return self._result('running', None, None)

    def _result(self, reason, success, task_score):
        process_score = self._process_score()
        invalid = reason in UNSCORED_ENDS
        return dict(protocol=PROPOSAL_PROTOCOL, task_id=self.contract.task_id, variant=self.contract.variant,
            termination_reason=reason, termination_mode=self.termination_mode, native_success=success,
            model_declared_success=(reason in ('done', 'model_finish') if reason in MODEL_ENDS else None),
            first_native_success_step=self.first_native_success_step,
            native_success_lost_after_first=(self.first_native_success_step is not None and self.current_native_success is False),
            task_score_100=None if invalid else task_score,
            score=None if invalid or task_score is None else task_score / 100.,
            process_score_100=None if invalid else process_score,
            process_score_available=not invalid and process_score is not None,
            partial_unavailable_reason=(reason if invalid else self.partial_unavailable_reason),
            first_physics_step=self.first_step, terminal_physics_step=self.last_step,
            observed_physics_ticks=self.observed_ticks, physics_evidence_sha256=self._digest.hexdigest(),
            milestone_witnesses=deepcopy(self.witnesses), score_mode=self.contract.mode,
            process_ceiling=self.contract.process_ceiling,
            accumulation='latched_native_milestones', terminal_result_immutable=reason != 'running')

    def finish(self, reason='done'):
        """Seal at the last trusted physics tick after the GUI terminal event.

        The caller must run the final native check and submit its tick before
        this call. Model declarations never override that native result.
        """
        if self.terminal is not None:
            return deepcopy(self.terminal)
        if reason not in MODEL_ENDS | BUDGET_ENDS | UNSCORED_ENDS:
            raise ValueError('Unknown terminal reason')
        if self.observed_ticks == 0 and reason not in UNSCORED_ENDS:
            reason = 'no_native_evidence'
        if reason in UNSCORED_ENDS:
            self.terminal = self._result(reason, None, None)
        else:
            success = self.current_native_success
            self.terminal = self._result(reason, success, 100. if success else self._process_score())
        return deepcopy(self.terminal)
