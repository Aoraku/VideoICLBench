"""Future-only RoboDawn decision-turn context. No model, GUI, or network calls.

A decision contains model-authored scene/progress/memory/plan/commands together.
Only completed physical decisions consume the twelve-turn history. Read-only
receipts use a separate bounded queue. Unresolved decisions are protected until
explicit host reconciliation; they are never replayed or evicted here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import base64
import json
import math
import os
from pathlib import Path
import re

from .embodied_public_observation import public_depth_measurement
from .robodawn_context import (
    ContextOverflow, ContextPolicyError, ImageAnchor, _image_sha, _public,
    _reported_measurement, _short_measured,
)

VERSION = 'robodawn-single-commit-context-v2'
DECISION_FIELDS = ('scene', 'progress', 'memory', 'plan', 'commands')
_ABSENT = object()
_BATCH_RECEIPT_COLUMNS = ('index', 'status', 'step', 'left', 'right',
    'tracking_error_m', 'orientation_error_rad', 'executed_action', 'control_feedback')
_CONTROL_COLUMNS = ('status', 'reason', 'requested_delta_m', 'actual_delta_m',
    'position_error_m', 'orientation_error_rad', 'consecutive_ik_refusals')
_PAIR_FEEDBACK_CONTRACT = dict(
    completion='completed means receipt confirmed, not achieved motion or task success',
    action_columns=['left', 'right', 'step_mm', 'rotation_deg'],
    receipt_columns=list(_BATCH_RECEIPT_COLUMNS), control_columns=list(_CONTROL_COLUMNS),
    mapping='index addresses requested commands[0].action_rows; executed_action "=" exactly matches that row, otherwise contains returned action-column values; left/right are control rows',
    missing='omitted trailing columns or {not_reported:true} mean unavailable; null and zero retain their returned meanings',
    equals_marker='error map "=" exactly equals the corresponding left/right control position_error_m or orientation_error_rad',
    precision=dict(position_m=0.0001, angle_rad=0.001, approximate_display_only=True),
    exact='Exact already-public values remain in completed history; zero displayed delta may be nonzero below0.05mm, never inferred from missing data',
    scope='already-public feedback only; null control_feedback means the whole returned packet was null; action_rows is display only, model commands require actions objects')


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _text_message(value, role='user'):
    return dict(role=role, content=[dict(type='input_text', text=value if isinstance(value, str) else _json(value))])


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
        raise ContextPolicyError('Bounded path-independent decision/event ID required')
    return value


def _no_rich(value):
    text = _json(value)
    if re.search(r'data:image/|depth_m_base64|encrypted_content', text):
        raise ContextPolicyError('Keep images/dense sensor payloads out of decision history and notes')
    return text


@dataclass(frozen=True)
class TurnPolicy:
    max_turns: int = 12
    max_readonly_receipts: int = 4
    max_commands: int = 1
    memory_max_chars: int = 2500
    memory_target_words: int = 120
    window_tokens: int = 128000
    compact_trigger_tokens: int = 96000
    cache_breakpoint_enabled: bool = False
    provider_cache_breakpoint_capability: bool = False
    lean_public_input: bool = False

    def __post_init__(self):
        for key in ('max_turns', 'max_readonly_receipts', 'max_commands', 'memory_max_chars',
                    'memory_target_words', 'window_tokens', 'compact_trigger_tokens'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ContextPolicyError(key + ' must be a positive integer')
        if self.max_turns > 12 or self.max_readonly_receipts > 12:
            raise ContextPolicyError('At most twelve decision turns and twelve readonly receipts')
        if self.max_commands != 1:
            raise ContextPolicyError('Single-Commit policy requires max_commands=1; old batch configurations cannot migrate silently')
        if self.memory_max_chars > 2500 or self.compact_trigger_tokens >= self.window_tokens:
            raise ContextPolicyError('Memory cap <=2500 and compact trigger <window required')
        if type(self.cache_breakpoint_enabled) is not bool or type(self.provider_cache_breakpoint_capability) is not bool:
            raise ContextPolicyError('Explicit boolean cache capability and opt-in required')
        if type(self.lean_public_input) is not bool:
            raise ContextPolicyError('lean_public_input must be an explicit boolean')
        if self.cache_breakpoint_enabled and not self.provider_cache_breakpoint_capability:
            raise ContextPolicyError('Cannot request an explicit cache breakpoint without provider capability declaration')


@dataclass
class TurnBuild:
    items: list
    tools: list
    estimated_tokens: int
    compaction_needed: bool
    static_prefix_hash: str
    cache_breakpoint: dict
    physical_turn_count: int
    readonly_count: int
    protected_decision_ids: list
    memory_words: int
    memory_target_exceeded: bool
    dropped_readonly_ids: list
    demo_inspection_count: int = 0

    def to_dict(self):
        return deepcopy(asdict(self))


class TurnContext:
    def __init__(self, identity, instruction, developer, tools, *, archive_dir,
                 policy=None, token_counter=None):
        if not isinstance(identity, dict) or not identity:
            raise ContextPolicyError('Stable nonempty episode/session identity required')
        if not isinstance(instruction, (str, list)) or not isinstance(developer, str) or not isinstance(tools, list):
            raise ContextPolicyError('Instruction string/messages, developer string and tools list required')
        self.policy = policy or TurnPolicy()
        self._identity, self._instruction, self._developer, self._tools = deepcopy((identity, instruction, developer, tools))
        _json([identity, instruction, developer, tools])
        self._counter = token_counter
        self._archive_dir = Path(archive_dir)
        if self._archive_dir.is_symlink():
            raise ContextPolicyError('Archive directory must not be a symlink')
        self._archive_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._sequence, self._archives, self._seen = 0, [], []
        self._turns, self._readonly, self._protected = [], [], {}
        self._memory, self._demo, self._current, self._public = '', [], None, None
        self._demo_info, self._inspection = None, []
        self._history_refs, self._history_selection = [], None
        self._camera_views = None
        self._public_gui_state = None
        self._prefix_frozen = False
        self._prefix_hash = None

    @property
    def identity(self):
        return deepcopy(self._identity)

    @property
    def notes(self):
        return self._memory

    @property
    def memory(self):
        return self._memory

    @property
    def latest_public_observation(self):
        return deepcopy(self._public)

    @property
    def protected_decision_ids(self):
        return list(self._protected)

    def set_notes(self, memory):
        if not isinstance(memory, str) or not memory.strip():
            raise ContextPolicyError('Every decision requires a nonempty model-authored memory')
        if len(memory) > self.policy.memory_max_chars:
            raise ContextPolicyError('Model memory exceeds character cap; no silent clipping of coordinates')
        _no_rich(memory)
        self._memory = memory

    def _anchor(self, anchor, kind):
        if not isinstance(anchor, ImageAnchor) or anchor.kind != kind or _image_sha(anchor.image_item) != anchor.sha256:
            raise ContextPolicyError('Image role/decoded-byte SHA mismatch')
        if type(anchor.token_cost) is not int or anchor.token_cost < 0:
            raise ContextPolicyError('Explicit nonnegative image token cost required')
        if kind == 'gui' and (not isinstance(anchor.frame_id, str) or not anchor.frame_id):
            raise ContextPolicyError('Current GUI must identify its returned frame')
        if kind == 'demo' and (not isinstance(anchor.source_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', anchor.source_sha256)):
            raise ContextPolicyError('Demo must pin the actual assigned source SHA')
        return deepcopy(anchor)

    def set_demo_anchors(self, anchors):
        if not isinstance(anchors, (list, tuple)):
            raise ContextPolicyError('Demo anchors must be an ordered list')
        clean, seen, frames_at_time, source_sha = [], {}, {}, None
        for anchor in anchors:
            a = self._anchor(anchor, 'demo')
            if source_sha is not None and source_sha != a.source_sha256:
                raise ContextPolicyError('All demo anchors must use the single assigned video source')
            source_sha = a.source_sha256
            if type(a.seconds) not in (int, float) or not math.isfinite(a.seconds) or a.seconds < 0:
                raise ContextPolicyError('Explicit finite nonnegative demo timestamp required')
            time_key = (a.source_sha256, a.seconds)
            if time_key in frames_at_time and frames_at_time[time_key] != a.sha256:
                raise ContextPolicyError('Assigned video timestamp has conflicting frame bytes')
            frames_at_time[time_key] = a.sha256
            key = (a.source_sha256, a.seconds, a.sha256)
            if key not in seen:
                clean.append(a); seen[key] = a
        # Volatile call IDs are deliberately excluded from stable demo identity.
        canonical = lambda values: [_demo_message(a) for a in values]
        if self._prefix_frozen and canonical(clean) != canonical(self._demo):
            raise ContextPolicyError('Fixed demo anchors cannot change after first decision build')
        self._validate_assigned_demo_frames(clean)
        self._demo = clean

    def set_demo_info(self, info):
        clean = _demo_info_projection(info)
        if self._prefix_frozen and clean != self._demo_info:
            raise ContextPolicyError('Assigned demo metadata is fixed after first decision build')
        previous = self._demo_info
        self._demo_info = clean
        try:
            self._validate_assigned_demo_frames(self._demo)
            self._validate_assigned_demo_frames(self._inspection)
        except ContextPolicyError:
            self._demo_info = previous
            raise

    def _validate_assigned_demo_frames(self, anchors):
        if not anchors or self._demo_info is None:
            return
        if not self._demo_info['available']:
            raise ContextPolicyError('No video is assigned to this input condition')
        for a in anchors:
            if a.source_sha256 != self._demo_info['source_sha256']:
                raise ContextPolicyError('Demo frame does not belong to the assigned video SHA')
            if type(a.seconds) not in (int, float) or not math.isfinite(a.seconds) or not 0 <= a.seconds < self._demo_info['duration_seconds']:
                raise ContextPolicyError('Demo timestamp must be inside the assigned video duration')

    def set_demo_inspection(self, anchors):
        if not isinstance(anchors, (list, tuple)) or len(anchors) > 12:
            raise ContextPolicyError('The most recent inspection must contain zero to twelve demo frames')
        if anchors and (self._demo_info is None or not self._demo_info['available']):
            raise ContextPolicyError('On-demand demo inspection requires assigned public video metadata')
        clean, seen, times = [], set(), {}
        for anchor in anchors:
            a = self._anchor(anchor, 'demo')
            self._validate_assigned_demo_frames([a])
            key = (a.source_sha256, a.seconds, a.sha256)
            if a.seconds in times and times[a.seconds] != a.sha256:
                raise ContextPolicyError('One demo inspection timestamp has conflicting frame bytes')
            times[a.seconds] = a.sha256
            if key not in seen:
                clean.append(a); seen.add(key)
        self._inspection = clean

    def clear_retrieval_views(self):
        """Host consumption after a successful response saved its same-reply notes.

        Never call while retrying an API request. Source video, fixed materials,
        public history/media and raw archives remain available for future queries.
        """
        info = dict(demo_inspection_frames=len(self._inspection),
            history_selection_count=self._history_selection['count'] if self._history_selection else 0,
            source_materials_retained=True)
        self._inspection = []
        self._history_selection = None
        return info

    def set_current_gui(self, anchor, public_observation=None, camera_views=None, public_gui_state=None):
        a = self._anchor(anchor, 'gui')
        public = _public(public_observation) if public_observation is not None else None
        if public_observation is not None and public is None:
            raise ContextPolicyError('Expected an existing public observation, not hidden simulator state')
        camera_projection = _camera_view_projection(camera_views)
        gui_projection = _public_gui_state_projection(public_gui_state)
        self._current, self._public, self._camera_views = a, public, camera_projection
        self._public_gui_state = gui_projection

    def _archive(self, kind, record):
        data = _json(dict(schema=VERSION, kind=kind, record=record)).encode()
        self._sequence += 1
        name = f'turn-{self._sequence:08d}.private.json'
        target = self._archive_dir / name
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError:
            self._sequence -= 1
            raise ContextPolicyError('Archive already exists; restore checkpoint rather than replay') from None
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        ref = dict(name=name, sha256=hashlib.sha256(data).hexdigest())
        self._archives.append(ref)
        return deepcopy(ref)

    def _decision(self, decision):
        if not isinstance(decision, dict) or set(decision) != set(DECISION_FIELDS):
            raise ContextPolicyError('Decision must contain exactly scene/progress/memory/plan/commands')
        for key in ('scene', 'progress', 'plan'):
            if not isinstance(decision[key], (str, list, dict)):
                raise ContextPolicyError('Scene/progress/plan must be model-authored text/JSON')
        if not isinstance(decision['memory'], str) or not decision['memory'].strip() or len(decision['memory']) > self.policy.memory_max_chars:
            raise ContextPolicyError('Nonempty bounded memory required in the same decision')
        commands = decision['commands']
        if not isinstance(commands, list) or len(commands) != 1:
            raise ContextPolicyError('Exactly one semantic command per decision: one Commit, one sensor query, or one terminal')
        _validate_single_command(commands[0])
        if commands[0]['type'] == 'demo_frames':
            if self._demo_info is None or not self._demo_info['available']:
                raise ContextPolicyError('No assigned video is available for this decision')
            if any(t >= self._demo_info['duration_seconds'] for t in commands[0]['seconds']):
                raise ContextPolicyError('Requested demo timestamp is outside the assigned video')
        if len(_no_rich(commands).encode()) > 8192:
            raise ContextPolicyError('Commands exceed bounded decision payload')
        _no_rich(decision['memory'])
        # Scene/plan are model interpretations, not sensor observations.
        return {**deepcopy(decision), **{k: (decision[k] if isinstance(decision[k], str) else _json(decision[k]))[:1000] for k in ('scene', 'progress', 'plan')}}

    def record_decision(self, decision, results, *, physical, decision_id, state='completed', step=None, tcp=None):
        _id(decision_id)
        if decision_id in self._seen:
            raise ContextPolicyError('Decision already recorded; never replay an accepted/unknown command')
        if type(physical) is not bool or state not in ('completed', 'pending', 'unknown', 'error', 'failed', 'blocked'):
            raise ContextPolicyError('Explicit physical flag and recognized decision state required')
        if not isinstance(results, list) or step is not None and (type(step) is not int or step < 0):
            raise ContextPolicyError('Result list and nullable nonnegative native step required')
        parsed = self._decision(decision)
        # Use the established typed public projection for TCP; unknown fields are dropped.
        tcp_public = _short_measured(_public(tcp)) if tcp is not None else None
        if tcp is not None and not tcp_public:
            raise ContextPolicyError('TCP must come from a complete returned public observation')
        archive = self._archive('decision', dict(decision=decision, results=results, state=state,
            physical=physical, step=step, tcp=tcp, decision_id=decision_id))
        record = dict(decision_id=decision_id, commands=parsed['commands'], results=_outcomes(results),
            steps_after=step, tcp=tcp_public, state=state, physical=physical, archive=archive)
        measurements = _measurements(results)
        if measurements:
            record['reported_measurements'] = measurements
        number = len(self._history_refs) + 1
        record['decision_number'] = number
        self._write_history_entry(record, observed_before=self._capture_history_observation())
        self.set_notes(parsed['memory'])
        self._seen.append(decision_id)
        if state != 'completed':
            self._protected[decision_id] = record
        elif physical:
            self._turns.append(record); self._turns = self._turns[-self.policy.max_turns:]
        else:
            self._readonly.append(record); self._readonly = self._readonly[-self.policy.max_readonly_receipts:]
        return deepcopy(record)

    def record_readonly(self, event, *, event_id, state='completed'):
        _id(event_id)
        if event_id in self._seen or not isinstance(event, dict):
            raise ContextPolicyError('Unique readonly event ID and object required')
        if state not in ('completed', 'pending', 'unknown', 'error', 'failed', 'blocked'):
            raise ContextPolicyError('Recognized readonly state required')
        archive = self._archive('readonly', dict(event_id=event_id, event=event, state=state))
        measurements = _measurements(event)
        record = dict(decision_id=event_id, state=state, physical=False,
            results=_outcomes([event]), archive=archive)
        if measurements:
            record['reported_measurements'] = measurements
        self._seen.append(event_id)
        if state != 'completed':
            self._protected[event_id] = record
        else:
            self._readonly.append(record); self._readonly = self._readonly[-self.policy.max_readonly_receipts:]
        return deepcopy(record)

    def reconcile(self, decision_id, *, state='completed', results=None, step=None, tcp=None, physical=None):
        if decision_id not in self._protected or state not in ('completed', 'pending', 'unknown'):
            raise ContextPolicyError('Only the host may explicitly reconcile a known unresolved decision')
        record = deepcopy(self._protected[decision_id])
        if physical is not None:
            if type(physical) is not bool:
                raise ContextPolicyError('Explicit actual physical flag must be boolean')
            record['physical'] = physical
        if results is not None:
            if not isinstance(results, list):
                raise ContextPolicyError('Result list required')
            record['results'] = _outcomes(results)
            measurements = _measurements(results)
            if measurements:
                record['reported_measurements'] = measurements
        if step is not None:
            if type(step) is not int or step < 0:
                raise ContextPolicyError('Native step must be nonnegative')
            record['steps_after'] = step
        if tcp is not None:
            record['tcp'] = _short_measured(_public(tcp))
        record['state'] = state
        record['result_archive'] = self._archive('reconcile', dict(decision_id=decision_id, record=record,
            returned_results=results, returned_tcp=tcp))
        # Host readonly events are not model decision turns and have no history index.
        # Preserve their explicit reconciliation without fabricating an observed decision.
        if 'decision_number' in record:
            self._write_history_entry(record)
        if state != 'completed':
            self._protected[decision_id] = record
            return deepcopy(record)
        del self._protected[decision_id]
        queue = self._turns if record['physical'] else self._readonly
        queue.append(record)
        limit = self.policy.max_turns if record['physical'] else self.policy.max_readonly_receipts
        del queue[:-limit]
        return deepcopy(record)

    @property
    def history_catalog(self):
        completed = [r['decision_number'] for r in self._history_refs if r['state'] == 'completed']
        return dict(total=len(self._history_refs), completed_count=len(completed),
            first_completed=completed[0] if completed else None,
            last_completed=completed[-1] if completed else None,
            retrievable='Only completed past decisions from this same episode; no private archive access.')

    def _history_directory(self, name):
        directory = self._archive_dir / name
        if directory.is_symlink():
            raise ContextPolicyError('History namespace must not be a symlink')
        directory.mkdir(mode=0o700, exist_ok=True)
        return directory

    def _immutable_history_file(self, directory, name, data):
        target = directory / name
        if target.is_symlink():
            raise ContextPolicyError('History file must not be a symlink')
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError:
            if not target.is_file() or target.read_bytes() != data:
                raise ContextPolicyError('History content-addressed file changed')
        else:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
        return target

    def _capture_history_observation(self):
        image = None
        if self._current is not None:
            a = self._anchor(self._current, 'gui')
            url = a.image_item['image_url']; raw = base64.b64decode(url.split(',', 1)[1], validate=True)
            if len(raw) > 16 * 1024 * 1024:
                raise ContextPolicyError('Historical GUI image exceeds bounded local media size')
            self._immutable_history_file(self._history_directory('history-media'), a.sha256 + '.image', raw)
            image = dict(sha256=a.sha256, name=a.sha256+'.image',
                mime_type=url.split(';',1)[0].split(':',1)[1], token_cost=a.token_cost,
                detail=a.image_item.get('detail', 'high'), frame_id=a.frame_id)
        return dict(image=image, public_observation=deepcopy(self._public),
            camera_views=deepcopy(self._camera_views), public_gui_state=deepcopy(self._public_gui_state))

    def _write_history_entry(self, record, observed_before=None):
        number = record['decision_number']
        if observed_before is None:
            observed_before = self._read_history_entry(number)['observed_before']
        # Exact raw provider/tool archives and model reasoning/notes are intentionally not queryable.
        entry = {k:deepcopy(record[k]) for k in ('decision_id', 'decision_number', 'commands', 'results',
            'steps_after', 'tcp', 'state', 'physical', 'reported_measurements') if k in record}
        entry.update(schema='same-episode-public-history-v1', identity_sha256=_hash(self._identity),
            observed_before=deepcopy(observed_before))
        data = _json(entry).encode(); digest = hashlib.sha256(data).hexdigest()
        name = f'{number:08d}-{digest}.json'
        self._immutable_history_file(self._history_directory('history-index'), name, data)
        ref = dict(decision_number=number, state=record['state'], name=name, sha256=digest)
        if number == len(self._history_refs) + 1:
            self._history_refs.append(ref)
        elif 1 <= number <= len(self._history_refs):
            self._history_refs[number-1] = ref
        else:
            raise ContextPolicyError('Public history decision sequence mismatch')

    def _read_history_entry(self, number):
        if type(number) is not int or not 1 <= number <= len(self._history_refs):
            raise ContextPolicyError('History decision is outside this episode index')
        ref = self._history_refs[number-1]; name = ref.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[0-9]{8}-[0-9a-f]{64}\.json', name):
            raise ContextPolicyError('Unsafe public history reference')
        f = self._history_directory('history-index') / name
        if f.is_symlink() or not f.is_file():
            raise ContextPolicyError('Public history index is missing or unsafe')
        raw = f.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref.get('sha256'):
            raise ContextPolicyError('Public history entry integrity mismatch')
        entry = json.loads(raw)
        if entry.get('schema') != 'same-episode-public-history-v1' or entry.get('identity_sha256') != _hash(self._identity):
            raise ContextPolicyError('History entry belongs to a different episode namespace')
        if entry.get('decision_number') != number or entry.get('state') != ref.get('state'):
            raise ContextPolicyError('Public history decision identity/state mismatch')
        return entry

    def _read_history_media(self, ref):
        sha = ref.get('sha256'); name = ref.get('name')
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha) or name != sha + '.image':
            raise ContextPolicyError('Unsafe history media reference')
        if not isinstance(ref.get('mime_type'), str) or not re.fullmatch(r'image/[A-Za-z0-9.+-]+', ref['mime_type']):
            raise ContextPolicyError('Invalid history image MIME type')
        if type(ref.get('token_cost')) is not int or ref['token_cost'] < 0:
            raise ContextPolicyError('History image token cost is invalid')
        f = self._history_directory('history-media') / name
        if f.is_symlink() or not f.is_file() or f.stat().st_size > 16*1024*1024:
            raise ContextPolicyError('History media file is missing, unsafe, or too large')
        raw = f.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ContextPolicyError('History image integrity mismatch')
        return dict(type='input_image', image_url='data:'+ref['mime_type']+';base64,'+
            base64.b64encode(raw).decode(), detail=ref.get('detail', 'high'))

    def inspect_history(self, start, count, include_images=False):
        _validate_history_selection(start, count, include_images)
        if start + count - 1 > len(self._history_refs):
            raise ContextPolicyError('Requested history is outside this episode completed range')
        numbers = list(range(start, start+count))
        for number in numbers:
            entry = self._read_history_entry(number)
            if entry['state'] != 'completed':
                raise ContextPolicyError('Pending/unknown/current decision cannot be inspected as completed history')
            if include_images and entry.get('observed_before', {}).get('image'):
                self._read_history_media(entry['observed_before']['image'])
        self._history_selection = dict(start=start, count=count, include_images=include_images)
        return dict(ok=True, start=start, count=count, include_images=include_images,
            decision_numbers=numbers, selection_sha256=_hash(self._history_selection))

    def _history_items(self):
        if self._history_selection is None:
            return [], {}
        selection = self._history_selection
        entries = [self._read_history_entry(n) for n in range(selection['start'], selection['start']+selection['count'])]
        if any(e['state'] != 'completed' for e in entries):
            raise ContextPolicyError('Only completed same-episode public history is visible')
        public = []
        images, costs = [], {}
        for entry in entries:
            clean = deepcopy(entry); clean.pop('identity_sha256', None)
            ref = clean['observed_before'].pop('image', None)
            if ref is not None:
                clean['observed_before']['gui_image_sha256'] = ref['sha256']
                clean['observed_before']['gui_frame_id'] = ref['frame_id']
            public.append(clean)
            if selection['include_images'] and ref is not None:
                block = self._read_history_media(ref)
                images.append(dict(role='user', content=[dict(type='input_text', text=_json(dict(
                    image_role='episode_history', decision_number=entry['decision_number'],
                    frame_id=ref['frame_id'], sha256=ref['sha256'], historical_observation=True))), block]))
                costs[ref['sha256']] = max(costs.get(ref['sha256'], 0), ref['token_cost'])
        return [_text_message(dict(inspected_episode_history=dict(entries=public,
            include_images=selection['include_images'])))] + images, costs

    def _prefix(self):
        instruction = [_text_message(self._instruction)] if isinstance(self._instruction, str) else deepcopy(self._instruction)
        return ([_text_message(self._developer, 'developer')] + instruction +
            [_text_message(dict(episode_identity=self._identity, identity_sha256=_hash(self._identity)))] +
            [_text_message(dict(assigned_demo_info=self._demo_info))] +
            [_demo_message(a) for a in self._demo] +
            [_text_message(dict(static_materials_end=True, notice='Current episode memory, history and returned GUI follow.'))])

    def _estimate(self, items):
        if self._counter:
            value = self._counter(deepcopy(items), deepcopy(self._tools))
            if type(value) is not int or value < 0:
                raise ContextPolicyError('Complete token estimator must return a nonnegative integer')
            return value
        images = 0
        costs = {}
        for a in [*self._demo, *self._inspection, *([self._current] if self._current else [])]:
            costs[a.sha256] = max(costs.get(a.sha256, 0), a.token_cost)
        for sha, cost in getattr(self, '_history_build_costs', {}).items():
            costs[sha] = max(costs.get(sha, 0), cost)
        def strip(value):
            nonlocal images
            if isinstance(value, dict):
                if value.get('type') == 'input_image':
                    sha = _image_sha(value)
                    if sha not in costs:
                        raise ContextPolicyError('Unregistered image in context')
                    images += costs[sha]
                    return dict(type='input_image', sha256=sha, detail=value.get('detail'))
                return {k: strip(v) for k, v in value.items()}
            if isinstance(value, list):
                return [strip(v) for v in value]
            return value
        return len(_json(dict(input=strip(items), tools=self._tools)).encode()) + images

    def build(self):
        if self._current is None:
            raise ContextPolicyError('One current returned GUI image is mandatory')
        prefix = self._prefix()
        prefix_hash = _hash(dict(items=prefix, tools=self._tools))
        if self._prefix_hash is not None and prefix_hash != self._prefix_hash:
            raise ContextPolicyError('Fixed prefix changed within the episode')
        self._prefix_hash, self._prefix_frozen = prefix_hash, True
        current = _text_message(dict(image_role='current_gui', sha256=self._current.sha256,
            frame_id=self._current.frame_id, call_id=self._current.call_id))
        current['content'].append(deepcopy(self._current.image_item))
        history_items, history_costs = self._history_items()
        inspection = [_demo_revisit_message(a) for a in self._inspection] + history_items
        self._history_build_costs = history_costs
        protected = list(self._protected.values())
        def assemble(active_readonly):
            calibrations = {}
            turns = deepcopy(self._turns)
            reads = deepcopy(active_readonly)
            selected_images_and_history = deepcopy(inspection)
            public = deepcopy(self._public)
            if self.policy.lean_public_input:
                turns = _model_measurement_projection([_lean_history_record(row, physical=True) for row in turns], calibrations)
                # Compact action -> outcome -> TCP summaries, independent of audit storage.
                reads = _model_measurement_projection([_lean_history_record(row, physical=False) for row in reads], calibrations)
                for message in selected_images_and_history:
                    block = message.get('content', [{}])[0]
                    if block.get('type') == 'input_text' and 'inspected_episode_history' in block.get('text', ''):
                        block['text'] = _json(_model_measurement_projection(json.loads(block['text']), calibrations))
                public = _lean_public_observation(public)
            tail = [_text_message(dict(model_memory=self._memory,
                memory_target_words=self.policy.memory_target_words, memory_max_chars=self.policy.memory_max_chars,
                physical_decision_history=turns, unresolved_decisions=protected, history_catalog=self.history_catalog,
                no_replay='Unresolved commands require explicit host reconciliation; never repeat accepted or unknown actions.'))]
            current_public = dict(current_public_observation=public,
                current_gui_camera_views=self._camera_views, current_public_gui_state=self._public_gui_state)
            if self.policy.lean_public_input:
                # Completed records are independent messages before the changing GUI.
                # Appending a decision preserves every older retained message; bounded
                # eviction naturally changes that prefix and never restores stale data.
                order = {decision_id: i for i, decision_id in enumerate(self._seen)}
                completed = [(order[row['decision_id']], 'physical_decision_history', shown)
                    for row, shown in zip(self._turns, turns)]
                completed += [(order[row['decision_id']], 'readonly_receipts', shown)
                    for row, shown in zip(active_readonly, reads)]
                completed.sort(key=lambda entry: entry[0])
                history_messages = [_text_message({kind: [shown]}) for _, kind, shown in completed]
                current_view = deepcopy(current)
                current_view['content'][0]['text'] = _json(dict(image_role='current_gui', frame_id=self._current.frame_id))
                history = dict(history_catalog=self.history_catalog)
                if any(shown.get('results') and any('receipt_rows' in r.get('action_batch', {})
                        for r in shown['results']) for _, _, shown in completed):
                    history['batch_feedback_contract'] = deepcopy(_PAIR_FEEDBACK_CONTRACT)
                if protected:
                    history['unresolved_decisions'] = protected  # Full identity/state: never conceal uncertain commands.
                if calibrations:
                    history.update(measurement_calibrations=calibrations,
                        calibration_reference_contract='Every calibration_ref resolves to measurement_calibrations[ref] in this request; frame and camera are exact.')
                return (prefix + history_messages + [current_view, _text_message(current_public), _text_message(history)] +
                    selected_images_and_history + [_text_message(dict(model_memory=self._memory))])
            if calibrations:
                current_public.update(measurement_calibrations=calibrations,
                    calibration_reference_contract='Each calibration_ref resolves to measurement_calibrations[ref] in this request, with its exact frame_id and camera. No external lookup or recomputation is needed.')
            return prefix + tail + ([_text_message(dict(readonly_receipts=reads))] if reads else []) + selected_images_and_history + [current, _text_message(current_public)]
        # Physical decision history and unresolved state are never silently removed for budget.
        mandatory = assemble([])
        if self._estimate(mandatory) > self.policy.window_tokens:
            raise ContextOverflow(self._estimate(mandatory), self.policy.window_tokens)
        readonly, dropped = list(self._readonly), []
        items = assemble(readonly); count = self._estimate(items)
        while count > self.policy.compact_trigger_tokens and readonly:
            dropped.append(readonly.pop(0)['decision_id']); items = assemble(readonly); count = self._estimate(items)
        if count > self.policy.window_tokens:
            raise ContextOverflow(count, self.policy.window_tokens)
        self._readonly = readonly
        candidate = dict(enabled=self.policy.cache_breakpoint_enabled,
            provider_capability_declared=self.policy.provider_cache_breakpoint_capability,
            applied_to_wire=False, empirically_validated=False, boundary_message_index=len(prefix)-1,
            static_prefix_hash=prefix_hash, boundary_content_index=0, includes_tools=True,
            warning='Candidate only. Transport must validate the exact provider cache protocol before applying.')
        if self.policy.lean_public_input:
            candidate['history_prefix_window'] = dict(
                ordering='completed_chronological_messages_before_current_gui',
                physical_decision_numbers=[r.get('decision_number') for r in self._turns],
                readonly_decision_numbers=[r.get('decision_number') for r in readonly],
                bounded_eviction_can_invalidate_prefix=True, cache_hit_guaranteed=False)
        words = len(self._memory.split())
        return TurnBuild(items, deepcopy(self._tools), count, count > self.policy.compact_trigger_tokens,
            prefix_hash, candidate, len(self._turns), len(readonly), list(self._protected), words,
            words > self.policy.memory_target_words, dropped, len(self._inspection))

    def export_state(self):
        state = dict(schema=VERSION, identity=deepcopy(self._identity), instruction=deepcopy(self._instruction),
            developer=self._developer, tools=deepcopy(self._tools), policy=asdict(self.policy),
            memory=self._memory, turns=deepcopy(self._turns), readonly=deepcopy(self._readonly),
            protected=deepcopy(self._protected), seen=deepcopy(self._seen), sequence=self._sequence,
            archives=deepcopy(self._archives), demo=[asdict(a) for a in self._demo],
            demo_info=deepcopy(self._demo_info), demo_inspection=[asdict(a) for a in self._inspection],
            public_history_refs=deepcopy(self._history_refs), history_selection=deepcopy(self._history_selection),
            current=asdict(self._current) if self._current else None, public_observation=deepcopy(self._public),
            camera_views=deepcopy(self._camera_views), public_gui_state=deepcopy(self._public_gui_state),
            prefix_frozen=self._prefix_frozen, prefix_hash=self._prefix_hash)
        state['state_sha256'] = _hash(state)
        return state

    @classmethod
    def from_state(cls, state, *, archive_dir, token_counter=None, expected_identity=None):
        state = deepcopy(state)
        digest = state.pop('state_sha256', None)
        if digest != _hash(state) or state.get('schema') != VERSION:
            raise ContextPolicyError('Checkpoint hash/schema mismatch')
        if expected_identity is not None and state['identity'] != expected_identity:
            raise ContextPolicyError('Episode/session identity mismatch')
        ctx = cls(state['identity'], state['instruction'], state['developer'], state['tools'],
            archive_dir=archive_dir, policy=TurnPolicy(**state['policy']), token_counter=token_counter)
        for ref in state['archives']:
            name = ref['name']
            if not re.fullmatch(r'turn-[0-9]{8}\.private\.json', name):
                raise ContextPolicyError('Unsafe archive reference')
            f = ctx._archive_dir / name
            if f.is_symlink() or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != ref['sha256']:
                raise ContextPolicyError('Private archive missing or changed; do not replay')
        expected_files = {r['name'] for r in state['archives']}
        if {f.name for f in ctx._archive_dir.glob('turn-*.private.json')} != expected_files:
            raise ContextPolicyError('Archive ahead of checkpoint; reconcile rather than replay')
        ctx._sequence, ctx._archives, ctx._seen = state['sequence'], state['archives'], state['seen']
        ctx._turns, ctx._readonly, ctx._protected = state['turns'], state['readonly'], state['protected']
        if len(ctx._turns) > ctx.policy.max_turns or len(ctx._readonly) > ctx.policy.max_readonly_receipts:
            raise ContextPolicyError('Checkpoint history exceeds policy')
        if state['memory']:
            ctx.set_notes(state['memory'])
        if state.get('demo_info') is not None:
            ctx.set_demo_info(state['demo_info'])
        ctx.set_demo_anchors([ImageAnchor(**a) for a in state['demo']])
        ctx.set_demo_inspection([ImageAnchor(**a) for a in state.get('demo_inspection', [])])
        if state['current']:
            ctx.set_current_gui(ImageAnchor(**state['current']), state['public_observation'],
                state.get('camera_views'), state.get('public_gui_state'))
        ctx._history_refs = deepcopy(state.get('public_history_refs', []))
        for number, ref in enumerate(ctx._history_refs, 1):
            if ref.get('decision_number') != number:
                raise ContextPolicyError('Public history sequence is invalid')
            entry = ctx._read_history_entry(number)
            if entry.get('observed_before', {}).get('image'):
                ctx._read_history_media(entry['observed_before']['image'])
        selection = state.get('history_selection')
        if selection is not None:
            ctx.inspect_history(selection['start'], selection['count'], selection['include_images'])
        ctx._prefix_frozen, ctx._prefix_hash = state['prefix_frozen'], state['prefix_hash']
        return ctx


def _demo_message(anchor):
    # No request/call/frame IDs: these would destroy a reusable static prefix.
    return dict(role='user', content=[dict(type='input_text', text=_json(dict(
        image_role='assigned_demo', sha256=anchor.sha256,
        source_sha256=anchor.source_sha256, seconds=anchor.seconds))), deepcopy(anchor.image_item)])


def _finite_metric(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _public_pair_receipt(row):
    """Only existing public pair actions and robot-control leaves, with hard bounds."""
    out = {k:row[k] for k in ('index', 'step') if type(row.get(k)) is int and row[k] >= 0}
    if type(row.get('status')) is str:
        out['status'] = row['status'][:48]
    action = row.get('action')
    if isinstance(action, dict):
        selected = {k:action[k] for k in ('left', 'right') if type(action.get(k)) is str and len(action[k]) <= 128}
        selected.update({k:action[k] for k in ('step_mm', 'rotation_deg') if _finite_metric(action.get(k))})
        if selected:
            out['action'] = selected
    receipt = row.get('receipt')
    if not isinstance(receipt, dict):
        return out
    safe = {}
    for key in ('tracking_error_m', 'orientation_error_rad'):
        value = receipt.get(key, _ABSENT)
        if value is None or _finite_metric(value):
            safe[key] = value
        elif isinstance(value, dict):
            safe[key] = {side:value[side] for side in ('left', 'right')
                if side in value and (value[side] is None or _finite_metric(value[side]))}
    controls = receipt.get('control_feedback')
    if controls is None and 'control_feedback' in receipt:
        safe['control_feedback'] = None
    elif isinstance(controls, dict):
        selected = {}
        for side in ('left', 'right'):
            arm = controls.get(side, _ABSENT)
            if arm is None:
                selected[side] = None
                continue
            if not isinstance(arm, dict):
                continue
            clean = {}
            for key in ('status', 'reason'):
                if key in arm and (arm[key] is None or type(arm[key]) is str):
                    clean[key] = arm[key][:240] if isinstance(arm[key], str) else None
            for key in ('requested_delta_m', 'actual_delta_m'):
                value = arm.get(key, _ABSENT)
                if value is None or isinstance(value, list) and len(value) == 3 and all(_finite_metric(n) for n in value):
                    clean[key] = deepcopy(value)
            for key in ('position_error_m', 'orientation_error_rad'):
                if key in arm and (arm[key] is None or _finite_metric(arm[key])):
                    clean[key] = arm[key]
            count = arm.get('consecutive_ik_refusals')
            if type(count) is int and 0 <= count <= 1000000000:
                clean['consecutive_ik_refusals'] = count
            if clean:
                selected[side] = clean
        safe['control_feedback'] = selected
    if safe:
        out['receipt'] = safe
    return out


def project_public_execution_results(results):
    """Pure typed projection for explicit, separately verified receipt migrations."""
    if not isinstance(results, list):
        raise ContextPolicyError('Existing public execution result list required')
    return _outcomes(results)


def project_public_pair_receipt(row):
    """One already-public browser batch pair; no simulator or archive access."""
    if not isinstance(row, dict):
        raise ContextPolicyError('Existing public batch pair object required')
    return _public_pair_receipt(row)


def _outcomes(results):
    """Framework-returned execution metadata; never convert it to task success."""
    clean = []
    for row in results[:16]:
        if not isinstance(row, dict):
            clean.append(dict(note=str(row)[:240], origin='returned_result_not_independently_verified'))
            continue
        selected = {key: deepcopy(row[key]) for key in ('ok', 'accepted', 'pending', 'physical_action', 'physical_commit','physical_action_count','requested_action_count','partial') if type(row.get(key)) in (bool, int, float)}
        for key in ('status', 'reason', 'note', 'error', 'frame_id', 'call_id', 'command'):
            if isinstance(row.get(key), str):
                selected[key] = row[key][:240]
        if isinstance(row.get('source_sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', row['source_sha256']):
            selected['source_sha256'] = row['source_sha256']
        if isinstance(row.get('demo_seconds'), list) and len(row['demo_seconds']) <= 12 and all(
                type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in row['demo_seconds']):
            selected['demo_seconds'] = deepcopy(row['demo_seconds'])
        batch = row.get('receipt') if isinstance(row.get('receipt'), dict) else row.get('action_batch')
        if isinstance(batch,dict) and (isinstance(batch.get('batch_id'),str) or isinstance(row.get('action_batch'), dict)):
            selected['action_batch'] = {k:deepcopy(batch[k]) for k in ('status','requested_count','completed_count','physical_action_count','next_index','accepted') if type(batch.get(k)) in (str,int,bool)}
            selected['action_batch'].update({k:batch[k] for k in ('partial','uncertain') if type(batch.get(k)) is bool})
            if 'uncertain_action_index' in batch and (batch['uncertain_action_index'] is None
                    or type(batch['uncertain_action_index']) is int and batch['uncertain_action_index'] >= 0):
                selected['action_batch']['uncertain_action_index'] = batch['uncertain_action_index']
            if isinstance(batch.get('receipts'),list):
                selected['action_batch']['receipts'] = [
                    _public_pair_receipt(r)
                    for r in batch['receipts'][:24] if isinstance(r,dict)]
        selected['origin'] = 'returned_execution_metadata'
        clean.append(selected)
    return clean


def _measurements(value):
    """Keep only returned numeric measurements; never recalculate or infer labels."""
    rows, seen = [], set()
    def walk(item, depth=0):
        if depth > 8 or len(rows) >= 16:
            return
        if isinstance(item, list):
            for child in item[:64]:
                walk(child, depth + 1)
        elif isinstance(item, dict):
            row = _reported_measurement(item, allow_depth_only=True)
            if row:
                source_public = public_depth_measurement(item)
                calibration = source_public.get('camera_calibration')
                if calibration:
                    row['camera_calibration'] = calibration
                for key in ('width','height','observation_tick','depth_convention','target_frame','rgb_sha256'):
                    if key in source_public:
                        row[key] = source_public[key]
                row['origin'] = 'returned_readonly_result'
                row['as_returned_not_independently_verified'] = True
                row['historical_frame_specific'] = True
                digest = _hash(row)
                if digest not in seen:
                    rows.append(row); seen.add(digest)
            for key in ('result', 'results', 'measurements', 'records'):
                if key in item:
                    walk(item[key], depth + 1)
    walk(value)
    return rows


def _camera_view_projection(raw):
    """Only the GUI's already-returned image geometry; never query or infer poses."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ContextPolicyError('Returned camera views must be an object')
    mapping = 'col=(x-image_rect.x)*native_width/image_rect.width; row=(y-image_rect.y)*native_height/image_rect.height'
    out = {}
    for name in ('head', 'left_wrist', 'right_wrist'):
        row = raw.get(name)
        if not isinstance(row, dict):
            continue
        clean = {}
        if type(row.get('available')) is bool:
            clean['available'] = row['available']
        for key in ('native_width', 'native_height'):
            if type(row.get(key)) is int and row[key] > 0:
                clean[key] = row[key]
        rect = row.get('image_rect')
        if isinstance(rect, dict):
            numbers = {k:rect[k] for k in ('x', 'y', 'width', 'height')
                if type(rect.get(k)) in (int, float) and math.isfinite(rect[k])}
            if len(numbers) == 4 and numbers['width'] > 0 and numbers['height'] > 0:
                clean['image_rect'] = numbers
        if row.get('pixel_mapping') == mapping:
            clean['pixel_mapping'] = mapping
        if clean:
            out[name] = clean
    return out


def _public_gui_state_projection(raw):
    """Already-visible budget/status only; missing fields stay unknown, never zero."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ContextPolicyError('Public GUI state must be an object')
    out = {}
    if type(raw.get('step')) is int and raw['step'] >= 0:
        out['step'] = raw['step']
    if type(raw.get('max_robot_actions')) is int and raw['max_robot_actions'] > 0:
        out['max_robot_actions'] = raw['max_robot_actions']
    status = raw.get('episode_status')
    if isinstance(status, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', status):
        out['episode_status'] = status
    return out


def _validate_single_command(command):
    if not isinstance(command, dict):
        raise ContextPolicyError('A single semantic command object is required')
    kind = command.get('type')
    fields = {
        'action': {'type', 'left', 'right', 'step_mm', 'rotation_deg'},
        'action_batch': {'type', 'actions'},
        'depth_points': {'type', 'camera', 'pixels'},
        'demo_frames': {'type', 'seconds'},
        'history': {'type', 'start', 'count', 'include_images'},
        'done': {'type', 'summary'},
        'giveup': {'type', 'reason'},
    }
    if not isinstance(kind, str) or kind not in fields or set(command) != fields[kind]:
        raise ContextPolicyError('Unknown command type or unexpected/missing public command fields')
    if kind == 'action_batch':
        actions = command['actions']
        if not isinstance(actions, list) or not 1 <= len(actions) <= 24:
            raise ContextPolicyError('One Commit accepts one to twenty-four ordered public action pairs')
        for pair in actions:
            if not isinstance(pair, dict) or set(pair) != {'left','right','step_mm','rotation_deg'}:
                raise ContextPolicyError('Batch item must be one complete public pair')
            _validate_single_command(dict(type='action', **pair))
    elif kind == 'action':
        if any(not isinstance(command[k], str) or not 1 <= len(command[k]) <= 64 for k in ('left', 'right')):
            raise ContextPolicyError('Explicit bounded left/right public action tokens required')
        if any(type(command[k]) not in (int, float) or not math.isfinite(command[k]) or command[k] < 0
               for k in ('step_mm', 'rotation_deg')):
            raise ContextPolicyError('Finite nonnegative action parameters required')
    elif kind == 'depth_points':
        if command['camera'] not in ('head', 'left_wrist', 'right_wrist'):
            raise ContextPolicyError('One public camera per sensor decision required')
        pixels = command['pixels']
        if not isinstance(pixels, list) or not 1 <= len(pixels) <= 16:
            raise ContextPolicyError('One to sixteen pixels in the single camera required')
        for pixel in pixels:
            if not isinstance(pixel, list) or len(pixel) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in pixel):
                raise ContextPolicyError('Finite nonnegative [row,col] sensor pixels required')
    elif kind == 'history':
        _validate_history_selection(command['start'], command['count'], command['include_images'])
    elif kind == 'demo_frames':
        seconds = command['seconds']
        if not isinstance(seconds, list) or not 1 <= len(seconds) <= 12 or any(
                type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in seconds):
            raise ContextPolicyError('One to twelve finite nonnegative demo timestamps required')
    else:
        key = 'summary' if kind == 'done' else 'reason'
        if not isinstance(command[key], str):
            raise ContextPolicyError('Terminal explanation must be text')


def _demo_info_projection(raw):
    if not isinstance(raw, dict) or type(raw.get('available')) is not bool:
        raise ContextPolicyError('Explicit public demo availability metadata required')
    if not raw['available']:
        return dict(available=False, on_demand=False)
    sha, duration = raw.get('source_sha256'), raw.get('duration_seconds')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise ContextPolicyError('Assigned video SHA256 must be exact hexadecimal')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ContextPolicyError('Assigned video must have a finite positive duration')
    if raw.get('on_demand') is not True:
        raise ContextPolicyError('Available assigned video must explicitly support on-demand replay')
    clean = dict(available=True, source_sha256=sha, duration_seconds=duration, on_demand=True)
    if 'fps' in raw:
        if type(raw['fps']) not in (int, float) or not math.isfinite(raw['fps']) or raw['fps'] <= 0:
            raise ContextPolicyError('Demo FPS must be finite and positive')
        clean['fps'] = raw['fps']
    if 'frame_count' in raw:
        if type(raw['frame_count']) is not int or raw['frame_count'] <= 0:
            raise ContextPolicyError('Demo frame count must be a positive integer')
        clean['frame_count'] = raw['frame_count']
    return clean


def _demo_revisit_message(anchor):
    provenance = dict(image_role='assigned_demo_revisit', sha256=anchor.sha256,
        source_sha256=anchor.source_sha256, seconds=anchor.seconds, historical_video_frame=True)
    if anchor.call_id is not None:
        provenance['call_id'] = anchor.call_id
    return dict(role='user', content=[dict(type='input_text', text=_json(provenance)), deepcopy(anchor.image_item)])


def _validate_history_selection(start, count, include_images):
    if type(start) is not int or start < 1 or type(count) is not int or not 1 <= count <= 5:
        raise ContextPolicyError('History requires a 1-based start and count one to five')
    if type(include_images) is not bool or include_images and count > 2:
        raise ContextPolicyError('History images require explicit boolean include_images and count at most two')


def _lean_public_observation(public):
    """Model display only. Preserve exact returned numbers, never infer task state."""
    if public is None:
        return None
    out = {k:deepcopy(public[k]) for k in ('schema','native_frame_id','condition','demo_available',
        'action_schema','observation_contract') if k in public}
    robot = public.get('robot_feedback')
    if not isinstance(robot, dict):
        return out
    selected = {k:deepcopy(robot[k]) for k in ('coordinate_frame','units','observation_tick','last_action') if k in robot}
    arms = {}
    for side in ('left','right'):
        arm = robot.get('arms', {}).get(side)
        if isinstance(arm, dict):
            clean = {k:deepcopy(arm[k]) for k in ('tcp_position','tcp_position_world_m',
                'tcp_quaternion_wxyz','tcp_quaternion_world_wxyz','gripper_open_fraction',
                'finger_joint_positions','finger_joint_position_units','holding_status','contact_status') if k in arm}
            if clean:
                arms[side] = clean
    if arms:
        selected['arms'] = arms
    out['robot_feedback'] = selected
    return out


def _model_measurement_projection(value, calibrations):
    """Deduplicate exact same-frame, same-camera K/T in the request, not in storage."""
    if isinstance(value, list):
        return [_model_measurement_projection(v, calibrations) for v in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    out = deepcopy(value)
    calibration = out.get('camera_calibration')
    if isinstance(calibration, dict) and isinstance(out.get('frame_id'), str) and out.get('camera') in ('head','left_wrist','right_wrist') and 'depth_m' in out and 'pixel' in out:
        frame, camera = out['frame_id'], out['camera']
        if calibration.get('frame_id', frame) != frame or calibration.get('camera', camera) != camera:
            raise ContextPolicyError('Cannot bind calibration from a different frame or camera')
        group = dict(frame_id=frame, camera=camera, camera_calibration=deepcopy(calibration))
        ref = 'cal:' + _hash(group)
        if ref in calibrations and calibrations[ref] != group:
            raise ContextPolicyError('Calibration content reference collision')
        calibrations[ref] = group
        del out['camera_calibration']
        out['calibration_ref'] = ref
    return {key:_model_measurement_projection(child, calibrations) for key,child in out.items()}


def _column_row(values):
    """Keep missing distinct from returned null/zero without padding trailing gaps."""
    while values and values[-1] is _ABSENT:
        values.pop()
    return [dict(not_reported=True) if value is _ABSENT else deepcopy(value) for value in values]


def _approx_feedback(value, angle=False):
    """Model display only. Raw public history/actions retain full returned precision."""
    if value is _ABSENT or value is None:
        return value
    if isinstance(value, dict):
        return {k:_approx_feedback(v, angle) for k, v in value.items()}
    if isinstance(value, list):
        return [_approx_feedback(v, angle) for v in value]
    if _finite_metric(value):
        quantum = Decimal('0.001' if angle else '0.0001')
        try:
            number = float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))
        except InvalidOperation:
            # Out-of-scale finite input stays exact; do not turn it into a plausible zero.
            return value
        return 0.0 if number == 0 else number
    return value


def _lean_batch_feedback(batch, actions=None):
    out = {key:deepcopy(value) for key, value in batch.items() if key != 'receipts'}
    rows = []
    for pair in batch.get('receipts', [])[:24]:
        receipt = pair.get('receipt') or {}
        returned_controls = receipt.get('control_feedback', _ABSENT)
        controls = returned_controls if isinstance(returned_controls, dict) else {}
        arms = []
        for side in ('left', 'right'):
            control = controls.get(side, _ABSENT)
            arms.append(_column_row([_approx_feedback(control.get(k, _ABSENT), angle=k=='orientation_error_rad')
                    if k in ('requested_delta_m','actual_delta_m','position_error_m','orientation_error_rad')
                    else control.get(k, _ABSENT) for k in _CONTROL_COLUMNS])
                if isinstance(control, dict) else control)
        errors = []
        for key, field in (('tracking_error_m', 'position_error_m'),
                           ('orientation_error_rad', 'orientation_error_rad')):
            value = receipt.get(key, _ABSENT)
            same = {side:control[field] for side in ('left', 'right')
                if isinstance(control := controls.get(side), dict) and field in control}
            # '=' is an exact reference to values present in this same row, never an estimate.
            errors.append('=' if isinstance(value, dict) and value and value == same else
                _approx_feedback(value, angle=key=='orientation_error_rad'))
        returned_action = pair.get('action', _ABSENT)
        index = pair.get('index')
        requested_action = actions[index] if isinstance(actions, list) and type(index) is int and 0 <= index < len(actions) else _ABSENT
        if isinstance(returned_action, dict):
            executed = '=' if returned_action == requested_action else _column_row([
                returned_action.get(k, _ABSENT) for k in ('left', 'right', 'step_mm', 'rotation_deg')])
        else:
            executed = _ABSENT
        rows.append(_column_row([pair.get(k, _ABSENT) for k in ('index', 'status', 'step')] + arms + errors +
            [executed, None if returned_controls is None else _ABSENT]))
    out['receipt_rows'] = rows
    return out


def _lean_history_record(record, *, physical):
    """RoboDawn-style command/outcome/TCP display; host audit record stays intact."""
    out = {}
    if type(record.get('decision_number')) is int:
        out['decision_number'] = record['decision_number']  # Public history lookup coordinate, not an audit identifier.
    if record.get('commands'):
        out['commands'] = deepcopy(record['commands'])
    outcomes = []
    for result in record.get('results', []):
        if not isinstance(result, dict):
            continue
        row = {k:deepcopy(result[k]) for k in ('ok','status','reason','note','error','accepted','pending','physical_action_count','requested_action_count','partial','action_batch') if k in result}
        if isinstance(row.get('action_batch'), dict) and 'receipts' in row['action_batch']:
            commands = record.get('commands', [])
            actions = commands[0].get('actions') if len(commands) == 1 and commands[0].get('type') == 'action_batch' else None
            row['action_batch'] = _lean_batch_feedback(row['action_batch'], actions)
        if 'demo_seconds' in result:
            row['demo_seconds'] = deepcopy(result['demo_seconds'])
        if row:
            outcomes.append(row)
    if outcomes:
        out['results'] = outcomes
    if any('receipt_rows' in r.get('action_batch', {}) for r in outcomes):
        # The indexed command values remain exact; names shared by every pair
        # are declared once per request rather than repeated up to288 times.
        for command in out.get('commands', []):
            if command.get('type') == 'action_batch' and isinstance(command.get('actions'), list):
                command['action_rows'] = [[deepcopy(pair[k]) for k in ('left', 'right', 'step_mm', 'rotation_deg')]
                    for pair in command.pop('actions')]
    if physical:
        if record.get('steps_after') is not None:
            out['steps_after'] = record['steps_after']
        if record.get('tcp'):
            # Preserve exact displayed TCP/gripper and native frame; avoid duplicating full controller diagnostics.
            tcp = record['tcp']
            clean = {k:deepcopy(tcp[k]) for k in ('native_frame_id','observation_tick') if k in tcp}
            arms = {}
            for side, arm in tcp.get('arms', {}).items():
                fields = {k:deepcopy(arm[k]) for k in ('tcp_position','tcp_position_world_m',
                    'tcp_quaternion_wxyz','tcp_quaternion_world_wxyz','gripper_open_fraction') if k in arm}
                if fields:
                    arms[side] = fields
            if arms:
                clean['arms'] = arms
            if clean:
                out['tcp'] = clean
    if record.get('reported_measurements'):
        out['reported_measurements'] = deepcopy(record['reported_measurements'])
    return out
