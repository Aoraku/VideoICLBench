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
    smoke = tomllib.loads(codex_config("model-custom", "https://gateway.example/v1", server, 6000))
    assert smoke["model_auto_compact_token_limit"] == 6000
    cmd, env = cli_command("codex", tmp_path, tmp_path, "model-custom", server, resume="session-id")
    assert Path(cmd[0]).name == "codex" and cmd[1] == "exec" and cmd[-3:] == ["resume", "session-id", "-"]
    cmd, env = cli_command("claude", tmp_path, tmp_path, "model-custom", server, resume="session-id")
    assert cmd[:2] == ["claude", "-p"] and cmd[-2:] == ["--resume", "session-id"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in env
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
