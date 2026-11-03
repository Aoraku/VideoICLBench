"""Controller-private file queue, actual barrier methods, synthetic CPU state."""
from copy import deepcopy
import json
import uuid

import pytest

from videoicl_isaaclab.pool_rpc import PoolRPCWorker, atomic_json
from test_room_pool_actions import active_pool


def worker(tmp_path, clock=lambda: 0., barrier_policy="fail_after_timeout"):
    pool, controllers, sim, events = active_pool()
    rooms = {room: dict(identity=dict(run_id=room+'-run', task_id=room, variant='A',
        seed=0, suite='test', epoch='v1'), fingerprints={'test_only': True}) for room in controllers}
    capture = lambda room: {name: f'SYNTHETIC:{room}:{pool.physics_ticks}'
                            for name in ('head', 'left_wrist', 'right_wrist')}
    rpc = PoolRPCWorker(pool, tmp_path/'rpc', rooms, capture, barrier_timeout_seconds=5, clock=clock,barrier_policy=barrier_policy)
    return rpc, pool, controllers, sim, events


def send(rpc, room, op, *, identifier=None, **values):
    identifier = identifier or uuid.uuid4().hex
    packet = dict(request_id=identifier, room_id=room, op=op, **values)
    atomic_json(rpc.root/'requests'/room/(identifier+'.json'), packet)
    return identifier


def response(rpc, room, identifier):
    return json.loads((rpc.root/'responses'/room/(identifier+'.json')).read_text())


def test_ready_binds_actual_pod_hostname_for_file_rpc_admission(tmp_path,monkeypatch):
    import videoicl_isaaclab.pool_rpc as module
    monkeypatch.setattr(module.socket,'gethostname',lambda:'actual-controller-pod')
    rpc,*_=worker(tmp_path)
    ready=json.loads((rpc.root/'ready.json').read_text())
    assert ready['hostname']=='actual-controller-pod'
    assert ready['metadata']['execution_topology']=='same_pod_kit_gui_cli_file_rpc'
    assert 'host_boot_id' in ready


def test_no_physics_until_all_replies_and_duplicate_nonce_never_reexecutes(tmp_path):
    rpc, pool, controllers, sim, _ = worker(tmp_path)
    first = send(rpc, 'E05', 'action', action={'left': 'GRASP'}, action_index=0)
    assert rpc.poll_once() is True
    assert pool.physics_ticks == 0
    assert not (rpc.root/'responses/E05'/(first+'.json')).exists()
    second = send(rpc, 'E32', 'action', action={'right': 'GRASP'}, action_index=0)
    rpc.poll_once()
    assert pool.physics_ticks == 100
    assert response(rpc, 'E05', first)['result']['receipt']['step_after'] == 1
    assert response(rpc, 'E32', second)['ok'] is True
    original = (rpc.root/'responses/E05'/(first+'.json')).read_bytes()
    send(rpc, 'E05', 'action', identifier=first, action={'left': 'RELEASE'})
    rpc.poll_once()
    assert pool.physics_ticks == 100 and controllers['E05'].grips['left'] == 0.
    assert (rpc.root/'responses/E05'/(first+'.json')).read_bytes() == original


def test_seal_caches_native_and_rgb_at_one_tick_then_other_rooms_continue(tmp_path):
    rpc, pool, _, _, _ = worker(tmp_path)
    seal = send(rpc, 'E05', 'seal', reason='gui_done')
    rpc.poll_once()
    terminal = deepcopy(response(rpc, 'E05', seal)['result'])
    assert terminal['receipt']['terminal_shared_tick'] == 0
    action = send(rpc, 'E32', 'action', action={})
    rpc.poll_once()
    assert pool.physics_ticks == 100 and response(rpc, 'E32', action)['ok']
    observation = send(rpc, 'E05', 'observe')
    evaluate = send(rpc, 'E05', 'evaluate')
    rpc.poll_once()
    assert response(rpc, 'E05', observation)['result']['images'] == terminal['images']
    assert response(rpc, 'E05', evaluate)['result'] == terminal['receipt']['native']
    assert json.loads((rpc.root/'terminal/E05.private.json').read_text()) == terminal


def test_missing_action_timeout_is_unscored_and_does_not_block_ready_room(tmp_path):
    now = [0.]
    rpc, pool, _, _, _ = worker(tmp_path, clock=lambda: now[0])
    action = send(rpc, 'E05', 'action', action={})
    rpc.poll_once()
    now[0] = 6.
    rpc.poll_once()
    assert pool.physics_ticks == 100 and response(rpc, 'E05', action)['ok']
    failure = json.loads((rpc.root/'terminal/E32.unscored.json').read_text())
    assert failure == dict(kind='infrastructure_error', code='action_barrier_timeout', scored=False)
    evaluate = send(rpc, 'E32', 'evaluate')
    rpc.poll_once()
    reply = response(rpc, 'E32', evaluate)
    assert reply['ok'] is False and reply['error']['scored'] is False
    assert 'success' not in reply['error'] and 'score' not in reply['error']


def test_evaluate_before_seal_and_stale_action_index_are_rejected(tmp_path):
    rpc, pool, _, _, _ = worker(tmp_path)
    evaluation = send(rpc, 'E05', 'evaluate')
    action = send(rpc, 'E32', 'action', action={}, action_index=1)
    rpc.poll_once()
    assert response(rpc, 'E05', evaluation)['error']['code'] == 'seal_required'
    assert response(rpc, 'E32', action)['error']['code'] == 'stale_action_index'
    assert pool.physics_ticks == 0


def test_last_seal_stops_worker_without_replacement(tmp_path):
    rpc, pool, _, _, _ = worker(tmp_path)
    a = send(rpc, 'E05', 'seal', reason='gui_give_up')
    b = send(rpc, 'E32', 'seal', reason='gui_done')
    assert rpc.poll_once() is False
    assert response(rpc, 'E05', a)['ok'] and response(rpc, 'E32', b)['ok']
    marker = json.loads((rpc.root/'all-rooms-terminal.json').read_text())
    assert marker['replacement_started'] is False
    assert marker['unscored_rooms'] == [] and pool.physics_ticks == 0


def test_close_flushes_pending_actions_as_unscored(tmp_path):
    rpc, pool, _, _, _ = worker(tmp_path)
    pending = send(rpc, 'E05', 'action', action={})
    rpc.poll_once()
    close = send(rpc, 'E32', 'close')
    assert rpc.poll_once() is False
    assert response(rpc, 'E05', pending)['error']['scored'] is False
    assert response(rpc, 'E32', close)['result']['closed'] is True
    assert pool.physics_ticks == 0


def test_request_identity_mismatch_does_not_touch_native_state(tmp_path):
    rpc, pool, _, _, _ = worker(tmp_path)
    identity = deepcopy(rpc.rooms['E05']['identity']);identity['epoch'] = 'wrong'
    request = send(rpc, 'E05', 'seal', identity=identity)
    rpc.poll_once()
    assert response(rpc, 'E05', request)['error']['code'] == 'identity_mismatch'
    assert not pool.terminal and pool.physics_ticks == 0


def test_public_robot_feedback_is_cached_at_seal_tick(tmp_path):
    rpc, pool, _, _, _ = worker(tmp_path)
    rpc.feedback = lambda room: dict(arms={room: dict(tcp_position=[0., 0., pool.physics_ticks / 1000.])})
    observe = send(rpc, 'E05', 'observe')
    rpc.poll_once()
    assert response(rpc, 'E05', observe)['result']['robot_feedback']['arms']['E05']['tcp_position'][2] == 0.
    seal = send(rpc, 'E05', 'seal')
    rpc.poll_once()
    terminal = response(rpc, 'E05', seal)['result']
    assert terminal['robot_feedback']['arms']['E05']['tcp_position'][2] == 0.
    action = send(rpc, 'E32', 'action', action={})
    rpc.poll_once()
    assert response(rpc, 'E32', action)['result']['robot_feedback']['arms']['E32']['tcp_position'][2] == .1
    observe = send(rpc, 'E05', 'observe')
    rpc.poll_once()
    result = response(rpc, 'E05', observe)['result']
    assert result['shared_tick'] == 0
    assert result['robot_feedback'] == terminal['robot_feedback']


def test_wait_policy_never_advances_or_evicts_a_slow_room(tmp_path):
    now=[0.]
    rpc,pool,controllers,sim,_=worker(tmp_path,clock=lambda:now[0],barrier_policy='wait')
    first=send(rpc,'E05','action',action={'left':'GRASP'})
    rpc.poll_once();now[0]=18000.;rpc.poll_once()
    assert pool.physics_ticks==0 and sim.current_time==0.
    assert not rpc.failures and not rpc.terminal and controllers['E05'].grips['left']==.04
    second=send(rpc,'E32','action',action={'right':'GRASP'})
    rpc.poll_once()
    assert pool.physics_ticks==100 and not rpc.failures
    assert response(rpc,'E05',first)['timing']['peer_wait_seconds']==18000.
    assert response(rpc,'E32',second)['timing']['peer_wait_seconds']==0.
    assert json.loads((rpc.root/'ready.json').read_text())['barrier_policy']=='wait'


def test_private_timing_separates_peer_wait_simulation_and_other_room_render(tmp_path):
    now=[10.]
    rpc,pool,_,_,_=worker(tmp_path,clock=lambda:now[0],barrier_policy='wait')
    actual_batch=pool.action_batch
    def batch(actions):
        result=actual_batch(actions);now[0]+=3.;return result
    pool.action_batch=batch
    original_capture=rpc.capture
    def capture(room):
        now[0]+=2.;return original_capture(room)
    rpc.capture=capture
    first=send(rpc,'E05','action',action={});rpc.poll_once()
    now[0]+=7.
    second=send(rpc,'E32','action',action={});rpc.poll_once()
    a=response(rpc,'E05',first);b=response(rpc,'E32',second)
    for value in (a,b):
        timing=value['timing']
        assert timing['native_execution_seconds']==3.
        assert timing['render_queue_seconds']==2.
        assert timing['render_seconds']==2.
        assert 'timing' not in value['result']['receipt']
    assert a['timing']['total_service_seconds']==14.
    assert b['timing']['total_service_seconds']==7.
    observe=send(rpc,'E05','observe');rpc.poll_once()
    assert response(rpc,'E05',observe)['timing']['render_seconds']==2.


def test_unknown_barrier_policy_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='barrier policy'):
        worker(tmp_path,barrier_policy='fill_missing_with_still')
