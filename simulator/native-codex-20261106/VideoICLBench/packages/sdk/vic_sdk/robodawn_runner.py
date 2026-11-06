"""Explicit bounded-history Responses driver over the unchanged GUI tools.

This is a new driver, not a Codex CLI or a transparent request-body rewriter.
All provider usage (including notes compaction) is recorded verbatim, and every
GUI intent is checkpointed before execution. An uncertain intent is never replayed.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time
import uuid

import httpx

from .robodawn_context import ContextPolicy, ContextOverflow, RoboDawnContext
from .robodawn_tools import GUIBridge, ToolResult

VERSION = 'videoicl-robodawn 2'
POLICY_INSTRUCTIONS = '''You control the same embodied GUI tools and assigned task below.
This driver uses bounded episode-local history: the assigned instruction, actual
requested demonstration frames, latest GUI, last twelve short tool receipts and
your working note. Old live images and old reasoning are not retained. Use
set_working_note to preserve essential observations, attempts and next steps
(maximum 2500 characters); do not copy full observations into notes. Program
memory remains local to this episode. Read a returned GUI observation before
choosing another Commit. A tool error, waiting, or API delay is not evidence that
the task is impossible. Do not repeat an accepted or uncertain action. Use a
fresh observe after an uncertain result. End using done or giveup, based on the
visible task state; an ordinary final message does not end the episode. There
are no hidden object-state or scoring tools. No shell or filesystem tools exist.
'''
NOTE_TOOL = dict(type='function', name='set_working_note', strict=False,
    description='Replace your short working note for this episode only. Preserve useful observations, attempts and next steps, not full raw state. No robot movement.',
    parameters=dict(type='object', properties=dict(text=dict(type='string', maxLength=2500)), required=['text'], additionalProperties=False))
PER_DECISION_INSTRUCTIONS = POLICY_INSTRUCTIONS.replace(
    'Use\nset_working_note to preserve essential observations, attempts and next steps\n(maximum 2500 characters); do not copy full observations into notes.',
    'Every tool call must include working_note: a short nonempty updated note\n(aim for at most 120 words; 2500 characters is a cap, not a target) preserving essential observations, attempts and next\nsteps. The driver removes that field before the original GUI tool executes.\nDo not call a separate note tool or copy full observations into notes.') + '''
read_public_measurements(ref) retrieves only already-returned public sensor
measurements from this same episode. Its reference is provided in your receipt;
it is not a new sensor query. Old frame geometry may be stale after movement.
It also requires an updated working_note in the same call.
'''
PUBLIC_MEASUREMENTS_TOOL = dict(type='function', name='read_public_measurements', strict=False,
    description='Read an already-returned public sensor packet by its receipt reference within this episode only. No hidden state, labels or score; no new observation or robot movement.',
    parameters=dict(type='object', properties=dict(ref=dict(type='string', minLength=1)),
                    required=['ref'], additionalProperties=False))


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with open(temporary, 'x', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def append_json(path, row):
    with open(path, 'a', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        stream.write(dumps(row) + '\n')
        stream.flush()


def redact(text):
    # Never store a provider or actor credential accidentally echoed by a gateway.
    for key in ('VIC_MODEL_API_KEY',):
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, '[redacted]')
    return text[:1600]


class ProviderFailure(RuntimeError):
    def __init__(self, message, status=None, code=None):
        self.status, self.code = status, code
        super().__init__(redact(message))


class ResponsesTransport:
    """Fully consume the stream before returning/retrying; no action is retried here."""
    def __init__(self, base_url, key, *, client=None, session_affinity_id=None):
        self.base_url = base_url.rstrip('/')
        self.key = key
        if session_affinity_id is not None and (not isinstance(session_affinity_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',session_affinity_id)):
            raise ValueError('Bounded opaque session affinity identifier required')
        self.session_affinity_id = session_affinity_id
        self.client = client or httpx.Client(trust_env=False,
            timeout=httpx.Timeout(connect=30., pool=30., read=None, write=None))
        self.owns_client = client is None

    def complete(self, body):
        result = None
        failure = None
        headers = {}
        request_headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'}
        if self.session_affinity_id is not None:
            if body.get('prompt_cache_key') != self.session_affinity_id:
                raise ValueError('Session affinity header and body cache identity must match')
            request_headers['session-id']=self.session_affinity_id
        with self.client.stream('POST', self.base_url + '/responses',
                headers=request_headers,
                json=body) as response:
            headers = {k: response.headers[k] for k in ('x-request-id', 'request-id', 'date') if k in response.headers}
            if response.status_code >= 400:
                raw = response.read()
                try:
                    error = json.loads(raw).get('error', {})
                except (ValueError, AttributeError):
                    error = {}
                if not isinstance(error, dict):
                    error = {}
                raise ProviderFailure(str(error.get('message', 'Provider HTTP failure')),
                    response.status_code, error.get('code') or error.get('type'))
            if 'text/event-stream' not in response.headers.get('content-type', ''):
                try:
                    result = json.loads(response.read())
                except ValueError:
                    raise ProviderFailure('Provider response is neither complete JSON nor SSE') from None
            else:
                event_data = []
                def consume(lines):
                    nonlocal result, failure
                    value = '\n'.join(lines)
                    if not value or value == '[DONE]':
                        return value == '[DONE]'
                    try:
                        event = json.loads(value)
                    except ValueError:
                        failure = 'Invalid provider SSE JSON'
                        return False
                    if event.get('type') == 'response.completed':
                        candidate = event.get('response')
                        if result is not None and dumps(result) != dumps(candidate):
                            failure = 'Conflicting response.completed events'
                        result = candidate
                    elif event.get('type') in ('response.failed', 'response.incomplete', 'error'):
                        failure = event.get('response', {}).get('error') or event.get('error') or event.get('message') or event.get('type')
                    return False
                for line in response.iter_lines():
                    if line.startswith('data:'):
                        event_data.append(line[5:].lstrip())
                    elif not line and event_data:
                        consume(event_data)
                        event_data = []
                if event_data:
                    consume(event_data)
        if failure:
            raise ProviderFailure('Provider stream failed: ' + dumps(failure))
        if not isinstance(result, dict) or result.get('status') not in (None, 'completed') or not isinstance(result.get('output'), list):
            raise ProviderFailure('Provider stream ended without a completed response')
        if result.get('error'):
            raise ProviderFailure('Provider response error: ' + dumps(result['error']))
        return result, headers

    def close(self):
        if self.owns_client:
            self.client.close()


def text_of(output):
    return '\n'.join(c.get('text', '') for item in output if item.get('type') == 'message'
        for c in item.get('content', []) if c.get('type') in ('output_text', 'text'))


def find_observation(value):
    """Only inspect actual public tool output, never controller/private scene state."""
    if isinstance(value, dict):
        if isinstance(value.get('frame_id'), str) and isinstance(value.get('public_observation'), dict):
            return value
        for key in ('observation', 'result', 'records', 'content'):
            found = find_observation(value.get(key))
            if found:
                return found
        if value.get('type') in ('text', 'input_text') and isinstance(value.get('text'), str):
            try:
                return find_observation(json.loads(value['text']))
            except ValueError:
                pass
    elif isinstance(value, (tuple, list)):
        for item in reversed(value):
            found = find_observation(item)
            if found:
                return found
    return None


def tool_observation(result):
    for block in reversed(result.text_blocks):
        try:
            value = json.loads(block['text'])
        except ValueError:
            continue
        found = find_observation(value)
        if found:
            return found
    return find_observation(result.structured_content)


class Runner:
    def __init__(self, config, *, bridge=None, transport=None, sleep=time.sleep, emit=None, resume=None):
        self.config = deepcopy(config)
        self.note_mode = config.get('note_mode', 'optional_tool')
        if self.note_mode not in ('optional_tool', 'per_decision'):
            raise ValueError('Unknown bounded driver note_mode')
        self.profile = Path(config['profile'])
        self.output = Path(config['output_root'])
        self.directory = self.profile / 'bounded-context'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_file = self.profile / 'robodawn-state.private.json'
        self.events = self.directory / 'driver-events.private.jsonl'
        self.sleep = sleep
        self.emit = emit or (lambda row: print(dumps(row), flush=True))
        self.bridge = bridge
        self.transport = transport
        self.computer = json.loads(Path(config['computer_config']).read_text())
        self.identity = self.computer.get('program_episode_identity') or {'run_id': self.computer['run_id']}
        self.policy = ContextPolicy(**config['policy'])
        self.demo_sha = None
        if self.computer.get('demo_video'):
            self.demo_sha = sha(Path(self.computer['demo_video']).read_bytes())
        self.config_pin = sha(dumps({k: v for k, v in self.config.items() if k != 'resume'}).encode())
        self.state = None
        self.context = None
        self.resume = resume

    def event(self, kind, **fields):
        append_json(self.events, dict(time=time.time(), type=kind, session_id=self.state['session_id'] if self.state else None, **fields))

    def save(self):
        self.state['context'] = self.context.export_state()
        atomic_json(self.state_file, self.state)

    def initialize(self):
        if self.bridge is None:
            self.bridge = GUIBridge(self.computer)
        if self.note_mode == 'per_decision':
            from .robodawn_context import decorate_tool_schema_for_working_note
            tools = [decorate_tool_schema_for_working_note(tool) for tool in
                     self.bridge.list_tools() + [deepcopy(PUBLIC_MEASUREMENTS_TOOL)]]
        else:
            tools = self.bridge.list_tools() + [deepcopy(NOTE_TOOL)]
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text())
            if not self.resume or self.resume != self.state['session_id'] or self.state['config_sha256'] != self.config_pin:
                raise RuntimeError('Bounded driver resume identity/config mismatch; refusing a new session')
            self.context = RoboDawnContext.from_state(self.state['context'],
                archive_dir=self.directory / 'archive', expected_identity=self.identity)
            if dumps(tools) != dumps(self.state['tools']):
                raise RuntimeError('Tool registry changed during the same episode')
            self.event('same_session_resume', previous_phase=self.state['phase'])
            if self.state['phase'] == 'tool_running':
                # The host has reconciled its native barrier before restarting us.
                # Still do not replay this tool: only its original receipt may do so.
                call = self.state['response']['output'][self.state['tool_index']]
                self.state['tool_outputs'].append(dict(type='function_call_output', call_id=call['call_id'],
                    output=dumps(dict(isError=True, outcome='unknown_before_checkpoint',
                        no_replay=True, instruction='The prior tool may have executed. Inspect a fresh observation.'))))
                self.state['completed_calls'].append(call['call_id'])
                self.state['uncertain_calls'].append(call['call_id'])
                self.state['phase'] = 'response_received'
                self.save()
        else:
            if self.resume:
                raise RuntimeError('Persisted driver checkpoint required for resume')
            instruction = Path(self.config['instruction_path']).read_text()
            instructions = PER_DECISION_INSTRUCTIONS if self.note_mode == 'per_decision' else POLICY_INSTRUCTIONS
            fixed = [dict(role='developer', content=[dict(type='input_text', text=self.config.get('developer_instructions', '') + '\n' + instructions)]),
                     dict(role='user', content=[dict(type='input_text', text=instruction)])]
            self.context = RoboDawnContext(self.identity, fixed, tools, archive_dir=self.directory / 'archive', policy=self.policy)
            self.state = dict(schema='videoicl-robodawn-checkpoint-v1', config_sha256=self.config_pin,
                session_id=str(uuid.uuid4()), phase='ready', latest_items=[], tools=tools,
                usage=dict(input_tokens=0, cached_input_tokens=0, output_tokens=0, reasoning_output_tokens=0),
                seen_response_ids=[], requests=0, successes=0, failures=0, compact_calls=0,
                completed_calls=[], uncertain_calls=[], terminal=False, last_observation=None)
            journal = self.profile / 'sessions' / (self.state['session_id'] + '.jsonl')
            journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            append_json(journal, dict(type='session_meta', payload=dict(id=self.state['session_id'],
                engine='robodawn', framework=VERSION, identity=self.identity)))
            self.save()
        self.emit(dict(type='thread.started', thread_id=self.state['session_id'], engine='robodawn'))
        if self.transport is None:
            key = os.environ.get('VIC_MODEL_API_KEY')
            if not key:
                raise RuntimeError('Missing VIC_MODEL_API_KEY')
            self.transport = ResponsesTransport(self.config['base_url'], key)
        if self.state['phase'] == 'ready' or self.state.get('uncertain_calls'):
            # Actual GUI observation, no fabricated model tool call and no movement.
            observed = self.bridge.call_tool('observe', {})
            self.capture_images(observed, None)
            if observed.is_error:
                raise RuntimeError('GUI transport failed during fresh observation')
            self.state['latest_items'] = [dict(role='user', content=[dict(type='input_text',
                text='Fresh actual GUI observation:\n' + observed.text)])]
            self.event('host_observe', result_text_sha256=sha(observed.text.encode()), is_error=False)
            self.save()

    def capture_images(self, result, call_id):
        observation = tool_observation(result)
        if observation:
            self.state['last_observation'] = observation
            status = observation.get('episode_status')
            if status in ('finished', 'done', 'give_up', 'giveup', 'budget_exhausted', 'budget_paused'):
                self.state['terminal'] = True
            if status == 'faulted':
                raise RuntimeError('GUI reports faulted environment')
        sources = getattr(result, 'image_sources', None)
        if result.images and (sources is None or len(sources) != len(result.images)):
            raise RuntimeError('GUI image provenance missing; refusing guessed demo/current classification')
        for image, source in zip(result.images, sources or []):
            raw = base64.b64decode(image['image_url'].split(',', 1)[1], validate=True)
            digest = sha(raw)
            # This is the same high-detail image; no resizing or recompression.
            if source['kind'] == 'gui':
                current = observation
                if not current:
                    raise RuntimeError('GUI image has no corresponding public frame identity')
                self.context.set_current_gui(image, digest, frame_id=current['frame_id'], token_cost=2800, call_id=call_id)
            elif source['kind'] == 'demo':
                if not self.demo_sha:
                    raise RuntimeError('Demo image without assigned demonstration')
                self.context.add_demo_anchor(image, digest, token_cost=2800,
                    source_sha256=self.demo_sha, seconds=source.get('demo_seconds'), call_id=call_id)
            else:
                raise RuntimeError('Unclassified image from tool')
        return observation

    def account(self, response, purpose, request_number):
        identity = response.get('id')
        if not isinstance(identity, str) or not identity:
            raise ProviderFailure('Provider omitted response id; usage cannot be reconciled')
        if identity in self.state['seen_response_ids']:
            raise ProviderFailure('Provider reused completed response id; refusing duplicate execution')
        usage = response.get('usage')
        if not isinstance(usage, dict) or not all(type(usage.get(k)) is int for k in ('input_tokens', 'output_tokens')):
            raise ProviderFailure('Completed provider response omitted numeric usage')
        cached = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
        reasoning = (usage.get('output_tokens_details') or {}).get('reasoning_tokens', 0)
        if type(cached) is not int or not 0 <= cached <= usage['input_tokens']:
            raise ProviderFailure('Invalid cached token usage')
        if type(reasoning) is not int or not 0 <= reasoning <= usage['output_tokens']:
            raise ProviderFailure('Invalid reasoning token usage')
        for name, value in (('input_tokens', usage['input_tokens']), ('cached_input_tokens', cached),
                            ('output_tokens', usage['output_tokens']), ('reasoning_output_tokens', reasoning)):
            self.state['usage'][name] += value
        self.state['seen_response_ids'].append(identity)
        self.state['successes'] += 1
        self.event('provider_usage', purpose=purpose, request_number=request_number, response_id=identity,
            raw_usage=usage, cumulative_usage=self.state['usage'])
        journal = self.profile / 'sessions' / (self.state['session_id'] + '.jsonl')
        append_json(journal, dict(type='driver_usage', payload=dict(response_id=identity, purpose=purpose, usage=usage)))
        self.emit(dict(type='turn.completed', usage=self.state['usage'], purpose=purpose, response_id=identity))

    def request(self, body, purpose):
        # Save the exact prompt before upstream acceptance. Retries contain no new
        # tool action and keep precisely the same body/session identity.
        body_bytes = dumps(body).encode()
        attempt = 0
        while True:
            self.state['requests'] += 1
            number = self.state['requests']
            self.state['phase'] = 'api_pending'
            self.state['pending_request'] = body
            self.state['pending_purpose'] = purpose
            self.save()
            atomic_json(self.directory / f'request-{number:06d}.private.json', body)
            start = time.monotonic()
            self.event('api_start', request_number=number, purpose=purpose,
                body_bytes=len(body_bytes), body_sha256=sha(body_bytes),
                input_items=len(body['input']), tool_count=len(body.get('tools', [])))
            try:
                response, headers = self.transport.complete(body)
            except (httpx.HTTPError, ProviderFailure) as exc:
                attempt += 1
                self.state['failures'] += 1
                code = getattr(exc, 'code', None)
                status = getattr(exc, 'status', None)
                wait = min(300, 5 * 2 ** min(attempt - 1, 6))
                if code == 'insufficient_quota':
                    wait = 300
                self.event('api_failure', request_number=number, purpose=purpose,
                    error_class=type(exc).__name__, status=status, code=code,
                    message=redact(str(exc)), elapsed_seconds=time.monotonic()-start,
                    retry_wait_seconds=wait, original_session_preserved=True, usage=None)
                self.save()
                self.sleep(wait)
                continue
            # Raw complete response and usage before any physical side effect.
            atomic_json(self.directory / f'response-{number:06d}.private.json', response)
            self.account(response, purpose, number)
            self.state['response'] = response
            self.state['phase'] = 'response_received'
            self.state['tool_outputs'] = []
            self.state['completed_calls'] = []
            self.state['uncertain_calls'] = []
            self.state.pop('pending_request', None)
            self.event('api_complete', request_number=number, purpose=purpose,
                response_id=response['id'], elapsed_seconds=time.monotonic()-start,
                headers=headers, output_items=len(response['output']))
            self.save()
            return response

    def body(self, items, tools):
        return dict(model=self.config['model'], input=items, tools=tools,
            reasoning=dict(effort=self.config.get('effort', 'high')),
            include=['reasoning.encrypted_content'], parallel_tool_calls=False,
            store=False, stream=True, max_output_tokens=8192)

    def compact_notes(self):
        material = self.context.note_compaction_request()
        body = self.body([dict(role='developer', content=[dict(type='input_text',
            text='Compress only the supplied episode-local working notes and factual public receipts. Return at most 2500 characters, no tools, no new world facts.')]),
            dict(role='user', content=[dict(type='input_text', text=dumps(material))])], [])
        response = self.request(body, 'notes_compaction')
        note = text_of(response['output'])
        self.context.set_notes(note)
        self.state['compact_calls'] += 1
        self.state['phase'] = 'ready'
        self.event('context_compaction', implementation='same_model_bounded_notes',
            native_codex_compact=False, max_chars=self.policy.notes_max_chars)
        self.emit(dict(type='compacted', source='bounded_context',
            implementation='same_model_bounded_notes', native_codex_compact=False,
            response_id=response['id']))
        self.save()

    def execute_response(self):
        response = self.state['response']
        output = response['output']
        calls = [(i, item) for i, item in enumerate(output) if item.get('type') == 'function_call']
        if not calls:
            text = text_of(output)
            self.emit(dict(type='item.completed', item=dict(type='agent_message', text=text)))
            self.state['latest_items'] = [dict(role='user', content=[dict(type='input_text',
                text='Your latest text did not end the episode. Continue with GUI tools; use done/giveup only when supported by the visible state. Latest text: ' + text[:2500])])]
            self.state['phase'] = 'ready'
            self.save()
            return
        for index, call in calls:
            if call['call_id'] in self.state['completed_calls']:
                continue
            self.state['phase'], self.state['tool_index'] = 'tool_running', index
            self.save()
            self.event('tool_intent', call_id=call['call_id'], name=call['name'],
                arguments_sha256=sha(call.get('arguments', '').encode()))
            try:
                arguments = json.loads(call.get('arguments', '{}'))
                if not isinstance(arguments, dict):
                    raise ValueError('Tool arguments must be object')
                if self.note_mode == 'per_decision':
                    from .robodawn_context import split_working_note
                    arguments, note = split_working_note(arguments, required=True)
                    self.context.set_notes(note)
                    # Keep the same-call note even if accepted GUI work is later
                    # interrupted. The tool_running checkpoint still forbids replay.
                    self.save()
                if call['name'] == 'set_working_note':
                    if self.note_mode != 'optional_tool':
                        raise ValueError('A separate working-note tool is unavailable in per_decision mode')
                    receipt = self.context.set_notes(arguments['text'])
                    result = ToolResult(call['name'], [dict(type='input_text', text=dumps(receipt))], [], receipt)
                elif call['name'] == 'read_public_measurements' and self.note_mode == 'per_decision':
                    if set(arguments) != {'ref'} or not isinstance(arguments['ref'], str):
                        raise ValueError('A public measurement reference is required')
                    packet = self.context.get_public_measurements(arguments['ref'])
                    result = ToolResult(call['name'], [dict(type='input_text', text=dumps(packet))], [], packet)
                else:
                    result = self.bridge.call_tool(call['name'], arguments)
            except (ValueError, KeyError, TypeError) as exc:
                result = ToolResult(call['name'], [dict(type='input_text', text=dumps(dict(isError=True,
                    error=redact(str(exc)), accepted=False)))], [], {}, True)
            atomic_json(self.directory / ('tool-' + sha(call['call_id'].encode()) + '.private.json'),
                dict(call=call, raw_result=result.raw, is_error=result.is_error))
            observation = self.capture_images(result, call['call_id'])
            self.state['tool_outputs'].append(result.response_output(call['call_id']))
            self.state['completed_calls'].append(call['call_id'])
            self.state['phase'] = 'response_received'
            uncertain = any(s in result.text.lower() for s in
                ('transport failed', 'outcome unknown', 'requires controller reconciliation', 'pending input'))
            if uncertain:
                self.state['uncertain_calls'].append(call['call_id'])
            self.event('tool_complete', call_id=call['call_id'], name=call['name'], is_error=result.is_error,
                uncertain=uncertain, image_count=len(result.images),
                frame_id=observation.get('frame_id') if observation else None)
            self.emit(dict(type='item.completed', item=dict(type='mcp_tool_call', tool=call['name'],
                status='failed' if result.is_error else 'completed')))
            self.save()
            if uncertain:
                raise RuntimeError('GUI transport failed; preserve world and reconcile before same-session resume')
        self.context.record_tool_exchange(output, self.state['tool_outputs'],
            public_observation=self.state.get('last_observation'),
            state='unknown' if self.state['uncertain_calls'] else 'completed',
            transport_error=bool(self.state['uncertain_calls']), exchange_id=response['id'].replace('/', '_')[:90])
        self.state['latest_items'] = deepcopy(output) + deepcopy(self.state['tool_outputs'])
        self.state['phase'] = 'ready'
        self.save()

    def run(self, *, max_decisions=None):
        self.initialize()
        decisions = 0
        while not self.state['terminal']:
            if self.state['phase'] == 'response_received':
                if self.state.get('pending_purpose') == 'notes_compaction':
                    self.context.set_notes(text_of(self.state['response']['output']))
                    self.state['compact_calls'] += 1
                    self.state['phase'] = 'ready'
                    self.save()
                else:
                    self.execute_response()
                if self.state['terminal']:
                    break
            if max_decisions is not None and decisions >= max_decisions:
                return self.state
            if self.state['phase'] == 'api_pending':
                response = self.request(self.state['pending_request'], self.state['pending_purpose'])
            else:
                build = self.context.build(self.state['latest_items'])
                if build.compaction_needed and self.state.get('notes_compaction_at') != build.identity_sha256 + str(self.state['successes']):
                    # Normally twelve receipts + current image are far below 96K.
                    # No per-action summarizer and no hidden provider compact call.
                    self.compact_notes()
                    build = self.context.build(self.state['latest_items'])
                    if build.compaction_needed:
                        raise ContextOverflow(build.estimated_tokens, self.policy.compact_trigger_tokens)
                self.event('context_build', estimated_tokens=build.estimated_tokens,
                    estimator=build.estimator, receipts=build.receipt_count,
                    demo_anchor_count=build.demo_anchor_count, old_gui_count=build.old_gui_count,
                    protected_exchange_ids=build.protected_exchange_ids,
                    dropped_receipt_ids=build.dropped_receipt_ids)
                self.request(self.body(build.items, build.tools), 'decision')
            decisions += 1
        self.event('terminal_gui_observed', usage=self.state['usage'], provider_requests=self.state['requests'])
        self.emit(dict(type='result', result='The actual GUI reported a terminal episode.',
            usage=self.state['usage'], is_error=False, subtype='bounded_driver_terminal'))
        return self.state

    def close(self):
        if self.bridge:
            self.bridge.close()
        if self.transport:
            self.transport.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--resume')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    runner = Runner(config, resume=args.resume)
    try:
        runner.run()
        return 0
    except Exception as exc:
        # Do not turn a harness/provider error into a scored task failure.
        message = redact(str(exc))
        if runner.state:
            runner.event('driver_failed', error_class=type(exc).__name__, message=message)
        print(dumps(dict(type='turn.failed', error=dict(message=message, type=type(exc).__name__))), flush=True)
        return 1
    finally:
        runner.close()


if __name__ == '__main__':
    raise SystemExit(main())
