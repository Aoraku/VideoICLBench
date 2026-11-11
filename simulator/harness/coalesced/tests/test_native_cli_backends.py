"""Native backend contracts with local fixtures, no model or simulator calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'worker'), str(ROOT / 'VideoICLBench/packages/sdk')]
spec = importlib.util.spec_from_file_location('shared_native_worker', ROOT / 'worker/run.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
from adapters import codex


def catalog(tmp_path, window=1000000):
    path = tmp_path / 'models.json'
    path.write_text(json.dumps({'models': [{'slug': 'gpt-6-astra', 'tool_mode': 'code_mode_only',
        'context_window': window, 'max_context_window': window, 'apply_patch_tool_type': 'freeform',
        'supports_parallel_tool_calls': True}]}))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_native_settings_preserve_explicit_overrides(tmp_path):
    binary = tmp_path / 'native-cli'
    binary.write_text('fixture')
    settings = worker.worker_settings(SimpleNamespace(engine='codex', binary=binary))
    assert (settings['model'], settings['context_window'], settings['compact_tokens']) == ('gpt-6-astra', 1000000, 150000)
    custom = worker.worker_settings(SimpleNamespace(engine='claude', binary=binary,
        model='claude-opus-5-5', effort='medium', context_window=800000, compact_tokens=130000))
    assert custom['effort'] == 'medium' and custom['context_window'] == 800000
    assert custom['compact_tokens'] == 130000
    with pytest.raises(ValueError):
        worker.worker_settings(SimpleNamespace(engine='codex', binary=binary, compact_tokens=0))


def test_codex_uses_native_config_and_original_session(tmp_path, monkeypatch):
    monkeypatch.setattr(codex.subprocess, 'check_output', lambda *a, **k: 'codex-cli 0.163.0\n')
    source, pin = catalog(tmp_path)
    profile = tmp_path / 'profile'
    profile.mkdir()
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    options = {'context_window': 1000000, 'compact_tokens': 150000, 'effort': 'high',
               'model_catalog': source, 'model_catalog_sha256': pin, 'binary': '/fixture/codex'}
    server = {'command': 'python', 'args': ['gui.py'], 'tool_timeout_sec': 86400}
    codex.configure(profile, workspace, 'gpt-6-astra', server,
                    {'base_url': 'http://127.0.0.1:12345/v1', 'api_key': 'loopback-fixture'}, options)
    config = (profile / 'config.toml').read_text()
    assert 'model_context_window = 1000000' in config
    assert 'model_auto_compact_token_limit = 150000' in config
    assert 'wire_api = "responses"' in config and 'shell_tool = false' in config
    frozen = json.loads((profile / 'model-catalog.direct.private.json').read_text())['models'][0]
    assert frozen['tool_mode'] == 'direct' and frozen['apply_patch_tool_type'] is None
    sessions = profile / 'sessions'
    sessions.mkdir()
    (sessions / 'fixture-original.jsonl').write_text(json.dumps({
        'type': 'session_meta', 'payload': {'id': 'original'}}) + '\n')
    cmd, env = codex.command(profile, workspace, 'gpt-6-astra', binary='/fixture/codex', resume='original')
    assert cmd[-3:] == ['resume', 'original', '-']
    assert env['CODEX_HOME'] == str(profile) and env['VIC_MODEL_API_KEY'] == 'loopback-fixture'
    with pytest.raises(ValueError):
        codex.command(profile, workspace, 'gpt-6-astra', binary='/fixture/codex', resume='different')


def test_codex_rejects_catalog_without_requested_capacity(tmp_path, monkeypatch):
    source, pin = catalog(tmp_path, 262144)
    options = {'context_window': 1000000, 'compact_tokens': 150000, 'effort': 'high',
               'model_catalog': source, 'model_catalog_sha256': pin, 'binary': '/fixture/codex'}
    with pytest.raises(ValueError, match='does not support'):
        codex.configure(tmp_path / 'profile', tmp_path, 'gpt-6-astra',
                        {'command': 'python', 'args': []}, {'base_url': 'http://127.0.0.1:1/v1','api_key': 'fixture'}, options)


@pytest.mark.parametrize('engine', ['codex', 'claude'])
def test_attempt_loop_reuses_selected_model_and_attaches_only_first_image(tmp_path, monkeypatch, engine):
    from vic_sdk import embodied_agent, embodied_recovery, native_agent, native_structured_supervisor
    room = tmp_path / 'room'
    room.mkdir()
    (room / 'native-structured').mkdir()
    from PIL import Image
    Image.new('RGB', (2,2), (0,0,0)).save(room / 'native-structured/initial-gui.png')
    out = room / 'cli'
    out.mkdir()
    (out / 'profile').mkdir()
    (out / 'workspace').mkdir()
    identity = {'run_id': 'fixture'}
    connection = room / 'connection.json'
    connection.write_text(json.dumps({'api_timing_log': str(room / 'timing.jsonl')}))
    (room / 'worker-owner.json').write_text(json.dumps({'connection': str(connection)}))
    model = 'gpt-6-astra-custom' if engine == 'codex' else 'claude-opus-5-5'
    worker.save(out / 'effective-config.json', {'model': model,'effort': 'medium',
                'context_window': 800000,'compact_tokens': 130000})
    states = iter([{'terminal': False}, {'terminal': True}])
    monkeypatch.setattr(worker, 'wait_for_provider', lambda *a: next(states))
    monkeypatch.setattr(native_structured_supervisor, 'native_terminal_proven', lambda state, _:state['terminal'])
    monkeypatch.setattr(native_structured_supervisor, 'unresolved_tool_input', lambda _: False)
    monkeypatch.setattr(embodied_recovery, 'checked_barrier', lambda *a: {'status':'running','recovery_id':None,'action_count':2})
    monkeypatch.setattr(embodied_recovery, 'failure_class', lambda *a:'transient_api_error')
    monkeypatch.setattr(embodied_recovery, 'recover_control', lambda *a, **k:True)
    monkeypatch.setattr(embodied_agent, 'checked_evaluation', lambda *a:{'success': False})
    def summary(*a, **k):
        return {'session_id':'original','usage':{},'errors':[],'model_response_observed':True}
    monkeypatch.setattr(native_agent, 'summarize', summary)
    profile = out / 'profile/projects/fixture'
    profile.mkdir(parents=True)
    (profile / 'original.jsonl').write_text(json.dumps({'sessionId':'original'})+'\n')
    calls = []
    def execute(cmd, **kwargs):
        calls.append((list(cmd),kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(worker.subprocess, 'run', execute)
    module = SimpleNamespace(command=lambda profile, workspace, chosen, **kw:
        ([str(kw['binary']), 'exec', chosen, *(['resume',kw['resume']] if kw['resume'] else []), '-'], {}),
        summarize=summary)
    class Owner:
        def post(self, *a, **k):
            return SimpleNamespace(raise_for_status=lambda:None, json=lambda:{})
    worker.attempt_loop(engine=engine, room=room, out=out, owner=Owner(),identity=identity,
        binary='/fixture/native',module=module,prompt='fixture-task',
        qwen_config=({'command':'python','args':[],'tool_timeout_sec':86400},'http://127.0.0.1:1','loopback-fixture'))
    assert len(calls)==2
    if engine=='codex':
        assert all(model in cmd for cmd,_ in calls)
        assert '--image' in calls[0][0] and '--image' not in calls[1][0]
        assert 'original' in calls[1][0]
    else:
        assert calls[0][1]['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS']=='800000'
        assert all(cmd[cmd.index('--autocompact')+1]=='130000' for cmd,_ in calls)
        assert calls[1][0][calls[1][0].index('--resume')+1]=='original'
        assert 'image' in calls[0][1]['input'].decode() and 'image' not in calls[1][1]['input'].decode()


def test_glm_rejects_unsupported_overrides_and_reports_native_policy(tmp_path):
    binary = tmp_path / 'zcode'
    binary.write_text('fixture')
    settings = worker.worker_settings(SimpleNamespace(engine='zcode', binary=binary))
    assert settings['compact_tokens'] is None
    assert settings['native_compact_expected_tokens'] == 150000
    assert settings['compaction_policy'] == 'native_context_output_budget'
    for overrides in ({'effort':'low'}, {'compact_tokens':150000}, {'model':'other'}):
        with pytest.raises(ValueError):
            worker.worker_settings(SimpleNamespace(engine='zcode',binary=binary,**overrides))


def test_worker_config_check_never_executes_cli_or_creates_world(tmp_path):
    import subprocess
    binary = tmp_path / 'not-executable-cli'
    binary.write_text('This fixture must never run')
    source, pin = catalog(tmp_path)
    command = [sys.executable,str(ROOT/'worker/run.py'),'--check-config',
               '--engine','codex','--binary',str(binary),
               '--codex-model-catalog',str(source),'--codex-model-catalog-sha256',pin]
    result = subprocess.run(command,capture_output=True,text=True,check=True)
    settings = json.loads(result.stdout)
    assert settings['context_window']==1000000 and settings['compact_tokens']==150000
    assert not (tmp_path/'profile').exists()
    rejected = subprocess.run([sys.executable,str(ROOT/'worker/run.py'),'--check-config',
        '--engine','zcode','--binary',str(binary),'--effort','low'],capture_output=True,text=True)
    assert rejected.returncode!=0 and 'high effort' in rejected.stderr
