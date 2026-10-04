import base64
import json
import os
import tomllib
from pathlib import Path

import httpx
import pytest

pytest.importorskip("mcp")

from vic_sdk.computer_mcp import Computer, make_server
from vic_sdk.native_agent import clean_env, cli_command, codex_config, private_json, summarize


def test_native_profiles_use_real_cli_and_no_custom_context_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-secret")
    monkeypatch.setenv("VIC_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("CLAUDECODE", "parent-session")
    env = clean_env()
    assert not {"OPENAI_API_KEY", "VIC_ADMIN_TOKEN", "CLAUDECODE"} & env.keys()
    server = {"command": "/python", "args": ["-m", "vic_sdk.computer_mcp", "--config", "/private/config"]}
    config = tomllib.loads(codex_config("model-custom", "https://gateway.example/v1", server))
    assert config["model"] == "model-custom"
    assert config["model_providers"]["vic_remote"]["wire_api"] == "responses"
    assert "model_auto_compact_token_limit" not in config
    compatibility = tomllib.loads(codex_config("model-custom", "https://gateway.example/v1", server, code_mode=True))
    assert compatibility["features"]["code_mode"] is True
    smoke = tomllib.loads(codex_config("model-custom", "https://gateway.example/v1", server, 6000))
    assert smoke["model_auto_compact_token_limit"] == 6000
    cmd, env = cli_command("codex", tmp_path, tmp_path, "model-custom", server, resume="session-id")
    assert Path(cmd[0]).name == "codex" and cmd[1] == "exec" and cmd[-3:] == ["resume", "session-id", "-"]
    assert "--dangerously-bypass-hook-trust" not in cmd
    (tmp_path / "hooks.json").write_text('{}')
    cmd, _ = cli_command("codex", tmp_path, tmp_path, "model-custom", server)
    assert "--dangerously-bypass-hook-trust" in cmd
    cmd, env = cli_command("claude", tmp_path, tmp_path, "model-custom", server, resume="session-id")
    assert cmd[:2] == ["claude", "-p"] and cmd[-2:] == ["--resume", "session-id"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in env
    cmd, _ = cli_command("claude", tmp_path, tmp_path, "model-custom", server, serial_tools=True)
    assert "--append-system-prompt" in cmd
    _, env = cli_command("claude", tmp_path, tmp_path, "model-custom", server, compact=5)
    assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "5"


def test_actor_only_tools_real_image_action_and_stale_frame(tmp_path):
    requests = []
    counter = 0
    def handler(request):
        nonlocal counter
        requests.append(request)
        assert request.headers["authorization"] == "Bearer actor-only"
        if request.method == "GET":
            counter += 1
            return httpx.Response(200, json={"image": "data:image/png;base64," + base64.b64encode(b"test-png").decode(),
                "frame": counter, "epoch": 2, "width": 1280, "height": 960})
        return httpx.Response(200, json={"accepted": True})
    computer = Computer({"control_url": "http://control", "actor_token": "actor-only", "run_id": "abc",
                         "output_dir": str(tmp_path), "max_actions": 1})
    computer.http.close()
    computer.http = httpx.Client(base_url="http://control", transport=httpx.MockTransport(handler),
                                headers={"Authorization": "Bearer actor-only"})
    with pytest.raises(ValueError, match="Observe first"):
        computer.act(0, "click", x=20, y=30)
    result = computer.observe()
    assert result.content[1].type == "image"
    computer.act(1, "click", x=20, y=30)
    body = json.loads(requests[1].content)
    assert body["kind"] == "click" and body["epoch"] == 2 and body["frame"] == 1
    assert len(requests) == 3  # observation, real action POST, new observation
    with pytest.raises(ValueError, match="Observe first"):
        computer.act(1, "click", x=20, y=30)
    with pytest.raises(ValueError, match="budget"):
        computer.act(2, "click", x=20, y=30)
    assert all("evaluate" not in str(r.url) and "commands" not in str(r.url) for r in requests)


@pytest.mark.asyncio
async def test_diagnostic_tool_is_never_in_production(tmp_path):
    computer = Computer({"control_url": "http://control", "actor_token": "actor", "run_id": "abc", "output_dir": str(tmp_path)})
    assert {t.name for t in await make_server(computer).list_tools()} == {
        "computer_observe", "computer_act", "demo_info", "demo_frame", "finish"}
    assert "diagnostic_payload" in {t.name for t in await make_server(computer, True).list_tools()}
    computer.http.close()


def test_compaction_evidence_comes_from_native_events(tmp_path):
    out = tmp_path / "stdout.jsonl"
    out.write_text(json.dumps({"type": "system", "subtype": "compact_boundary", "session_id": "test",
                              "compact_metadata": {"trigger": "auto", "pre_tokens": 12000}}) + "\n")
    assert summarize("claude", out, tmp_path)["compaction_events"][0]["event"]["compact_metadata"]["trigger"] == "auto"
    out.write_text(json.dumps({"type": "thread.started", "thread_id": "test"}) + "\n")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "rollout-test.jsonl").write_text(json.dumps({"type": "compacted", "timestamp": "test-time", "payload": {}}) + "\n")
    assert summarize("codex", out, tmp_path)["compaction_events"][0]["source"] == "native_rollout"
    # A model claiming it compacted is not evidence.
    out.write_text(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "I compacted history"}}))
    assert not summarize("codex", out, tmp_path)["compaction_events"]


def test_private_files(tmp_path):
    path = tmp_path / "private.json"
    private_json(path, {"secret": "test"})
    assert path.stat().st_mode & 0o777 == 0o600


def test_environment_failure_is_terminal_and_logged(tmp_path):
    computer = Computer({'control_url': 'http://control', 'actor_token': 'actor',
                         'run_id': 'run', 'output_dir': str(tmp_path)})
    computer.http.close()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={'detail': 'Browser unavailable'})
    computer.http = httpx.Client(base_url='http://control', transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        computer.observe()
    assert (tmp_path / 'environment-error.json').is_file()
    with pytest.raises(ValueError, match='finished'):
        computer.observe()
    assert len(calls) == 1
    computer.http.close()


@pytest.mark.parametrize('preflight_status,eval_status,expected', [(503, 200, 'environment_error'), (200, 409, 'evaluation_error'), (200, 200, 'fail'), (200, 200, 'incomplete')])
def test_runner_preserves_terminal_results(tmp_path, monkeypatch, preflight_status, eval_status, expected):
    from types import SimpleNamespace
    from vic_sdk.native_agent import run
    credentials = tmp_path / 'credentials.json'
    credentials.write_text(json.dumps({'claude': {'base_url': 'https://gateway.example', 'api_key': 'private-test-key'}}))
    admin = tmp_path / 'admin'
    admin.write_text('manager-test-key')
    requests = []
    def handler(request):
        requests.append(request.url.path)
        if request.url.path == '/v1/runs':
            return httpx.Response(200, json={'id': 'test-run', 'actor_token': 'actor'})
        if request.url.path.endswith('/contract'):
            return httpx.Response(200, json={'assignment': 'Public task', 'rules': 'HIDDEN'})
        if request.url.path.endswith('/observation'):
            return httpx.Response(preflight_status, json={})
        return httpx.Response(eval_status, json={'success': False, 'status': 'completed'})
    client = httpx.Client
    monkeypatch.setattr('vic_sdk.native_agent.httpx.Client', lambda **kw: client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr('vic_sdk.native_agent.subprocess.check_output', lambda *a, **kw: 'test-version')
    launches = []
    class Process:
        returncode = 0
        def __init__(self, *a, **kw):
            launches.append(a)
            kw['stdout'].write(json.dumps({'type': 'result', 'result': 'done', 'is_error': False}) + '\n')
            if expected != 'incomplete':
                (Path(kw['stdout'].name).parent / 'computer.jsonl').write_text(
                    json.dumps({'type': 'finish', 'summary': 'Stopped', 'time': 0}) + '\n')
        def communicate(self, prompt, timeout):
            assert 'HIDDEN' not in prompt
    monkeypatch.setattr('vic_sdk.native_agent.subprocess.Popen', Process)
    args = SimpleNamespace(engine='claude', output_root=tmp_path / 'runs', credentials=credentials,
        api_key_env=None, base_url=None, model='test-model', resume=None, admin_token_file=admin,
        control_url='http://control', task=11, variant='A', seed=10001, max_actions=100, timeout=280,
        demo=None, compaction_smoke=False, compact_threshold=None, max_budget_usd=1,
        binary=None, prompt=None, evaluate=True)
    code = run(args)
    result = json.loads(next((tmp_path / 'runs').glob('*/result.json')).read_text())
    assert result['outcome'] == expected
    assert code == (0 if expected == 'fail' else 1)
    assert bool(launches) == (preflight_status == 200)
    assert ('/v2/tasks/11/eval' in requests) == (preflight_status == 200 and expected != 'incomplete')


def test_native_stop_hook_requires_finish_with_bounded_retries(tmp_path):
    from vic_sdk.native_stop_hook import decision
    config = {'output_dir': str(tmp_path), 'deadline_unix': 200}
    assert decision(config, now=100)['decision'] == 'block'
    assert decision(config, now=100)['decision'] == 'block'
    assert decision(config, now=100)['decision'] == 'block'
    assert decision(config, now=100) == {}
    (tmp_path / 'stop-guard-count.json').unlink()
    (tmp_path / 'computer.jsonl').write_text(json.dumps({'type':'finish','summary':'Unable to complete'})+'\n')
    assert decision(config, now=100) == {}
    (tmp_path / 'computer.jsonl').unlink()
    assert decision(config, now=190) == {}
    (tmp_path / 'environment-error.json').write_text('{}')
    assert decision(config, now=100) == {}
