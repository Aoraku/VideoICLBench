"""Trial lifecycle shared by the robot MCP and human-facing workbench.

The runtime is injected by the native Isaac launcher. It is the only source of
images, executed actions and evaluator evidence; no model-reported state is
accepted. This module can be tested without importing Isaac or starting Kit.
"""
from copy import deepcopy
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

from .scoring import score_native_terminal
from ..api_timing import ApiTimingLedger, interval_seconds
from ..episode_api_admission import EpisodeApiAdmission


TOKENS = frozenset(('STILL', 'GRASP', 'RELEASE', 'FWD', 'BACK', 'LEFT', 'RIGHT',
    'UP', 'DOWN', 'ROTATE_CCW', 'ROTATE_CW', 'PITCH_UP', 'PITCH_DOWN', 'ROLL_LEFT', 'ROLL_RIGHT'))
IDENTITY_FIELDS = ('run_id', 'task_id', 'variant', 'seed', 'suite', 'epoch')


class PublicError(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class Identity:
    run_id: str
    task_id: str
    variant: str
    seed: int
    suite: str
    epoch: str

    def __post_init__(self):
        if not isinstance(self.run_id, str) or not self.run_id.strip() or not isinstance(self.task_id, str) or not re.fullmatch(r'E(?:0[1-9]|[1-4][0-9]|50)', self.task_id):
            raise ValueError('A unique run ID and E01-E50 task are required')
        if self.variant not in ('A', 'B', 'C') or type(self.seed) is not int or self.seed < 0:
            raise ValueError('Invalid variant or seed')
        if not isinstance(self.suite, str) or not self.suite.strip() or not isinstance(self.epoch, str) or not self.epoch.strip():
            raise ValueError('Suite and epoch must be explicit nonempty strings')


def private_write(path, value):
    """Create immutable controller evidence without exposing it to the agent."""
    import os
    path = Path(path)
    serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(serialized)


class Episode:
    def __init__(self, runtime, identity, *, title, instruction, condition,
                 max_actions, timeout_seconds, output, action_schema,
                 demo=None, text_rule=None, require_rule_report=True, validation_only=False, defer_budget_start=False,
                 api_timing_log=None, unknown_api_policy='retire_unscored', clock=time.monotonic):
        if condition not in ('real', 'sim', 'text_rule'):
            raise ValueError('Unknown input condition')
        if type(max_actions) is not int or max_actions <= 0:
            raise ValueError('Explicit positive action budget required')
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError('Nonnegative time budget required; zero disables the time limit')
        if unknown_api_policy not in {'retire_unscored', 'preserve_world', 'resume_closed_unknown'}:
            raise ValueError('Unknown API uncertainty policy')
        if unknown_api_policy == 'resume_closed_unknown' and (timeout_seconds != 0 or api_timing_log is None):
            raise ValueError('Closed unknown recovery requires no time budget and a private API journal')
        self.unknown_api_policy = unknown_api_policy
        self.last_confirmed_observe_monotonic = None
        self.unknown_continuation_recorded = None
        self.demo = None
        if condition == 'text_rule':
            if demo is not None or not isinstance(text_rule, str) or not text_rule.strip():
                raise ValueError('Text condition requires an explicit rule and no demo')
        else:
            if text_rule is not None or not isinstance(demo, dict):
                raise ValueError('Video condition requires one assigned demo and no rule text')
            path = Path(demo['path']).resolve(strict=True)
            if hashlib.sha256(path.read_bytes()).hexdigest() != demo['sha256']:
                raise ValueError('Assigned demonstration checksum mismatch')
            self.demo = dict(demo, path=str(path))
        self.runtime, self.identity = runtime, identity
        self.title, self.instruction, self.condition = title, instruction, condition
        self.max_actions, self.timeout_seconds = max_actions, (timeout_seconds or None)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        if self.demo:
            source = Path(self.demo['path'])
            frozen = self.output / ('assigned-demo' + source.suffix)
            shutil.copyfile(source, frozen)
            if hashlib.sha256(frozen.read_bytes()).hexdigest() != self.demo['sha256']:
                raise ValueError('Assigned demonstration changed while freezing the trial')
            self.demo = dict(self.demo, source_path=str(source), path=str(frozen))
        self.action_schema = deepcopy(action_schema)
        if not self.action_schema.get('tokens') or not set(self.action_schema['tokens']) <= TOKENS:
            raise ValueError('Action schema must contain bounded public tokens')
        for field in ('step_mm', 'rotation_deg'):
            spec = self.action_schema[field]
            if not all(type(spec[k]) in (int, float) and math.isfinite(spec[k]) for k in ('minimum', 'maximum', 'default')):
                raise ValueError('Action bounds must be finite numeric values')
            if not 0 < spec['minimum'] <= spec['default'] <= spec['maximum']:
                raise ValueError('Invalid action limits')
        self.text_rule = text_rule
        self.validation_only = bool(validation_only)
        self.require_rule_report = require_rule_report
        self.rule_report = None
        self.steps, self.status = 0, 'running'
        self.frame_id, self.images = None, None
        self.clock, self.created = clock, clock()
        self.started = None if defer_budget_start else self.created
        self.budget_policy = ('effective_time_graceful_v1' if getattr(runtime, 'barrier_policy', None) == 'wait'
                              else 'wall_time_v1')
        self.infrastructure_baseline = self._infrastructure_total()
        self.recovery_id = None
        self.recovery_started = None
        self.recovery_native_baseline = 0.
        self.recovery_wait_completed = 0.
        self.recovery_intervals = []
        if api_timing_log is not None and not Path(api_timing_log).is_absolute():
            raise ValueError('An absolute private per-episode API timing path is required')
        self.api_timing = ApiTimingLedger(api_timing_log, clock=clock) if api_timing_log is not None else None
        if self.api_timing is not None and (self.budget_policy != 'effective_time_graceful_v1' or
                not callable(getattr(runtime, 'infrastructure_wait_intervals', None))):
            raise ValueError('API timing requires the effective policy and trusted native service intervals')
        self.authoritative = None
        self.terminal_native = None
        self.terminal_snapshot_ready = False
        self.native_abandoned = False
        self.terminal_metadata = None
        self.model_stop = None
        self.last_action = None
        self.last_action_batch = None
        self._action_batch_lock = threading.Lock()
        self._unresolved_action_batch = None
        private_write(self.output / 'identity.private.json', asdict(identity))
        private_write(self.output / 'assignment.private.json', dict(condition=condition,
            max_actions=max_actions, timeout_seconds=timeout_seconds,
            budget_policy=self.budget_policy, unknown_api_policy=self.unknown_api_policy,
            api_timing_log=str(api_timing_log) if api_timing_log is not None else None,
            demo=self.demo, text_rule=text_rule, action_schema=self.action_schema,
            validation_only=self.validation_only, budget_start_deferred=bool(defer_budget_start)))

    def wall_elapsed(self):
        return 0. if self.started is None else max(0., self.clock() - self.started)

    def _infrastructure_total(self):
        reader = getattr(self.runtime, 'infrastructure_wait_seconds', None)
        value = reader() if callable(reader) else 0.
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid trusted infrastructure timer')
        return float(value)

    def infrastructure_elapsed(self):
        if self.started is None or self.budget_policy != 'effective_time_graceful_v1':
            return 0.
        if self.api_timing is not None:
            return self._api_budget_reading()['excluded_seconds']
        native = self._infrastructure_total()
        recovery = self.recovery_wait_completed
        if self.recovery_started is not None:
            # Exclude the union, never double-count native service during recovery.
            recovery += max(0., self.clock() - self.recovery_started -
                            max(0., native - self.recovery_native_baseline))
        return min(self.wall_elapsed(), max(0., native - self.infrastructure_baseline) + recovery)

    def private_state(self):
        """Owner-queue completion barrier; never exposed through actor endpoints."""
        return dict(identity=asdict(self.identity), state=self.state(), owner_barrier=dict(
            schema='videoicl-owner-action-barrier-v1', action_count=self.steps,
            status=self.status, terminal_snapshot_ready=self.terminal_snapshot_ready,
            unknown_api_policy=self.unknown_api_policy,time_limit_enabled=self.timeout_seconds is not None,
            model_stop=self.model_stop, recovery_id=self.recovery_id,
            api_timing_log=str(self.api_timing.path) if self.api_timing is not None else None,
            api_timing=self.api_timing.snapshot() if self.api_timing is not None else None,
            elapsed_seconds=self.elapsed(), wall_elapsed_seconds=self.wall_elapsed(),
            infrastructure_wait_seconds=self.infrastructure_elapsed()))

    def begin_recovery(self, recovery_id):
        self._await_api_classification(for_recovery=True)
        if self.budget_policy != 'effective_time_graceful_v1':
            raise PublicError('recovery_not_supported', 'Recovery requires the effective budget policy.')
        if not isinstance(recovery_id, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', recovery_id):
            raise PublicError('invalid_recovery_id', 'A bounded recovery identifier is required.', 400)
        if self.recovery_id is not None:
            if self.recovery_id != recovery_id:
                raise PublicError('recovery_already_active', 'Another recovery holds this episode.')
            return self.private_state()
        self.expire_budget_if_due()
        if self.status == 'running':
            self.recovery_id = recovery_id
            self.recovery_started = self.clock()
            self.recovery_native_baseline = self._infrastructure_total()
            self.frame_id = None
            self._log('recovery_started', recovery_id=recovery_id)
        return self.private_state()

    def end_recovery(self, recovery_id):
        self._await_api_classification(for_recovery=True)
        if self.recovery_id != recovery_id or self.recovery_started is None:
            raise PublicError('recovery_identity_mismatch', 'The recovery identifier does not match.')
        self.recovery_wait_completed += max(0., self.clock() - self.recovery_started -
            max(0., self._infrastructure_total() - self.recovery_native_baseline))
        self.recovery_intervals.append([self.recovery_started, self.clock()])
        self.recovery_started = None
        self.recovery_id = None
        self._log('recovery_ended', recovery_id=recovery_id)
        return self.private_state()

    def elapsed(self):
        return max(0., self.wall_elapsed() - self.infrastructure_elapsed())

    def actor_activity(self):
        if self.api_timing is not None:
            self.api_timing.actor_activity()

    def _api_classified(self):
        if self.api_timing is None:
            return True
        state = self.api_timing.snapshot()
        return not state['active'] and (not state['uncertain'] or self._unknown_resume_allowed(state))

    def _api_budget_reading(self):
        """One API snapshot for both elapsed time and the seal-admission decision."""
        now = self.clock()
        state = self.api_timing.snapshot(now=now)
        intervals = list(self.runtime.infrastructure_wait_intervals(now=now))
        intervals += state['excluded_intervals'] + self.recovery_intervals
        if self.recovery_started is not None:
            intervals += [[self.recovery_started, now]]
        excluded = interval_seconds(intervals, start=self.started, end=now) if self.started is not None else 0.
        wall = max(0., now - self.started) if self.started is not None else 0.
        return dict(elapsed_seconds=max(0., wall-excluded), excluded_seconds=excluded,
                    classified=not state['active'] and (not state['uncertain'] or self._unknown_resume_allowed(state)), api=state)

    def _unknown_resume_allowed(self, state, *, for_recovery=False):
        # This is permission to continue, never a rewritten API outcome or
        # timing credit. Request IDs and unknown counts remain in the ledger.
        if (self.unknown_api_policy != 'resume_closed_unknown' or self.timeout_seconds is not None
                or not state.get('closed_unknown_recoverable') or state.get('active')
                or not state.get('ledger_integrity_valid') or state.get('pending_log_write')):
            return False
        if for_recovery:
            return True  # Reconnect the same CLI; this grants no robot action.
        success=state.get('subsequent_success_end')
        return (success is not None and self.last_confirmed_observe_monotonic is not None
                and self.last_confirmed_observe_monotonic >= success and self.frame_id is not None)

    def _await_api_classification(self, *, for_recovery=False):
        # Owner waits without advancing physics or cancelling a live request.
        # Tools can arrive before the relay has emitted its terminal record.
        while self.api_timing is not None:
            state = self.api_timing.snapshot()
            if state.get('pending_log_write'):
                time.sleep(.05)
                continue
            if state['uncertain']:
                if self._unknown_resume_allowed(state, for_recovery=for_recovery):
                    if not for_recovery and self.unknown_continuation_recorded != state['unknown_request_ids']:
                        self.unknown_continuation_recorded=list(state['unknown_request_ids'])
                        self._log('api_unknown_continuation_authorized', policy=self.unknown_api_policy,
                            unknown_request_ids=state['unknown_request_ids'],
                            subsequent_success_end=state['subsequent_success_end'],
                            fresh_observe_monotonic=self.last_confirmed_observe_monotonic)
                    return
                raise PublicError('api_timing_uncertain', 'Provider timing is incomplete; retain unscored infrastructure evidence.', 503)
            if not state['active']:
                return
            time.sleep(.05)

    def expire_budget_if_due(self):
        """Only called on the environment owner thread, between operations.

        A pending native action finishes before this thread can seal. No CLI
        process or model request is cancelled by the budget boundary.
        """
        # An accepted batch must first establish its executed prefix. Never
        # seal an unknown/in-flight physical operation on a timer.
        if self._unresolved_action_batch is not None:
            return
        reading = self._api_budget_reading() if self.api_timing is not None else dict(
            elapsed_seconds=self.elapsed(), classified=True)
        if (self.timeout_seconds is not None and self.started is not None and self.status == 'running' and reading['elapsed_seconds'] >= self.timeout_seconds
                and reading['classified']):
            self._seal('budget_exhausted', 'effective_time_budget' if self.budget_policy == 'effective_time_graceful_v1' else 'wall_time_budget')

    def start(self, started_monotonic=None):
        """Controller-only, one-way gate after every room has finished warmup.

        A shared same-host monotonic timestamp gives all rooms the same budget.
        Retries may confirm that timestamp but can never reset an existing clock.
        """
        if self.started is not None:
            if started_monotonic is not None and started_monotonic != self.started:
                raise PublicError('budget_already_started', 'The episode clock cannot be reset.')
            return dict(budget_started=True, started_monotonic=self.started)
        if self.status != 'running':
            raise PublicError('episode_stopped', 'This episode has stopped.')
        if self.recovery_id is not None:
            raise PublicError('recovery_in_progress', 'End recovery before starting the episode budget.')
        now = self.clock()
        proposed = now if started_monotonic is None else started_monotonic
        if (type(proposed) not in (int, float) or not math.isfinite(proposed)
                or proposed < max(self.created, now - 60.) or proposed > now):
            raise PublicError('invalid_start_time', 'A recent same-host start timestamp is required.', 400)
        self.started = proposed
        self.infrastructure_baseline = self._infrastructure_total()
        self.recovery_wait_completed = 0.  # Preparation happened before this one-way start.
        self._log('budget_started', started_monotonic=proposed)
        return dict(budget_started=True, started_monotonic=proposed)

    def _require_started(self):
        if self.started is None:
            raise PublicError('episode_not_started', 'The environment is preparing.')

    def _log(self, event, **value):
        with (self.output / 'environment.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(event=event, elapsed_seconds=self.elapsed(),
                                    wall_elapsed_seconds=self.wall_elapsed(),
                                    infrastructure_wait_seconds=self.infrastructure_elapsed(), **value),
                                    ensure_ascii=False, allow_nan=False) + '\n')

    def _active(self):
        self._require_started()
        if self.recovery_id is not None:
            raise PublicError('recovery_in_progress', 'The controller is reconnecting; observe again afterwards.')
        if self.status != 'running':
            raise PublicError('episode_stopped', 'This episode has stopped.')
        if self.api_timing is not None and self.api_timing.snapshot()['uncertain']:
            self._await_api_classification()
        if self.timeout_seconds is not None and self.elapsed() >= self.timeout_seconds:
            self._await_api_classification()
        self.expire_budget_if_due()
        if self.status == 'budget_exhausted':
            raise PublicError('budget_exhausted', 'The episode time budget has ended.')

    def state(self):
        self.expire_budget_if_due()
        result = dict(run_id=self.identity.run_id, task_id=self.identity.task_id,
            title=self.title, instruction=self.instruction, status=self.status,
            steps=self.steps, max_actions=self.max_actions, condition=self.condition,
            frame_id=self.frame_id, action_schema=deepcopy(self.action_schema),
            demo_available=self.demo is not None, rule_reported=self.rule_report is not None,
            diagnostics_enabled=self.require_rule_report)
        if self.last_action_batch is not None:
            result['action_batch'] = deepcopy(self.last_action_batch)
        public_feedback = getattr(self.runtime, 'public_feedback', None)
        if public_feedback:
            result['robot_feedback'] = public_feedback()
            if self.last_action:
                result['robot_feedback']['last_action'] = deepcopy(self.last_action)
            sensors = result['robot_feedback'].get('depth_sensors', {})
            available = sorted(name for name, data in sensors.items()
                               if isinstance(data, dict) and data.get('available') is True)
            result['observation_contract'] = dict(
                schema='videoicl-public-observation-v2',
                depth_source='simulator_axial_depth' if available else 'none_available',
                sensor_depth_cameras=available,
                simulator_depth_assisted=bool(available),
                coordinates='Agent computes from same-frame pixel, depth and declared K/T',
                task_object_state_exposed=False, evaluator_exposed=False)
        if self.condition == 'text_rule':
            result['text_rule'] = self.text_rule
        return result

    def observe(self):
        self.expire_budget_if_due()
        if self.status not in ('running', 'finished', 'done', 'give_up', 'budget_exhausted'):
            raise PublicError('environment_unavailable', 'The environment is unavailable.', 503)
        try:
            images = self.runtime.observe()
            known = {'head', 'left_wrist', 'right_wrist'}
            if (not isinstance(images, dict) or set(images) - known or
                    not isinstance(images.get('head'), str) or not images['head']):
                raise ValueError('Native adapter returned no valid head RGB stream')
            # Missing wrist views do not invalidate a usable head observation.
            # No placeholder images are manufactured; GUI shows unavailable views.
            images = {name: data for name, data in images.items() if isinstance(data, str) and data}
            unavailable = sorted(known - set(images))
            if unavailable != getattr(self, '_unavailable_rgb_cameras', []):
                self._log('rgb_camera_availability', unavailable=unavailable)
                self._unavailable_rgb_cameras = unavailable
        except Exception as exc:
            self.status = 'faulted'
            self._log('infrastructure_error', operation='observe', error=repr(exc))
            raise PublicError('environment_unavailable', 'The environment observation failed.', 503) from exc
        self.images, self.frame_id = images, uuid.uuid4().hex
        self.last_confirmed_observe_monotonic = self.clock()
        self._log('observe', frame_id=self.frame_id)
        state = self.state()
        contract = state.get('observation_contract')
        if contract != getattr(self, '_last_observation_contract', None):
            self._log('observation_contract', contract=contract)
            self._last_observation_contract = deepcopy(contract)
        return dict(frame_id=self.frame_id, images=deepcopy(images), state=state)

    def report_inferred_rule(self, rule, evidence_seconds):
        self._active()
        if self.steps or self.rule_report is not None:
            raise PublicError('rule_report_locked', 'Record the rule once before the first action.')
        if not isinstance(rule, str) or not 1 <= len(rule.strip()) <= 10000:
            raise PublicError('invalid_rule_report', 'A nonempty rule description is required.', 400)
        if not isinstance(evidence_seconds, list) or len(evidence_seconds) > 12 or any(
            type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in evidence_seconds):
            raise PublicError('invalid_timestamps', 'Supply up to 12 nonnegative video timestamps.', 400)
        if self.condition != 'text_rule' and not evidence_seconds:
            raise PublicError('missing_timestamps', 'Include the video timestamps used to infer the rule.', 400)
        if self.condition == 'text_rule' and evidence_seconds:
            raise PublicError('video_disabled', 'This condition has no demonstration video.', 400)
        self.rule_report = dict(rule=rule.strip(), evidence_seconds=list(evidence_seconds))
        self._log('report_inferred_rule', **self.rule_report)
        return dict(recorded=True, state=self.state())

    def action(self, *, frame_id, left, right, step_mm, rotation_deg):
        self._check_action_batch_idle()
        self._active()
        if self.require_rule_report and self.rule_report is None:
            raise PublicError('rule_report_required', 'Record the inferred rule before acting.')
        if self.frame_id is None or frame_id != self.frame_id:
            raise PublicError('stale_frame', 'Observe the current environment before acting.')
        if left not in self.action_schema['tokens'] or right not in self.action_schema['tokens']:
            raise PublicError('invalid_action', 'Choose an available action token.', 400)
        for name, value in [('step_mm', step_mm), ('rotation_deg', rotation_deg)]:
            bounds = self.action_schema[name]
            if type(value) not in (int, float) or not math.isfinite(value) or not bounds['minimum'] <= value <= bounds['maximum']:
                raise PublicError('invalid_action', 'Action parameters must be within the displayed limits.', 400)
        self.frame_id = None  # Consume before execution; an ambiguous action cannot be replayed.
        self._log('action_started', step=self.steps, left=left, right=right,
                  step_mm=step_mm, rotation_deg=rotation_deg)
        try:
            receipt = self.runtime.action(left=left, right=right, step_mm=step_mm, rotation_deg=rotation_deg)
        except Exception as exc:
            self.status = 'faulted'
            self._log('infrastructure_error', operation='action', error=repr(exc))
            raise PublicError('action_execution_failed', 'The environment could not confirm this action.', 503) from exc
        self.steps += 1
        self.last_action = dict(left=left, right=right, step_mm=step_mm, rotation_deg=rotation_deg,
                                tracking_error_m=receipt.get('tracking_error_m') if isinstance(receipt, dict) else None)
        if isinstance(receipt, dict):
            for field in ('orientation_error_rad', 'control_feedback'):
                if field in receipt:
                    self.last_action[field] = deepcopy(receipt[field])
        self._log('action_completed', step=self.steps, receipt=receipt)
        if self.steps == self.max_actions:
            if self.unknown_api_policy == 'resume_closed_unknown':
                # The accepted action consumed its frame. Capture its actual
                # result before applying the same fresh-observation seal guard.
                self.observe()
            self._seal('budget_exhausted', 'action_budget')
        return self.observe()

    def _check_action_batch_idle(self):
        if self._unresolved_action_batch is not None or self._action_batch_lock.locked():
            raise PublicError('operation_pending',
                'An accepted action batch requires its original receipt; do not replay or stop it.')

    def _write_action_batch(self, path, record):
        """Durable write-ahead cursor; it is never an instruction to replay."""
        import os
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        raw = (json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n').encode()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _public_action_batch(record):
        # The raw native receipt stays private. Publish only the proprioceptive
        # fields already displayed by the single-action GUI, never object state
        # or evaluator/score fields a runtime might include in a raw receipt.
        rows = []
        for row in record['receipts']:
            clean = {key: deepcopy(row[key]) for key in ('index', 'status', 'step', 'action') if key in row}
            raw = row.get('receipt')
            if isinstance(raw, dict):
                clean['receipt'] = {key: deepcopy(raw[key]) for key in
                    ('tracking_error_m', 'orientation_error_rad', 'control_feedback') if key in raw}
            rows.append(clean)
        return dict(batch_id=record['batch_id'], status=record['status'], accepted=True,
            requested_count=len(record['actions']), completed_count=record['completed_count'],
            physical_action_count=record['completed_count'], next_index=record['next_index'],
            commands_sha256=record['commands_sha256'], receipts=rows,
            uncertain_action_index=record.get('uncertain_action_index'))

    def action_batch(self, *, frame_id, batch_id, actions):
        """One public Commit, 1..24 ordered dual-arm physical action pairs.

        No intermediate model observation and no automatic action retry. A
        duplicate completed ID only reads its receipt; unknown prefixes remain
        blocked for owner reconciliation, even if another ID is supplied.
        """
        if not isinstance(batch_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', batch_id):
            raise PublicError('invalid_action', 'A bounded public batch ID is required.', 400)
        if not isinstance(actions, list) or not 1 <= len(actions) <= 24:
            raise PublicError('invalid_action', 'A Commit contains one to twenty-four action pairs.', 400)
        checked = deepcopy(actions)
        for action in checked:
            if not isinstance(action, dict) or set(action) != {'left', 'right', 'step_mm', 'rotation_deg'}:
                raise PublicError('invalid_action', 'Each queued pair needs exactly the public action fields.', 400)
            if any(not isinstance(action[side], str) or action[side] not in self.action_schema['tokens']
                   for side in ('left', 'right')):
                raise PublicError('invalid_action', 'Choose available queued action tokens.', 400)
            for name in ('step_mm', 'rotation_deg'):
                bounds, value = self.action_schema[name], action[name]
                if type(value) not in (int, float) or not math.isfinite(value) or not bounds['minimum'] <= value <= bounds['maximum']:
                    raise PublicError('invalid_action', 'Queued parameters must be within the displayed limits.', 400)
        digest = hashlib.sha256(json.dumps(checked, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        path = self.output / 'action-batches' / (hashlib.sha256(batch_id.encode()).hexdigest() + '.private.json')
        if not self._action_batch_lock.acquire(blocking=False):
            raise PublicError('operation_pending', 'The original Commit is still running; do not submit again.')
        try:
            if path.exists():
                record = json.loads(path.read_text())
                if record['commands_sha256'] != digest or record['identity'] != asdict(self.identity):
                    raise PublicError('invalid_action', 'Batch ID already belongs to a different ordered request.', 409)
                self.last_action_batch = self._public_action_batch(record)
                if record['status'] not in ('completed', 'partial'):
                    self._unresolved_action_batch = batch_id
                    raise PublicError('operation_pending', 'The accepted batch has an unconfirmed action; preserve it without replay.')
                result = self.observe()
                result['action_batch'] = deepcopy(self.last_action_batch)
                result['action_batch']['replayed'] = False
                return result
            if self._unresolved_action_batch is not None:
                raise PublicError('operation_pending', 'An earlier accepted batch is unresolved; do not submit another.')
            self._active()
            if self.require_rule_report and self.rule_report is None:
                raise PublicError('rule_report_required', 'Record the inferred rule before acting.')
            if self.frame_id is None or frame_id != self.frame_id:
                raise PublicError('stale_frame', 'Observe the current environment before committing.')
            if len(checked) > self.max_actions - self.steps:
                raise PublicError('invalid_action', 'The complete queue exceeds the remaining physical action budget.', 400)
            record = dict(schema='public-action-batch-v1', identity=asdict(self.identity),
                batch_id=batch_id, initial_frame_id=frame_id, commands_sha256=digest,
                actions=checked, initial_step=self.steps, status='accepted', next_index=0,
                completed_count=0, receipts=[])
            self._write_action_batch(path, record)
            self._unresolved_action_batch = batch_id
            self.frame_id = None  # One accepted Commit consumes the initial frame.
            for index, action in enumerate(checked):
                if self.status != 'running':
                    record['status'] = 'partial'
                    break
                record.update(status='inflight', next_index=index, uncertain_action_index=index)
                self._write_action_batch(path, record)  # Must reach disk before touching physics.
                self._log('action_started', step=self.steps, batch_id=batch_id, batch_index=index, **action)
                try:
                    receipt = self.runtime.action(**action)
                except Exception as exc:
                    record['status'] = 'unknown'
                    record['error_type'] = type(exc).__name__
                    self._write_action_batch(path, record)
                    self.last_action_batch = self._public_action_batch(record)
                    self._log('action_batch_unknown', batch_id=batch_id, batch_index=index,
                              confirmed_action_count=self.steps, error_type=type(exc).__name__)
                    # No terminal/score is manufactured and no suffix executes.
                    raise PublicError('operation_pending', 'Action outcome is unconfirmed; retain the original batch without replay.', 503) from exc
                if isinstance(receipt, dict) and (receipt.get('pending') is True or receipt.get('uncertain') is True
                        or receipt.get('status') in ('accepted', 'inflight', 'pending', 'unknown', 'uncertain')):
                    record.update(status='unknown')
                    record['receipts'].append(dict(index=index, status='unknown', step=self.steps,
                                                   action=action, receipt=deepcopy(receipt)))
                    self._write_action_batch(path, record)
                    self.last_action_batch = self._public_action_batch(record)
                    raise PublicError('operation_pending', 'Action receipt is unconfirmed; retain the accepted batch.', 503)
                if isinstance(receipt, dict) and receipt.get('accepted') is False:
                    record['receipts'].append(dict(index=index, status='rejected', step=self.steps,
                                                   action=action, receipt=deepcopy(receipt)))
                    record.update(status='partial', uncertain_action_index=None)
                    break  # Explicit non-admission is not a physical action.
                self.steps += 1
                self.last_action = dict(**action, tracking_error_m=receipt.get('tracking_error_m') if isinstance(receipt, dict) else None)
                if isinstance(receipt, dict):
                    for field in ('orientation_error_rad', 'control_feedback'):
                        if field in receipt:
                            self.last_action[field] = deepcopy(receipt[field])
                record['receipts'].append(dict(index=index, status='completed', step=self.steps,
                                               action=action, receipt=deepcopy(receipt)))
                record.update(completed_count=record['completed_count'] + 1, next_index=index + 1,
                              uncertain_action_index=None)
                self._write_action_batch(path, record)
                self._log('action_completed', step=self.steps, batch_id=batch_id, batch_index=index, receipt=receipt)
                if isinstance(receipt, dict) and (receipt.get('ok') is False or receipt.get('terminal') is True
                        or receipt.get('status') in ('done', 'give_up', 'finished', 'sealed', 'stopped', 'faulted', 'failed')):
                    record['status'] = 'partial' if index + 1 < len(checked) else 'completed'
                    break
            else:
                record['status'] = 'completed'
            self._write_action_batch(path, record)
            self.last_action_batch = self._public_action_batch(record)
            self._unresolved_action_batch = None
            if self.steps == self.max_actions and self.status == 'running':
                if self.unknown_api_policy == 'resume_closed_unknown':
                    self.observe()
                self._seal('budget_exhausted', 'action_budget')
            result = self.observe()
            result['action_batch'] = deepcopy(self.last_action_batch)
            return result
        finally:
            self._action_batch_lock.release()

    def _seal(self, status, reason, summary=''):
        if self.api_timing is not None:
            admission = EpisodeApiAdmission(self.api_timing.path)
            while True:
                self._await_api_classification()
                # API registration and this final decision share one lock.
                # A fresh request admitted after the earlier wait must drain;
                # once closed, no later request can reach the upstream API.
                with admission.guard():
                    reading = self._api_budget_reading()
                    if not reading['classified']:
                        continue
                    if reason in {'effective_time_budget', 'wall_time_budget'} and (self.timeout_seconds is None or reading['elapsed_seconds'] < self.timeout_seconds):
                        return False
                    admission.close_locked(reason=reason, monotonic=self.clock())
                    break
        else:
            self._await_api_classification()
            if reason in {'effective_time_budget', 'wall_time_budget'} and (self.timeout_seconds is None or self.elapsed() < self.timeout_seconds):
                return False  # A just-classified failed request restored the effective budget.
        # Runtime.seal stops mutation; it must not return an evaluator score.
        try:
            self.runtime.seal()
            # Capture privately now: other rooms in a pool may keep simulating
            # before the controller requests its authoritative evaluation.
            self.terminal_native = deepcopy(self.runtime.evaluate())
            self.terminal_metadata = dict(status=status, reason=reason,
                model_stop=self.model_stop, action_count=self.steps,
                elapsed_seconds=self.elapsed(),
                wall_elapsed_seconds=self.wall_elapsed(),
                infrastructure_wait_seconds=self.infrastructure_elapsed(), budget_policy=self.budget_policy,
                api_timing=self.api_timing.snapshot() if self.api_timing is not None else None,
                sampling='sealed_runtime_final_native_check')
            private_write(self.output / 'terminal-native.private.json',
                dict(terminal=self.terminal_metadata, evidence=self.terminal_native))
            self.terminal_snapshot_ready = True
        except Exception as exc:
            self.status = 'faulted'
            self._log('infrastructure_error', operation='seal', error=repr(exc))
            raise PublicError('environment_unavailable', 'The environment could not be sealed.', 503) from exc
        self.status = status
        self._log('sealed', status=status, reason=reason, summary=summary)
        return True

    def abandon(self, reason='controller_close_without_score'):
        """Retire only this native room without manufacturing a scored terminal.

        By default, a completely received but logically unknown response permits
        unscored retirement to release siblings at the shared barrier. Explicit
        preserve_world policy instead retains the room pending diagnosis and
        can block those siblings. Neither policy repairs/reclassifies API logs.
        A damaged ledger never establishes that requests ended.
        """
        self._check_action_batch_idle()
        if self.terminal_snapshot_ready or self.native_abandoned:
            return dict(native_detached=True, unscored_retirement=self.native_abandoned)
        timing = None
        if self.api_timing is not None:
            admission = EpisodeApiAdmission(self.api_timing.path)
            with admission.guard():
                timing = self.api_timing.snapshot()
                if not timing.get('transport_quiescent_confirmed'):
                    raise PublicError('api_transport_not_quiescent',
                        'Cannot confirm provider requests ended; retain the owner for diagnosis.', 503)
                if self.unknown_api_policy in {'preserve_world','resume_closed_unknown'} and timing.get('uncertain'):
                    # Do not rewrite unknown outcomes or remove this room from
                    # the shared barrier. Siblings may wait until diagnosis.
                    raise PublicError('api_timing_uncertain',
                        'Provider outcome requires diagnosis; preserve the original world and ledger.', 503)
                admission.close_locked(reason=reason, monotonic=self.clock())
        self.status = 'faulted'
        try:
            self.runtime.seal()  # Existing per-room seal removes its barrier membership.
        except Exception as exc:
            self._log('infrastructure_error', operation='abandon', error=repr(exc))
            raise PublicError('native_retirement_unconfirmed', 'Native room retirement is unconfirmed.', 503) from exc
        self.native_abandoned = True
        private_write(self.output / 'abandoned-native.private.json', dict(identity=asdict(self.identity),
            reason=reason, native_detached=True, scored=False, api_timing=timing))
        self._log('native_abandoned', reason=reason, scored=False)
        return dict(native_detached=True, unscored_retirement=True)

    def finish(self, summary='', *, reason='agent_finish'):
        self._check_action_batch_idle()
        self._require_started()
        if not isinstance(summary, str) or len(summary) > 10000:
            raise PublicError('invalid_summary', 'A short text summary is required.', 400)
        if self.status == 'running':
            self._await_api_classification()
            if self.timeout_seconds is not None and self.elapsed() >= self.timeout_seconds:
                if self._seal('budget_exhausted', 'effective_time_budget' if self.budget_policy == 'effective_time_graceful_v1' else 'wall_time_budget', summary) is False:
                    self._seal('finished', reason, summary)
            else:
                self._seal('finished', reason, summary)
        elif self.status not in ('finished', 'done', 'give_up', 'budget_exhausted'):
            raise PublicError('environment_unavailable', 'The environment cannot finish normally.', 503)
        return dict(stopped=True, state=self.state())

    def terminal(self, kind, summary=''):
        self._check_action_batch_idle()
        self._require_started()
        if self.recovery_id is not None and self.status == 'running':
            raise PublicError('recovery_in_progress', 'The controller is reconnecting; observe again afterwards.')
        if kind not in ('done', 'give_up') or not isinstance(summary, str) or len(summary) > 10000:
            raise PublicError('invalid_terminal_request', 'Choose Done or Give up with a short explanation.', 400)
        if self.status == 'running':
            self._await_api_classification()
            self.model_stop = kind
            if self.timeout_seconds is not None and self.elapsed() >= self.timeout_seconds:
                if self._seal('budget_exhausted', 'effective_time_budget' if self.budget_policy == 'effective_time_graceful_v1' else 'wall_time_budget', summary) is False:
                    self._seal(kind, 'model_' + kind, summary)
            else:
                self._seal(kind, 'model_' + kind, summary)
        elif self.status not in ('finished', 'done', 'give_up', 'budget_exhausted'):
            raise PublicError('environment_unavailable', 'The environment cannot stop normally.', 503)
        return dict(stopped=True, state=self.state())

    def evaluate(self):
        """Controller-only: score an immutable native terminal state once."""
        if self.status not in ('finished', 'done', 'give_up', 'budget_exhausted'):
            raise ValueError('Only a sealed, non-faulted episode can be evaluated')
        if self.authoritative is not None:
            return deepcopy(self.authoritative)
        if not self.terminal_snapshot_ready:
            raise ValueError('Missing immutable native terminal snapshot')
        native = deepcopy(self.terminal_native)
        scoring = score_native_terminal(native, task_id=self.identity.task_id, variant=self.identity.variant)
        result = dict(asdict(self.identity), success=native['success'],
            native_success=native['success'], model_success=(self.model_stop == 'done') if self.model_stop else None,
            model_stop=self.model_stop,
            condition=self.condition, steps=self.steps, termination=self.status,
            terminal_snapshot=deepcopy(self.terminal_metadata),
            validation_only=self.validation_only, scientific_evaluation=not self.validation_only,
            backend='isaaclab_physx', evidence=deepcopy(native))
        result.update(scoring)
        private_write(self.output / 'authoritative-evaluation.json', result)
        self.authoritative = result
        return deepcopy(result)
