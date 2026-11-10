"""Native Claude Code structured GUI adapter; no model loop or history reconstruction."""
import base64
import json
from pathlib import Path
import re
import subprocess
from .native_agent import cli_command, private_json
from .embodied_codex_mcp import NATIVE_MODEL_INSTRUCTIONS, NATIVE_TOOL_INSTRUCTIONS


def configure(profile, binary, model):
    version = subprocess.check_output([str(binary), '--version'], text=True, timeout=15).strip()
    if not re.match(r'^2\.1\.292(?:\s|$)', version):
        raise ValueError('Structured Claude requires audited CLI 2.1.292')
    if model != 'claude-opus-5-5':
        raise ValueError('Structured Claude currently requires explicit claude-opus-5-5')
    private_json(Path(profile)/'settings.json', {'autoCompactEnabled': True})
    receipt = dict(cli_version=version, context_window=1000000, auto_compact_window=150000,
        compact_percent=80, nominal_compact_threshold_tokens=120000,
        compact_owner='native_claude_code', history_reconstructed=False)
    private_json(Path(profile)/'claude-context.private.json', receipt)
    return receipt


def command(profile, workspace, model, server, *, binary, budget, base_url, key, effort='high', resume=None):
    cmd, env = cli_command('claude', profile, workspace, model, server,
        binary=binary, budget=budget, resume=resume, serial_tools=False)
    cmd += ['--input-format', 'stream-json', '--system-prompt',
        NATIVE_MODEL_INSTRUCTIONS+'\n'+NATIVE_TOOL_INSTRUCTIONS,
        '--effort', effort, '--autocompact', '150000']
    # A fresh isolated profile owns native history and session persistence.
    home = Path(profile)/'home'
    home.mkdir(exist_ok=True, mode=0o700)
    if base_url.endswith('/v1'): base_url = base_url[:-3]
    env.update(HOME=str(home), ANTHROPIC_BASE_URL=base_url, ANTHROPIC_AUTH_TOKEN=key,
        CLAUDE_CODE_MAX_CONTEXT_TOKENS='1000000', CLAUDE_CODE_AUTO_COMPACT_WINDOW='150000',
        CLAUDE_AUTOCOMPACT_PCT_OVERRIDE='80', DISABLE_COMPACT='0', DISABLE_AUTO_COMPACT='0',
        CLAUDE_CODE_DISABLE_1M_CONTEXT='0', DISABLE_AUTOUPDATER='1', DISABLE_UPDATES='1',
        MCP_TOOL_TIMEOUT=str(server['tool_timeout_sec']*1000))
    return cmd, env


def user_message(text, image_path=None):
    content = [{'type':'text', 'text':text}]
    if image_path is not None:
        raw = Path(image_path).read_bytes()
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Initial GUI must be a PNG')
        content.append({'type':'image', 'source':{'type':'base64', 'media_type':'image/png',
            'data':base64.b64encode(raw).decode()}})
    return json.dumps({'type':'user', 'message':{'role':'user','content':content}}, ensure_ascii=False)+'\n'


def resolve_session(profile, summary, expected=None):
    reported = summary.get('session_id')
    if reported is not None and (not isinstance(reported,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}',reported)):
        raise ValueError('Invalid Claude session identity')
    if expected and reported and expected != reported:
        raise ValueError('Claude session changed')
    candidate = expected or reported
    if candidate is None:
        if summary.get('model_response_observed'):
            raise ValueError('Claude model response lacks session identity')
        return None
    matches = list((Path(profile)/'projects').glob('*/'+candidate+'.jsonl'))
    if len(matches) != 1:
        raise ValueError('Claude persisted session missing or ambiguous')
    identities=set()
    for line in matches[0].read_text().splitlines():
        row=json.loads(line)
        if row.get('sessionId'): identities.add(row['sessionId'])
    if identities != {candidate}:
        raise ValueError('Claude persisted session identity mismatch')
    return candidate
