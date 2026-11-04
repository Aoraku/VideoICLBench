"""Pure filesystem/config/parser checks; no CLI, MCP, API, or GPU starts."""
import json
import os
from pathlib import Path
import pytest
from vic_sdk.native_cli_engines import gemini


def prepared(tmp_path, **options):
    profile, workspace = tmp_path/'profile', tmp_path/'workspace'
    receipt = gemini.configure(profile, workspace, 'gemini-explicit',
        dict(command='/python', args=['-m','fake_mcp'], env={'PYTHONPATH':'/sdk'}),
        dict(api_key='private-example', base_url='https://provider.example'), options)
    return profile, workspace, receipt


def test_isolated_native_configuration_and_command(tmp_path):
    profile, workspace, receipt = prepared(tmp_path, context_window=1050000)
    settings = json.loads((profile/'.gemini/settings.json').read_text())
    assert settings['tools']['core'] == []
    assert settings['agents']['overrides']['cli_help']['enabled'] is False
    assert settings['agents']['overrides']['codebase_investigator']['enabled'] is False
    assert list(settings['mcpServers']) == ['vic']
    assert settings['model']['compressionThreshold'] * 1048576 == 945000
    assert 'private-example' not in json.dumps(receipt)
    assert receipt['context_window'] == 1048576
    assert receipt['resume_snapshot_retained'] is False
    assert any('resume_snapshot_retained=false' in note for note in receipt['compatibility_notes'])
    for p in [profile/'.gemini/settings.json', profile/'gemini-provider.private.json']:
        assert p.stat().st_mode & 0o777 == 0o600
    sid='71b8bfa4-1585-499e-8b17-a1347555cc19'
    cmd, env = gemini.command(profile, workspace, 'gemini-explicit', binary='/gemini', resume=sid)
    assert cmd[-2:] == ['--resume',sid]
    assert cmd[cmd.index('--output-format')+1] == 'stream-json'
    assert env['GEMINI_API_KEY'] == 'private-example'
    assert env['HOME'] == env['GEMINI_CLI_HOME'] == str(profile)
    assert 'private-example' not in ' '.join(cmd)
    with pytest.raises(ValueError): gemini.command(profile, workspace, 'other')
    with pytest.raises(ValueError): gemini.command(profile, workspace, 'gemini-explicit', resume='latest')


def test_provider_and_compaction_rejected(tmp_path):
    with pytest.raises(ValueError): prepared(tmp_path, compact_tokens=1048576)
    for base in ['http://remote.example', 'https://u:p@remote.example', 'https://host/?key=x']:
        with pytest.raises(ValueError):
            gemini.configure(tmp_path/'p', tmp_path/'w', 'm', {'command':'p'}, {'api_key':'x','base_url':base}, {})
    with pytest.raises(ValueError):
        gemini.configure(tmp_path/'p', tmp_path/'w', 'm', {'command':'p'}, {'api_key':'x','base_url':'https://host','wire_api':'responses'}, {})


def test_latest_stats_cache_and_null_reasoning(tmp_path):
    events = [dict(type='init',session_id='s'), dict(type='message',role='assistant',content='Done',delta=True),
              dict(type='tool_use',tool_id='t',tool_name='program'), dict(type='tool_result',tool_id='t',status='success'),
              dict(type='result',status='success',stats={'input_tokens':100,'cached':75,'input':25,'output_tokens':10,'total_tokens':115})]
    p=tmp_path/'stream';p.write_text('\n'.join(json.dumps(e) for e in events+[events[-1]]))
    result=gemini.summarize(p,tmp_path)
    assert result['usage']['input_tokens']==100
    assert result['usage']['input_tokens_details']['cached_tokens']==75
    assert result['usage']['output_tokens_details']['reasoning_tokens'] is None
    assert result['usage']['usage_includes_compaction'] is True
    assert result['usage']['usage_scope']=='native_reported_generation_responses_this_cli_invocation_all_roles'
    assert 'processApiResponse' in result['usage']['usage_scope_source']
    assert 'not_a_provider_billing_ledger' in result['usage']['billing_completeness']
    assert result['final_text']=='Done' and not result['is_error']
    assert result['model_response_observed'] and result['tool_calls'][0]['status']=='success'
    assert gemini.summarize(p,tmp_path)==result
    assert gemini.summarize(p,tmp_path,session_id='wrong')['is_error']


def test_truncated_stream_is_not_success_and_missing_cache_is_null(tmp_path):
    p=tmp_path/'stream';p.write_text('{"type":"message","role":"assistant","content":"thinking"}\n{partial')
    assert gemini.summarize(p,tmp_path)['is_error']
    p.write_text(json.dumps(dict(type='result',status='success',stats={'input_tokens':9})))
    result=gemini.summarize(p,tmp_path)
    assert result['usage']['input_tokens_details']['cached_tokens'] is None
    assert result['usage']['cached_tokens_source']=='not_available_in_pinned_stream'


def test_real_cli_diagnostic_prefix_does_not_lose_session_identity(tmp_path):
    p=tmp_path/'stream'
    p.write_text('MCP issues detected.'+json.dumps(dict(type='init',session_id='exact'))+'\n'+
                 json.dumps(dict(type='tool_result',tool_id='t',status='error',error={'type':'missing','message':'tool not found'}))+'\n'+
                 json.dumps(dict(type='result',status='success')))
    result=gemini.summarize(p,tmp_path)
    assert result['session_id']=='exact'
    assert result['errors'][0]['severity']=='warning'
    assert result['errors'][1]['type']=='missing'
