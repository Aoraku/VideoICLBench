"""Harbor embodied trials through the existing native Codex/Claude harness.

The CLI owns model calls, tools, history and compaction. This adapter validates
inputs, connects an already-created exclusive environment, then seals/scores it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import uuid

import httpx

from .native_agent import codex_config, cli_command, private_json, summarize, execution_status
from . import native_cli_engines
from .embodied_recovery import (failure_class, resolve_session, recover_control, append_ledger,
                                checked_barrier, reconcile_pending, retire_exited_cli_tools,
                                stream_identity_and_completion)
from .embodied_protocol import EPISODE_CONTRACT_VERSION, EPISODE_INSTRUCTIONS
from .rule_qa_gate import load_assignment, needs_qa_continuation, RuleQAGate, digest as qa_digest, INSTRUCTIONS as QA_INSTRUCTIONS
from .process_identity import named_python_command
from .direct_tools import validate_model_catalog, freeze_direct_model_catalog, validate_context_window

IDENTITY_FIELDS = ("run_id", "task_id", "variant", "seed", "suite", "epoch")
CONDITIONS = ("real", "sim", "text_rule")
TRANSPORT_CONTRACT_VERSION = EPISODE_CONTRACT_VERSION
TRANSPORT_CONTRACT = EPISODE_INSTRUCTIONS


def same_identity(actual, expected):
    return isinstance(actual, dict) and all(
        field in expected and type(actual.get(field)) is type(expected[field])
        and actual[field] == expected[field] for field in IDENTITY_FIELDS)


def assigned_material(task_dir, spec, condition):
    if condition == "text_rule":
        return None
    entry = spec.get("demo" if condition == "real" else "demo_sim")
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise ValueError("No verified video assigned for condition " + condition)
    value = os.path.expandvars(entry["path"])
    if "$" in value:
        raise ValueError("Assigned video path contains an unresolved environment variable")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = task_dir / path
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != entry.get("sha256"):
        raise ValueError("Assigned video checksum mismatch")
    return {"path": str(path.resolve()), "sha256": digest.hexdigest()}


def load_inputs(args):
    task_dir = args.embodied_task_dir.resolve()
    spec = json.loads((task_dir / "environment/native.json").read_text())
    connection_path = args.embodied_connection.resolve()
    connection = json.loads(connection_path.read_text())
    if not isinstance(spec, dict) or not isinstance(connection, dict):
        raise ValueError("Task and connection must be JSON objects")
    if any(not isinstance(connection.get(k), str) or not connection[k] for k in ("control_url", "actor_token_file", "admin_token_file")):
        raise ValueError("Connection requires controller URL and separate actor/admin token files")
    if spec.get("kind") != "embodied" or spec.get("backend") != "videoicl-native-slurm":
        raise ValueError("An embodied Harbor task is required")
    if spec.get("action_interface") != "bounded_dual_arm_tokens_v1":
        raise ValueError("Task action interface does not match the native GUI controller")
    if spec.get("agent_interaction") != "gui_only" or spec.get("agent_protocol") != "roboprobe_gui_v1":
        raise ValueError("Task requires the RoboProbe GUI interaction protocol")
    controls = spec.get("gui_controls", {})
    if not isinstance(controls, dict) or not isinstance(controls.get("path"), str):
        raise ValueError("Task requires a public GUI controls manual")
    controls_path = (task_dir / "environment" / controls.get("path", "")).resolve()
    if not controls_path.is_relative_to((task_dir / "environment").resolve()) or not controls_path.is_file():
        raise ValueError("Task requires a public GUI controls manual")
    if hashlib.sha256(controls_path.read_bytes()).hexdigest() != controls.get("sha256"):
        raise ValueError("GUI controls manual checksum mismatch")
    if args.condition not in CONDITIONS or connection.get("condition") != args.condition:
        raise ValueError("Connection input condition mismatch")
    compact_tokens = getattr(args, 'codex_compact_tokens', 32768)
    if type(compact_tokens) is not int or compact_tokens <= 0:
        raise ValueError('Codex automatic compaction threshold must be a positive integer')
    gui_budget = getattr(args, 'max_gui_inputs', None)
    if gui_budget is not None and (type(gui_budget) is not int or gui_budget <= 0):
        raise ValueError('GUI input budget must be a positive integer')
    barrier = connection.get('barrier_timeout_seconds', 300)
    if type(barrier) not in (int, float) or not math.isfinite(barrier) or barrier <= 0:
        raise ValueError('Native pool barrier timeout must be finite and positive')
    native_response = connection.get('native_response_timeout_seconds', barrier + 120)
    if not (native_response is None and connection.get('barrier_policy') == 'wait') and (
            type(native_response) not in (int, float) or not math.isfinite(native_response) or native_response <= 0):
        raise ValueError('Native response timeout must be finite and positive')
    identity = connection.get("identity", {})
    if not isinstance(identity, dict) or any(k not in identity for k in IDENTITY_FIELDS):
        raise ValueError("Connection requires all six runtime identity fields")
    if any(not isinstance(identity[k], str) or not identity[k] for k in ("run_id", "task_id", "variant", "suite", "epoch")):
        raise ValueError("Runtime identifiers must be nonempty strings")
    if identity["task_id"] != spec.get("task_id") or identity["variant"] != spec.get("variant"):
        raise ValueError("Task package and exclusive environment identity mismatch")
    if type(identity["seed"]) is not int or identity["seed"] != spec.get("seed"):
        raise ValueError("Task and environment seed mismatch")
    for key, value in (("max_actions", args.max_actions), ("timeout_seconds", args.timeout)):
        if type(value) is not int or value < (0 if key == 'timeout_seconds' else 1) or type(connection.get(key)) is not int or connection.get(key) != value:
            raise ValueError("Explicit budget must match controller connection: " + key)
    if args.timeout == 0 and connection.get('budget_policy') != 'effective_time_graceful_v1':
        raise ValueError('Unlimited time requires graceful episode budgeting')
    url = urlparse(connection["control_url"])
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.username or url.password:
        raise ValueError("Use a localhost controller or an explicit SSH tunnel")
    instruction = (task_dir / "instruction.md").read_bytes()
    if hashlib.sha256(instruction).hexdigest() != spec.get("instruction_sha256"):
        raise ValueError("Harbor instruction checksum mismatch")
    material = assigned_material(task_dir, spec, args.condition)
    if connection.get("demo") and material:
        demo = connection["demo"]
        if not isinstance(demo, dict) or demo.get("sha256") != material["sha256"]:
            raise ValueError("Controller video assignment differs from task package")
    load_assignment(task_dir, spec, args.condition, material)  # New release requires QA for all conditions.
    return task_dir, spec, connection_path, connection, instruction.decode("utf-8").strip(), material


def token_file(connection_path, connection, field):
    path = Path(connection[field])
    if not path.is_absolute():
        path = connection_path.parent / path
    token = path.read_text().strip()
    if not token:
        raise ValueError("Empty controller credential")
    return token


def checked_evaluation(value, identity):
    if not same_identity(value, identity) or type(value.get("success")) is not bool:
        raise ValueError("Authoritative evaluation identity or success type mismatch")
    score = value.get("score")
    if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Authoritative evaluation requires a finite score in [0,1]")
    if score != float(value['success']):
        raise ValueError('Primary score must equal terminal native success; process score is separate')
    return value


def run(args):
    if not getattr(args, "embodied_connection", None):
        raise ValueError("--embodied-connection is required")
    if getattr(args, "resume", None):
        raise ValueError("Each embodied condition requires a new trial; resume is not enabled")
    try:
        task_dir, spec, connection_path, connection, instruction, material = load_inputs(args)
    except (ValueError, OSError, KeyError) as exc:
        if not getattr(args, "preflight", False):
            raise
        print(json.dumps({"condition": args.condition, "scientific_evaluation": False,
                          "blocked_reason": str(exc), "stage": "input_validation"}, ensure_ascii=False))
        return 2
    ready = (spec.get("readiness") in {"available", "ready"}
             and spec.get("native_interaction_validated") is True
             and spec.get("budget", {}).get("status") == "frozen"
             and not connection.get("validation_only", False))
    if ready and (spec['budget'].get('max_actions') != args.max_actions
                  or spec['budget'].get('timeout_sec') != args.timeout):
        raise ValueError("Formal budgets must match the frozen task package")
    validation_only = not ready and getattr(args, "allow_unvalidated_environment", False)
    preflight = {"task_id": spec["task_id"], "variant": spec["variant"], "condition": args.condition,
                 "readiness": spec.get("readiness"), "validation_only": validation_only,
                 "scientific_evaluation": ready, "input_sha256": material["sha256"] if material else None,
                 "blocked_reason": None if ready or validation_only else "Native interaction validation required"}
    if getattr(args, "preflight", False):
        print(json.dumps(preflight, ensure_ascii=False))
        return 0 if ready or validation_only else 2
    if not ready and not validation_only:
        raise ValueError("Task is not executable; validate it with --allow-unvalidated-environment first")
    if getattr(args, "demo", None) or getattr(args, "rule_file", None):
        raise ValueError("Embodied materials must come from the task package and controller")
    provider_file = getattr(args, "credentials", None)
    providers = json.loads(provider_file.read_text()) if provider_file and provider_file.exists() else {}
    provider = providers.get(args.engine, {})
    key = os.environ.get(getattr(args, "api_key_env", None) or "") or provider.get("api_key")
    base_url = getattr(args, "base_url", None) or provider.get("base_url")
    if not key or not base_url:
        raise ValueError("Provide a private configured native CLI provider")
    auto_recover = getattr(args, 'embodied_auto_recover', False)
    if auto_recover:
        policy = 'per_episode_failed_request_and_retry_wait_v1'
        timing_path = connection.get('api_timing_log')
        if (connection.get('api_failure_budget_policy') != policy or provider.get('api_failure_budget_policy') != policy
                or not isinstance(timing_path, str) or not Path(timing_path).is_absolute()
                or provider.get('api_timing_log') != timing_path):
            raise ValueError('Automatic recovery requires matching per-episode provider/controller API timing')
        if getattr(args, 'api_timing_log', None) is not None and str(args.api_timing_log) != timing_path:
            raise ValueError('CLI and controller API timing path differ')
        route = urlparse(base_url)
        if route.hostname not in {'127.0.0.1','localhost','::1'} or not re.fullmatch(r'/episodes/[A-Za-z0-9_-]+/v1/?', route.path):
            raise ValueError('Automatic recovery requires the assigned local per-episode provider route')
    model = args.model or provider.get("model")
    if not model:
        raise ValueError("Choose an explicit supported model")
    if args.engine == 'codex':
        if getattr(args, 'code_mode', False):
            raise ValueError('Embodied episodes require blocking direct GUI tools, not code-mode cells')
        catalog_source = getattr(args, 'codex_model_catalog', None)
        catalog_hash = getattr(args, 'codex_model_catalog_sha256', None)
        if catalog_source is None:
            raise ValueError('Codex embodied episodes require a pinned --codex-model-catalog and SHA256')
        validate_model_catalog(catalog_source, catalog_hash, model)
        validate_context_window(catalog_source, catalog_hash, model,
            getattr(args, "codex_context_window", None), getattr(args, "codex_compact_tokens", 32768))
    budget = getattr(args, "max_budget_usd", 1.)
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Claude budget must be finite and positive")
    actor = token_file(connection_path, connection, "actor_token_file")
    admin = token_file(connection_path, connection, "admin_token_file")
    identity = {k: connection["identity"][k] for k in IDENTITY_FIELDS}
    harness = getattr(args, 'embodied_harness', 'gui')
    if harness not in {'gui', 'program_gui'}:
        raise ValueError('Unknown embodied harness')
    transport_contract, transport_version = TRANSPORT_CONTRACT, TRANSPORT_CONTRACT_VERSION
    if harness == 'program_gui':
        if args.engine not in native_cli_engines.ENGINES:
            raise ValueError('Unknown native engine for program GUI')
        from .embodied_program_gui import PROGRAM_INSTRUCTIONS, PROGRAM_VERSION
        transport_contract += '\n\n' + PROGRAM_INSTRUCTIONS
        transport_version += '+' + PROGRAM_VERSION
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    out = root / (args.engine + "-embodied-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    out.mkdir(mode=0o700)
    if material:
        assigned = out / 'assigned-input'
        assigned.mkdir(mode=0o700)
        frozen = assigned / Path(material['path']).name
        shutil.copyfile(material['path'], frozen)
        if hashlib.sha256(frozen.read_bytes()).hexdigest() != material['sha256']:
            raise ValueError('Assigned video changed while freezing the native CLI input')
        material = dict(material, path=str(frozen))
    profile = out / "profile"
    profile.mkdir(mode=0o700)
    workspace = Path(tempfile.mkdtemp(prefix="vic-embodied-workspace-"))
    graceful_budget = connection.get('budget_policy') == 'effective_time_graceful_v1'
    if auto_recover and (args.engine != 'codex' or not graceful_budget):
        raise ValueError('Automatic embodied recovery requires Codex and the effective budget policy')
    native_response = connection.get('native_response_timeout_seconds', connection.get('barrier_timeout_seconds', 300) + 120)
    browser_timeout_ms = 0 if native_response is None else math.ceil((native_response + 30) * 1000)
    tool_timeout_seconds = 86400 if native_response is None else math.ceil(native_response + 90)
    deadline = time.time() + args.timeout if args.timeout else None
    computer = {"control_url": connection["control_url"], "actor_token": actor,
                "run_id": identity["run_id"], "output_dir": str(out), "condition": args.condition,
                "max_actions": args.max_actions, "timeout_seconds": args.timeout,
                "deadline_unix": deadline, "demo_video": material["path"] if material else None,
                "budget_policy": connection.get('budget_policy', 'wall_time_v1'),
                "api_failure_budget_policy": connection.get('api_failure_budget_policy'),
                "agent_interaction": "gui_only", "agent_protocol": "roboprobe_gui_v1",
                "gui_viewport": [1440, 1280],
                "max_gui_inputs": getattr(args, "max_gui_inputs", None) or max(200, 20 * args.max_actions),
                "browser_path": str(args.browser_path) if getattr(args, "browser_path", None) else None,
                "gui_settle_timeout_ms": browser_timeout_ms,
                "gui_observation_timeout_ms": browser_timeout_ms,
                "rule_diagnostic": False}
    computer['rule_qa'] = load_assignment(task_dir, spec, args.condition, material)
    computer['embodied_harness'] = harness
    if harness == 'program_gui':
        computer['program_episode_identity'] = identity
    computer['lean_text_projection'] = harness == 'program_gui' and getattr(args, 'lean_text_projection', True)
    computer['lean_text_mode'] = 'compact'
    private_json(out / "computer-private.json", computer)
    metadata = {**identity, **preflight, "engine": args.engine, "model": model, "framework": "native CLI",
                "provider_service": provider.get('service', 'configured_provider'),
                "provider_transport": provider.get('transport_adapter', 'direct'),
                "execution_hostname": socket.gethostname(),
                "native_pool_hostname": connection.get('native_pool_hostname'),
                "execution_topology": connection.get('execution_topology','single_environment'),
                "task_package": str(task_dir), "workspace": str(workspace),
                "task_manifest_sha256": hashlib.sha256((task_dir / 'environment/native.json').read_bytes()).hexdigest(),
                "instruction_sha256": spec['instruction_sha256'],
                "input_representation": 'explicit_text_rule' if args.condition == 'text_rule' else 'timestamped_video_frames',
                "input_condition": args.condition, "agent_interaction": "gui_only", "agent_protocol": "roboprobe_gui_v1",
                "automatic_recovery": dict(enabled=auto_recover, implementation='same_native_session_v1',
                    retries_rebuild_environment=False, physical_input_replay=False,
                    transport_backoff_seconds=[5, 300], quota_backoff_seconds=[300, 1800]),
                "developer_transport_contract": dict(version=transport_version,
                    sha256=hashlib.sha256(transport_contract.encode()).hexdigest(),
                    enabled=args.engine == 'codex' or args.engine in native_cli_engines.EXTRA_ENGINES,
                    transport='developer_config' if args.engine == 'codex' else 'stdin_prompt',
                    task_information_added=False),
                "gui_controls_sha256": spec['gui_controls']['sha256'],
                "gui_viewport": computer['gui_viewport'],
                "budgets": {"time_limit_seconds": args.timeout or None, "time_limit_enabled": args.timeout > 0, "clock": 'effective_time_excluding_native_service' if graceful_budget else 'wall_time',
                            "inflight_api_cancelled_at_budget": False if graceful_budget else True,
                            "max_physical_actions": args.max_actions,
                            "max_gui_inputs": computer['max_gui_inputs']},
                "reasoning_effort": getattr(args, "effort", "low") if args.engine == "codex" else None,
                "claude_reported_cost_cap_usd": budget if args.engine == "claude" else None,
                "compaction": ({"implementation": "native Codex automatic compaction",
                    "threshold_tokens": getattr(args, "codex_compact_tokens", 32768),
                    "context_window": getattr(args, "codex_context_window", None),
                    "tool_output_token_limit": 4096, "custom_history_reconstruction": False,
                    "independent_episode_session": True} if args.engine == "codex" else "native default"), "environment_fingerprints": connection.get("runtime_fingerprints", {})}
    metadata['rule_qa'] = dict(protocol='qa_then_act', required=True, source=args.condition,
        question_id=computer['rule_qa']['packet']['question_id'], source_sha256=computer['rule_qa']['source_sha256'],
        assignment_identity_sha256=qa_digest(computer['rule_qa']),
        scoring='independent_offline', first_valid_answer_final=True, action_baseline_comparable=False)
    metadata['embodied_harness'] = harness
    metadata['text_projection'] = dict(enabled=computer['lean_text_projection'], mode='compact', version='compact-json-v1', images_changed=False, metadata_references=False)
    metadata['episode_learning'] = dict(scope='current_episode_only', development_practice=False,
        cross_episode_transfer=False, program_enabled=harness == 'program_gui')
    private_json(out / "manifest.json", metadata)
    server = {"command": sys.executable, "args": ["-m", "vic_sdk.embodied_gui_mcp", "--config", str(out / "computer-private.json")],
              "startup_timeout_sec": 120,
              "tool_timeout_sec": tool_timeout_seconds,
              "env": {"PYTHONPATH": str(Path(__file__).resolve().parents[1])}}
    mcp_command = named_python_command([server["command"], *server["args"]], out/"process-identities", "gui-mcp")
    server["command"], server["args"] = mcp_command[0], mcp_command[1:]
    hook = shlex.join(named_python_command([sys.executable, str(Path(__file__).with_name("native_stop_hook.py")), "--config", str(out / "computer-private.json")], out/"process-identities", "native-stop-hook"))
    hooks = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": hook, "timeout": 10}]}]}}
    if args.engine == "codex":
        executable = str(Path(getattr(args, 'binary', None) or provider.get('binary') or shutil.which('codex') or 'codex').resolve())
        metadata['cli_version'] = subprocess.check_output([executable, '--version'], text=True, timeout=15).strip()
        direct_receipt = freeze_direct_model_catalog(profile, catalog_source, catalog_hash, model,
            cli_version=metadata['cli_version'])
        metadata['native_tool_policy'] = direct_receipt
        (profile / "config.toml").write_text('model_catalog_json = ' + json.dumps(direct_receipt['catalog_path']) + '\n' +
            'developer_instructions = ' + json.dumps(transport_contract) + '\n' + codex_config(model, base_url, server,
            native_auth=provider.get("native_auth", False), code_mode=False,
            effort=getattr(args, "effort", "low"), isolated_tools=True,
            compact_tokens=getattr(args, "codex_compact_tokens", 32768), tool_output_tokens=4096,
            context_window=getattr(args, "codex_context_window", None),
            stream_idle_timeout_ms=86400000 if graceful_budget else None))
        private_json(profile / "hooks.json", hooks)
        if provider.get("native_auth", False):
            private_json(profile / "auth.json", {"auth_mode": "apikey", "OPENAI_API_KEY": key})
    elif args.engine == 'claude':
        claude_server = {name: server[name] for name in ('command', 'args', 'env')}
        private_json(profile / "mcp.json", {"mcpServers": {"vic": claude_server}})
        private_json(profile / "settings.json", hooks)
    else:
        metadata['native_cli_adapter'] = native_cli_engines.configure(args.engine, profile, workspace, model, server,
            {**provider, 'api_key': key, 'base_url': base_url}, native_cli_engines.options_from_args(args, provider))
        receipt = metadata['native_cli_adapter']
        metadata['compaction'] = dict(implementation='native ' + args.engine,
            context_window=receipt.get('context_window'), threshold_tokens=receipt.get('compact_tokens'),
            custom_history_reconstruction=False, independent_episode_session=True)
    compact = getattr(args, "claude_compact_percent", None)
    if compact is not None and not 1 <= compact <= 95:
        raise ValueError("Claude compaction percentage must be 1..95")
    command, env = cli_command(args.engine, profile, workspace, model, server, budget=budget,
        binary=getattr(args, "binary", None) or provider.get("binary"), compact=compact,
        serial_tools=getattr(args, "serial_tools", False))
    if args.engine == "codex":
        env["VIC_MODEL_API_KEY"] = key
    elif args.engine == 'claude':
        env.update(ANTHROPIC_BASE_URL=base_url, ANTHROPIC_AUTH_TOKEN=key)
        env['MCP_TOOL_TIMEOUT'] = str(server['tool_timeout_sec'] * 1000)
    if args.engine in native_cli_engines.EXTRA_ENGINES:
        metadata['cli_version'] = native_cli_engines.binary_version(args.engine,
            getattr(args, 'binary', None) or provider.get('binary'), env=env)
        private_json(out / 'manifest.json', metadata)
    result = {"engine": args.engine, "evaluation": None, "outcome": "environment_error",
              "validation_only": validation_only, "scientific_evaluation": ready,
              'native_attempts': [], 'recovery': dict(enabled=auto_recover, attempt_count=0,
                  resume_count=0, preflight_retries=0), **identity}
    with httpx.Client(base_url=connection["control_url"], timeout=None if native_response is None else native_response + 30, trust_env=False,
                      headers={"Authorization": "Bearer " + admin}) as control:
        try:
            state_response = control.get("/api/private/state")
            state_response.raise_for_status()
            public = state_response.json()
            if not same_identity(public.get("identity"), identity):
                raise ValueError("Controller runtime identity mismatch")
            state = public.get("state", {})
            if state.get("condition") != args.condition:
                raise ValueError("Controller runtime condition mismatch")
            if auto_recover and public.get('owner_barrier', {}).get('api_timing_log') != connection['api_timing_log']:
                raise ValueError('The actual owner and provider API timing paths differ')
            if args.condition == 'text_rule':
                rule = state.get('text_rule')
                if not isinstance(rule, str) or hashlib.sha256(rule.encode()).hexdigest() != computer['rule_qa']['source_sha256']:
                    raise ValueError('QA assignment differs from public text rule')
            # Probe actual image delivery before paying for model inference.
            from .embodied_gui_mcp import GuiBrowser
            while True:
                robot = None
                try:
                    robot = GuiBrowser(computer)
                    robot.observe()
                    break
                except Exception as exc:
                    if robot is not None and type(exc).__name__ in {'TargetClosedError', 'TimeoutError', 'ConnectionError'}:
                        robot.unavailable(type(exc).__name__)
                    error_path = out / 'environment-error.json'
                    error = json.loads(error_path.read_text()) if error_path.exists() else None
                    failure = failure_class({}, environment_error=error)
                    if not auto_recover or failure is None:
                        raise
                    result['recovery']['preflight_retries'] += 1
                    number = result['recovery']['preflight_retries']
                    if not recover_control(control, identity, out, attempt='preflight-' + str(number),
                                           failure=failure, consecutive=number):
                        raise RuntimeError('Environment stopped during GUI initialization recovery')
                finally:
                    if robot is not None:
                        robot.close()
            # Public assignment only. GUI affordances teach interaction; limits
            # remain enforced by the controller rather than narrated to the model.
            prompt = instruction + "\n\n" + QA_INSTRUCTIONS
            if args.engine in native_cli_engines.EXTRA_ENGINES:
                prompt = transport_contract + '\n\n' + prompt
            if args.condition == "text_rule":
                rule = state.get("text_rule")
                if not isinstance(rule, str) or not rule.strip():
                    raise ValueError("Text condition requires the controller's public explicit rule")
                metadata['input_sha256'] = hashlib.sha256(rule.encode('utf-8')).hexdigest()
                metadata['text_rule_sha256'] = metadata['input_sha256']
                prompt += "\n\n请按以下规则完成任务：\n" + rule
            (out / "prompt-1.txt").write_text(prompt)
            if 'cli_version' not in metadata:
                metadata["cli_version"] = subprocess.check_output([command[0], "--version"], text=True, timeout=15).strip()
            private_json(out / "manifest.json", metadata)
            if graceful_budget:
                admission = control.post('/api/private/start', json={'identity': identity})
                admission.raise_for_status()
            started = time.monotonic()
            timed_out = False
            attempt = 0
            expected_session = None
            consecutive = 0
            previous_recovery_reason = None
            while True:
                attempt += 1
                if attempt > 1:
                    command, env = cli_command(args.engine, profile, workspace, model, server,
                        resume=expected_session, budget=budget,
                        binary=getattr(args, 'binary', None) or provider.get('binary'), compact=compact,
                        serial_tools=getattr(args, 'serial_tools', False))
                    env['VIC_MODEL_API_KEY'] = key
                    if expected_session:
                        result['recovery']['resume_count'] += 1
                attempt_prompt = prompt if not expected_session else (
                    'Continue the same episode and native session. The controller reconnected after a transport interruption. '
                    'Observe the GUI again before taking any action. Previous inputs may already have completed; '
                    'do not replay them or restore previous widget edits automatically. Use the current visible state.')
                if expected_session and previous_recovery_reason == 'qa_pending':
                    attempt_prompt = 'Continue this same episode and session. The required QA answer has not been submitted. ' + QA_INSTRUCTIONS + ' Observe fresh before any physical action; never replay previous inputs.'
                (out / f'prompt-{attempt}.txt').write_text(attempt_prompt)
                stdout_path, stderr_path = out / f'stdout-{attempt}.jsonl', out / f'stderr-{attempt}.log'
                append_ledger(out, 'native_attempt_started', attempt=attempt, session_id=expected_session,
                              resume=bool(expected_session), stdout=stdout_path.name, stderr=stderr_path.name)
                with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
                    process = subprocess.Popen(command, env=env, cwd=workspace, stdin=subprocess.PIPE,
                        stdout=stdout, stderr=stderr, text=True, start_new_session=True)
                    pending = attempt_prompt
                    while True:
                        try:
                            process.communicate(pending, timeout=1.)
                            break
                        except subprocess.TimeoutExpired:
                            pending = None
                            timed_out = not graceful_budget and deadline is not None and time.time() >= deadline
                            # A live API request is never interrupted under effective budgeting.
                            if not graceful_budget and (timed_out or (out / 'environment-error.json').exists()):
                                os.killpg(process.pid, signal.SIGTERM)
                                try:
                                    process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    os.killpg(process.pid, signal.SIGKILL)
                                    process.wait()
                                break
                timed_out = timed_out or (not graceful_budget and deadline is not None and time.time() >= deadline)
                for path in (stdout_path, stderr_path):
                    text = path.read_text()
                    for secret in (key, actor, admin):
                        text = text.replace(secret, '[REDACTED]')
                    path.write_text(text)
                summary = summarize(args.engine, stdout_path, profile)
                error_path = out / 'environment-error.json'
                environment_error = json.loads(error_path.read_text()) if error_path.exists() else None
                failure = failure_class(summary, stderr_path.read_text(), environment_error)
                if auto_recover and stream_identity_and_completion(stdout_path) and process.returncode == 0 and environment_error is None:
                    failure = None
                if auto_recover and needs_qa_continuation(computer, completed=stream_identity_and_completion(stdout_path),
                        returncode=process.returncode, environment_error=environment_error):
                    failure = 'qa_pending'  # Explicit protocol continuation; not an invented API error.
                record = dict(attempt=attempt, stdout=stdout_path.name, stderr=stderr_path.name,
                    session_id=summary.get('session_id'), exit_code=process.returncode,
                    errors=summary.get('errors', []), model_response_observed=summary.get('model_response_observed', False),
                    usage=summary.get('usage'), recovery_class=failure)
                result['native_attempts'].append(record)
                result['recovery']['attempt_count'] = attempt
                result.update(summary)
                result.update(exit_code=process.returncode, duration_seconds=round(time.monotonic()-started, 3))
                append_ledger(out, 'native_attempt_exited', **record)
                if auto_recover and (expected_session or failure):
                    expected_session = resolve_session(profile, summary, expected_session)
                    result['session_id'] = expected_session
                if not auto_recover or failure is None:
                    break
                # Recovery is reached only after communicate returned and the CLI exited.
                if process.poll() is None:
                    raise RuntimeError('Refusing recovery while the native CLI is still running')
                retire_exited_cli_tools(process, evidence_dir=out)
                consecutive += 1
                previous_recovery_reason = failure
                if not recover_control(control, identity, out, attempt=attempt,
                                       failure=failure, consecutive=consecutive):
                    result['recovery']['stopped_by_environment'] = True
                    break
            result['duration_seconds'] = round(time.monotonic() - started, 3)
            result["execution_status"] = execution_status(result, timed_out=timed_out,
                environment_error=(out / "environment-error.json").exists())
            if (out/'gui-input-pending.private.json').exists():
                result['execution_status'] = 'environment_error'
                result['unscored_reason'] = 'gui_input_not_acknowledged_before_runner_exit'
            if (result['execution_status'] != 'environment_error' and result.get('errors')
                    and not result.get('model_response_observed')):
                # A request that never produced a model response is an
                # infrastructure attempt, even if the wall guard fired later.
                result['execution_status'] = 'agent_error'
                result['unscored_reason'] = 'provider_errors_without_valid_model_response'
            tool_log = out / "computer.jsonl"
            events = [json.loads(line) for line in tool_log.read_text().splitlines()] if tool_log.exists() else []
            result['model_terminal_declared'] = any(e.get('type')=='finish'
                and e.get('termination') in {'done','give_up','giveup'} for e in events)
            result['environment_terminal_observed'] = any(e.get('type')=='environment_terminal' for e in events)
            result["agent_finished"] = result['model_terminal_declared']
            result['gui_inputs'] = sum(e.get('type') == 'action' and e.get('interaction') == 'gui_only' for e in events)
            result['physical_commits_attempted'] = sum(e.get('type') == 'action' and e.get('physical_commit') is True for e in events)
            if result["execution_status"] == "completed" and not result["agent_finished"]:
                result["execution_status"] = ('budget_exhausted' if any(
                    e.get('type')=='environment_terminal' and e.get('termination')=='budget_exhausted'
                    for e in events) else 'incomplete')
            result["outcome"] = result["execution_status"]
            sealed = control.post("/api/private/seal", json={"identity": identity, "reason": result["execution_status"]})
            sealed.raise_for_status()
            state_response = control.get('/api/private/state')
            state_response.raise_for_status()
            final_state = state_response.json()
            if not same_identity(final_state.get('identity'), identity):
                raise ValueError('Final controller identity mismatch')
            barrier = checked_barrier(final_state, identity) if 'owner_barrier' in final_state else None
            native_sealed = bool(barrier and barrier.get('terminal_snapshot_ready') is True)
            observed_attempt = any(r.get('model_response_observed') for r in result['native_attempts'])
            if native_sealed:
                result['terminal_owner_barrier'] = barrier
                try:
                    reconciled = reconcile_pending(out, barrier, attempt)
                    if reconciled:
                        result['pending_reconciliation'] = reconciled['disposition']
                        result.pop('unscored_reason', None)
                except ValueError:
                    # The GUI input remains unresolved, but an independently sealed
                    # native state may still be retained as an interrupted-state score.
                    result['pending_reconciliation'] = 'uncertain_not_replayed'
                if barrier.get('model_stop') in {'done', 'give_up'}:
                    result['model_terminal_declared'] = result['agent_finished'] = True
                    result['execution_status'] = 'completed'
                elif barrier.get('status') == 'budget_exhausted' and (observed_attempt or barrier['action_count'] > 0):
                    result['execution_status'] = 'budget_exhausted'
            normal = result['execution_status'] in {'completed', 'timed_out', 'budget_exhausted'}
            interrupted = native_sealed and (observed_attempt or barrier['action_count'] > 0)
            result['benchmark_completed'] = normal
            if normal or interrupted:
                response = control.post("/api/private/evaluate", json={"identity": identity})
                response.raise_for_status()
                evaluation = checked_evaluation(response.json(), identity)
                if ready and (evaluation.get('validation_only') is True or evaluation.get('scientific_evaluation') is False):
                    raise ValueError('Diagnostic native evidence cannot become a scientific evaluation')
                result["evaluation"] = evaluation
                result['physical_actions_confirmed'] = evaluation.get('steps')
                result['evaluation_scope'] = 'normal_terminal' if normal else 'interrupted_native_state'
                result["outcome"] = ("success" if evaluation["success"] else "fail") if normal else 'interrupted_scored'
        except (httpx.HTTPError, ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            result["outcome"] = "evaluation_error" if result.get("execution_status") else "environment_error"
            result["error"] = {"type": type(exc).__name__, "message": "Controller or native CLI integration failed; retain unscored evidence"}
        finally:
            for endpoint, body in (("seal", {"identity": identity, "reason": "runner_exit"}),
                                   ("close", {"identity": identity})):
                try:
                    cleanup = control.post("/api/private/" + endpoint, json=body)
                    cleanup.raise_for_status()
                    if endpoint == 'close' and cleanup.json().get('unscored_retirement') is True:
                        result['native_unscored_retirement'] = True
                except httpx.HTTPError:
                    result[endpoint + "_error"] = True
                    result.setdefault('cleanup_errors', []).append(dict(operation=endpoint, error='controller_cleanup_failed'))
                    if result.get('evaluation') is None:
                        result["outcome"] = "environment_error"
    gui_cleanup = out / 'gui-cleanup-errors.private.jsonl'
    if gui_cleanup.exists():
        result['gui_cleanup_errors'] = [json.loads(line) for line in gui_cleanup.read_text().splitlines()]
    qa_gate = RuleQAGate(computer)
    result['rule_qa'] = dict(metadata['rule_qa'], answered=qa_gate.answer.exists(),
        answer_file=str(qa_gate.answer) if qa_gate.answer.exists() else None, correctness_returned_to_model=False)
    result["scored"] = result.get("evaluation") is not None
    result["scientific_evaluation"] = bool(ready and result["scored"] and result.get('benchmark_completed'))
    if result["scored"]:
        private_json(out / "authoritative-evaluation.json", result["evaluation"])
    private_json(out / "result.json", result)
    print(json.dumps({"artifacts": str(out), **result}, ensure_ascii=False))
    return 0 if result["outcome"] in {"success", "fail"} else 1
