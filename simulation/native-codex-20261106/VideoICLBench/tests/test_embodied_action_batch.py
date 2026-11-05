"""One visible Commit executes a durable ordered batch; no model or simulator.

The fake runtime tests lifecycle/attribution, not physical success or IK.
"""
from copy import deepcopy
import json
from pathlib import Path
import threading

import pytest

from vic_sdk.embodied_environment.episode import Episode, Identity, PublicError
from test_embodied_environment import Runtime


def make_episode(tmp_path, *, budget=50, clock=lambda: 0.):
    runtime = Runtime()
    runtime.observation_calls = 0
    observe = runtime.observe
    def counted_observe():
        runtime.observation_calls += 1
        return observe()
    runtime.observe = counted_observe
    value = Episode(runtime, Identity('batch-test', 'E22', 'C', 4201, 'test', 'queue-v1'),
        title='Public action batch', instruction='Use the public controls.', condition='text_rule',
        text_rule='Synthetic lifecycle test only.', max_actions=budget, timeout_seconds=0,
        output=tmp_path / 'episode', clock=clock, require_rule_report=False,
        action_schema=dict(tokens=['STILL', 'UP', 'DOWN', 'GRASP', 'RELEASE'],
            step_mm=dict(minimum=.5, maximum=50., default=20.),
            rotation_deg=dict(minimum=.5, maximum=20., default=10.)))
    return value, runtime


def pair(left='UP', right='STILL', step=20., rotation=10.):
    return dict(left=left, right=right, step_mm=step, rotation_deg=rotation)


def send(value, actions, batch='decision_1', frame=None):
    return value.action_batch(frame_id=frame or value.frame_id, batch_id=batch, actions=actions)


def journal(value):
    paths = list((value.output / 'action-batches').glob('*.private.json'))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_ordered_pairs_one_commit_one_final_observation_and_persistent_cursor(tmp_path):
    value, runtime = make_episode(tmp_path)
    first = value.observe()['frame_id']
    requests = [pair('UP', 'DOWN', 3., 2.), pair('GRASP', 'UP', 7., 4.), pair('DOWN', 'RELEASE', 9., 6.)]
    action = runtime.action
    def action_with_write_ahead(**fields):
        record = journal(value)
        assert record['status'] == 'inflight'
        assert record['next_index'] == len(runtime.actions)
        assert record['completed_count'] == len(runtime.actions)
        assert record['actions'][record['next_index']] == fields
        assert value.frame_id is None
        return action(**fields)
    runtime.action = action_with_write_ahead
    result = send(value, requests, frame=first)
    assert runtime.actions == requests
    assert runtime.observation_calls == 2  # Initial and batch end; no per-pair observe.
    assert result['frame_id'] != first
    assert result['state']['steps'] == 3
    batch = result['action_batch']
    assert batch['status'] == 'completed' and batch['accepted'] is True
    assert batch['requested_count'] == batch['completed_count'] == batch['physical_action_count'] == 3
    assert batch['next_index'] == 3 and batch['uncertain_action_index'] is None
    assert [r['step'] for r in batch['receipts']] == [1, 2, 3]
    assert journal(value)['status'] == 'completed'
    assert not runtime.sealed and runtime.scored == 0


def test_duplicate_batch_is_receipt_read_not_action_replay_even_with_stale_frame(tmp_path):
    value, runtime = make_episode(tmp_path)
    frame = value.observe()['frame_id']
    actions = [pair(), pair('GRASP')]
    original = send(value, actions, frame=frame)
    repeated = send(value, deepcopy(actions), frame=frame)
    assert len(runtime.actions) == 2 and value.steps == 2
    assert repeated['action_batch']['commands_sha256'] == original['action_batch']['commands_sha256']
    assert repeated['action_batch']['replayed'] is False
    with pytest.raises(PublicError, match='different ordered request'):
        send(value, [pair('DOWN')], frame=frame)
    assert len(runtime.actions) == 2


@pytest.mark.parametrize('actions', [[], [pair()] * 25, [pair(), pair('BOGUS')],
    [pair(), dict(pair(), step_mm=float('nan'))], [pair(), dict(pair(), private_score=100)],
    [pair(), dict(pair(), rotation_deg=True)]])
def test_entire_batch_validated_before_any_physical_operation(tmp_path, actions):
    value, runtime = make_episode(tmp_path)
    value.observe()
    with pytest.raises(PublicError):
        send(value, actions)
    assert value.steps == 0 and not runtime.actions
    assert not (value.output / 'action-batches').exists()


def test_budget_reserves_whole_queue_and_counts_every_pair(tmp_path):
    value, runtime = make_episode(tmp_path, budget=2)
    value.observe()
    with pytest.raises(PublicError, match='complete queue exceeds'):
        send(value, [pair()] * 3)
    assert not runtime.actions
    result = send(value, [pair(), pair('GRASP')])
    assert value.steps == 2 and result['action_batch']['physical_action_count'] == 2
    assert result['state']['status'] == 'budget_exhausted'
    assert runtime.sealed and runtime.scored == 1
    send(value, [pair(), pair('GRASP')])
    assert len(runtime.actions) == 2 and runtime.scored == 1


def test_partial_confirmed_failure_stops_suffix_and_keeps_raw_receipt_private(tmp_path):
    value, runtime = make_episode(tmp_path)
    value.observe()
    calls = []
    def execute(**fields):
        calls.append(fields)
        return {'ok': len(calls) != 2, 'tracking_error_m': .03,
                'private_object_state': {'hidden_score': 100}}
    runtime.action = execute
    result = send(value, [pair(), pair('GRASP'), pair('DOWN')])
    assert len(calls) == value.steps == 2
    batch = result['action_batch']
    assert batch['status'] == 'partial' and batch['next_index'] == 2
    assert batch['completed_count'] == 2
    assert 'private_object_state' in journal(value)['receipts'][1]['receipt']
    assert 'private_object_state' not in json.dumps(batch)
    assert 'hidden_score' not in json.dumps(result)
    assert value.status == 'running' and runtime.scored == 0
    send(value, [pair(), pair('GRASP'), pair('DOWN')])
    assert len(calls) == 2  # A partial prefix is never resumed by a duplicate POST.


@pytest.mark.parametrize('uncertainty', ['raise', 'pending', 'uncertain'])
def test_unknown_prefix_holds_world_and_blocks_suffix_new_ids_legacy_and_done(tmp_path, uncertainty):
    value, runtime = make_episode(tmp_path)
    value.observe()
    calls = []
    def execute(**fields):
        calls.append(fields)
        if len(calls) == 2:
            if uncertainty == 'raise':
                raise TimeoutError('PRIVATE inaccessible native receipt')
            return {uncertainty: True}
        return {'tracking_error_m': .001}
    runtime.action = execute
    actions = [pair(), pair('GRASP'), pair('DOWN')]
    with pytest.raises(PublicError) as failure:
        send(value, actions)
    assert failure.value.code == 'operation_pending' and 'PRIVATE' not in str(failure.value)
    assert len(calls) == 2 and value.steps == 1
    record = journal(value)
    assert record['status'] == 'unknown' and record['next_index'] == 1
    assert record['completed_count'] == 1 and record['uncertain_action_index'] == 1
    assert value.status == 'running' and not runtime.sealed and runtime.scored == 0
    fresh = value.observe()['frame_id']  # Public diagnostic read is permitted, never a replay.
    for operation in (lambda: send(value, actions), lambda: send(value, [pair()], batch='new_id'),
                      lambda: value.action(frame_id=fresh, **pair()),
                      lambda: value.terminal('done'), lambda: value.finish(), lambda: value.abandon()):
        with pytest.raises(PublicError) as blocked:
            operation()
        assert blocked.value.code == 'operation_pending'
    assert len(calls) == 2 and not runtime.sealed


def test_pending_receipt_does_not_auto_seal_at_time_budget(tmp_path):
    now = [0.]
    value, runtime = make_episode(tmp_path, clock=lambda: now[0])
    value.timeout_seconds = 2.
    value.observe()
    runtime.action = lambda **fields: dict(pending=True)
    with pytest.raises(PublicError):
        send(value, [pair()])
    now[0] = 100.
    value.expire_budget_if_due()
    assert not runtime.sealed and runtime.scored == 0 and value.status == 'running'


def test_native_terminal_marker_stops_queue_without_fabricating_model_done(tmp_path):
    value, runtime = make_episode(tmp_path)
    value.observe()
    calls = []
    def execute(**fields):
        calls.append(fields)
        return dict(terminal=True)
    runtime.action = execute
    result = send(value, [pair(), pair('DOWN')])
    assert len(calls) == 1 and value.steps == 1
    assert result['action_batch']['status'] == 'partial'
    assert value.model_stop is None and runtime.scored == 0


def test_one_batch_mutex_rejects_competing_commit_without_enqueuing_it(tmp_path):
    value, runtime = make_episode(tmp_path)
    frame = value.observe()['frame_id']
    started, finish = threading.Event(), threading.Event()
    action = runtime.action
    def execute(**fields):
        started.set()
        assert finish.wait(5)
        return action(**fields)
    runtime.action = execute
    result = []
    worker = threading.Thread(target=lambda: result.append(send(value, [pair()], frame=frame)))
    worker.start()
    assert started.wait(5)
    try:
        with pytest.raises(PublicError) as denied:
            send(value, [pair('DOWN')], batch='competing', frame=frame)
        assert denied.value.code == 'operation_pending'
        assert not runtime.actions
    finally:
        finish.set()
        worker.join(5)
    assert not worker.is_alive()
    assert len(runtime.actions) == 1 and result[0]['action_batch']['completed_count'] == 1


def test_legacy_single_pair_still_works_and_stale_frame_not_reused(tmp_path):
    value, runtime = make_episode(tmp_path)
    frame = value.observe()['frame_id']
    value.action(frame_id=frame, **pair())
    assert value.steps == 1 and len(runtime.actions) == 1
    with pytest.raises(PublicError):
        send(value, [pair()], frame=frame)
    assert len(runtime.actions) == 1


def test_explicit_non_admission_is_not_counted_or_retried(tmp_path):
    value, runtime = make_episode(tmp_path)
    value.observe()
    calls = []
    def execute(**fields):
        calls.append(fields)
        return dict(accepted=False, queued=False)
    runtime.action = execute
    result = send(value, [pair(), pair('DOWN')])
    assert len(calls) == 1 and value.steps == 0
    assert result['action_batch']['status'] == 'partial'
    assert result['action_batch']['physical_action_count'] == 0
    assert result['action_batch']['receipts'][0]['status'] == 'rejected'
    send(value, [pair(), pair('DOWN')])
    assert len(calls) == 1


def test_http_batch_contract_and_legacy_single_request_share_original_owner(tmp_path):
    import httpx
    import queue
    from dataclasses import asdict
    from vic_sdk.embodied_environment.server import serve
    value, runtime = make_episode(tmp_path)
    frontend = Path(__file__).resolve().parents[1] / 'apps/portal/public/embodied'
    ready = queue.Queue()
    owner = threading.Thread(target=serve, args=(value,), kwargs=dict(port=0,
        agent_token='local-test-actor', admin_token='local-test-owner', frontend=frontend, ready=ready.put), daemon=True)
    owner.start()
    port = ready.get(timeout=5)
    with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False,
                      headers={'Authorization': 'Bearer local-test-actor'}) as client:
        try:
            frame = client.get('/api/observe').json()['frame_id']
            body = dict(frame_id=frame, batch_id='http_batch', actions=[pair(), pair('GRASP')])
            result = client.post('/api/action', json=body)
            assert result.status_code == 200
            assert result.json()['action_batch']['physical_action_count'] == 2
            assert client.post('/api/action', json=body).status_code == 200
            assert len(runtime.actions) == 2
            frame = client.get('/api/observe').json()['frame_id']
            assert client.post('/api/action', json=dict(frame_id=frame, **pair('DOWN'))).status_code == 200
            assert value.steps == len(runtime.actions) == 3
            invalid = dict(frame_id=frame, batch_id='bad', actions=[pair()], hidden=100)
            assert client.post('/api/action', json=invalid).status_code == 400
            assert len(runtime.actions) == 3
        finally:
            response = client.post('/api/private/close', json={'identity': asdict(value.identity)},
                headers={'Authorization': 'Bearer local-test-owner'})
            assert response.status_code == 200
    owner.join(5)
    assert not owner.is_alive()
    assert len(set(runtime.threads)) == 1
