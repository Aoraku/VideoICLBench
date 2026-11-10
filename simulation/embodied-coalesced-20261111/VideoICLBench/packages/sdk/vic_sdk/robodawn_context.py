"""Finite episode-local Responses context policy; no transport or model loop.

Closed tool exchanges become paired, public-only user ledger entries. Unresolved
exchanges and the caller's current assistant/reasoning/tool chain stay verbatim.
Image blocks are separate input messages, never function_call_output payloads.
The policy never executes/retries an action or edits an old rollout.
"""
from __future__ import annotations

import ast
import base64
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Callable

from .embodied_public_observation import public_observation as project_public


# Canonical-only future revision; existing frozen v1 runs never import this copy.
FUTURE_NOTE_POLICY_VERSION = 'robodawn-per-decision-notes-v2'


class ContextPolicyError(ValueError):
    pass


class ContextOverflow(ContextPolicyError):
    """Mandatory content does not fit; caller must not silently drop materials."""

    def __init__(self, estimated_tokens, window_tokens, *, mandatory=True):
        self.estimated_tokens = estimated_tokens
        self.window_tokens = window_tokens
        self.mandatory = mandatory
        super().__init__(f'Mandatory episode context needs {estimated_tokens} tokens; window is {window_tokens}')


@dataclass(frozen=True)
class ContextPolicy:
    window_tokens: int = 128000
    compact_trigger_tokens: int = 96000
    max_receipts: int = 12
    receipt_max_utf8_bytes: int = 1400
    notes_max_chars: int = 2500
    max_old_gui: int = 0

    def __post_init__(self):
        for key in ('window_tokens', 'compact_trigger_tokens', 'max_receipts',
                    'receipt_max_utf8_bytes', 'notes_max_chars'):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ContextPolicyError(key + ' must be a positive integer')
        if self.compact_trigger_tokens >= self.window_tokens:
            raise ContextPolicyError('compact trigger must be below window')
        if self.max_receipts > 12 or type(self.max_old_gui) is not int or self.max_old_gui not in (0, 1, 2):
            raise ContextPolicyError('At most twelve receipts and two old GUI images')
        if self.notes_max_chars > 2500:
            raise ContextPolicyError('Model notes cannot exceed 2500 characters')


@dataclass(frozen=True)
class ImageAnchor:
    image_item: dict
    sha256: str
    token_cost: int
    kind: str
    frame_id: str | None = None
    source_sha256: str | None = None
    seconds: float | None = None
    call_id: str | None = None


@dataclass
class ContextBuild:
    items: list
    tools: list
    estimated_tokens: int
    identity_sha256: str
    receipt_count: int
    old_gui_count: int
    demo_anchor_count: int
    protected_exchange_ids: list[str]
    dropped_receipt_ids: list[str] = field(default_factory=list)
    dropped_old_gui_sha256: list[str] = field(default_factory=list)
    compaction_needed: bool = False
    estimator: str = 'utf8_bytes_upper_bound_plus_declared_image_tokens'

    def to_dict(self):
        return deepcopy(asdict(self))


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _hash_json(value):
    return _sha(_json(value).encode())


def _valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)


def _image_sha(item):
    if not isinstance(item, dict) or item.get('type') != 'input_image':
        raise ContextPolicyError('Expected a separate Responses input_image item')
    url = item.get('image_url')
    if not isinstance(url, str) or not re.fullmatch(r'data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\r\n]+', url):
        raise ContextPolicyError('Inline image bytes required to verify SHA without network')
    try:
        raw = base64.b64decode(url.split(',', 1)[1], validate=True)
    except ValueError:
        raise ContextPolicyError('Invalid inline image encoding') from None
    return _sha(raw)


def _images(value):
    if isinstance(value, list):
        for item in value:
            yield from _images(item)
    elif isinstance(value, dict):
        if value.get('type') == 'input_image':
            yield value
        else:
            for key in ('content', 'output'):
                if isinstance(value.get(key), (list, dict)):
                    yield from _images(value[key])


def _contains_image_payload(value):
    if isinstance(value, list):
        return any(_contains_image_payload(x) for x in value)
    if isinstance(value, dict):
        if value.get('type') in ('input_image', 'image', 'image_url'):
            return True
        return any(_contains_image_payload(v) for v in value.values() if isinstance(v, (list, dict)))
    return False


def _no_tool_images(items):
    for item in items:
        if not isinstance(item, dict) or item.get('type') != 'function_call_output':
            continue
        output = item.get('output')
        if _contains_image_payload(output) or isinstance(output, str) and 'data:image/' in output:
            raise ContextPolicyError('Move tool images to separate image input messages')
        if isinstance(output, str):
            try:
                decoded = json.loads(output)
            except ValueError:
                decoded = None
            if _contains_image_payload(decoded):
                raise ContextPolicyError('Move encoded tool image blocks to separate input messages')


def _pairs(requests, responses, *, require_closed):
    _no_tool_images(responses)
    calls = {}
    for item in requests:
        if not isinstance(item, dict) or item.get('type') != 'function_call':
            continue
        call_id, name = item.get('call_id'), item.get('name')
        if not isinstance(call_id, str) or not call_id or len(call_id) > 160:
            raise ContextPolicyError('Bounded nonempty tool call_id required')
        if not isinstance(name, str) or not name or len(name) > 80 or call_id in calls:
            raise ContextPolicyError('Unique tool call IDs and bounded names required')
        calls[call_id] = name
    if not calls:
        raise ContextPolicyError('Tool exchange must include its original function_call')
    outputs = {}
    for item in responses:
        if not isinstance(item, dict) or item.get('type') != 'function_call_output':
            continue
        call_id = item.get('call_id')
        if call_id not in calls or call_id in outputs:
            raise ContextPolicyError('Unpaired or duplicate tool response')
        outputs[call_id] = True
    if require_closed and set(calls) != set(outputs):
        raise ContextPolicyError('Closed exchange requires every tool response')
    return [dict(call_id=cid, tool=name, response_present=cid in outputs) for cid, name in calls.items()]


def _snippet(text, limit=400):
    if not isinstance(text, str):
        return ''
    if re.search(r'data:image/|depth_m_base64|encrypted_content|"(?:robot_feedback|camera_calibration|image_url)"', text):
        return '[rich payload archived]'
    if re.search(r'[A-Za-z0-9+/=]{256,}', text):
        return '[binary-like payload archived]'
    return text[:limit]


def _pair_details(pairs, requests, responses):
    calls = {v['call_id']: v for v in requests if isinstance(v, dict) and v.get('type') == 'function_call'}
    outputs = {v['call_id']: v for v in responses if isinstance(v, dict) and v.get('type') == 'function_call_output'}
    enriched = deepcopy(pairs)
    for pair in enriched:
        call = calls[pair['call_id']]
        arguments = call.get('arguments', '')
        encoded = arguments.encode() if isinstance(arguments, str) else _json(arguments).encode()
        pair['arguments_sha256'] = _sha(encoded)
        parsed = arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except ValueError:
                pass
        action = parsed.get('code') if isinstance(parsed, dict) and isinstance(parsed.get('code'), str) else _json(parsed)
        pair['action'] = _snippet(action)
        result = outputs.get(pair['call_id'])
        if result is None:
            continue
        value = result.get('output')
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        if isinstance(value, dict) and isinstance(value.get('content'), list):
            texts = [v.get('text') for v in value['content'] if isinstance(v, dict) and v.get('type') in ('text', 'input_text') and isinstance(v.get('text'), str)]
            if texts:
                value = '\n'.join(texts)
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
        elif isinstance(value, list):
            texts = [v.get('text') for v in value if isinstance(v, dict) and v.get('type') in ('text', 'input_text') and isinstance(v.get('text'), str)]
            if texts:
                value = '\n'.join(texts)
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
        if isinstance(value, dict):
            # Never promote task success/score/reward or a full observation.
            short = {k: value[k] for k in ('ok', 'status', 'cached', 'current_observation',
                     'physical_action', 'accepted', 'pending', 'isError') if type(value.get(k)) in (str, bool, int, float)}
            for k in ('error', 'stdout', 'stderr'):
                if isinstance(value.get(k), str):
                    short[k] = _snippet(value[k])
                elif k == 'error' and isinstance(value.get(k), dict):
                    short[k] = {key: _snippet(value[k][key], 120) for key in ('code', 'type', 'message') if isinstance(value[k].get(key), str)}
            text = _json(short) if short else '[public result privately archived; public_ref is an audit identifier]'
        else:
            text = value if isinstance(value, str) else '[non-text result archived]'
        pair['result_text'] = _snippet(text)
        if type(result.get('isError')) is bool:
            pair['is_error'] = result['isError']
    return enriched


def decorate_tool_schema_for_working_note(tool, *, notes_max_chars=2500):
    """Future-v2 only: require the model's note in the same normal tool call.

    Returns a copy. The old optional set_working_note tool is unchanged; callers
    opt into this helper explicitly and must strip the extra field before GUI.
    """
    if type(notes_max_chars) is not int or not 1 <= notes_max_chars <= 2500:
        raise ContextPolicyError('Working-note schema limit must be 1..2500')
    out = deepcopy(tool)
    if not isinstance(out, dict) or out.get('type') != 'function':
        raise ContextPolicyError('Responses function tool schema required')
    if out.get('name') == 'set_working_note':
        return out
    parameters = out.get('parameters')
    if not isinstance(parameters, dict) or parameters.get('type') != 'object':
        raise ContextPolicyError('Object tool parameters required for note policy')
    properties = parameters.setdefault('properties', {})
    if 'working_note' in properties:
        raise ContextPolicyError('working_note collides with an actual tool argument')
    properties['working_note'] = dict(type='string', minLength=1, maxLength=notes_max_chars,
        description='Rewrite your running episode-local note: measured frame-referenced facts, attempts, current stage and next check. No hidden facts or full raw observations.')
    required = parameters.setdefault('required', [])
    if not isinstance(required, list):
        raise ContextPolicyError('Tool required fields must be a list')
    required.append('working_note')
    return out


def split_working_note(arguments, *, required=True, notes_max_chars=2500):
    """Future-v2 pure validation: (original GUI args without note, model note).

    No action/transport runs here. Missing notes stay optional only for explicit
    legacy mode; present notes must be nonempty and safe. The author-style 2500
    character cap clips text, without adding an extra model/tool turn.
    """
    if not isinstance(arguments, dict):
        raise ContextPolicyError('Tool arguments must be an object')
    if type(notes_max_chars) is not int or not 1 <= notes_max_chars <= 2500:
        raise ContextPolicyError('Working-note limit must be 1..2500')
    clean = deepcopy(arguments)
    if 'working_note' not in clean:
        if required:
            raise ContextPolicyError('Future-v2 decision requires working_note before GUI execution')
        return clean, None
    note = clean.pop('working_note')
    if not isinstance(note, str) or not note.strip():
        raise ContextPolicyError('Working note must be nonempty model-authored text')
    note = note[:notes_max_chars]
    if re.search(r'data:image/|depth_m_base64|encrypted_content|["\'](?:robot_feedback|camera_calibration|image_url)["\']', note):
        raise ContextPolicyError('Working note may not contain binary/rich observation payloads')
    if re.search(r'[A-Za-z0-9+/=]{256,}', note):
        raise ContextPolicyError('Working note may not contain binary-like blobs')
    return clean, note


def _reported_measurement(value, *, allow_depth_only=False):
    """Whitelist explicit previously returned numbers; never infer object goals."""
    if not isinstance(value, dict) or value.get('valid') is not True or value.get('estimated') is not False:
        return None
    if value.get('physical_action') is not False or value.get('units') != 'm':
        return None
    if not isinstance(value.get('frame_id'), str) or not 1 <= len(value['frame_id']) <= 160:
        return None
    if value.get('camera') not in ('head', 'left_wrist', 'right_wrist'):
        return None
    def vector(x, length):
        return type(x) is list and len(x) == length and all(type(n) in (int, float) and math.isfinite(n) for n in x)
    if not vector(value.get('pixel'), 2) or type(value.get('depth_m')) not in (int, float) or not math.isfinite(value['depth_m']) or value['depth_m'] <= 0:
        return None
    xyz = {name: deepcopy(value[name]) for name in ('xyz_world_m', 'xyz_task_m', 'xyz_camera_m') if vector(value.get(name), 3)}
    if not xyz and not allow_depth_only:
        return None
    out = dict(valid=True, estimated=False, physical_action=False, units='m', frame_id=value['frame_id'],
        camera=value['camera'], pixel=deepcopy(value['pixel']), depth_m=value['depth_m'], **xyz)
    for name, allowed in (('coordinate_frame', ('task', 'world', 'camera')), ('pixel_order', ('row_col',)), ('pixel_space', ('native_image',))):
        if value.get(name) in allowed:
            out[name] = value[name]
    for name in ('measurement_source', 'method', 'sensor_source'):
        text = value.get(name)
        if isinstance(text, str) and re.fullmatch(r'[A-Za-z0-9_.:/ -]{1,120}', text):
            out[name] = text
    if value.get('origin') in ('program_stdout', 'program_result', 'unknown_tool_output', 'direct_depth_points_server_response'):
        out['origin'] = value['origin']
    if value.get('as_returned_not_independently_verified') is True:
        out['as_returned_not_independently_verified'] = True
    if value.get('historical_frame_specific') is True:
        out['historical_frame_specific'] = True
    return out


def _public_measurement_packet(result_items, tool_names=None):
    """Read JSON or bounded Python-literal stdout already returned by a tool.

    Only named output containers are traversed; no code evaluation, numeric
    regex guessing, private archive reads or object-labelled state lookup.
    """
    records = []; seen = set(); tool_names = tool_names or {}
    def visit(value, depth=0, origin='unknown_tool_output', preserve_origin=False):
        if depth > 12 or len(records) >= 256:
            return
        if isinstance(value, str):
            if len(value) > 65536:
                return
            try:
                decoded = json.loads(value)
            except ValueError:
                decoded = None
            if isinstance(decoded, (dict, list)):
                visit(decoded, depth + 1, origin, preserve_origin)
            else:
                for line in value.splitlines()[:256]:
                    if not line.strip().startswith(('{', '[')):
                        continue
                    try:
                        parsed = ast.literal_eval(line)
                    except (ValueError, SyntaxError, RecursionError, MemoryError):
                        continue
                    if isinstance(parsed, (dict, list)):
                        visit(parsed, depth + 1, origin, preserve_origin)
        elif isinstance(value, list):
            for item in value[:256]:
                visit(item, depth + 1, origin, preserve_origin)
        elif isinstance(value, dict):
            if value.get('type') == 'function_call_output':
                tool = tool_names.get(value.get('call_id'))
                origin = 'direct_depth_points_server_response' if tool == 'depth_points' else 'program_result' if tool == 'program' else 'unknown_tool_output'
                preserve_origin = tool == 'read_public_measurements'
            row = _reported_measurement(value, allow_depth_only=origin == 'direct_depth_points_server_response')
            if row:
                if not preserve_origin or 'origin' not in row:
                    row['origin'] = origin
                row['as_returned_not_independently_verified'] = True
                row['historical_frame_specific'] = True
                key = _hash_json(row)
                if key not in seen:
                    records.append(row); seen.add(key)
            for name in ('output', 'content', 'text', 'result', 'measurements', 'records', 'stdout'):
                if name in value:
                    child_origin = 'program_stdout' if name == 'stdout' else origin
                    visit(value[name], depth + 1, child_origin, preserve_origin)
    visit(result_items)
    return dict(schema='reported-public-measurements-v2', records=records) if records else None


def _short_measurement_groups(packet):
    groups = []; by_key = {}
    for row in packet['records'][:4]:
        shared = {k: row[k] for k in ('frame_id', 'camera', 'units', 'coordinate_frame', 'pixel_order', 'pixel_space', 'origin', 'as_returned_not_independently_verified', 'historical_frame_specific') if k in row}
        key = _hash_json(shared)
        if key not in by_key:
            by_key[key] = dict(**shared, points=[]); groups.append(by_key[key])
        point = {k: deepcopy(row[k]) for k in ('pixel', 'depth_m')}
        # Show the explicit target-frame XYZ first; camera XYZ remains fully
        # available through public_measurements_ref, with no recomputation.
        xyz_name = next((k for k in ('xyz_world_m', 'xyz_task_m', 'xyz_camera_m') if k in row), None)
        if xyz_name is not None:
            point[xyz_name] = deepcopy(row[xyz_name])
        by_key[key]['points'].append(point)
    return groups


def _public(raw):
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get('state'), dict):
        return project_public(raw)
    if isinstance(raw.get('observation'), dict):
        return _public(raw['observation'])
    candidate = raw.get('public_observation', raw)
    if not isinstance(candidate, dict):
        return None
    frame = candidate.get('native_frame_id')
    if not isinstance(frame, str) or not frame:
        return None
    return project_public(dict(frame_id=frame, state=candidate))


def _short_measured(public):
    if not public:
        return {}
    robot = public.get('robot_feedback', {})
    out = {'native_frame_id': public['native_frame_id']}
    if 'observation_tick' in robot:
        out['observation_tick'] = robot['observation_tick']
    arms = {}
    for side, arm in robot.get('arms', {}).items():
        selected = {}
        for key in ('tcp_position_world_m', 'tcp_position', 'tcp_quaternion_world_wxyz',
                    'tcp_quaternion_wxyz', 'gripper_open_fraction'):
            if key in arm:
                selected[key] = arm[key]
        if selected:
            arms[side] = selected
    if arms:
        out['arms'] = arms
    feedback = robot.get('last_action', {}).get('control_feedback')
    if feedback:
        out['control_feedback'] = deepcopy(feedback)
    return out


def _bound_receipt(receipt, maximum):
    if len(_json(receipt).encode()) > maximum:
        receipt.pop('measured', None)
    if receipt.get('measurements') and len(_json(receipt).encode()) > maximum:
        for pair in receipt.get('pairs', []):
            pair.pop('action', None); pair.pop('result_text', None)
    while len(_json(receipt).encode()) > maximum and receipt.get('measurements'):
        groups = receipt['measurements']
        groups[-1]['points'].pop()
        if not groups[-1]['points']:
            groups.pop()
        receipt['displayed_measurement_count'] = sum(len(group['points']) for group in groups)
        if not groups:
            receipt.pop('measurements')
    while len(_json(receipt).encode()) > maximum and any(p.get('action') or p.get('result_text') for p in receipt.get('pairs', [])):
        for pair in receipt['pairs']:
            for name in ('action', 'result_text'):
                if name in pair:
                    pair[name] = pair[name][:len(pair[name]) // 2]
    if len(_json(receipt).encode()) > maximum and 'pairs' in receipt:
        pairs = receipt.pop('pairs')
        receipt.update(pair_count=len(pairs), pairs_sha256=_hash_json(pairs))
    if len(_json(receipt).encode()) > maximum:
        raise ContextPolicyError('Even minimal paired receipt exceeds explicit byte budget')
    return receipt


class RoboDawnContext:
    """One episode's bounded context. All transport and note generation are external.

    ``token_counter(items, tools)`` may provide a model-specific complete estimate.
    Otherwise JSON UTF8 bytes are a conservative text upper bound; inline image
    bytes are replaced by caller-declared token_cost after SHA verification.
    ``fixed_items`` must contain all original instructions/condition materials.
    No method changes, clips or selectively removes those items.
    """

    def __init__(self, identity, fixed_items, tools, demo_anchors=(), *, archive_dir,
                 policy=None, token_counter: Callable | None = None):
        self.policy = policy or ContextPolicy()
        self._identity = deepcopy(identity)
        self.identity_sha256 = _hash_json(identity)
        self._fixed = deepcopy(fixed_items)
        self._tools = deepcopy(tools)
        _json(self._fixed); _json(self._tools)
        self._counter = token_counter
        self._archive_dir = Path(archive_dir)
        if self._archive_dir.is_symlink():
            raise ContextPolicyError('Private archive must not be a symlink')
        self._archive_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self._archive_dir.is_dir():
            raise ContextPolicyError('Private archive directory required')
        self._receipts = []
        self._exchanges = {}
        self._public = {}
        self._measurements = {}
        self._latest_public_ref = None
        self._demo = {}
        self._gui_shas = set()
        self._current = None
        self._old_gui = []
        self._notes = ''
        self._sequence = 0
        for anchor in demo_anchors:
            if isinstance(anchor, ImageAnchor):
                if anchor.kind != 'demo':
                    raise ContextPolicyError('Only demo image anchors may initialize demos')
                self.add_demo_anchor(anchor.image_item, anchor.sha256, token_cost=anchor.token_cost,
                    source_sha256=anchor.source_sha256, seconds=anchor.seconds, call_id=anchor.call_id)
            else:
                self.add_demo_anchor(**deepcopy(anchor))

    @property
    def identity(self):
        return deepcopy(self._identity)

    @property
    def unresolved_exchange_ids(self):
        return [key for key, value in self._exchanges.items() if value['protected']]

    @property
    def latest_public_observation(self):
        return deepcopy(self._public.get(self._latest_public_ref))

    @property
    def notes(self):
        return self._notes

    def _archive(self, kind, value):
        self._sequence += 1
        path = self._archive_dir / f'{self._sequence:06d}-{kind}.private.json'
        body = (_json(dict(schema='robodawn-context-archive-v1', identity_sha256=self.identity_sha256,
                           kind=kind, value=value)) + '\n').encode()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
            stream.write(body)
        return dict(sha256=_sha(body), filename=path.name)

    def set_notes(self, model_text):
        if not isinstance(model_text, str):
            raise ContextPolicyError('Model-authored notes must be text')
        clipped = model_text[:self.policy.notes_max_chars]
        if re.search(r'data:image/|depth_m_base64|encrypted_content|"(?:robot_feedback|camera_calibration|image_url)"', clipped):
            raise ContextPolicyError('Notes may not embed images, dense/rich observations or reasoning payloads')
        if re.search(r'[A-Za-z0-9+/=]{256,}', clipped):
            raise ContextPolicyError('Notes may not embed long binary/base64-like blobs')
        self._notes = clipped
        return dict(chars=len(clipped), clipped=len(model_text) > len(clipped))

    def _anchor(self, item, sha256, token_cost, kind, **metadata):
        if not _valid_sha(sha256) or _image_sha(item) != sha256:
            raise ContextPolicyError('Image bytes and SHA must match')
        if type(token_cost) is not int or token_cost <= 0:
            raise ContextPolicyError('Explicit positive image token cost required')
        return ImageAnchor(deepcopy(item), sha256, token_cost, kind, **metadata)

    def add_demo_anchor(self, image_item, sha256, *, token_cost, source_sha256,
                        seconds=None, call_id=None, origin_tool='demo_frames'):
        if origin_tool != 'demo_frames' or not _valid_sha(source_sha256):
            raise ContextPolicyError('Demo anchors require actual demo_frames source provenance')
        if sha256 in self._gui_shas:
            raise ContextPolicyError('A GUI screenshot cannot become a demo anchor')
        if seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
            raise ContextPolicyError('Finite nonnegative demo timestamp required')
        anchor = self._anchor(image_item, sha256, token_cost, 'demo', source_sha256=source_sha256,
                              seconds=seconds, call_id=call_id)
        previous = self._demo.get(sha256)
        if previous:
            if previous.source_sha256 != source_sha256 or previous.token_cost != token_cost:
                raise ContextPolicyError('Conflicting deduplicated demo provenance/cost')
            return False
        self._demo[sha256] = anchor
        return True

    def set_current_gui(self, image_item, sha256, *, frame_id, token_cost, call_id=None):
        if not isinstance(frame_id, str) or not frame_id:
            raise ContextPolicyError('GUI image needs its actual frame_id')
        if sha256 in self._demo:
            raise ContextPolicyError('A demo frame cannot become the current GUI')
        anchor = self._anchor(image_item, sha256, token_cost, 'current_gui', frame_id=frame_id, call_id=call_id)
        if self._current and self._current.sha256 != sha256:
            self._old_gui.append(self._current)
        self._old_gui = self._old_gui[-self.policy.max_old_gui:] if self.policy.max_old_gui else []
        self._current = anchor
        self._gui_shas.add(sha256)

    def _attach_public_measurements(self, receipt, result_items):
        packet = _public_measurement_packet(result_items, {p['call_id']: p['tool'] for p in receipt.get('pairs', [])})
        if not packet:
            return
        reference = _hash_json(packet)
        self._measurements[reference] = packet
        receipt.update(public_measurements_ref=reference, measurement_count=len(packet['records']),
            displayed_measurement_count=min(4, len(packet['records'])), measurements=_short_measurement_groups(packet))

    def get_public_measurements(self, reference):
        """Future-v2 lookup of already returned public measurements, not a sensor RPC."""
        if reference not in self._measurements:
            raise ContextPolicyError('Unknown episode-local public measurements reference')
        return deepcopy(self._measurements[reference])

    def record_tool_exchange(self, request_items, result_items, *, public_observation=None,
                             state='unknown', exchange_id=None, transport_error=False):
        if state not in ('completed', 'pending', 'unknown', 'error', 'failed', 'blocked'):
            raise ContextPolicyError('Explicit recognized exchange state required')
        exchange_id = exchange_id or f'exchange-{len(self._exchanges) + 1:06d}'
        if not isinstance(exchange_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}', exchange_id):
            raise ContextPolicyError('Bounded path-independent exchange ID required')
        if exchange_id in self._exchanges:
            raise ContextPolicyError('Exchange already recorded; actions must not be replayed')
        archive = self._archive('exchange', dict(exchange_id=exchange_id, request_items=request_items,
            result_items=result_items, state=state, transport_error=bool(transport_error), public_observation=public_observation))
        protected = state != 'completed' or bool(transport_error)
        pairs = _pair_details(_pairs(request_items, result_items, require_closed=not protected), request_items, result_items)
        seen_call_ids = {p['call_id'] for ex in self._exchanges.values() for p in ex['pairs']}
        if any(p['call_id'] in seen_call_ids for p in pairs):
            raise ContextPolicyError('Tool call already recorded; reconcile its existing exchange, never replay')
        public = _public(public_observation)
        ref = _hash_json(public) if public else None
        if public:
            self._public[ref] = deepcopy(public)
            self._latest_public_ref = ref
        receipt = dict(exchange_id=exchange_id, pairs=pairs, state=state, protected=protected)
        if ref:
            receipt['public_ref'] = ref
        measured = _short_measured(public)
        if measured:
            receipt['measured'] = measured
        self._attach_public_measurements(receipt, result_items)
        # Keep paired identity/state/hash and reported points before generic snippets.
        _bound_receipt(receipt, self.policy.receipt_max_utf8_bytes)
        self._exchanges[exchange_id] = dict(protected=protected, request_items=deepcopy(request_items),
            result_items=deepcopy(result_items), pairs=pairs, archive=archive, receipt=receipt)
        self._receipts.append(exchange_id)
        self._receipts = self._receipts[-self.policy.max_receipts:]
        return deepcopy(receipt)

    def reconcile(self, exchange_id, *, state='completed', public_observation=None, result_items=None):
        """Host-only explicit reconciliation; never replay an action or infer success."""
        if exchange_id not in self._exchanges or state != 'completed':
            raise ContextPolicyError('Known exchange and explicit completed reconciliation required')
        ex = self._exchanges[exchange_id]
        results = deepcopy(ex['result_items'] if result_items is None else result_items)
        pairs = _pair_details(_pairs(ex['request_items'], results, require_closed=True), ex['request_items'], results)
        self._archive('reconcile', dict(exchange_id=exchange_id, state=state, public_observation=public_observation, result_items=results))
        ex['result_items'] = results
        ex['pairs'] = pairs
        if 'pairs' in ex['receipt']:
            ex['receipt']['pairs'] = pairs
        else:
            ex['receipt']['pairs_sha256'] = _hash_json(pairs)
        ex['protected'] = False
        ex['receipt'].update(state=state, protected=False)
        if public_observation is not None:
            public = _public(public_observation)
            if public:
                ref = _hash_json(public); self._public[ref] = public
                self._latest_public_ref = ref
                ex['receipt']['public_ref'] = ref
                ex['receipt']['measured'] = _short_measured(public)
        self._attach_public_measurements(ex['receipt'], results)
        _bound_receipt(ex['receipt'], self.policy.receipt_max_utf8_bytes)
        return deepcopy(ex['receipt'])

    def get_public_observation(self, reference):
        """Public-only lazy lookup; never opens provider archives or hidden state."""
        if reference not in self._public:
            raise ContextPolicyError('Unknown public observation reference')
        return deepcopy(self._public[reference])

    def export_state(self):
        """JSON-only private checkpoint; closed raw payloads stay in archive files."""
        exchanges = {}
        for key, ex in self._exchanges.items():
            exchanges[key] = {k: deepcopy(ex[k]) for k in ('protected', 'pairs', 'archive', 'receipt')}
            if ex['protected']:
                exchanges[key].update(request_items=deepcopy(ex['request_items']), result_items=deepcopy(ex['result_items']))
        state = dict(schema='robodawn-context-checkpoint-v1', identity=self.identity,
            identity_sha256=self.identity_sha256, policy=asdict(self.policy), fixed_items=deepcopy(self._fixed),
            tools=deepcopy(self._tools), archive_sequence=self._sequence, exchanges=exchanges,
            receipt_ids=list(self._receipts), public_observations=deepcopy(self._public),
            public_measurements=deepcopy(self._measurements),
            latest_public_ref=self._latest_public_ref, demo_anchors=[asdict(a) for a in self._demo.values()],
            current_gui=asdict(self._current) if self._current else None,
            old_gui=[asdict(a) for a in self._old_gui], gui_sha256=sorted(self._gui_shas), notes=self._notes)
        state['checkpoint_sha256'] = _hash_json(state)
        return json.loads(_json(state))

    @classmethod
    def from_state(cls, state, *, archive_dir, token_counter=None, expected_identity=None):
        """Restore bookkeeping only. Never run/replay tools or repair an old world.

        Archive-ahead checkpoints are refused explicitly: the host must reconcile
        its pre-tool pending journal against the existing private archive first.
        """
        state = json.loads(_json(state))
        signature = state.pop('checkpoint_sha256', None)
        if state.get('schema') != 'robodawn-context-checkpoint-v1' or signature != _hash_json(state):
            raise ContextPolicyError('Checkpoint schema/digest mismatch')
        if _hash_json(state.get('identity')) != state.get('identity_sha256'):
            raise ContextPolicyError('Checkpoint episode identity mismatch')
        if expected_identity is not None and expected_identity != state['identity']:
            raise ContextPolicyError('Checkpoint belongs to a different episode/session')
        ctx = cls(state['identity'], state['fixed_items'], state['tools'], archive_dir=archive_dir,
                  policy=ContextPolicy(**state['policy']), token_counter=token_counter)
        sequence = state.get('archive_sequence')
        if type(sequence) is not int or sequence < 0:
            raise ContextPolicyError('Invalid private archive sequence')
        for path in ctx._archive_dir.glob('*.private.json'):
            match = re.fullmatch(r'([0-9]{6})-[a-z]+\.private\.json', path.name)
            if match and int(match.group(1)) > sequence:
                raise ContextPolicyError('Checkpoint is behind private archive; host reconciliation required, no replay')
        ctx._sequence = sequence
        ctx.set_notes(state['notes'])
        ctx._public = state['public_observations']
        for ref, value in ctx._public.items():
            if _hash_json(value) != ref or _public(value) != value:
                raise ContextPolicyError('Checkpoint public observation is invalid')
        ctx._measurements = state.get('public_measurements', {})
        for ref, packet in ctx._measurements.items():
            if not isinstance(packet, dict) or set(packet) != {'schema', 'records'} or packet.get('schema') != 'reported-public-measurements-v2' or _hash_json(packet) != ref:
                raise ContextPolicyError('Checkpoint public measurement packet invalid')
            if not isinstance(packet['records'], list) or any(_reported_measurement(row, allow_depth_only=row.get('origin') == 'direct_depth_points_server_response') != row for row in packet['records']):
                raise ContextPolicyError('Checkpoint public measurement values invalid')
        ctx._latest_public_ref = state.get('latest_public_ref')
        if ctx._latest_public_ref is not None and ctx._latest_public_ref not in ctx._public:
            raise ContextPolicyError('Checkpoint latest public reference missing')
        for record in state['demo_anchors']:
            if record.get('kind') != 'demo':
                raise ContextPolicyError('Checkpoint demo kind mismatch')
            ctx.add_demo_anchor(record['image_item'], record['sha256'], token_cost=record['token_cost'],
                source_sha256=record['source_sha256'], seconds=record.get('seconds'), call_id=record.get('call_id'))
        for record in [*state['old_gui'], *([state['current_gui']] if state.get('current_gui') else [])]:
            if record.get('kind') != 'current_gui':
                raise ContextPolicyError('Checkpoint GUI kind mismatch')
            ctx.set_current_gui(record['image_item'], record['sha256'], frame_id=record['frame_id'],
                                token_cost=record['token_cost'], call_id=record.get('call_id'))
        saved_gui = state.get('gui_sha256', [])
        if any(not _valid_sha(v) for v in saved_gui) or set(saved_gui) & set(ctx._demo):
            raise ContextPolicyError('Checkpoint GUI/demo provenance conflict')
        ctx._gui_shas.update(saved_gui)
        ctx._exchanges = state['exchanges']
        for key, ex in ctx._exchanges.items():
            archive = ex.get('archive', {})
            filename = archive.get('filename', '')
            if not re.fullmatch(r'[0-9]{6}-exchange\.private\.json', filename):
                raise ContextPolicyError('Invalid checkpoint archive reference')
            path = ctx._archive_dir / filename
            if path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != archive.get('sha256'):
                raise ContextPolicyError('Checkpoint private archive missing or changed')
            receipt = ex['receipt']
            if receipt.get('exchange_id') != key or receipt.get('protected') is not ex.get('protected'):
                raise ContextPolicyError('Checkpoint exchange identity/state mismatch')
            if len(_json(receipt).encode()) > ctx.policy.receipt_max_utf8_bytes:
                raise ContextPolicyError('Checkpoint receipt exceeds byte limit')
            if ex['protected']:
                _pairs(ex['request_items'], ex['result_items'], require_closed=False)
            else:
                # Raw closed payloads remain solely in the verified private archive.
                ex.setdefault('request_items', []); ex.setdefault('result_items', [])
        ctx._receipts = list(state['receipt_ids'])
        if len(ctx._receipts) > ctx.policy.max_receipts or len(set(ctx._receipts)) != len(ctx._receipts) or any(x not in ctx._exchanges for x in ctx._receipts):
            raise ContextPolicyError('Checkpoint receipt index invalid')
        return ctx

    def note_compaction_request(self):
        """Pure material for a same-model notes update; runner owns HTTP and usage."""
        return dict(identity_sha256=self.identity_sha256, notes=self._notes,
            receipts=[deepcopy(self._exchanges[x]['receipt']) for x in self._receipts],
            notes_max_chars=self.policy.notes_max_chars, protected_exchange_ids=self.unresolved_exchange_ids,
            instruction='Update only episode-local notes from these public receipts and prior model notes. Do not infer success or replay unresolved actions. Return notes only.')

    @staticmethod
    def _image_message(anchor):
        provenance = dict(image_role=anchor.kind, sha256=anchor.sha256)
        for key in ('frame_id', 'source_sha256', 'seconds', 'call_id'):
            value = getattr(anchor, key)
            if value is not None:
                provenance[key] = value
        return dict(role='user', content=[dict(type='input_text', text=_json(provenance)), deepcopy(anchor.image_item)])

    def _estimate(self, items):
        if self._counter:
            count = self._counter(deepcopy(items), deepcopy(self._tools))
            if type(count) is not int or count < 0:
                raise ContextPolicyError('Token counter must return a nonnegative complete estimate')
            return count
        costs = {a.sha256: a.token_cost for a in [*self._demo.values(), *self._old_gui, *([self._current] if self._current else [])]}
        image_tokens = 0
        def stripped(value):
            nonlocal image_tokens
            if isinstance(value, dict):
                if value.get('type') == 'input_image':
                    key = _image_sha(value)
                    if key not in costs:
                        raise ContextPolicyError('Pending/fixed image requires registered image cost and provenance')
                    image_tokens += costs[key]
                    return {'type': 'input_image', 'detail': value.get('detail')}
                return {k: stripped(v) for k, v in value.items()}
            if isinstance(value, list):
                return [stripped(v) for v in value]
            return value
        return len(_json(dict(input=stripped(items), tools=self._tools)).encode()) + image_tokens

    def build(self, pending_items=()):
        if self._current is None:
            raise ContextPolicyError('A current GUI image is mandatory')
        pending = deepcopy(list(pending_items))
        _no_tool_images(pending)
        protected = self.unresolved_exchange_ids
        # Deduplicate only exact cross-source pending items. Conflicting same-ID
        # items fail rather than mutating a pending reasoning/tool chain.
        raw = []; seen = set(); calls = {}
        sources = [[*self._exchanges[x]['request_items'], *self._exchanges[x]['result_items']] for x in protected] + [pending]
        for source in sources:
            within = set()
            for item in source:
                key = _hash_json(item)
                if key in seen and key not in within:
                    continue
                if isinstance(item, dict) and item.get('type') in ('function_call', 'function_call_output'):
                    pairkey = (item['type'], item.get('call_id'))
                    if pairkey in calls and calls[pairkey] != key:
                        raise ContextPolicyError('Conflicting pending items for the same tool call')
                    calls[pairkey] = key
                raw.append(deepcopy(item)); within.add(key)
            seen.update(within)
        # Outputs require their original pending call; dangling requests are fine.
        request_ids = {x.get('call_id') for x in raw if isinstance(x, dict) and x.get('type') == 'function_call'}
        if any(x.get('call_id') not in request_ids for x in raw if isinstance(x, dict) and x.get('type') == 'function_call_output'):
            raise ContextPolicyError('Pending tool output without original request')
        pending_shas = {_image_sha(image) for image in _images(raw)}
        identity = dict(role='user', content=[dict(type='input_text', text=_json(dict(episode_identity=self._identity,
            identity_sha256=self.identity_sha256, unresolved_exchanges=protected,
            no_replay='Unresolved actions must be reconciled; do not replay accepted actions.')))])
        notes = [dict(role='user', content=[dict(type='input_text', text=_json(dict(episode_model_notes=self._notes)))])] if self._notes else []
        demo = [self._image_message(a) for a in self._demo.values() if a.sha256 not in pending_shas]
        current = [] if self._current.sha256 in pending_shas else [self._image_message(self._current)]
        # Mandatory prefix/materials and the current raw pending chain never change.
        mandatory = deepcopy(self._fixed) + [identity] + demo + notes + current + raw
        count = self._estimate(mandatory)
        if count > self.policy.window_tokens:
            raise ContextOverflow(count, self.policy.window_tokens)
        receipts = list(self._receipts); old = list(self._old_gui); dropped_r = []; dropped_g = []
        def assemble():
            ledger = [dict(role='user', content=[dict(type='input_text', text=_json(dict(historical_tool_receipt=self._exchanges[x]['receipt'])))]) for x in receipts]
            old_images = [self._image_message(a) for a in old if a.sha256 not in pending_shas]
            return deepcopy(self._fixed) + [identity] + demo + notes + ledger + old_images + current + raw
        items = assemble(); count = self._estimate(items)
        while count > self.policy.compact_trigger_tokens and old:
            dropped_g.append(old.pop(0).sha256); items = assemble(); count = self._estimate(items)
        while count > self.policy.compact_trigger_tokens and receipts:
            dropped_r.append(receipts.pop(0)); items = assemble(); count = self._estimate(items)
        # Persist deterministic eviction, but never mutate unresolved raw chains.
        self._receipts = receipts; self._old_gui = old
        if count > self.policy.window_tokens:
            raise ContextOverflow(count, self.policy.window_tokens)
        return ContextBuild(items=items, tools=deepcopy(self._tools), estimated_tokens=count,
            identity_sha256=self.identity_sha256, receipt_count=len(receipts), old_gui_count=len(old),
            demo_anchor_count=len(self._demo), protected_exchange_ids=protected,
            dropped_receipt_ids=dropped_r, dropped_old_gui_sha256=dropped_g,
            compaction_needed=count > self.policy.compact_trigger_tokens,
            estimator='caller_complete_token_counter' if self._counter else 'utf8_bytes_upper_bound_plus_declared_image_tokens')
