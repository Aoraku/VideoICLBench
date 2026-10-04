"""Launch unmodified Codex/Claude Code CLIs with a private computer MCP.

The native CLI owns all model calls, history, tool loops and compaction.
This module only prepares a run, starts the CLI and preserves its evidence.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[3]


def private_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def clean_env():
    # Deliberately do not inherit this developer's agent/session/provider settings.
    keep = {"PATH", "HOME", "USER", "TMPDIR", "LANG", "LC_ALL", "SHELL", "SYSTEMROOT",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
    return {k: v for k, v in os.environ.items() if k in keep}


def codex_config(model, base_url, server, compact_tokens=None, native_auth=False, code_mode=False):
    q = json.dumps
    lines = [f"model = {q(model)}", 'model_provider = "vic_remote"', 'model_reasoning_effort = "low"',
             'approval_policy = "never"', 'sandbox_mode = "read-only"', 'web_search = "disabled"',
             'project_doc_max_bytes = 0']
    if compact_tokens is not None:
        lines.extend([f"model_auto_compact_token_limit = {compact_tokens}", "tool_output_token_limit = 24000"])
    lines += ['[features]']
    if code_mode:
        lines.append('code_mode = true')
    # These are native feature switches, not replacement implementations.
    for feature in ["shell_tool", "unified_exec", "apps", "plugins", "remote_plugin", "skill_search",
                    "browser_use", "computer_use", "in_app_browser",
                    "multi_agent", "memories"]:
        lines.append(f"{feature} = false")
    lines += ['[model_providers.vic_remote]', 'name = "VideoICL configured gateway"',
              f"base_url = {q(base_url)}", 'wire_api = "responses"',
              *(['requires_openai_auth = true', 'supports_websockets = true'] if native_auth else ['env_key = "VIC_MODEL_API_KEY"']),
              'request_max_retries = 1', 'stream_max_retries = 1',
              '[mcp_servers.vic]', f"command = {q(server['command'])}", f"args = {q(server['args'])}",
              'startup_timeout_sec = 30', 'tool_timeout_sec = 120', 'required = true',
              'default_tools_approval_mode = "approve"']
    return "\n".join(lines) + "\n"


def cli_command(engine, profile, workspace, model, server, *, resume=None, compact=None, budget=1.0, binary=None, serial_tools=False):
    env = clean_env()
    if engine == "codex":
        # CODEX_HOME is used for its documented purpose, only in the child process.
        env["CODEX_HOME"] = str(profile)
        # Resolve a desktop-installed symlink so its native code-mode host is found beside it.
        codex_binary = str(Path(binary or shutil.which("codex") or "codex").resolve())
        cmd = [codex_binary, "exec", "--skip-git-repo-check", "--json", "--color", "never"]
        if (profile / "hooks.json").exists():
            # Only our generated, isolated profile hook is trusted; shell/tool permissions stay unchanged.
            cmd.append("--dangerously-bypass-hook-trust")
        if resume:
            cmd += ["resume", resume, "-"]
        else:
            cmd += ["-C", str(workspace), "-"]
    else:
        env.update({"CLAUDE_CONFIG_DIR": str(profile), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
                    "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1"})
        if compact is not None:
            env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(compact)
        cmd = [str(binary or "claude"), "-p", "--model", model, "--tools", "", "--setting-sources", "",
               "--strict-mcp-config", "--mcp-config", str(profile / "mcp.json"),
               "--settings", str(profile / "settings.json"),
               "--disable-slash-commands", "--permission-mode", "dontAsk",
               "--allowedTools", "mcp__vic__*", "--output-format", "stream-json", "--verbose",
               "--max-budget-usd", str(budget)]
        if resume:
            cmd += ["--resume", resume]
        if serial_tools:
            cmd += ["--append-system-prompt", "Call exactly one tool per assistant response. Wait for its result before calling the next tool. The configured gateway cannot transport parallel tool calls reliably."]
    return cmd, env


def summarize(engine: str, output: Path, profile: Path, session_id=None):
    result = {"engine": engine, "session_id": session_id, "final_text": "", "compaction_events": [],
              "tool_calls": [], "errors": [], "usage": None}
    for line in output.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "thread.started":
            result["session_id"] = e["thread_id"]
        if e.get("session_id"):
            result["session_id"] = e["session_id"]
        item = e.get("item", {})
        if e.get("type") == "error":
            result["errors"].append(e.get("message"))
        if e.get("type") == "turn.failed":
            result["errors"].append(e.get("error"))
        if e.get("type") == "item.completed" and item.get("type") == "agent_message":
            result["final_text"] = item.get("text", "")
        if e.get("type") == "turn.completed":
            result["usage"] = e.get("usage")
        if e.get("type") == "result":
            result.update(final_text=e.get("result", ""), usage=e.get("usage"),
                          reported_cost_usd=e.get("total_cost_usd"), is_error=e.get("is_error", False))
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
            result["compaction_events"].append({"source": "native_stream", "event": e})
        if item.get("type") == "mcp_tool_call" and e.get("type") == "item.completed":
            result["tool_calls"].append({"name": item.get("tool"), "status": item.get("status")})
        for block in e.get("message", {}).get("content", []) if isinstance(e.get("message"), dict) else []:
            if block.get("type") == "tool_use":
                result["tool_calls"].append({"name": block.get("name")})
    if engine == "codex" and result["session_id"]:
        # `codex exec --json` may omit compaction; the native persisted rollout does not.
        for file in (profile / "sessions").rglob(f"*{result['session_id']}*.jsonl"):
            for number, line in enumerate(file.read_text().splitlines(), 1):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") == "compacted" or (e.get("type") == "event_msg" and
                        e.get("payload", {}).get("type") == "context_compacted"):
                    result["compaction_events"].append({"source": "native_rollout", "file": file.name,
                                                        "line": number, "type": e.get("type"),
                                                        "timestamp": e.get("timestamp")})
    return result


def run(args):
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = json.loads(args.credentials.read_text()) if args.credentials.exists() else {}
    provider = config.get(args.engine, {})
    api_key = os.environ.get(args.api_key_env or "") or provider.get("api_key")
    base_url = args.base_url or provider.get("base_url")
    if not api_key or not base_url:
        raise ValueError("Provide --base-url and --api-key-env, or a private credentials JSON file")
    model = args.model or provider.get("model") or {"codex": "gpt-5.6-luna", "claude": "claude-sonnet-4-6"}[args.engine]
    if args.resume:
        output_dir = args.resume.resolve()
        meta = json.loads((output_dir / "manifest.json").read_text())
        if meta["engine"] != args.engine or meta["model"] != model:
            raise ValueError("Resume must use the original engine and model")
        computer_config = json.loads((output_dir / "computer-private.json").read_text())
        prior = json.loads((output_dir / "result.json").read_text())
        session_id = prior["session_id"]
        workspace = Path(meta["workspace"])
    else:
        output_dir = root / f"{args.engine}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        output_dir.mkdir(mode=0o700)
        workspace = Path(tempfile.mkdtemp(prefix="vic-native-workspace-"))
        session_id = None
        admin = args.admin_token_file.read_text().strip()
        with httpx.Client(base_url=args.control_url, timeout=90,
                          headers={"Authorization": "Bearer " + admin}) as c:
            r = c.post('/v1/runs', json={"suite": "v2", "task_id": args.task, "variant": args.variant,
                      "seed": args.seed, "mode": "eval", "runtime": "browser", "interaction": "agent",
                      "timeout_seconds": min(7200, args.timeout + 120), "max_actions": args.max_actions})
            r.raise_for_status()
            platform_run = r.json()
            # Only the public assignment and execution requirements enter the model prompt.
            r = c.get(f"/v2/tasks/{args.task}/contract")
            r.raise_for_status()
            contract = r.json()
        computer_config = {"control_url": args.control_url, "run_id": platform_run["id"],
            "actor_token": platform_run["actor_token"], "output_dir": str(output_dir),
            "max_actions": args.max_actions, "timeout_seconds": args.timeout,
            "demo_video": str(args.demo.resolve()) if args.demo else None, "smoke_payload": args.compaction_smoke}
        meta = {"engine": args.engine, "model": model, "base_url": base_url, "run_id": platform_run["id"],
                "task_id": args.task, "variant": args.variant, "seed": args.seed,
                "workspace": str(workspace), "framework": "native CLI",
                "demo_representation": "timestamped frames" if args.demo else "none",
                "input_condition": "text_rule" if getattr(args, "rule_file", None) else "video" if args.demo else "no_demo",
                "budgets": {"wall_seconds": args.timeout, "max_actions": args.max_actions},
                "compaction": "native default" if not args.compaction_smoke else "native, lowered test threshold",
                "public_task": {k: contract.get(k) for k in ("assignment", "delivery", "inference")}}
        material = args.demo or getattr(args, "rule_file", None)
        if material:
            meta["input_sha256"] = hashlib.sha256(material.read_bytes()).hexdigest()
        private_json(output_dir / "computer-private.json", computer_config)
        private_json(output_dir / "manifest.json", meta)
    profile = output_dir / "profile"
    profile.mkdir(exist_ok=True, mode=0o700)
    # Check the actual browser before paying for model inference. No model sees this image.
    if not args.resume:
        with httpx.Client(base_url=computer_config["control_url"], timeout=90,
                         headers={"Authorization": "Bearer " + computer_config["actor_token"]}) as c:
            response = c.get(f"/v1/runs/{meta['run_id']}/observation")
        if response.status_code != 200:
            failure = {"engine": args.engine, "outcome": "environment_error",
                       "stage": "preflight", "http_status": response.status_code,
                       "run_id": meta["run_id"], "evaluation": None}
            private_json(output_dir / "result.json", failure)
            print(json.dumps(failure))
            return 1
    server = {"command": sys.executable, "args": ["-m", "vic_sdk.computer_mcp", "--config",
                                                   str(output_dir / "computer-private.json")]}
    compact = (args.compact_threshold or (6000 if args.engine == "codex" else 5)) if args.compaction_smoke else None
    if args.engine == "claude" and not args.compaction_smoke:
        compact = getattr(args, "claude_compact_percent", None) or provider.get("compact_percent")
        if compact is not None:
            if not 1 <= compact <= 95:
                raise ValueError("Claude native compaction percentage must be between 1 and 95")
            meta["compaction"] = {"implementation": "native Claude Code", "threshold_percent": compact}
    hook_command = shlex.join([sys.executable, "-m", "vic_sdk.native_stop_hook", "--config",
                               str(output_dir / "computer-private.json")])
    hook_settings = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": hook_command, "timeout": 10}]}]}}
    if args.engine == "codex":
        native_auth = provider.get("native_auth", False)
        code_mode = getattr(args, "code_mode", False) or provider.get("code_mode", False)
        meta["code_mode"] = code_mode
        (profile / "config.toml").write_text(codex_config(model, base_url, server, compact, native_auth, code_mode))
        private_json(profile / "hooks.json", hook_settings)
        if native_auth:
            private_json(profile / "auth.json", {"auth_mode": "apikey", "OPENAI_API_KEY": api_key})
    else:
        private_json(profile / "mcp.json", {"mcpServers": {"vic": server}})
        private_json(profile / "settings.json", hook_settings)
    cmd, env = cli_command(args.engine, profile, workspace, model, server,
                            resume=session_id, compact=compact, budget=args.max_budget_usd,
                            binary=args.binary or provider.get("binary"),
                            serial_tools=getattr(args, "serial_tools", False) or provider.get("serial_tools", False))
    meta["serial_tools_instruction"] = getattr(args, "serial_tools", False) or provider.get("serial_tools", False)
    if args.engine == "codex":
        env["VIC_MODEL_API_KEY"] = api_key
    else:
        env.update(ANTHROPIC_BASE_URL=base_url, ANTHROPIC_AUTH_TOKEN=api_key)
    prompt = args.prompt or (
        "Use only the vic computer tools to operate the real application. "
        + ("Read the assigned demonstration using demo_info/demo_frame. " if args.demo else "No video is supplied. ") +
        "Follow the supplied rule and the public assignment below. Observe the live screen, "
        "then act using screenshot coordinates. Do not guess that a click succeeded; inspect the next image. "
        "For key input use Enter, ArrowLeft/Right/Up/Down, Escape or ControlOrMeta combinations. "
        "Call finish when done or when the operation budget is almost exhausted. "
        f"You have {args.timeout} seconds total and {args.max_actions} input actions. "
        "If an environment error occurs, stop; do not repeatedly retry unavailable tools.\n" +
        json.dumps(meta["public_task"], ensure_ascii=False))
    if getattr(args, "rule_file", None):
        prompt += "\nExplicit rule for this diagnostic condition:\n" + args.rule_file.read_text()
    index = len(list(output_dir.glob("stdout-*.jsonl"))) + 1
    stdout, stderr = output_dir / f"stdout-{index}.jsonl", output_dir / f"stderr-{index}.log"
    (output_dir / f"prompt-{index}.txt").write_text(prompt)
    version = subprocess.check_output([cmd[0], "--version"], text=True).strip()
    meta["cli_version"] = version
    private_json(output_dir / "manifest.json", meta)
    print(f"Starting {version}; model={model}; artifacts={output_dir}", flush=True)
    started = time.monotonic()
    attempt_started_unix = time.time()
    computer_config["deadline_unix"] = attempt_started_unix + args.timeout
    private_json(output_dir / "computer-private.json", computer_config)
    with ExitStack() as resources, stdout.open("w") as out, stderr.open("w") as err:
        if args.engine == "claude" and (getattr(args, "lift_tool_images", False) or provider.get("lift_tool_images", False)):
            from vic_sdk.anthropic_image_proxy import image_compat_proxy
            proxy_url, proxy_token = resources.enter_context(image_compat_proxy(
                base_url, api_key, output_dir / f"image-compat-{index}.jsonl"))
            env.update(ANTHROPIC_BASE_URL=proxy_url, ANTHROPIC_AUTH_TOKEN=proxy_token)
            meta["image_transport"] = "tool images lifted unchanged into the same user message"
            private_json(output_dir / "manifest.json", meta)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
                                cwd=workspace, env=env, start_new_session=True)
        timed_out = False
        environment_error = False
        pending_input = prompt
        while True:
            try:
                proc.communicate(pending_input, timeout=min(1, args.timeout))
                break
            except subprocess.TimeoutExpired:
                pending_input = None
                environment_error = (output_dir / "environment-error.json").exists()
                timed_out = time.monotonic() - started >= args.timeout
                if environment_error or timed_out:
                    break
        if environment_error or timed_out:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    # Redact before parsing so result summaries cannot repeat a gateway's echoed key.
    for path in (stdout, stderr):
        text = path.read_text()
        path.write_text(text.replace(api_key, "[REDACTED]"))
    result = summarize(args.engine, stdout, profile, session_id)
    result["agent_finished"] = False
    result.update(exit_code=proc.returncode, timed_out=timed_out, duration_seconds=round(time.monotonic()-started, 2))
    result["execution_status"] = ("environment_error" if environment_error else "timed_out" if timed_out
                                  else "agent_error" if proc.returncode or result.get("is_error") else "completed")
    log = output_dir / "computer.jsonl"
    if log.exists():
        events = [json.loads(line) for line in log.read_text().splitlines()]
        result["computer_evidence"] = {"screenshots": sum(e["type"] == "observation" for e in events),
            "actions": sum(e["type"] == "action" for e in events),
            "video_frames": sum(e["type"] == "demo_frame" for e in events),
            "finish_summaries": [e["summary"] for e in events if e["type"] == "finish"]}
        intervals = sorted((max(attempt_started_unix, e["time"] - e["duration_seconds"]), e["time"])
                           for e in events if "duration_seconds" in e and e["time"] >= attempt_started_unix)
        merged = []
        for begin, end in intervals:
            if merged and begin <= merged[-1][1]:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([begin, end])
        result["timing"] = {"tool_io_seconds": round(sum(end - begin for begin, end in merged), 2)}
        result["timing"]["outside_tool_io_seconds"] = round(result["duration_seconds"] - result["timing"]["tool_io_seconds"], 2)
        result["agent_finished"] = bool(result["computer_evidence"]["finish_summaries"])
    if result["execution_status"] == "completed" and not result["agent_finished"]:
        result["execution_status"] = "incomplete"
    result["outcome"] = ("environment_error" if environment_error else
                         "agent_error" if result["execution_status"] == "agent_error" else
                         "incomplete" if result["execution_status"] == "incomplete" else "unevaluated")
    if args.evaluate and result["outcome"] == "unevaluated":
        try:
            with httpx.Client(base_url=computer_config["control_url"], timeout=90,
                              headers={"Authorization": "Bearer " + args.admin_token_file.read_text().strip()}) as c:
                response = c.post(f"/v2/tasks/{meta['task_id']}/eval", json={"run_id": meta["run_id"]})
                if response.is_success:
                    result["evaluation"] = response.json()
                    result["outcome"] = "success" if result["evaluation"]["success"] else "fail"
                else:
                    result["outcome"] = "evaluation_error"
                    result["evaluation_error"] = {"http_status": response.status_code}
        except httpx.RequestError as exc:
            result["outcome"] = "evaluation_error"
            result["evaluation_error"] = {"type": type(exc).__name__}
    private_json(output_dir / f"result-{index}.json", result)
    private_json(output_dir / "result.json", result)
    print(json.dumps({"artifacts": str(output_dir), **result}, ensure_ascii=False, indent=2))
    return 1 if timed_out or proc.returncode or result.get("is_error") or result["outcome"].endswith("error") or result["outcome"] == "incomplete" else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("engine", choices=["codex", "claude"])
    p.add_argument("--model")
    p.add_argument("--code-mode", action="store_true", help="Enable native Codex Code Mode for gateways requiring that tool transport")
    p.add_argument("--lift-tool-images", action="store_true", help="CC only: compatibility for gateways dropping nested tool_result images; no pixel or history changes")
    p.add_argument("--serial-tools", action="store_true", help="CC only: native system prompt requests one tool call per response for gateways with broken parallel-call transport")
    p.add_argument("--claude-compact-percent", type=int, help="CC native automatic compaction threshold percentage (1-95); no custom summarizer")
    p.add_argument("--binary", type=Path, help="Optional pinned native CLI executable")
    p.add_argument("--base-url")
    p.add_argument("--api-key-env")
    p.add_argument("--credentials", type=Path, default=ROOT / ".local/native-agents/credentials.json")
    p.add_argument("--control-url", default="http://127.0.0.1:8765")
    p.add_argument("--admin-token-file", type=Path, default=ROOT / ".local/admin-token")
    p.add_argument("--output-root", type=Path, default=ROOT / ".local/native-agents/runs")
    p.add_argument("--task", type=int, default=1)
    p.add_argument("--variant", choices=list("ABC"), default="A")
    p.add_argument("--seed", type=int, default=10001)
    p.add_argument("--demo", type=Path)
    p.add_argument("--rule-file", type=Path, help="Explicit text-rule diagnostic, mutually exclusive with --demo")
    p.add_argument("--prompt")
    p.add_argument("--resume", type=Path, help="Previous artifact directory; uses native CLI resume")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--max-actions", type=int, default=120)
    p.add_argument("--max-budget-usd", type=float, default=1.0, help="Claude CLI reported-cost cap; gateway billing may differ")
    p.add_argument("--compaction-smoke", action="store_true", help="Enable inert diagnostic payload and lower native threshold")
    p.add_argument("--compact-threshold", type=int, help="Smoke only: Codex tokens / Claude percentage")
    p.add_argument("--evaluate", action="store_true", help="Seal and score the run after the native CLI exits")
    args = p.parse_args()
    if args.demo and not args.demo.is_file():
        p.error("Assigned demo video does not exist")
    if args.rule_file and (args.demo or not args.rule_file.is_file()):
        p.error("--rule-file must exist and cannot be combined with --demo")
    try:
        raise SystemExit(run(args))
    except (httpx.HTTPError, ValueError, FileNotFoundError) as e:
        # Do not print headers or private configuration.
        print(f"Native runner failed: {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
