"""Native Codex exec/resume using the shared GUI-only SDK and pinned catalog."""
from pathlib import Path
import json
import subprocess

from vic_sdk.direct_tools import freeze_direct_model_catalog, validate_context_window
from vic_sdk.native_agent import cli_command, codex_config, private_json, summarize as native_summary
from vic_sdk.embodied_recovery import resolve_session


def configure(profile, workspace, model, server, provider, options):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    source = options.get('model_catalog')
    checksum = options.get('model_catalog_sha256')
    if not source or not checksum:
        raise ValueError('Codex requires an explicit complete model catalog and SHA256')
    binary = options['binary']
    window, compact = options['context_window'], options['compact_tokens']
    validate_context_window(source, checksum, model, window, compact)
    version = subprocess.check_output([str(binary), '--version'], text=True, timeout=15).strip()
    catalog = freeze_direct_model_catalog(profile, source, checksum, model,
                                         cli_version=version, serial_tools=False)
    # Task-specific instructions arrive once in the user prompt. The native role
    # and developer contract are shared with the other CLI backends.
    from vic_sdk.embodied_codex_mcp import NATIVE_MODEL_INSTRUCTIONS, NATIVE_TOOL_INSTRUCTIONS
    role = profile / 'model-instructions.md'
    role.write_text(NATIVE_MODEL_INSTRUCTIONS + '\n')
    configuration = ('model_instructions_file = ' + json.dumps(str(role)) + '\n'
                     + 'model_catalog_json = ' + json.dumps(catalog['catalog_path']) + '\n'
                     + 'developer_instructions = ' + json.dumps(NATIVE_TOOL_INSTRUCTIONS) + '\n'
                     + codex_config(model, provider['base_url'], server,
                         compact_tokens=compact, context_window=window,
                         effort=options['effort'], isolated_tools=True,
                         tool_output_tokens=32768, stream_idle_timeout_ms=86400000))
    (profile / 'config.toml').write_text(configuration)
    private_json(profile / 'codex-adapter.private.json', {
        'model': model, 'workspace': str(workspace), 'server': server,
        'base_url': provider['base_url'], 'api_key': provider['api_key'],
        'cli_version': version, 'context_window': window, 'compact_tokens': compact,
        'effort': options['effort'], 'catalog_sha256': catalog['output_sha256']})


def command(profile, workspace, model, *, binary, resume=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    metadata = json.loads((profile / 'codex-adapter.private.json').read_text())
    if metadata['model'] != model or metadata['workspace'] != str(workspace):
        raise ValueError('Original Codex model/workspace identity changed')
    if resume:
        resolve_session(profile, {'session_id': resume}, resume)
    cmd, env = cli_command('codex', profile, workspace, model, metadata['server'],
                           resume=resume, binary=binary)
    env['VIC_MODEL_API_KEY'] = metadata['api_key']
    return cmd, env


def summarize(output, profile, session_id=None):
    result = native_summary('codex', Path(output), Path(profile), session_id=session_id)
    result['session_id'] = resolve_session(profile, result, session_id)
    return result
