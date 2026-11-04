"""Profiles and event readers for unmodified native model loops.

No adapter implements model requests, a replacement conversation or compaction.
"""
from importlib import import_module
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

EXTRA_ENGINES = ('gemini', 'dsh', 'zcode', 'kimi')
ENGINES = ('codex', 'claude', *EXTRA_ENGINES)

def claude_context_config(profile, model, options):
    return import_module('.claude_context', __name__).configure(Path(profile), model, options)

def claude_context_environment(profile, binary):
    return import_module('.claude_context', __name__).environment(Path(profile), binary)

def options_from_args(args, provider):
    options = dict(provider.get('cli_options') or {})
    requested = getattr(args, 'native_context_window', None)
    compact = getattr(args, 'native_compact_tokens', None)
    if requested is not None:
        options['context_window'] = requested
    if compact is not None:
        options['compact_tokens'] = compact
    options.setdefault('context_window', 1048576)
    options.setdefault('compact_tokens', 945000)
    options.setdefault('effort', getattr(args, 'effort', 'high'))
    return options

def adapter(engine):
    if engine not in EXTRA_ENGINES:
        raise ValueError('Unknown native CLI adapter: ' + str(engine))
    return import_module('.' + engine, __name__)

def _private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def configure(engine, profile, workspace, model, server, provider, options=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    options = dict(options or {})
    for name in ('context_window', 'compact_tokens'):
        if name in options and (type(options[name]) is not int or options[name] <= 0):
            raise ValueError(name + ' must be a positive integer')
    if options.get('context_window') and options.get('compact_tokens', 0) >= options['context_window']:
        raise ValueError('compact_tokens must be below context_window')
    metadata = dict(engine=engine, model=model, workspace=str(workspace))
    lock = profile/'native-cli-identity.private.json'
    if lock.exists() and json.loads(lock.read_text()) != metadata:
        raise ValueError('Cannot change the native engine/model/workspace of a trial')
    receipt = adapter(engine).configure(profile, workspace, model, server, provider, options)
    key = provider.get('api_key')
    if key and key in json.dumps(receipt):
        raise ValueError('Adapter receipt must not contain provider credentials')
    _private(lock, metadata)
    _private(profile/'native-cli-receipt.json', receipt)
    return receipt

def command(engine, profile, workspace, model, *, binary=None, resume=None):
    profile, workspace = Path(profile).resolve(), Path(workspace).resolve()
    expected = dict(engine=engine, model=model, workspace=str(workspace))
    if json.loads((profile/'native-cli-identity.private.json').read_text()) != expected:
        raise ValueError('Native CLI identity differs from its original profile')
    session_file = profile/'native-cli-session.private.json'
    persisted = json.loads(session_file.read_text()) if session_file.exists() else None
    if resume is not None:
        if persisted != dict(engine=engine, session_id=resume):
            raise ValueError('Resume requires the exact original persisted native session')
    elif persisted is not None:
        raise ValueError('Existing native session requires explicit resume')
    return adapter(engine).command(profile, workspace, model, binary=binary, resume=resume)

def preflight(engine, model, provider, options, *, binary=None, server=None, env=None):
    """Validate local CLI and protocol before allocating a task environment."""
    with tempfile.TemporaryDirectory(prefix='vic-cli-preflight-') as temporary:
        profile = Path(temporary)/'profile'
        workspace = Path(temporary)/'workspace'
        receipt = configure(engine, profile, workspace, model,
            server or {'command': 'python3', 'args': []}, provider, options)
        _, extra = command(engine, profile, workspace, model, binary=binary)
        version = binary_version(engine, binary, env={**(env or {}), **extra})
    return dict(receipt=receipt, cli_version=version)

def summarize(engine, output, profile, session_id=None):
    result = adapter(engine).summarize(Path(output), Path(profile), session_id=session_id)
    if result.get('engine') != engine:
        raise ValueError('Native CLI event reader returned a different engine')
    # A failed request still owns its original session. Preserve that identity
    # before any caller can issue a native resume command.
    try:
        value = resolve_session(engine, profile, result, session_id)
        result['session_identity_verified'] = value is not None
    except ValueError as error:
        result['session_identity_verified'] = False
        result['is_error'] = True
        result.setdefault('errors', []).append(dict(type='session_identity_error', message=str(error)))
    return result

def binary_version(engine, binary, *, env=None):
    """Read CLI identity, including official source-built Node artifacts."""
    executable = str(binary or engine)
    prefix = [shutil.which('node') or 'node', executable] if Path(executable).suffix in {'.js', '.cjs', '.mjs'} else [executable]
    result = subprocess.run([*prefix, '--version'], capture_output=True, text=True, timeout=20, env=env)
    if result.returncode:
        raise ValueError('Native CLI version check failed: ' + engine)
    version = result.stdout.strip()
    if not version:
        raise ValueError('Native CLI did not report its version: ' + engine)
    module = adapter(engine)
    supported = getattr(module, 'SUPPORTED_VERSIONS', ())
    if not supported and getattr(module, 'SUPPORTED_CLI_VERSION', None):
        supported = (module.SUPPORTED_CLI_VERSION,)
    versions = re.findall(r'(?<![\w.])\d+\.\d+\.\d+(?:-[\w.-]+)?(?![\w.])', version)
    if supported and (len(versions) != 1 or versions[0] not in supported):
        raise ValueError('Unsupported native CLI version for ' + engine)
    return version

def resolve_session(engine, profile, summary, expected=None):
    """Keep one native identity; never silently fall back to a fresh session."""
    identity = summary.get('session_id')
    if expected is not None and identity is not None and expected != identity:
        raise ValueError('Native CLI session identity changed')
    value = expected or identity
    if value is None and summary.get('model_response_observed'):
        raise ValueError('Model output without a native session cannot be continued')
    if value is not None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Invalid native session identity')
        path = Path(profile)/'native-cli-session.private.json'
        record = dict(engine=engine, session_id=value)
        if path.exists() and json.loads(path.read_text()) != record:
            raise ValueError('Native session differs from the persisted trial identity')
        _private(path, record)
    return value
