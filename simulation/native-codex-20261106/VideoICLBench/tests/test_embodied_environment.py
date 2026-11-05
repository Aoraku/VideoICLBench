"""Exercise the actual lifecycle and HTTP boundary with a synthetic runtime.

These are protocol/evidence tests, not native PhysX or model trial results.
"""
from dataclasses import asdict
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import queue
import threading

import httpx
import pytest

from vic_sdk.embodied_environment.episode import Episode, Identity, PublicError
from vic_sdk.embodied_environment.server import serve


class Runtime:
    def __init__(self):
        self.actions = []
        self.scored = 0
        self.sealed = False
        self.threads = []
        self.fail_action = False
        self.success = False

    def observe(self):
        self.threads.append(threading.get_ident())
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (36, 24), (40, 100, 160)).save(buffer, format='PNG')
        return {name: base64.b64encode(buffer.getvalue()).decode() for name in ('head', 'left_wrist', 'right_wrist')}

    def action(self, **value):
        self.threads.append(threading.get_ident())
        if self.fail_action:
            raise RuntimeError('PRIVATE task rule and source paths must not leak')
        assert not self.sealed
        self.actions.append(value)
        return {'step_after': len(self.actions)}

    def seal(self):
        self.threads.append(threading.get_ident())
        self.sealed = True

    def evaluate(self):
        self.threads.append(threading.get_ident())
        assert self.sealed
        self.scored += 1
        return {'success': self.success, 'history_valid': True, 'backend': 'isaaclab_physx',
                'conditions': [{'type': 'native_one', 'passed': True}, {'type': 'native_two', 'passed': self.success}]}


def episode(tmp_path, max_actions=2, clock=lambda: 0., identity=None, validation_only=False, require_rule_report=True, defer_budget_start=False):
    runtime = Runtime()
    value = Episode(runtime, identity or Identity('trial-1', 'E05', 'A', 4201, 'realworld50', 'v1'),
        title='Synthetic protocol test', instruction='Match the shapes.', condition='text_rule',
        text_rule='Explicit diagnostic mapping.', max_actions=max_actions, timeout_seconds=30,
        output=tmp_path / 'environment', clock=clock, validation_only=validation_only,
        require_rule_report=require_rule_report, defer_budget_start=defer_budget_start,
        action_schema=dict(tokens=['STILL', 'UP', 'GRASP'],
            step_mm=dict(minimum=.5, maximum=50., default=20.),
            rotation_deg=dict(minimum=.5, maximum=20., default=10.)))
    return value, runtime


def act(value, frame_id):
    return value.action(frame_id=frame_id, left='UP', right='STILL', step_mm=20., rotation_deg=10.)


def test_rule_gate_stale_frame_and_budget_seal(tmp_path):
    value, runtime = episode(tmp_path)
    first = value.observe()['frame_id']
    with pytest.raises(PublicError, match='inferred rule'):
        act(value, first)
    value.report_inferred_rule('An explicit text diagnostic.', [])
    second = act(value, first)['frame_id']
    with pytest.raises(PublicError, match='current environment'):
        act(value, first)
    act(value, second)
    assert value.status == 'budget_exhausted'
    assert runtime.sealed and len(runtime.actions) == 2
    assert runtime.scored == 1  # Private final check captured at the seal tick.
    with pytest.raises(PublicError):
        act(value, value.frame_id)


def test_finish_has_no_score_and_authority_is_immutable(tmp_path):
    value, runtime = episode(tmp_path)
    assert 'success' not in value.finish('Stopped after a synthetic test.')
    assert runtime.scored == 1
    a = value.evaluate()
    digest = hashlib.sha256((value.output / 'authoritative-evaluation.json').read_bytes()).hexdigest()
    a['success'] = True
    b = value.evaluate()
    assert b['success'] is False and b['score'] == 0.
    assert b['success_score'] == 0.
    assert b['progress_score'] is None and b['process_score'] is None
    assert b['condition_pass_fraction_diagnostic'] == .5
    assert 'partial_credit' not in b
    assert runtime.scored == 1
    assert hashlib.sha256((value.output / 'authoritative-evaluation.json').read_bytes()).hexdigest() == digest


def test_terminal_snapshot_is_captured_before_other_room_physics_can_change_it(tmp_path):
    value, runtime = episode(tmp_path)
    value.terminal('done', 'model thinks complete')
    raw_snapshot = (value.output / 'terminal-native.private.json').read_bytes()
    runtime.success = True  # A pooled room may keep changing after its seal.
    result = value.evaluate()
    assert result['success'] is False and result['model_success'] is True
    assert result['score'] == 0. and result['progress_score'] is None
    assert result['terminal_snapshot']['reason'] == 'model_done'
    assert runtime.scored == 1
    assert (value.output / 'terminal-native.private.json').read_bytes() == raw_snapshot


def test_give_up_does_not_override_native_success(tmp_path):
    value, runtime = episode(tmp_path)
    runtime.success = True
    public = value.terminal('give_up', 'model stopped')
    assert 'success' not in public and 'score' not in public
    result = value.evaluate()
    assert result['native_success'] is True and result['model_success'] is False
    assert result['model_stop'] == 'give_up' and result['score'] == 1.
    assert result['progress_score'] is None


def test_intermediate_success_does_not_auto_stop_and_can_be_lost(tmp_path):
    value, runtime = episode(tmp_path, max_actions=3, require_rule_report=False)
    frame = value.observe()['frame_id']
    runtime.success = True
    act(value, frame)
    assert value.status == 'running' and not runtime.sealed
    assert runtime.scored == 0
    runtime.success = False
    value.terminal('done')
    assert value.evaluate()['native_success'] is False


def test_final_native_check_error_is_unscored_infrastructure(tmp_path):
    value, runtime = episode(tmp_path)
    def broken():
        raise RuntimeError('PRIVATE checker internals')
    runtime.evaluate = broken
    with pytest.raises(PublicError) as exc:
        value.terminal('done')
    assert 'PRIVATE' not in str(exc.value)
    assert value.status == 'faulted' and not value.terminal_snapshot_ready
    with pytest.raises(ValueError):
        value.evaluate()
    assert not (value.output / 'authoritative-evaluation.json').exists()


def test_ambiguous_action_is_infrastructure_not_a_zero(tmp_path):
    value, runtime = episode(tmp_path)
    value.report_inferred_rule('diagnostic', [])
    frame = value.observe()['frame_id']
    runtime.fail_action = True
    with pytest.raises(PublicError) as exc:
        act(value, frame)
    assert 'PRIVATE' not in str(exc.value)
    assert value.status == 'faulted' and value.frame_id is None
    with pytest.raises(ValueError):
        value.evaluate()
    assert not (value.output / 'authoritative-evaluation.json').exists()


def test_text_condition_rejects_video_and_video_timestamps(tmp_path):
    value, _ = episode(tmp_path)
    assert value.state()['demo_available'] is False
    with pytest.raises(PublicError, match='no demonstration'):
        value.report_inferred_rule('text', [1.])


def test_wall_budget_seals_without_changing_native_state(tmp_path):
    now = [0.]
    value, runtime = episode(tmp_path, clock=lambda: now[0])
    now[0] = 31.
    value.finish()
    assert value.status == 'budget_exhausted' and runtime.sealed
    assert runtime.actions == []


def test_missing_native_checks_stay_unscored(tmp_path):
    value, runtime = episode(tmp_path)
    runtime.evaluate = lambda: {'success': True, 'conditions': []}
    value.finish()
    with pytest.raises(ValueError, match='condition evidence'):
        value.evaluate()
    assert not (value.output / 'authoritative-evaluation.json').exists()


def test_nonfinite_private_evidence_does_not_create_a_result_file(tmp_path):
    from vic_sdk.embodied_environment.episode import private_write
    with pytest.raises(ValueError):
        private_write(tmp_path / 'authority.json', {'score': float('nan')})
    assert not (tmp_path / 'authority.json').exists()


def test_assigned_video_is_frozen_before_the_trial(tmp_path):
    original = tmp_path / 'source.mp4'
    original.write_bytes(b'synthetic-video-fixture')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    value = Episode(Runtime(), Identity('video-trial', 'E05', 'A', 0, 'suite', 'v1'),
        title='Synthetic test', instruction='test', condition='real',
        max_actions=2, timeout_seconds=10, output=tmp_path / 'video-environment',
        demo={'path': str(original), 'sha256': digest},
        action_schema=dict(tokens=['STILL'], step_mm=dict(minimum=.5, maximum=50, default=20),
                           rotation_deg=dict(minimum=.5, maximum=20, default=10)))
    original.write_bytes(b'changed-source')
    assert Path(value.demo['path']).read_bytes() == b'synthetic-video-fixture'
    assert value.demo['sha256'] == digest


def test_http_private_identity_and_native_thread_boundary(tmp_path):
    value, runtime = episode(tmp_path)
    frontend = tmp_path / 'frontend'
    frontend.mkdir()
    (frontend / 'index.html').write_text('<p>Synthetic test frontend</p>')
    ports = queue.Queue()
    thread = threading.Thread(target=serve, args=(value,), kwargs=dict(port=0,
        agent_token='actor-private-test', admin_token='admin-private-test',
        frontend=frontend, ready=ports.put), daemon=True)
    thread.start()
    port = ports.get(timeout=5)
    url = f'http://127.0.0.1:{port}'
    actor = httpx.Client(base_url=url, headers={'Authorization': 'Bearer actor-private-test'}, trust_env=False)
    admin = httpx.Client(base_url=url, headers={'Authorization': 'Bearer admin-private-test'}, trust_env=False)
    identity = asdict(value.identity)
    try:
        assert httpx.get(url + '/api/observe', trust_env=False).status_code == 401
        assert actor.get('/api/private/state').status_code == 403
        public = actor.get('/api/state').json()
        assert 'variant' not in public and 'identity' not in public
        assert actor.get('/demo.mp4').status_code == 404
        assert admin.get('/api/private/state').json()['identity'] == identity
        bad = dict(identity, epoch='another-run')
        assert admin.post('/api/private/evaluate', json={'identity': bad}).status_code == 409
        observed = actor.get('/api/observe').json()
        assert actor.post('/api/action', json={'frame_id': observed['frame_id'], 'left': 'UP',
            'right': 'STILL', 'step_mm': 20, 'rotation_deg': 10, 'success': True}).status_code == 400
        assert actor.post('/api/report-inferred-rule', json={'rule': 'diagnostic', 'evidence_seconds': []}).status_code == 200
        # Exercise the real MCP adapter against this real transport, using
        # synthetic RGB rather than substituting an HTTP response contract.
        from vic_sdk.embodied_mcp import Robot
        robot = Robot(dict(control_url=url, actor_token='actor-private-test', run_id=value.identity.run_id,
            output_dir=str(tmp_path / 'mcp'), condition='text_rule', max_actions=2,
            timeout_seconds=30, rule_diagnostic=False, demo_video=None))
        try:
            image_result = robot.observe()
            assert sum(c.type == 'image' for c in image_result.content) == 3
            robot.act(robot.frame, left='UP', right='STILL')
            robot.finish('synthetic completion')
        finally:
            robot.http.close()
        finished = actor.post('/api/finish', json={'summary': 'synthetic completion'}).json()
        assert finished['stopped'] and 'success' not in finished and runtime.scored == 1
        response = admin.post('/api/private/evaluate', json={'identity': identity})
        assert response.status_code == 200
        evaluation = response.json()
        assert evaluation['success'] is False and evaluation['score'] == 0.
        assert evaluation['progress_score'] is None
        verifier_path = Path(__file__).resolve().parents[1] / 'scripts/harbor/verify_embodied.py'
        spec = importlib.util.spec_from_file_location('strict_embodied_test_verifier', verifier_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.validate_evaluation(evaluation, identity) == 0.
        assert set(runtime.threads) == {thread.ident}
    finally:
        admin.post('/api/private/close', json={'identity': identity})
        actor.close()
        admin.close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_fake_cli_through_actual_bridge_and_mcp_is_explicitly_diagnostic(tmp_path):
    from test_embodied_native_agent import inputs, IDENTITY
    from vic_sdk.embodied_agent import run
    value, runtime = episode(tmp_path, max_actions=6, identity=Identity(**IDENTITY),
                             validation_only=True, require_rule_report=False)
    value.text_rule = 'PUBLIC EXPLICIT TEXT RULE'
    frontend = Path(__file__).resolve().parents[1] / 'apps/portal/public/embodied'
    ports = queue.Queue()
    thread = threading.Thread(target=serve, args=(value,), kwargs=dict(port=0,
        agent_token='actor-test', admin_token='admin-test', frontend=frontend, ready=ports.put), daemon=True)
    thread.start()
    port = ports.get(timeout=5)
    control = dict(url=f'http://127.0.0.1:{port}')
    args = inputs(tmp_path / 'runner', control, condition='text_rule',
                  readiness='requires_native_interaction_validation')
    args.allow_unvalidated_environment = True
    try:
        assert run(args) == 0
    finally:
        # close acknowledges before the HTTP server's shutdown thread joins.
        thread.join(timeout=2)
        if thread.is_alive():
            with httpx.Client(base_url=control['url'], trust_env=False,
                              headers={'Authorization': 'Bearer admin-test'}) as admin:
                admin.post('/api/private/close', json={'identity': IDENTITY})
        thread.join(timeout=5)
    assert not thread.is_alive()
    result = json.loads(next(args.output_root.glob('*/result.json')).read_text())
    assert result['evaluation']['success'] is False
    assert result['validation_only'] is True and result['scientific_evaluation'] is False
    assert result['evaluation']['validation_only'] is True
    assert runtime.scored == 1


def test_v2_progress_is_private_identity_bound_and_sealed_once(tmp_path):
    from test_embodied_scoring import bound_progress_native
    value,runtime=episode(tmp_path)
    private=bound_progress_native(raw=50,cap=75)
    def evaluate():
        runtime.scored+=1
        return private
    runtime.evaluate=evaluate
    public=value.terminal('give_up','Stop after partial work')
    assert 'progress_result' not in json.dumps(public)
    assert 'task_score_100' not in json.dumps(public)
    private['progress_result']['task_score_100']=0
    result=value.evaluate()
    assert result['score']==0 and result['task_score_100']==50
    assert result['model_stop']=='give_up'
    assert runtime.scored==1
    result['progress_units'].clear()
    assert value.evaluate()['progress_units']


def test_v2_progress_from_another_room_cannot_enter_episode_score(tmp_path):
    from test_embodied_scoring import bound_progress_native
    value,runtime=episode(tmp_path)
    runtime.evaluate=lambda:bound_progress_native(raw=100,task='E06')
    value.terminal('done','Claims done')
    result=value.evaluate()
    assert result['score']==0 and result['task_score_100'] is None
    assert result['progress_unavailable_reason']=='native_progress_identity_mismatch'


def test_deferred_budget_excludes_warmup_and_cannot_reset(tmp_path):
    now = [10.]
    value, runtime = episode(tmp_path, clock=lambda: now[0], defer_budget_start=True,
                             require_rule_report=False)
    now[0] = 1000.
    first = value.observe()['frame_id']
    assert value.elapsed() == 0 and value.started is None
    for operation in (lambda: act(value, first), value.finish, lambda: value.terminal('done')):
        with pytest.raises(PublicError) as error:
            operation()
        assert error.value.code == 'episode_not_started'
    assert not runtime.sealed and not runtime.actions
    state_before = value.state()
    assert value.start(999.) == dict(budget_started=True, started_monotonic=999.)
    assert value.state() == state_before  # Private gate adds no model instruction/field.
    now[0] = 1005.
    assert value.start(999.)['started_monotonic'] == 999.
    with pytest.raises(PublicError) as error:
        value.start(1005.)
    assert error.value.code == 'budget_already_started'
    act(value, first)
    now[0] = 1029.
    with pytest.raises(PublicError) as error:
        act(value, value.frame_id)
    assert error.value.code == 'budget_exhausted'
    assert value.terminal_metadata['elapsed_seconds'] == 30.


@pytest.mark.parametrize('stamp', [float('nan'), float('inf'), True, -1., 41., 101.])
def test_deferred_budget_rejects_invalid_start(tmp_path, stamp):
    now = [50.]
    value, _ = episode(tmp_path, clock=lambda: now[0], defer_budget_start=True)
    now[0] = 100.
    with pytest.raises(PublicError) as error:
        value.start(stamp)
    assert error.value.code == 'invalid_start_time' and value.started is None


def test_private_start_authentication_identity_and_unstarted_close(tmp_path):
    value, runtime = episode(tmp_path, defer_budget_start=True)
    frontend = tmp_path/'frontend'; frontend.mkdir()
    (frontend/'index.html').write_text('<p>test</p>')
    ports = queue.Queue()
    thread = threading.Thread(target=serve, args=(value,), kwargs=dict(port=0,
        agent_token='actor', admin_token='admin', frontend=frontend, ready=ports.put), daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{ports.get(timeout=5)}'
    ident = asdict(value.identity)
    try:
        with httpx.Client(base_url=url, trust_env=False) as client:
            assert client.post('/api/private/start', json={'identity':ident}).status_code == 401
            assert client.post('/api/private/start', headers={'Authorization':'Bearer actor'}, json={'identity':ident}).status_code == 403
            admin = {'Authorization':'Bearer admin'}
            assert client.post('/api/private/start', headers=admin, json={'identity':dict(ident,seed=True)}).status_code == 409
            assert value.started is None
            assert client.post('/api/private/start', headers=admin, json={'identity':ident,'started_monotonic':0.}).json() == dict(budget_started=True,started_monotonic=0.)
            assert client.post('/api/private/start', headers=admin, json={'identity':ident,'started_monotonic':1.}).status_code == 409
    finally:
        httpx.post(url+'/api/private/close', headers={'Authorization':'Bearer admin'},json={'identity':ident}, trust_env=False)
        thread.join(timeout=5)
    assert not thread.is_alive() and not runtime.sealed
