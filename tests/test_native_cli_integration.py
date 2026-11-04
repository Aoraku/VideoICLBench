"""Offline integration checks: no simulator or model API is invoked."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from vic_sdk import native_cli_engines as engines
from vic_sdk.native_agent import clean_env, cli_command, run


def configure(tmp_path, engine='gemini'):
    profile, work = tmp_path/'profile', tmp_path/'work'
    receipt = engines.configure(engine, profile, work, 'explicit-model',
        {'command': sys.executable, 'args': ['fixture.py']},
        {'base_url': 'http://127.0.0.1:9000', 'api_key': 'test-secret'},
        {'context_window': 1050000, 'compact_tokens': 945000})
    assert 'test-secret' not in json.dumps(receipt)
    return profile, work


def test_explicit_cli_options_override_private_provider_defaults():
    p = {'cli_options': {'context_window': 900000, 'compact_tokens': 700000}}
    assert engines.options_from_args(SimpleNamespace(native_context_window=800000,
        native_compact_tokens=600000), p)['context_window'] == 800000
    assert engines.options_from_args(SimpleNamespace(), p)['compact_tokens'] == 700000


@pytest.mark.parametrize('options', [{'context_window': -1}, {'compact_tokens': True},
                                    {'context_window': 100, 'compact_tokens': 100}])
def test_invalid_budgets_fail_before_profile_creation(tmp_path, options):
    profile = tmp_path/'profile'
    with pytest.raises(ValueError):
        engines.configure('gemini', profile, tmp_path/'work', 'model', {}, {}, options)
    assert not profile.exists()


def test_unknown_engine_does_not_fall_through_to_claude(tmp_path):
    with pytest.raises(ValueError, match='Unknown native CLI'):
        cli_command('typo', tmp_path, tmp_path, 'model', {})


def test_profile_engine_model_and_workspace_are_bound(tmp_path):
    profile, work = configure(tmp_path)
    with pytest.raises(ValueError, match='identity'):
        engines.command('gemini', profile, work, 'different-model')
    with pytest.raises(ValueError, match='Cannot change'):
        engines.configure('dsh', profile, work, 'explicit-model', {}, {}, {})


def test_resume_requires_persisted_exact_identity(tmp_path):
    profile, work = configure(tmp_path)
    session = 'a68e6153-7ddd-41d4-9e09-33d5e777b5cc'
    with pytest.raises(ValueError, match='exact original'):
        engines.command('gemini', profile, work, 'explicit-model', resume=session)
    engines.resolve_session('gemini', profile, {'session_id': session})
    with pytest.raises(ValueError, match='explicit resume'):
        engines.command('gemini', profile, work, 'explicit-model')
    cmd, _ = cli_command('gemini', profile, work, 'explicit-model', {}, resume=session)
    assert cmd[-2:] == ['--resume', session]
    with pytest.raises(ValueError, match='exact original'):
        engines.command('gemini', profile, work, 'explicit-model', resume='latest')


def test_native_summary_persists_identity_and_rejects_missing_identity(tmp_path):
    profile, _ = configure(tmp_path)
    output = tmp_path/'stdout.jsonl'
    sid = 'a68e6153-7ddd-41d4-9e09-33d5e777b5cc'
    output.write_text(json.dumps({'type': 'init', 'session_id': sid})+'\n'+
        json.dumps({'type': 'result', 'status': 'success'})+'\n')
    assert engines.summarize('gemini', output, profile)['session_identity_verified']
    persisted = (profile/'native-cli-session.private.json').read_bytes()
    output.write_text(json.dumps({'type': 'message', 'role': 'assistant', 'content': 'done'})+'\n'+
        json.dumps({'type': 'result', 'status': 'success'})+'\n')
    result = engines.summarize('gemini', output, profile)
    assert result['is_error'] and not result['session_identity_verified']
    assert (profile/'native-cli-session.private.json').read_bytes() == persisted


def test_actual_cli_version_is_checked_not_the_python_carrier(tmp_path):
    binary = tmp_path/'native.cjs'
    binary.write_text('console.log("0.32.1");\n')
    assert engines.binary_version('gemini', binary) == '0.32.1'
    binary.write_text('console.log("99.0.0");\n')
    with pytest.raises(ValueError, match='Unsupported native CLI version'):
        engines.binary_version('gemini', binary)


def test_protocol_preflight_runs_before_web_or_os_allocation(tmp_path, monkeypatch):
    credentials = tmp_path/'credentials.json'
    credentials.write_text(json.dumps({'gemini': {'api_key': 'test-secret',
        'base_url': 'http://127.0.0.1:9000', 'wire_api': 'responses'}}))
    def forbidden(*args, **kwargs):
        pytest.fail('Environment/control request before native protocol validation')
    monkeypatch.setattr('vic_sdk.native_agent.httpx.Client', forbidden)
    args = SimpleNamespace(output_root=tmp_path/'output', credentials=credentials,
        engine='gemini', api_key_env=None, base_url=None, model='test-model', binary=None)
    with pytest.raises(ValueError, match='GenerateContent'):
        run(args)


def test_tls_ca_is_preserved_but_unrelated_provider_keys_are_not(monkeypatch):
    monkeypatch.setenv('NODE_EXTRA_CA_CERTS', '/private/local-ca.pem')
    monkeypatch.setenv('GEMINI_API_KEY', 'unrelated-key')
    monkeypatch.setenv('KIMI_CODE_HOME', '/other-session')
    env = clean_env()
    assert env['NODE_EXTRA_CA_CERTS'] == '/private/local-ca.pem'
    assert 'GEMINI_API_KEY' not in env and 'KIMI_CODE_HOME' not in env
