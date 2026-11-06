"""Native harness + actual Chrome over synthetic HTTP; no model calls."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tomllib

import pytest

from vic_sdk.embodied_agent import run, checked_evaluation
from test_embodied_gui_mcp import IDENTITY, gui_controller, chrome_path


@pytest.fixture
def controller(gui_controller, chrome_path):
    gui_controller['browser_path'] = chrome_path
    return gui_controller


def inputs(tmp_path, controller, *, condition="real", readiness="available", engine="codex"):
    task = tmp_path / "task"
    (task / "environment").mkdir(parents=True)
    manual = b"Use screenshot observe and coordinate act. End with done or giveup. GUI ONLY.\n"
    (task / "environment/gui-controls.md").write_bytes(manual)
    instruction = "按分配示范中的对应关系摆放物体。\n".encode()
    (task / "instruction.md").write_bytes(instruction)
    real, sim = tmp_path / "real.mp4", tmp_path / "sim.mp4"
    real.write_bytes(b"REAL VIDEO TEST FIXTURE")
    sim.write_bytes(b"SIM VIDEO TEST FIXTURE")
    material = lambda p: {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    spec = dict(kind="embodied", backend="videoicl-native-slurm", task_id="E05", variant="A", seed=7, readiness=readiness,
        agent_interaction="gui_only", agent_protocol="roboprobe_gui_v1",
        gui_controls=dict(path="gui-controls.md", sha256=hashlib.sha256(manual).hexdigest()),
        action_interface="bounded_dual_arm_tokens_v1", native_interaction_validated=readiness == 'available',
        budget=dict(status='frozen', max_actions=6, timeout_sec=45),
        instruction_sha256=hashlib.sha256(instruction).hexdigest(), demo=material(real), demo_sim=material(sim))
    (task / "environment/native.json").write_text(json.dumps(spec))
    (tmp_path / "actor").write_text("actor-test")
    (tmp_path / "admin").write_text("admin-test")
    connection = dict(control_url=controller["url"], identity=IDENTITY,
        actor_token_file="actor", admin_token_file="admin", condition=condition,
        max_actions=6, timeout_seconds=45)
    controller["condition"] = condition
    path = tmp_path / "connection.json"
    path.write_text(json.dumps(connection))
    provider = tmp_path / "provider.json"
    provider.write_text(json.dumps({engine: dict(api_key="provider-test-key", base_url="https://invalid-provider.test/v1")}))
    catalog=tmp_path/'catalog.json'
    catalog.write_text(json.dumps(dict(models=[dict(slug='test-model',tool_mode='code_mode_only')])))
    catalog_sha=hashlib.sha256(catalog.read_bytes()).hexdigest()
    cli = tmp_path / "native-cli"
    sdk = str(Path(__file__).resolve().parents[1] / "packages/sdk")
    cli.write_text("#!" + sys.executable + "\n" + '''
import json,os,sys,tomllib
from pathlib import Path
if '--version' in sys.argv:
 print('codex-cli 0.163.0');raise SystemExit(0)
sys.path.insert(0, SDK_PATH)
from vic_sdk.embodied_gui_mcp import GuiBrowser
profile=Path(os.environ.get('CODEX_HOME') or os.environ['CLAUDE_CONFIG_DIR'])
if 'CODEX_HOME' in os.environ:
 settings=tomllib.loads((profile/'config.toml').read_text())
 server=settings['mcp_servers']['vic']
else:
 server=json.loads((profile/'mcp.json').read_text())['mcpServers']['vic']
cfg=json.loads(Path(server['args'][-1]).read_text())
assert 'admin_token' not in cfg and 'admin_token_file' not in cfg
assert 'vic_sdk.embodied_gui_mcp' in server['args']
assert cfg['agent_interaction']=='gui_only' and cfg['rule_diagnostic'] is False
if 'CLAUDE_CONFIG_DIR' in os.environ:
 assert int(os.environ['MCP_TOOL_TIMEOUT']) > cfg['gui_settle_timeout_ms']
 assert set(server)=={'command','args','env'}
robot=GuiBrowser(cfg)
try:
 observation=robot.observe()
 assert [c.type for c in observation.content]==['text','image']
 def click(selector):
  box=robot.page.locator(selector).bounding_box()
  return dict(kind='click',x=box['x']+box['width']/2,y=box['y']+box['height']/2)
 robot.act(robot.frame,[click('#left-actions [data-token="UP"]'),click('#step-mm'),
  dict(kind='key',key='ControlOrMeta+A'),dict(kind='text',text='7.5'),
  click('#right-actions [data-token="STILL"]'),click('#commit')])
 robot.terminal('done','Model claims success; evaluator must decide',robot.frame)
finally:
 robot.close()
prompt=sys.stdin.read()
if cfg['condition']=='text_rule':
 assert 'PUBLIC EXPLICIT TEXT RULE' in prompt and cfg['demo_video'] is None
if 'CODEX_HOME' in os.environ:
 print(json.dumps({'type':'thread.started','thread_id':'fake-session'}))
 print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Success provider-test-key'}}))
 print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1}}))
else:
 print(json.dumps({'type':'result','session_id':'fake-session','result':'Success provider-test-key','is_error':False,'subtype':'success','total_cost_usd':.05}))
'''.replace("SDK_PATH", repr(sdk)))
    cli.chmod(0o700)
    return SimpleNamespace(embodied_task_dir=task, embodied_connection=path,
        condition=condition, max_actions=6, timeout=45, model="test-model", engine=engine,
        credentials=provider, base_url=None, api_key_env=None, output_root=tmp_path / "outputs",
        binary=cli, effort="high", code_mode=False, max_budget_usd=3.,
        codex_model_catalog=catalog,codex_model_catalog_sha256=catalog_sha,
        preflight=False, allow_unvalidated_environment=False,
        browser_path=Path(controller.get("browser_path", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")),
        max_gui_inputs=200, claude_compact_percent=None, serial_tools=False)


def artifacts(args):
    return next(args.output_root.iterdir())


def test_graceful_model_request_survives_old_wall_deadline(tmp_path, controller):
    args=inputs(tmp_path,controller,condition='text_rule')
    args.timeout=1
    spec_path=args.embodied_task_dir/'environment/native.json'
    spec=json.loads(spec_path.read_text());spec['budget']['timeout_sec']=1
    spec_path.write_text(json.dumps(spec))
    connection=json.loads(args.embodied_connection.read_text())
    connection.update(timeout_seconds=1,barrier_policy='wait',native_response_timeout_seconds=None,
                      budget_policy='effective_time_graceful_v1')
    args.embodied_connection.write_text(json.dumps(connection))
    code=args.binary.read_text().replace('robot=GuiBrowser(cfg)', 'import time;time.sleep(2.0)\nrobot=GuiBrowser(cfg)')
    args.binary.write_text(code)
    assert run(args)==0
    out=artifacts(args);result=json.loads((out/'result.json').read_text())
    assert result['exit_code']==0 and result['physical_actions_confirmed']==1
    assert result['duration_seconds']>1 and result['execution_status']=='completed'
    assert any(row[1]=='/api/private/start' for row in controller['calls'])
    config=tomllib.loads((out/'profile/config.toml').read_text())
    assert config['model_providers']['vic_remote']['stream_idle_timeout_ms']==86400000


@pytest.mark.parametrize("engine", ["codex", "claude"])
@pytest.mark.parametrize("condition", ["real", "sim", "text_rule"])
def test_actual_fake_native_cli_uses_actor_tools_then_controller_scores(tmp_path, controller, engine, condition):
    args = inputs(tmp_path, controller, engine=engine, condition=condition)
    assert run(args) == 0
    out = artifacts(args)
    result = json.loads((out / "result.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    assert result["outcome"] == "fail"  # Model's success claim cannot produce success.
    assert result["evaluation"]["score"] == 0. and result["agent_finished"]
    assert result['evaluation']['progress_score'] is None
    assert result["scientific_evaluation"] is True
    assert manifest['agent_interaction'] == 'gui_only'
    assert manifest['agent_protocol'] == 'roboprobe_gui_v1'
    assert manifest['budgets']['max_physical_actions'] == 6
    assert manifest['budgets']['max_gui_inputs'] == 200
    posts = [x for x in controller['calls'] if x[1] == '/api/action']
    assert len(posts) == 1 and posts[0][3]['left'] == 'UP' and posts[0][3]['step_mm'] == 7.5
    assert controller['status'] == 'done'
    events = [json.loads(line) for line in (out / 'computer.jsonl').read_text().splitlines()]
    assert sum(e.get('physical_commit', False) for e in events) == 1
    assert sum(e['type'] == 'action' for e in events) == 6
    assert result['gui_inputs'] == 6 and result['physical_commits_attempted'] == 1
    prompt = (out / 'prompt-1.txt').read_text()
    expected = (args.embodied_task_dir / 'instruction.md').read_text().strip()
    if condition == 'text_rule':
        expected += '\n\n请按以下规则完成任务：\nPUBLIC EXPLICIT TEXT RULE'
    assert prompt == expected
    assert 'GUI ONLY' not in prompt and 'Budget:' not in prompt
    assert 'Public GUI' not in prompt and 'report_inferred_rule' not in prompt
    if condition == 'text_rule':
        assert manifest['input_sha256'] == hashlib.sha256(b'PUBLIC EXPLICIT TEXT RULE').hexdigest()
    else:
        assert Path(json.loads((out / 'computer-private.json').read_text())['demo_video']).parent == out / 'assigned-input'
    assert "provider-test-key" not in (out / "stdout-1.jsonl").read_text()
    assert "provider-test-key" not in (out / "result.json").read_text()
    config = json.loads((out / "computer-private.json").read_text())
    assert set(config).isdisjoint({"admin_token", "admin_token_file", "rule", "expected_rule"})
    assert config["demo_video"] is None if condition == "text_rule" else Path(config["demo_video"]).name == condition + ".mp4"
    if engine == "codex":
        settings = tomllib.loads((out / "profile/config.toml").read_text())
        assert settings["model_reasoning_effort"] == "high"
        assert settings['model_auto_compact_token_limit'] == 32768
        assert settings['tool_output_token_limit'] == 4096
        assert manifest['compaction']['threshold_tokens'] == 32768
        contract=settings['developer_instructions']
        assert manifest['developer_transport_contract']['sha256']==hashlib.sha256(contract.encode()).hexdigest()
        assert 'Pending is not task failure' in contract
        assert manifest['compaction']['custom_history_reconstruction'] is False
        assert settings["features"]["shell_tool"] is False
        assert settings["features"]["view_image"] is False
        assert settings['mcp_servers']['vic']['tool_timeout_sec'] > config['gui_settle_timeout_ms'] / 1000
    else:
        assert manifest["reasoning_effort"] is None
        assert manifest["claude_reported_cost_cap_usd"] == 3.
    for _, path, auth, body in controller["calls"]:
        if "/private/" in path:
            assert auth == "Bearer admin-test"
            if body is not None:
                assert body["identity"] == IDENTITY
        else:
            assert auth == "Bearer actor-test"
    assert controller["calls"][-1][1] == "/api/private/close"


def test_native_inference_budget_stop_keeps_trusted_terminal_score(tmp_path, controller):
    args = inputs(tmp_path, controller, engine='claude')
    script = args.binary.read_text().replace(
        " robot.terminal('done','Model claims success; evaluator must decide',robot.frame)", '')
    script = script.replace("'is_error':False,'subtype':'success'",
                            "'is_error':True,'subtype':'error_max_turns'")
    script = script.replace(" print(json.dumps({'type':'result'",
        " print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','name':'mcp__vic__act'}]}}))\n print(json.dumps({'type':'result'")
    args.binary.write_text(script)
    assert run(args) == 0
    result = json.loads((artifacts(args) / 'result.json').read_text())
    assert result['execution_status'] == 'budget_exhausted'
    assert result['agent_finished'] is False
    assert result['scored'] is True and result['evaluation']['score'] == 0.


def test_provider_errors_without_model_response_remain_unscored_at_deadline(tmp_path, controller, monkeypatch):
    args = inputs(tmp_path, controller)
    args.binary.write_text('#!' + sys.executable + '\n' + '''
import json,sys
if '--version' in sys.argv:
 print('codex-cli 0.163.0');raise SystemExit(0)
sys.stdin.read()
print(json.dumps({'type':'thread.started','thread_id':'no-response'}))
print(json.dumps({'type':'error','message':'Reconnecting... waiting for network (Connection failed: error sending request)'}))
''')
    monkeypatch.setattr('vic_sdk.embodied_agent.execution_status', lambda *a, **kw: 'timed_out')
    assert run(args) == 1
    result = json.loads((artifacts(args) / 'result.json').read_text())
    assert result['execution_status'] == 'agent_error'
    assert result['evaluation'] is None and result['scored'] is False
    assert result['unscored_reason'] == 'provider_errors_without_valid_model_response'
    assert result['model_response_observed'] is False
    assert not any(path=='/api/private/evaluate' for _,path,_,_ in controller['calls'])


def test_unacknowledged_gui_input_is_infrastructure_unscored(tmp_path,controller):
    args = inputs(tmp_path,controller)
    args.binary.write_text('#!'+sys.executable+'\n'+'''
import json,sys,os,tomllib
from pathlib import Path
if '--version' in sys.argv:
 print('codex-cli 0.163.0');raise SystemExit(0)
sys.stdin.read()
settings=tomllib.loads((Path(os.environ['CODEX_HOME'])/'config.toml').read_text())
cfg=json.loads(Path(settings['mcp_servers']['vic']['args'][-1]).read_text())
(Path(cfg['output_dir'])/'gui-input-pending.private.json').write_text(json.dumps({'physical_commit':True}))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1}}))
''')
    assert run(args)==1
    result=json.loads((artifacts(args)/'result.json').read_text())
    assert result['model_response_observed'] is True
    assert result['execution_status']=='environment_error'
    assert result['unscored_reason']=='gui_input_not_acknowledged_before_runner_exit'
    assert result['evaluation'] is None and result['scored'] is False


def test_unvalidated_tasks_require_explicit_validation_only_and_never_claim_science(tmp_path, controller, capsys):
    args = inputs(tmp_path, controller, readiness="requires_native_interaction_validation")
    args.preflight = True
    assert run(args) == 2
    assert controller["calls"] == []
    args.allow_unvalidated_environment = True
    assert run(args) == 0
    args.preflight = False
    assert run(args) == 0
    result = json.loads((artifacts(args) / "result.json").read_text())
    assert result["validation_only"] is True and result["scientific_evaluation"] is False


def test_bad_video_hash_fails_before_native_cli_or_controller(tmp_path, controller):
    args = inputs(tmp_path, controller)
    (tmp_path / "real.mp4").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        run(args)
    assert controller["calls"] == []
    assert not args.output_root.exists()


@pytest.mark.parametrize('change', ['manual_checksum', 'manual_missing', 'direct_protocol'])
def test_gui_contract_is_verified_before_controller_or_cli(tmp_path, controller, change):
    args = inputs(tmp_path, controller)
    if change == 'manual_checksum':
        (args.embodied_task_dir / 'environment/gui-controls.md').write_text('tampered')
    elif change == 'manual_missing':
        (args.embodied_task_dir / 'environment/gui-controls.md').unlink()
    else:
        path = args.embodied_task_dir / 'environment/native.json'
        spec = json.loads(path.read_text())
        spec['agent_interaction'] = 'direct_robot_mcp'
        path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='GUI'):
        run(args)
    assert controller['calls'] == [] and not args.output_root.exists()


def test_preflight_reports_missing_material_without_model_or_environment_calls(tmp_path, controller, capsys):
    args = inputs(tmp_path, controller, condition="sim")
    args.preflight = True
    (tmp_path / "sim.mp4").unlink()
    assert run(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["stage"] == "input_validation" and report["scientific_evaluation"] is False
    assert controller["calls"] == []


def test_wrong_evaluation_identity_is_unscored(tmp_path, controller):
    args = inputs(tmp_path, controller)
    controller["evaluation_identity"]["epoch"] = "other-epoch"
    assert run(args) == 1
    out = artifacts(args)
    result = json.loads((out / "result.json").read_text())
    assert result["outcome"] == "evaluation_error" and result["evaluation"] is None
    assert not (out / "authoritative-evaluation.json").exists()


def test_cli_exit_without_gui_terminal_is_incomplete_and_unscored(tmp_path, controller):
    args = inputs(tmp_path, controller)
    source = args.binary.read_text()
    source = source.replace(" robot.terminal('done','Model claims success; evaluator must decide',robot.frame)\n", '')
    args.binary.write_text(source)
    assert run(args) == 1
    out = artifacts(args)
    result = json.loads((out / 'result.json').read_text())
    assert result['execution_status'] == 'incomplete'
    assert result['outcome'] == 'incomplete'
    assert result['evaluation'] is None and result['agent_finished'] is False
    assert result['scored'] is False and result['scientific_evaluation'] is False
    assert not (out / 'authoritative-evaluation.json').exists()
    assert not any(path == '/api/private/evaluate' for _, path, _, _ in controller['calls'])


def test_unavailable_rgb_preflight_never_calls_native_cli_or_fabricates_zero(tmp_path, controller, monkeypatch):
    from vic_sdk import embodied_gui_mcp
    original = embodied_gui_mcp.GuiBrowser
    class QuickFailureBrowser(original):
        def __init__(self, config):
            super().__init__({**config, 'gui_observation_timeout_ms':500})
    monkeypatch.setattr(embodied_gui_mcp, 'GuiBrowser', QuickFailureBrowser)
    args = inputs(tmp_path, controller)
    controller["observation_error"] = True
    assert run(args) == 1
    out = artifacts(args)
    result = json.loads((out / "result.json").read_text())
    assert result["outcome"] == "environment_error" and result["evaluation"] is None
    assert not (out / "stdout-1.jsonl").exists()
    assert not any(path == "/api/private/evaluate" for _, path, _, _ in controller["calls"])


def test_close_is_attempted_even_if_seal_fails(tmp_path, controller):
    args = inputs(tmp_path, controller)
    controller["seal_error"] = True
    assert run(args) == 1
    paths = [path for _, path, _, _ in controller["calls"]]
    assert paths[-1] == "/api/private/close"
    assert not (artifacts(args) / "authoritative-evaluation.json").exists()


def test_provisional_connection_cannot_be_reported_as_scientific_evaluation(tmp_path, controller):
    args = inputs(tmp_path, controller)
    connection = json.loads(args.embodied_connection.read_text())
    connection["validation_only"] = True
    args.embodied_connection.write_text(json.dumps(connection))
    with pytest.raises(ValueError, match="not executable"):
        run(args)
    args.allow_unvalidated_environment = True
    assert run(args) == 0
    result = json.loads((artifacts(args) / "result.json").read_text())
    assert result["validation_only"] is True and result["scientific_evaluation"] is False


def test_provisional_task_budget_cannot_be_promoted_by_a_ready_label(tmp_path, controller):
    args = inputs(tmp_path, controller)
    path = args.embodied_task_dir / 'environment/native.json'
    spec = json.loads(path.read_text())
    spec['budget']['status'] = 'provisional_integration_only'
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='not executable'):
        run(args)
    assert controller['calls'] == []


def test_frozen_task_budget_cannot_be_silently_changed(tmp_path, controller):
    args = inputs(tmp_path, controller)
    path = args.embodied_task_dir / 'environment/native.json'
    spec = json.loads(path.read_text())
    spec['budget']['max_actions'] = 12
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='frozen task'):
        run(args)
    assert controller['calls'] == []


@pytest.mark.parametrize("score", [None, True, -1., 1.1, float("nan"), float("inf")])
def test_invalid_scores_cannot_enter_verifier(score):
    with pytest.raises(ValueError, match="finite score"):
        checked_evaluation({**IDENTITY, "success": False, "score": score}, IDENTITY)


@pytest.mark.parametrize('success,score', [(False, 1.), (True, 0.), (False, .5), (True, .5)])
def test_finite_primary_scores_must_match_terminal_success(success, score):
    with pytest.raises(ValueError):
        checked_evaluation({**IDENTITY, 'success':success, 'score':score}, IDENTITY)


def test_opt_in_program_gui_native_manifest_and_high_prompt(tmp_path, controller):
    args = inputs(tmp_path, controller, condition='text_rule')
    args.embodied_harness = 'program_gui'
    assert run(args) == 0
    out = artifacts(args)
    config = json.loads((out / 'computer-private.json').read_text())
    manifest = json.loads((out / 'manifest.json').read_text())
    settings = tomllib.loads((out / 'profile/config.toml').read_text())
    assert config['embodied_harness'] == manifest['embodied_harness'] == 'program_gui'
    assert config['program_episode_identity'] == IDENTITY
    assert manifest['episode_learning'] == dict(scope='current_episode_only', development_practice=False,
        cross_episode_transfer=False, program_enabled=True)
    assert settings['model_reasoning_effort'] == 'high'
    assert 'at most ONE act call' in settings['developer_instructions']
    assert 'No prior episode' in settings['developer_instructions']
    assert 'program_enabled' not in (out / 'prompt-1.txt').read_text()
