"""Z.ai's official ZCode source-build CLI adapter, not a similarly named npm CLI.

Official source: zai-org/ZCode/apps/zcode-cli/docs/usage. The native CLI
requires --prompt text, so a transparent exec launcher preserves stdin exactly.
"""
from __future__ import annotations

import json
import copy
import os
from pathlib import Path
import sys

if __package__:
    from .dsh import (_empty, _events, _options, _private_json, _provider, _native_compactions,
                      _model_context_window, MAX_MODEL_CONTEXT_WINDOW)
else:  # Invoked directly only as the stdin-to-native-argv exec carrier.
    import importlib.util
    _spec = importlib.util.spec_from_file_location('vic_native_dsh_helpers', Path(__file__).with_name('dsh.py'))
    _helpers = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_helpers)
    _empty, _events = _helpers._empty, _helpers._events
    _options, _private_json = _helpers._options, _helpers._private_json
    _provider, _native_compactions = _helpers._provider, _helpers._native_compactions
    _model_context_window = _helpers._model_context_window
    MAX_MODEL_CONTEXT_WINDOW = _helpers.MAX_MODEL_CONTEXT_WINDOW

# Pinned-build outgoing tool schemas must still be checked: this is a deny list,
# not a false claim that every future builtin/plugin tool is known here.
DISALLOWED_TOOLS = (
    'Bash', 'Read', 'Write', 'Edit', 'MultiEdit', 'Glob', 'Grep', 'LS',
    'NotebookEdit', 'Agent', 'Task', 'WebSearch', 'WebFetch', 'TodoWrite',
    'AskUserQuestion', 'EnterPlanMode', 'ExitPlanMode', 'TaskOutput', 'TaskStop',
    'TodoRead', 'ReadSessionContext',
)
SUPPORTED_CLI_VERSION = '0.17.1'
SOURCE_COMMIT = 'a9fe401eede6e6e5e01be9048679c206fe6f02d9'


def configure(profile: Path, workspace: Path, model, server, provider, options=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    p, base, key = _provider(provider)
    opt = _options(options)
    if opt.get('cli_version') not in (None, SUPPORTED_CLI_VERSION):
        raise ValueError('ZCode native source contract is pinned to ' + SUPPORTED_CLI_VERSION)
    protocol = p.get('wire_api', p.get('protocol', 'openai-chat-completions'))
    protocols = {'chat-completions': 'openai-chat-completions',
                 'openai-chat-completions': 'openai-chat-completions',
                 'responses': 'openai-responses', 'openai-responses': 'openai-responses',
                 'messages': 'anthropic-messages', 'anthropic': 'anthropic-messages',
                 'anthropic-messages': 'anthropic-messages'}
    if protocol not in protocols:
        raise ValueError('Unsupported native ZCode provider protocol')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('An explicit native model ID is required')
    if not isinstance(server, dict) or not server.get('command'):
        raise ValueError('Exactly one stdio GUI MCP server is required')
    userhome = profile / 'home'
    provider_path = userhome / '.zcode/v2/provider_config.json'
    provider_config = dict(schemaVersion=1, config=dict(
        providerConfigRules=dict(providerRules=[dict(providerId='vic', providerName='VideoICL',
            config=dict(group='standard-personal', access=dict(type='api-key', apiKey=key),
                        api=dict(type=protocols[protocol], baseUrl=base), personalModelIds=[model]))]),
        modelConfigRules=dict(providerModelRules=[], manualProviderModelRules=[]),
        defaultModelSelection=dict(providerId='vic', modelId=model)))
    requested_effort = opt.get('effort')
    if requested_effort is not None:
        if not isinstance(requested_effort, str) or not requested_effort.strip():
            raise ValueError('Native reasoning effort must be a nonempty level name')
        # Official modelSelectionSchema supports options.reasoningLevel. The
        # native model registry validates membership; never relabel max as high.
        provider_config['config']['defaultModelSelection']['options'] = {
            'reasoningLevel': requested_effort.strip()}
    # Current provider model rules are sparse overlays. Declare image transport
    # explicitly: the native fallback catalog otherwise strips tool-result PNGs.
    properties = {'inputFormat': {'supportsImage': True}}
    requested_window = opt.get('context_window')
    window = _model_context_window(requested_window)
    properties['contextWindow'] = window
    provider_config['config']['modelConfigRules']['providerModelRules'] = [
        dict(providerId='vic', modelId=model, config=dict(properties=properties))]
    # Optional full native rules remain supported without guessing reasoning maps.
    if opt.get('native_model_rules') is not None:
        rules = opt['native_model_rules']
        if not isinstance(rules, dict) or set(rules) - {'providerModelRules', 'manualProviderModelRules'}:
            raise ValueError('native_model_rules must contain official model rule arrays')
        if any(not isinstance(value, list) for value in rules.values()):
            raise ValueError('Native model rule values must be arrays')
        rules = copy.deepcopy(rules)
        # A manual model rule also defines capacity. Apply the selected model's
        # official ceiling and preserve explicitly smaller native limits.
        for group in rules.values():
            for rule in group:
                if rule.get('providerId') != 'vic' or rule.get('modelId') != model:
                    continue
                prop = rule.get('config', {}).get('properties', {})
                if prop.get('contextWindow') is not None:
                    prop['contextWindow'] = _model_context_window(prop['contextWindow'])
                    window = min(window, prop['contextWindow'])
        provider_config['config']['modelConfigRules'].update(rules)
        target_rules = provider_config['config']['modelConfigRules']
        target = next((rule for group in target_rules.values() for rule in group
                       if rule.get('providerId') == 'vic' and rule.get('modelId') == model), None)
        if target is None:
            target = dict(providerId='vic', modelId=model, config=dict(properties={}))
            target_rules['providerModelRules'].append(target)
        target.setdefault('config', {}).setdefault('properties', {})['contextWindow'] = window
        target['config']['properties'].setdefault('inputFormat', {})['supportsImage'] = True
    stream_idle_ms = opt.get('stream_idle_timeout_ms', 1800000)
    if any(type(value) is not int or not 0 < value <= 2147483647
           for value in (stream_idle_ms,)):
        raise ValueError('Native stream/network timeouts require positive bounded integer milliseconds')
    runtime = dict(modelStream=dict(idleTimeoutMs=stream_idle_ms),
        features=dict(mcp=True, subagent=False, memory=False, skill=False, compact=True),
        memory=dict(use=False), plugins=dict(enabled=False), skills=dict(enabled=False),
        hooks=dict(enabled=False), mcp=dict(servers=dict(vic=dict(
            type='stdio', command=server['command'], args=list(server.get('args', [])),
            env=dict(server.get('env', {})), cwd=str(workspace), enabled=True,
            isolation='session', timeoutMs=opt.get('mcp_timeout_ms', 2147483647)))))
    _private_json(provider_path, provider_config)
    _private_json(userhome / '.zcode/cli/config.json', runtime)
    receipt = dict(engine='zcode', model=model, workspace=str(workspace),
        native_protocol=protocols[protocol], native_compact=True,
        requested_effort=requested_effort, effective_effort=None,
        stream_idle_timeout_ms=stream_idle_ms,
        effort_runtime_verified=False,
        configured_reasoning_level=requested_effort.strip() if requested_effort else None,
        effort_configuration_status='Native defaultModelSelection.options.reasoningLevel configured; existing sessions retain their persisted selection and require an explicit native model switch',
        requested_context_window=opt.get('context_window'), requested_compact_tokens=opt.get('compact_tokens'),
        context_window=window, compact_tokens=None, context_window_runtime_verified=False,
        model_max_context_window=MAX_MODEL_CONTEXT_WINDOW,
        context_window_mapping='legacy_1050000_to_official_1048576'
        if requested_window == 1050000 else 'explicit_or_official_maximum',
        compact_tokens_status='No independent threshold override; native threshold is derived from configured contextWindow and model output budget',
        native_compact_threshold_expected=window-34000,
        native_compact_threshold_assumption='Pinned GLM normal output budget >=21000 and native buffer13000; verify native event',
        native_compact_threshold_formula='contextWindow - min(normalRequestMaxOutputTokens,21000) - 13000',
        context_configuration_status='native model rule configured; exact compact threshold uses native policy',
        gui_mcp_only_requested=True, tool_surface_runtime_verified=False,
        mcp_images_runtime_verified=False, provider_capability_verified=False,
        cli_version=SUPPORTED_CLI_VERSION, source_commit=SOURCE_COMMIT,
        prompt_transport='stdin-to-native-prompt-exec',
        credentials_in_receipt=False)
    _private_json(profile / 'adapter-receipt.json', receipt)
    return receipt


def command(profile, workspace, model, *, binary=None, resume=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    native = str(binary or 'zcode')
    cmd = ['node', native] if Path(native).suffix in ('.cjs', '.mjs', '.js') else [native]
    # The carrier adds --prompt after reading all stdin. No fake '-' prompt.
    cmd += ['--cwd', str(workspace), '--mode', 'yolo', '--workflow-mode', 'disabled',
            '--disallowed-tools', ' '.join(DISALLOWED_TOOLS),
            '--output-format', 'stream-json', '--no-color']
    if resume:
        cmd += ['--resume', str(resume)]
    userhome = profile / 'home'
    env = dict(HOME=str(userhome), USERPROFILE=str(userhome), ZCODE_DATA_BASE_DIR=str(userhome),
        ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=str(userhome / '.zcode/v2/provider_config.json'),
        ZCODE_STORAGE_DIR=str(userhome / '.zcode/cli'),
        ZCODE_SESSION_DB_PATH=str(userhome / '.zcode/cli/db/db.sqlite'),
        ZCODE_LOG_DIR=str(userhome / '.zcode/cli/logs'),
        ZCODE_MODEL_TELEMETRY_ENABLED='0')
    return [sys.executable, str(Path(__file__).resolve()), '--stdin-exec', *cmd], env


def summarize(output: Path, profile: Path, session_id=None):
    result = _empty('zcode', session_id)
    terminal = False
    seen_calls = set()
    for _, event in _events(output):
        kind = event.get('type')
        sid = event.get('sessionId', event.get('session_id'))
        if sid:
            if result['session_id'] and result['session_id'] != sid:
                result['errors'].append({'type': 'session_identity_mismatch'})
            else:
                result['session_id'] = sid
        if kind in ('error', 'turn.failed', '_malformed_ndjson') or event.get('is_error') is True:
            result['errors'].append(event)
        if kind == 'result':
            terminal = True
            response = event.get('response', '')
            result['final_text'] = response if isinstance(response, str) else ''
            result['model_response_observed'] |= bool(result['final_text'])
            result['usage'] = event.get('usage') if isinstance(event.get('usage'), dict) else None
            result['usage_scope'] = 'native_headless_current_attempt_including_compaction'
            result['native_projection'] = event.get('projection')
        if kind == 'session.updated' and isinstance(event.get('payload'), dict):
            # 0.17.1 result.projection reports the 200K projection default even
            # when the native model request completed with a custom 1M rule.
            # Preserve both native facts instead of relabeling the projection.
            capacity = event['payload'].get('contextWindow')
            if type(capacity) is int and capacity > 0:
                result['native_model_context_window'] = capacity
            payload = event['payload']
            if 'compactReason' in payload or 'autoCompactThreshold' in payload:
                result['compaction_events'].append(dict(source='native_stream', event=event))
        # Preserve official native event records; no synthetic success events.
        if kind in ('tool_call', 'tool/call'):
            data = event.get('data') if isinstance(event.get('data'), dict) else event
            result['tool_calls'].append(dict(name=data.get('name', data.get('tool')),
                                            call_id=data.get('callId', data.get('id'))))
            result['model_response_observed'] = True
        if kind == 'tool.updated':
            payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
            call_id = payload.get('toolCallId', payload.get('callId', payload.get('id')))
            name = payload.get('toolName', payload.get('name', payload.get('tool')))
            if payload.get('kind') in ('started', 'scheduled') and (call_id or name):
                identity = call_id or name
                if identity not in seen_calls:
                    result['tool_calls'].append(dict(name=name, call_id=call_id))
                    seen_calls.add(identity)
                result['model_response_observed'] = True
            if payload.get('kind') == 'error':
                result['errors'].append(dict(type='tool_error', payload=payload))
        if kind == 'model.streaming':
            payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
            if payload.get('kind') in ('text_delta', 'reasoning_delta', 'tool_call', 'tool_input_start'):
                result['model_response_observed'] = True
        if kind in ('assistant/message', 'assistant_message', 'text', 'thinking'):
            result['model_response_observed'] = True
        if isinstance(kind, str) and 'compac' in kind.lower():
            result['compaction_events'].append(dict(source='native_stream', event=event))
    if not terminal:
        result['errors'].append({'type': 'missing_native_result'})
    result['compaction_events'] += _native_compactions(profile, result['session_id'],
                                                      ['home/.zcode/cli/rollout'])
    result['is_error'] = bool(result['errors'])
    return result


def _stdin_exec(argv):
    prompt = sys.stdin.buffer.read().decode('utf-8')
    if not prompt.strip() or '\0' in prompt:
        raise ValueError('Native ZCode --prompt requires nonempty NUL-free UTF-8 input')
    if not argv:
        raise ValueError('Missing native ZCode binary')
    os.execvpe(argv[0], argv + ['--prompt', prompt], os.environ.copy())


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] != '--stdin-exec':
        raise SystemExit('This module is only a native ZCode stdin exec carrier')
    _stdin_exec(sys.argv[2:])
