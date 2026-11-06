"""Diagnostic transport tests; optional real CLI uses a dummy localhost provider only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/diagnostics/probe_native_tool_wait.py'
spec = importlib.util.spec_from_file_location('native_wait_probe', SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_request_tools_includes_responses_lite_and_discovery():
    namespace = {'type': 'namespace', 'name': 'mcp__slow', 'tools': [
        {'type': 'function', 'name': 'wait_once'}]}
    _, found = probe.request_tools({'input': [
        {'type': 'additional_tools', 'tools': [{'type': 'custom', 'name': 'exec'}]},
        {'type': 'tool_search_output', 'tools': [namespace]}]})
    assert {'name': 'wait_once', 'type': 'function', 'namespace': 'mcp__slow'} in found
    assert any(t['name'] == 'exec' for t in found)


def test_standard_tools_and_unrelated_message_are_not_lost():
    _, found = probe.request_tools({'tools': [{'type': 'function', 'name': 'a'}],
                                    'input': [{'type': 'message', 'tools': [{'name': 'fake'}]}]})
    assert [t['name'] for t in found] == ['a']


def test_synthetic_mcp_returns_only_after_end_marker(tmp_path):
    events = tmp_path / 'mcp.jsonl'
    process = subprocess.Popen([sys.executable, str(SCRIPT), '--mcp-server', str(events),
                                '--delay', '.05'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                        'params': {'name': 'wait_once', 'arguments': {}}}) + '\n')
        process.stdin.flush()
        result = json.loads(process.stdout.readline())
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        assert [r['event'] for r in rows] == ['tool_start', 'tool_end']
        assert rows[1]['at'] - rows[0]['at'] >= .05
        assert result['result']['content'][0]['text'] == 'ACK: synthetic wait completed'
    finally:
        process.stdin.close()
        process.wait(timeout=5)


@pytest.mark.skipif(not os.environ.get('VIDEOICL_TEST_CODEX_BINARY'),
                    reason='Opt-in isolated real Codex + localhost mock, no provider')
def test_real_codex_direct_waits_past_async_yield(tmp_path):
    catalog = os.environ.get('VIDEOICL_TEST_DIRECT_CATALOG')
    if not catalog:
        pytest.skip('Requires an isolated model catalog with tool_mode=direct')
    result = probe.run_probe(os.environ['VIDEOICL_TEST_CODEX_BINARY'], tmp_path / 'run',
                             seconds=35, model_catalog=catalog)
    assert result['external_api_requests'] == 0
    assert result['direct_tool_wait_passed'], result


def _catalog(tmp_path):
    import hashlib
    value = {'metadata': {'exact': [1, 2]}, 'models': [
        {'slug': 'gpt-6-astra', 'tool_mode': 'code_mode_only', 'model_messages': {'keep': 'native'}, 'context_window': 272000,
         'supports_search_tool': True, 'multi_agent_version': 'v2'},
        {'slug': 'another-model', 'tool_mode': 'code_mode_only', 'opaque': [True, None]}]}
    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps(value))
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), value


def test_freeze_changes_only_target_registry_fields_and_pins_profile(tmp_path):
    import copy
    import hashlib
    from vic_sdk.direct_tools import freeze_direct_model_catalog, validate_model_catalog
    path, digest, original = _catalog(tmp_path)
    assert validate_model_catalog(path, digest, 'gpt-6-astra')['original_tool_mode'] == 'code_mode_only'
    receipt = freeze_direct_model_catalog(tmp_path / 'profile', path, digest, 'gpt-6-astra', cli_version='codex-cli 0.163.0')
    expected = copy.deepcopy(original)
    expected['models'][0].update(tool_mode='direct', apply_patch_tool_type=None, experimental_supported_tools=[], supports_search_tool=False)
    del expected['models'][0]['multi_agent_version']
    assert receipt['registry_changes']['multi_agent_version']['removed'] is True
    result = Path(receipt['catalog_path'])
    assert json.loads(result.read_text()) == expected
    assert result.stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(result.read_bytes()).hexdigest() == receipt['output_sha256']
    assert Path(receipt['source_copy_path']).read_bytes() == path.read_bytes()
    assert freeze_direct_model_catalog(tmp_path / 'profile', path, digest, 'gpt-6-astra', cli_version='codex-cli 0.163.0') == receipt
    assert json.loads(path.read_text()) == original


@pytest.mark.parametrize('mutation', ['hash', 'duplicate', 'missing_mode', 'missing_model'])
def test_catalog_rejects_unpinned_or_ambiguous_input(tmp_path, mutation):
    import hashlib
    from vic_sdk.direct_tools import validate_model_catalog
    path, digest, value = _catalog(tmp_path)
    if mutation == 'hash':
        digest = '0' * 64
    else:
        if mutation == 'duplicate': value['models'].append(value['models'][0])
        if mutation == 'missing_mode': del value['models'][0]['tool_mode']
        if mutation == 'missing_model': value['models'] = []
        path.write_text(json.dumps(value));digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        validate_model_catalog(path, digest, 'gpt-6-astra')


def test_profile_catalog_refuses_cross_version_or_content_replacement(tmp_path):
    from vic_sdk.direct_tools import freeze_direct_model_catalog
    path, digest, _ = _catalog(tmp_path)
    receipt = freeze_direct_model_catalog(tmp_path / 'profile', path, digest, 'gpt-6-astra', cli_version='codex-cli 0.163.0')
    before = Path(receipt['catalog_path']).read_bytes()
    with pytest.raises(ValueError, match='Refusing'):
        freeze_direct_model_catalog(tmp_path / 'profile', path, digest, 'gpt-6-astra', cli_version='codex-cli 0.164.0')
    assert Path(receipt['catalog_path']).read_bytes() == before


def test_profile_rejects_unverified_native_cli_version(tmp_path):
    from vic_sdk.direct_tools import freeze_direct_model_catalog
    path, digest, _ = _catalog(tmp_path)
    with pytest.raises(ValueError, match='has not passed'):
        freeze_direct_model_catalog(tmp_path / 'profile', path, digest, 'gpt-6-astra', cli_version='codex-cli 9.99.0')
    assert not (tmp_path / 'profile').exists()
