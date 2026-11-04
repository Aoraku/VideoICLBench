"""Explicit native context policy checks; no models, GPU or external APIs."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from vic_sdk.native_cli_engines import claude_context as cc


@pytest.mark.parametrize('requested', [1000000, 1048576, 1050000])
@pytest.mark.parametrize('model', ['claude-opus-5-5', 'qwen3.8-max'])
def test_maximum_context_normalized_preserves_alias_hooks(tmp_path, requested, model):
    profile = tmp_path / 'profile'
    profile.mkdir()
    hooks = {'Stop': [{'hooks': [{'type': 'command', 'command': 'local-stop-hook'}]}]}
    (profile / 'settings.json').write_text(json.dumps({'hooks': hooks, 'permissions': {'deny': ['Bash']}}))
    receipt = cc.configure(profile, model, {'context_window': requested})
    assert receipt['model'] == model
    assert receipt['requested_context_window'] == requested
    assert receipt['context_window'] == receipt['auto_compact_window'] == 1000000
    assert receipt['default_effective_compact_threshold_tokens'] == 967000
    assert receipt['auto_compact_enabled'] is True
    settings = json.loads((profile / 'settings.json').read_text())
    assert settings['hooks'] == hooks and settings['permissions']['deny'] == ['Bash']
    assert settings['autoCompactEnabled'] is True
    for path in (profile / 'settings.json', profile / cc.RECEIPT):
        assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads((profile / cc.RECEIPT).read_text()) == receipt


def test_legacy_absent_receipt_does_not_probe_or_change_env(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('legacy caller must not run a version probe')
    monkeypatch.setattr(cc.subprocess, 'run', unexpected)
    assert cc.environment(tmp_path, 'unused') == {}


def test_version_guard_and_credential_free_probe(tmp_path, monkeypatch):
    cc.configure(tmp_path, 'qwen3.8-max', {'context_window': 1050000})
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private-no-probe')
    monkeypatch.setenv('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', '25')
    def version(cmd, **kwargs):
        assert cmd == ['/pinned/claude', '--version']
        assert not any('KEY' in k or k.startswith('ANTHROPIC') for k in kwargs['env'])
        assert kwargs['timeout'] == 15
        return SimpleNamespace(stdout='2.1.292 (Claude Code)\n')
    monkeypatch.setattr(cc.subprocess, 'run', version)
    env = cc.environment(tmp_path, '/pinned/claude')
    assert env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'] == '1000000'
    assert env['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] == '1000000'
    assert env['DISABLE_COMPACT'] == env['DISABLE_AUTO_COMPACT'] == '0'
    assert env['CLAUDE_CODE_DISABLE_1M_CONTEXT'] == '0'
    assert env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'] == ''
    assert 'MAX_INPUT_TOKENS' not in env
    for old in ('2.1.152', '2.1.280', '2.1.304', 'unknown'):
        monkeypatch.setattr(cc.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=old))
        with pytest.raises(RuntimeError, match='requires audited'):
            cc.environment(tmp_path, '/pinned/claude')


def test_explicit_compact_percent_preserved(tmp_path, monkeypatch):
    cc.configure(tmp_path, 'qwen3.8-max', {'claude_compact_percent': 90})
    monkeypatch.setattr(cc.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='2.1.292 (Claude Code)'))
    assert cc.environment(tmp_path)['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'] == '90'


@pytest.mark.parametrize('model', ['opus', 'claude-opus-4-5', 'claude-unknown', 'vendor/claude-sonnet-4-6'])
def test_does_not_rewrite_models_or_claim_unrecognized_claude_override(tmp_path, model):
    with pytest.raises(ValueError):
        cc.configure(tmp_path, model, {'context_window': 1000000})


@pytest.mark.parametrize('value', [32000, 200000, 2000000, True, '1000000'])
def test_unsupported_tier_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        cc.configure(tmp_path, 'qwen3.8-max', {'context_window': value})


def test_symlink_configuration_rejected(tmp_path):
    outside = tmp_path / 'other'
    outside.write_text('{}')
    (tmp_path / 'settings.json').symlink_to(outside)
    with pytest.raises(ValueError):
        cc.configure(tmp_path, 'qwen3.8-max', {})
    assert outside.read_text() == '{}'
