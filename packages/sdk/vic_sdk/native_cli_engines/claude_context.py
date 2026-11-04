"""Explicit 1M native Claude Code context policy, without an inference loop.

The pinned CLI supports declared context for unknown provider IDs while keeping
native compaction. Older installations must not silently assume 200K instead.
"""
import json
import os
from pathlib import Path
import re
import subprocess

SUPPORTED_VERSIONS = ('2.1.292',)
CONTEXT_WINDOW = 1000000
RECEIPT = 'claude-context.private.json'
SOURCES = [
    'https://code.claude.com/docs/en/model-config#context-window-and-auto-compaction',
    'https://code.claude.com/docs/en/model-config#which-ids-claude_code_max_context_tokens-applies-to',
    'https://code.claude.com/docs/en/env-vars',
]


def _read(path):
    if path.is_symlink():
        raise ValueError('Refusing symbolic-link Claude context configuration')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Claude context configuration must be an object')
    return value


def _private(path, value):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def configure(profile: Path, model: str, options: dict):
    """Enable an explicit 1M tier, preserving API aliases and existing hooks.

    1,048,576 and 1,050,000 are existing harness labels for the 1M tier; neither
    is advertised as the actual Claude model capacity. A small requested window
    is rejected here rather than silently enlarged. Legacy callers use no helper.
    """
    profile = Path(profile).absolute()
    if profile.is_symlink():
        raise ValueError('Refusing symbolic-link Claude profile')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('Claude context requires an explicit model ID')
    requested = options.get('context_window', options.get('codex_context_window', CONTEXT_WINDOW))
    if type(requested) is not int or requested not in (1000000, 1048576, 1050000):
        raise ValueError('Explicit Claude context requires a supported 1M tier')
    # A recognized older Claude model cannot be expanded by MAX_CONTEXT_TOKENS
    # with compaction enabled. Only the audited native-1M family is accepted;
    # unknown provider spellings use the supported declared-window mechanism.
    lower = model.lower()
    native = 'claude-opus-5-5' in lower
    if not native and ('claude-' in lower or lower in ('opus', 'sonnet', 'haiku', 'default', 'best', 'opusplan')):
        raise ValueError('Use an explicit supported native-1M model or declared provider ID; aliases are not rewritten')
    pct = options.get('claude_compact_percent')
    if pct is not None and (isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 0 < pct <= 100):
        raise ValueError('Explicit Claude compact percent must be between 0 and 100')
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings_path = profile / 'settings.json'
    settings = _read(settings_path) if settings_path.exists() or settings_path.is_symlink() else {}
    settings['autoCompactEnabled'] = True
    _private(settings_path, settings)
    receipt = dict(
        engine='claude', model=model, supported_versions=list(SUPPORTED_VERSIONS),
        requested_context_window=requested, context_window=CONTEXT_WINDOW,
        context_window_source='native_model_catalog' if native else 'explicit_provider_declared_window',
        auto_compact_enabled=True, compact_owner='native_claude_code',
        auto_compact_window=CONTEXT_WINDOW, claude_compact_percent=pct,
        native_output_reserve_cap_tokens=20000, native_compaction_reserve_tokens=13000,
        default_effective_compact_threshold_tokens=967000,
        compact_threshold_source='Claude Code2.1.292 K3=min(output,20000) reserve; iV=window-output_reserve-13000; explicit percent may lower threshold; native background precomputation can begin earlier',
        credentials_included=False, sources=SOURCES,
        compatibility_notes=[
            'Model ID is passed unchanged; provider must actually support the declared window',
            '1M is1000000 tokens; harness1048576/1050000 tier values are normalized explicitly',
            'No MAX_INPUT_TOKENS cap is set; output budget is independent of model context',
            'Native compact replaces history before capacity; this does not promise a full1M input prompt',
        ])
    _private(profile / RECEIPT, receipt)
    return receipt


def environment(profile: Path, binary=None):
    """Return launch overrides after a credential-free local version check.

    No receipt means a historical non-explicit caller: do not change its policy.
    Call this during preflight, before a simulation world or any model starts.
    """
    profile = Path(profile).absolute()
    path = profile / RECEIPT
    if not path.exists() and not path.is_symlink():
        return {}
    receipt = _read(path)
    if (receipt.get('context_window') != CONTEXT_WINDOW or
            receipt.get('auto_compact_window') != CONTEXT_WINDOW or
            receipt.get('auto_compact_enabled') is not True or
            receipt.get('supported_versions') != list(SUPPORTED_VERSIONS)):
        raise ValueError('Invalid or unsupported explicit Claude context receipt')
    # --version is purely local; exclude inherited auth, providers and projects.
    probe_env = {'PATH': os.environ.get('PATH', os.defpath), 'HOME': str(profile),
                 'CLAUDE_CONFIG_DIR': str(profile), 'DISABLE_AUTOUPDATER': '1',
                 'DISABLE_UPDATES': '1', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1'}
    try:
        result = subprocess.run([str(binary or 'claude'), '--version'], env=probe_env,
                                capture_output=True, text=True, timeout=15, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError('Cannot verify the installed Claude Code version before1M launch') from error
    match = re.search(r'(?m)^\s*(\d+\.\d+\.\d+)(?:\s|$)', result.stdout)
    version = match.group(1) if match else None
    if version not in SUPPORTED_VERSIONS:
        raise RuntimeError('Explicit Claude1M+native compact requires audited Claude Code2.1.292; installed=' + str(version))
    pct = receipt.get('claude_compact_percent')
    return dict(CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(CONTEXT_WINDOW),
                CLAUDE_CODE_AUTO_COMPACT_WINDOW=str(CONTEXT_WINDOW),
                DISABLE_COMPACT='0', DISABLE_AUTO_COMPACT='0',
                CLAUDE_CODE_DISABLE_1M_CONTEXT='0',
                CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT='0',
                CLAUDE_AUTOCOMPACT_PCT_OVERRIDE='' if pct is None else str(pct),
                CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE='')
