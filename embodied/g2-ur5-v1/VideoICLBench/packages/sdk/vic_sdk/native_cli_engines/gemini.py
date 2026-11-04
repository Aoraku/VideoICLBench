"""Pinned Gemini CLI headless adapter; CLI owns inference, history and compact."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

ENGINE = 'gemini'
SUPPORTED_VERSIONS = ('0.32.1',)
CONTEXT_WINDOW = 1048576


def _private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Refusing symbolic-link private configuration')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def configure(profile: Path, workspace: Path, model: str, server: dict,
              provider: dict, options: dict):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    if not model or not provider.get('api_key'):
        raise ValueError('Gemini requires an explicit model and private API key')
    base = provider.get('base_url', '')
    parsed = urlparse(base)
    if (parsed.scheme not in {'https', 'http'} or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.scheme == 'http' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}):
        raise ValueError('Gemini provider requires HTTPS or explicit localhost HTTP')
    if provider.get('wire_api', 'google_generate_content') not in {'generate_content', 'google_generate_content', 'gemini'}:
        raise ValueError('Gemini requires GenerateContent protocol, not OpenAI transport')
    compact = options.get('compact_tokens', options.get('codex_compact_tokens', 945000))
    if type(compact) is not int or not 0 < compact < CONTEXT_WINDOW:
        raise ValueError('Gemini compact threshold must be below native1048576 window')
    requested = options.get('context_window', options.get('codex_context_window'))
    # The existing harness uses1050000 as its1M-tier value; actual native Gemini
    # capacity remains explicit and no CLI model window is overwritten.
    if requested is not None and (type(requested) is not int or requested <= 0 or requested > 1050000):
        raise ValueError('Requested Gemini context window exceeds supported1M tier')
    mechanism = provider.get('api_key_auth_mechanism', 'x-goog-api-key')
    if mechanism not in {'x-goog-api-key', 'bearer'}:
        raise ValueError('Unknown Gemini API key mechanism')
    mcp = dict(command=server['command'], args=list(server.get('args', [])),
               env=dict(server.get('env', {})), trust=True,
               timeout=int(server.get('tool_timeout_sec', 86400) * 1000))
    if server.get('includeTools') is not None:
        mcp['includeTools'] = list(server['includeTools'])
    settings = {
        'security': {'auth': {'selectedType': 'gemini-api-key'}, 'folderTrust': {'enabled': False}},
        'model': {'name': model, 'maxSessionTurns': -1, 'compressionThreshold': compact / CONTEXT_WINDOW},
        'tools': {'core': []}, 'mcp': {'allowed': ['vic']}, 'mcpServers': {'vic': mcp},
        'agents': {'enabled': False, 'overrides': {'codebase_investigator': {'enabled': False}, 'cli_help': {'enabled': False}}},
        'skills': {'enabled': False}, 'hooksConfig': {'enabled': False},
        'telemetry': {'enabled': False}, 'ide': {'enabled': False},
        'context': {'fileName': [], 'includeDirectoryTree': False},
        'general': {'sessionRetention': {'enabled': False}},
    }
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    _private(profile / '.gemini/settings.json', settings)
    _private(profile / 'empty-system-settings.json', {})
    _private(profile / 'gemini-provider.private.json', {
        'api_key': provider['api_key'], 'base_url': base,
        'api_key_auth_mechanism': mechanism, 'api_version': provider.get('api_version'),
        'model': model, 'workspace': str(workspace),
    })
    return dict(engine=ENGINE, supported_versions=list(SUPPORTED_VERSIONS),
                protocol='google_generate_content', model=model,
                requested_context_window=requested, context_window=CONTEXT_WINDOW,
                compact_tokens=compact, compression_threshold=compact / CONTEXT_WINDOW,
                compact_owner='native_gemini_cli', builtin_tools=[], mcp_servers=['vic'],
                resume_snapshot_retained=False,
                settings_path=str(profile / '.gemini/settings.json'), credentials_included=False,
                compatibility_notes=['MCP isError images become error text in0.32.1; parity pending',
                                     'resume_snapshot_retained=false: native0.32.1 restores original transcript across process resume, not compressed snapshot',
                                     'Provider protocol and real image/action acceptance require separate verification'])


def command(profile, workspace, model, *, binary=None, resume=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    provider = json.loads((profile / 'gemini-provider.private.json').read_text())
    if provider['workspace'] != str(workspace) or provider['model'] != model:
        raise ValueError('Gemini resume must retain configured workspace/model')
    cmd = [str(binary or 'gemini'), '--model', model, '--prompt',
           'Follow the episode task supplied on stdin.', '--output-format', 'stream-json',
           '--approval-mode', 'default', '--allowed-mcp-server-names', 'vic']
    if resume:
        if resume == 'latest' or not isinstance(resume, str):
            raise ValueError('Gemini requires the exact native session UUID')
        import uuid
        try: uuid.UUID(resume)
        except (ValueError, AttributeError): raise ValueError('Gemini requires the exact native session UUID')
        cmd += ['--resume', resume]
    env = dict(GEMINI_CLI_HOME=str(profile), HOME=str(profile),
               GEMINI_API_KEY=provider['api_key'], GOOGLE_GEMINI_BASE_URL=provider['base_url'],
               GEMINI_API_KEY_AUTH_MECHANISM=provider['api_key_auth_mechanism'],
               GEMINI_CLI_SYSTEM_SETTINGS_PATH=str(profile / 'empty-system-settings.json'),
               GEMINI_CLI_SYSTEM_DEFAULTS_PATH=str(profile / 'empty-system-settings.json'),
               GOOGLE_GENAI_USE_GCA='false', GOOGLE_GENAI_USE_VERTEXAI='false',
               GEMINI_CLI_USE_COMPUTE_ADC='false', CLOUD_SHELL='false',
               GEMINI_TELEMETRY_ENABLED='false')
    if provider.get('api_version'):
        env['GOOGLE_GENAI_API_VERSION'] = provider['api_version']
    return cmd, env


def summarize(output: Path, profile: Path, session_id=None):
    result = dict(engine=ENGINE, session_id=session_id, final_text='', usage=None,
                  errors=[], compaction_events=[], tool_calls=[],
                  model_response_observed=False, is_error=False,
                  compaction_events_source='not_emitted_by_gemini0.32.1_headless_stream')
    calls, final, identities = {}, None, set()
    for line in Path(output).read_text().splitlines():
        try: event = json.loads(line)
        except ValueError:
            #0.32.1 can concatenate a startup diagnostic and the init JSON.
            # Recover only the explicit event suffix, retaining the diagnostic.
            index = line.find('{"type":')
            if index <= 0: continue
            try: event = json.loads(line[index:])
            except ValueError: continue
            result['errors'].append(dict(message=line[:index], severity='warning'))
        if not isinstance(event, dict): continue
        kind = event.get('type')
        if kind == 'init' and event.get('session_id'):
            identities.add(event['session_id'])
        elif kind == 'message' and event.get('role') == 'assistant':
            content = event.get('content', '')
            if isinstance(content, str):
                result['model_response_observed'] |= bool(content)
                result['final_text'] = result['final_text'] + content if event.get('delta') else content
        elif kind == 'tool_use':
            result['model_response_observed'] = True
            calls[event.get('tool_id')] = dict(name=event.get('tool_name'), status='requested', id=event.get('tool_id'))
        elif kind == 'tool_result':
            calls.setdefault(event.get('tool_id'), dict(id=event.get('tool_id'))).update(status=event.get('status'))
            if event.get('status') == 'error':
                result['errors'].append(event.get('error') or dict(message=event.get('output'), severity='tool_error'))
        elif kind == 'error':
            result['errors'].append(dict(message=event.get('message'), severity=event.get('severity')))
        elif kind == 'result':
            final = event  # Native stats are cumulative: latest result only.
    if len(identities) == 1:
        actual = next(iter(identities))
        if session_id is None: result['session_id'] = actual
        elif session_id != actual:
            result['is_error'] = True
            result['errors'].append(dict(message='Gemini native session identity mismatch'))
    elif len(identities) > 1:
        result['is_error'] = True
        result['errors'].append(dict(message='Multiple Gemini native session identities'))
    if final is None or final.get('status') != 'success':
        result['is_error'] = True
        result['errors'].append(final.get('error') if final and final.get('error') else dict(message='Gemini stream has no successful final result'))
    if final and isinstance(final.get('stats'), dict):
        s = final['stats']
        result['usage'] = dict(input_tokens=s.get('input_tokens'), output_tokens=s.get('output_tokens'),
                               total_tokens=s.get('total_tokens'),
                               input_tokens_details=dict(cached_tokens=s.get('cached')),
                               output_tokens_details=dict(reasoning_tokens=None),
                               uncached_input_tokens=s.get('input'), source='gemini_native_result_stats',
                               usage_scope='native_reported_generation_responses_this_cli_invocation_all_roles',
                               usage_includes_compaction=True,
                               usage_scope_source='gemini0.32.1 LoggingContentGenerator->uiTelemetryService.processApiResponse(all roles)->StreamJsonFormatter; verified local native compact fixture',
                               billing_completeness='not_a_provider_billing_ledger; countTokens and failures_without_returned_usage_are_not_included',
                               reasoning_tokens_source='not_available_in_pinned_stream',
                               cached_tokens_source='gemini_native_result_stats' if 'cached' in s else 'not_available_in_pinned_stream')
    result['tool_calls'] = list(calls.values())
    return result
