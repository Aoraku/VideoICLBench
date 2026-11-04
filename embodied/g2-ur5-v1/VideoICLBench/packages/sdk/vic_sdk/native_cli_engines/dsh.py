"""Official DeepSeek Harness headless contract; no substitute agent loop.

Source: deepseek-ai/deepseek-harness, apps/cli and packages/bundle/headless.
Only profile generation and native-event normalization live here. Native tools,
compaction and persistence remain owned by the pinned DSH installation.
"""
from __future__ import annotations

import json
import io
import os
from pathlib import Path
from urllib.parse import urlsplit

# These IDs are from the official base bundle, not guessed tool-name globs.
DISABLED_ROWS = (
    'tool-plugin-manager', 'tool-working-directory', 'tool-bash', 'tool-pwsh',
    'tool-jobs', 'tool-fs', 'tool-fs-search', 'tool-skill', 'tool-subagent-list-agents',
    'tool-subagent-control', 'tool-subagent', 'tool-subagent-fork', 'tool-workflow',
    'tool-todo', 'tool-goal', 'tool-web', 'mcp-resources', 'session-title-llm', 'plan-mode',
    'agent-instructions', 'skill-filesystem', 'session-log-deepseek',
    'plugin-package-inventory-deepseek',
)
SUPPORTED_CLI_VERSION = '0.2.1-rc.5'
MAX_MODEL_CONTEXT_WINDOW = 1048576


def _model_context_window(requested=None):
    """Honor smaller limits; the historical 1050000 spelling means the 1M tier."""
    value = MAX_MODEL_CONTEXT_WINDOW if requested is None else _positive(requested, 'context_window')
    if value == 1050000:
        return MAX_MODEL_CONTEXT_WINDOW
    if value > MAX_MODEL_CONTEXT_WINDOW:
        raise ValueError('Selected official model supports at most 1048576 context tokens')
    return value


def _options(value):
    return dict(value or {}) if isinstance(value, dict) or value is None else vars(value)


def _private_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Refuse a symlink in isolated CLI configuration')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _provider(provider):
    p = _options(provider)
    base = p.get('base_url', p.get('baseURL'))
    key = p.get('api_key', p.get('apiKey'))
    if not isinstance(base, str) or not base or not isinstance(key, str) or not key:
        raise ValueError('Explicit base_url and api_key are required')
    u = urlsplit(base)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('Provider must have an HTTP(S) endpoint without URL credentials')
    if u.query or u.fragment:
        raise ValueError('Provider URL query and fragment are not supported')
    return p, base, key


def _positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


def _events(path):
    path = Path(path)
    if path.suffix == '.zstd':
        import zstandard
        stream = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(path.open('rb')),
                                  encoding='utf-8')
    else:
        stream = path.open(encoding='utf-8')
    with stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                yield number, {'type': '_malformed_ndjson', 'line': number}
                continue
            if not isinstance(event, dict):
                event = {'type': '_malformed_ndjson', 'line': number}
            yield number, event


def _empty(engine, session_id):
    return dict(engine=engine, session_id=session_id, final_text='', usage=None,
                errors=[], compaction_events=[], tool_calls=[],
                model_response_observed=False, is_error=False)


def _native_compactions(profile, session_id, directories, turns=None):
    # Exact session association is required; never merge another room's history.
    if not session_id:
        return []
    markers = []
    for relative in directories:
        root = Path(profile) / relative
        if not root.is_dir():
            continue
        for path in root.rglob('*'):
            if not path.is_file() or not (path.name.endswith('.jsonl') or path.name.endswith('.jsonl.zstd')):
                continue
            if session_id not in path.name and session_id not in path.parts:
                continue
            selected = set()
            for number, event in _events(path):
                kind = event.get('type', '')
                if isinstance(kind, str) and 'compac' in kind.lower():
                    data = event.get('data', {})
                    compact_id = data.get('compactionId')
                    if turns is not None:
                        if data.get('turn') in turns and compact_id:
                            selected.add(compact_id)
                        if compact_id not in selected:
                            continue
                    markers.append(dict(source='native_session', file=str(path.relative_to(profile)),
                                        line=number, type=kind, seq=event.get('seq'),
                                        timestamp=event.get('timestamp', event.get('time')), data=data))
    return markers


def configure(profile: Path, workspace: Path, model, server, provider, options=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    opt = _options(options)
    if opt.get('cli_version') not in (None, SUPPORTED_CLI_VERSION):
        raise ValueError('DSH GUI-only composition is pinned to ' + SUPPORTED_CLI_VERSION)
    p, base, key = _provider(provider)
    protocol = p.get('wire_api', p.get('protocol', 'anthropic-messages'))
    if protocol not in ('anthropic-messages', 'messages', 'anthropic', 'deepseek-messages'):
        raise ValueError('Official DSH adapter requires a Messages-compatible endpoint; no Responses conversion')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('An explicit native model ID is required')
    if not isinstance(server, dict) or not server.get('command'):
        raise ValueError('Exactly one stdio GUI MCP server is required')
    requested_window = opt.get('context_window')
    window = _model_context_window(requested_window)
    max_tokens = _positive(opt.get('max_output_tokens', 16384), 'max_output_tokens')
    headroom = _positive(opt.get('compact_headroom_tokens', 65536), 'compact_headroom_tokens')
    threshold = _positive(opt.get('compact_tokens', min(945000, int(window * .9),
                         window - max_tokens - headroom)), 'compact_tokens')
    if threshold >= window or threshold > window - max_tokens - headroom:
        raise ValueError('Compact threshold must leave native output and summary headroom')
    effort = opt.get('effort', 'high')
    if effort not in ('off', 'low', 'high', 'max'):
        raise ValueError('DSH native effort must be off, low, high or max')
    model_row = dict(id=model, contextWindow=window, maxTokens=max_tokens,
                     inputModalities=['text', 'image'])
    overlay = [dict(id=row, disabled=True) for row in DISABLED_ROWS]
    overlay += [
        dict(id='agent-default-model', config=dict(provider='deepseek-official', model=model,
                                                    reasoningEffort=effort)),
        dict(id='llm-deepseek', config=dict(baseURL=base, apiKeyEnv='DEEPSEEK_API_KEY',
             reasoningEffort=effort, maxTokens=max_tokens, defaultContextWindow=window,
             models=[model_row])),
        dict(id='compaction-basic', config=dict(auto=True, thresholdRatio=threshold / window,
             headroomTokens=headroom, retainRatio=.16, maxTokens=max_tokens)),
        {'insert': [dict(id='vic-gui-mcp', name='@deepseek-ai/dsh-mcp-client',
            config=dict(serverName='vic', transport='stdio', command=server['command'],
                        args=list(server.get('args', [])), env=dict(server.get('env', {})),
                        cwd=str(workspace), startupTimeoutMs=30000,
                        toolCallTimeoutMs=opt.get('mcp_timeout_ms', 2147483647),
                        failOnStartupError=True))]},
    ]
    # JSON is valid YAML; native Cordis loader owns schema parsing/validation.
    _private_json(profile / 'profiles/headless/cordis.patch.yml', overlay)
    _private_json(profile / 'profiles/headless/package.json',
                  {'private': True, 'dsh': {'profile': {'bundles': ['@deepseek-ai/dsh-base',
                                                             '@deepseek-ai/dsh-headless']}}})
    _private_json(profile / 'provider.private.json', {'api_key': key})
    receipt = dict(engine='dsh', model=model, workspace=str(workspace), native_compact=True,
                   context_window=window, compact_tokens=threshold, gui_mcp_only_requested=True,
                   requested_context_window=requested_window, model_max_context_window=MAX_MODEL_CONTEXT_WINDOW,
                   context_window_mapping='legacy_1050000_to_official_1048576'
                   if requested_window == 1050000 else 'explicit_or_official_maximum',
                   tool_surface_runtime_verified=False, provider_capability_verified=False,
                   native_protocol='anthropic-messages', cli_version=SUPPORTED_CLI_VERSION,
                   prompt_transport='stdin', credentials_in_receipt=False)
    _private_json(profile / 'adapter-receipt.json', receipt)
    return receipt


def command(profile, workspace, model, *, binary=None, resume=None):
    profile = Path(profile).resolve()
    key = json.loads((profile / 'provider.private.json').read_text())['api_key']
    env = dict(DSH_HOME=str(profile), DEEPSEEK_API_KEY=key, DSH_TELEMETRY_DISABLED='1')
    cmd = [str(binary or 'dsh'), '--profile', 'headless', '--json']
    if resume:
        cmd += ['--session-id', str(resume)]
    return cmd + ['-'], env


def summarize(output: Path, profile: Path, session_id=None):
    result = _empty('dsh', session_id)
    samples, usage_complete, final = [], True, False
    turns = set()
    last_turn_reason = None
    for _, event in _events(output):
        kind = event.get('type')
        sid = event.get('sessionId')
        if sid:
            if result['session_id'] and result['session_id'] != sid:
                result['errors'].append({'type': 'session_identity_mismatch'})
            else:
                result['session_id'] = sid
        if kind in ('error', '_malformed_ndjson'):
            result['errors'].append(event)
        if kind in ('text', 'thinking', 'tool_call'):
            result['model_response_observed'] = True
        if kind == 'tool_call':
            result['tool_calls'].append(dict(name=event.get('tool'), call_id=event.get('callId')))
        if kind == 'tool_result' and event.get('status') == 'error':
            result['errors'].append({'type': 'tool_error', 'call_id': event.get('callId'),
                                     'error': event.get('error')})
        if kind == 'status' and event.get('phase') == 'step_end':
            if isinstance(event.get('usage'), dict):
                samples.append(event['usage'])
            else:
                usage_complete = False
        if kind == 'status' and event.get('phase') == 'turn_start':
            last_turn_reason = None
            if event.get('turn') is not None:
                turns.add(event['turn'])
        if kind == 'status' and event.get('phase') == 'turn_end':
            last_turn_reason = event.get('reason')
        if kind == 'final':
            final = True
            text = event.get('text', '')
            result['final_text'] = text if isinstance(text, str) else ''
            result['model_response_observed'] |= bool(result['final_text'])
            # rc.5 emits reason on turn_end; later native builds repeat it
            # on final. Never infer completion solely from final text.
            reason = event.get('reason', last_turn_reason)
            if not isinstance(reason, dict) or reason.get('kind') != 'completed':
                result['errors'].append({'type': 'native_final_not_completed', 'reason': reason})
        if isinstance(kind, str) and 'compac' in kind.lower():
            result['compaction_events'].append({'source': 'native_stream', 'event': event})
    if samples and usage_complete:
        fields = dict(input_tokens='inputTokens', output_tokens='outputTokens',
                      total_tokens='totalTokens', cached_input_tokens='cacheReadTokens',
                      cache_write_tokens='cacheWriteTokens', reasoning_tokens='reasoningTokens')
        result['usage'] = {public: sum(s[native] for s in samples)
                           if all(type(s.get(native)) in (int, float) for s in samples) else None
                           for public, native in fields.items()}
    if not final:
        result['errors'].append({'type': 'missing_native_final'})
    result['usage_scope'] = 'native_step_end_current_attempt_excludes_compaction'
    result['compaction_usage'] = None
    try:
        result['compaction_events'] += _native_compactions(profile, result['session_id'],
                                                         ['sessions'], turns=turns)
        compact_summaries = [m for m in result['compaction_events']
                             if m.get('type') == 'compaction/summary']
        compact_samples = [m['data'].get('usage') for m in compact_summaries]
        if compact_samples and all(isinstance(sample, dict) for sample in compact_samples):
            fields = dict(input_tokens='inputTokens', output_tokens='outputTokens',
                          total_tokens='totalTokens', cached_input_tokens='cacheReadTokens',
                          cache_write_tokens='cacheWriteTokens', reasoning_tokens='reasoningTokens')
            result['compaction_usage'] = {
                public: sum(s[native] for s in compact_samples)
                if all(type(s.get(native)) in (int, float) for s in compact_samples) else None
                for public, native in fields.items()}
    except ImportError:
        result.setdefault('warnings', []).append({
            'type': 'native_compaction_log_decoder_unavailable', 'required_dependency': 'zstandard'})
        result['compaction_observability'] = 'unknown_without_zstandard'
    result['is_error'] = bool(result['errors'])
    return result
