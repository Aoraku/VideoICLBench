"""Native file-transport contract, using a synthetic worker without PhysX."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import threading
import time

import pytest

from vic_sdk.embodied_environment.pool import NativePoolProxy


ID = dict(run_id='pool-test-1', task_id='E05', variant='A', seed=4201, suite='test', epoch='cpu')
IMAGES = dict(head='RGB-head', left_wrist='RGB-left', right_wrist='RGB-right')


def atomic(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


@pytest.fixture
def rpc(tmp_path):
    for name in ('requests', 'responses', 'terminal'):
        (tmp_path / name).mkdir()
    for room in ('one', 'two'):
        for kind in ('requests', 'responses'):
            (tmp_path / kind / room).mkdir()
    rooms = {r: dict(identity=dict(ID, run_id='pool-test-'+r)) for r in ('one', 'two')}
    atomic(tmp_path / 'ready.json', dict(schema='videoicl-room-pool-rpc-v1', rooms=rooms,
                                       barrier_timeout_seconds=.1))
    return tmp_path, rooms


def worker(root, rooms, stop, calls, *, corrupt=False, pending=None):
    seen = set()
    while not stop.is_set():
        for path in sorted((root / 'requests').glob('*/*.json')):
            if path in seen:
                continue
            seen.add(path)
            req = json.loads(path.read_text())
            calls.append(req)
            op, room = req['op'], req['room_id']
            if pending is not None and op == 'action':
                pending[room] = (path, req)
                if set(pending) != set(rooms):
                    continue
                batch = list(pending.values())
            else:
                batch = [(path, req)]
            for filename, body in batch:
                target_room = body['room_id']
                result = dict(images=IMAGES, robot_feedback=dict(arms={}, coordinate_frame='task'))
                if body['op'] == 'action':
                    result['receipt'] = dict(step_after=1, tracking_error_m={'left': .001})
                if body['op'] == 'seal':
                    result.update(room_id=target_room, identity=rooms[target_room]['identity'])
                    result['receipt'] = dict(native=dict(success=False, conditions=[dict(passed=False)]),
                                             terminal_shared_tick=80)
                    atomic(root / 'terminal' / (target_room+'.private.json'), result)
                atomic(root / 'responses' / target_room / filename.name, dict(request_id=body['request_id'],
                    room_id=target_room, identity=dict(rooms[target_room]['identity'],
                        seed=True) if corrupt else rooms[target_room]['identity'], ok=True, result=result))
        time.sleep(.002)


def test_parallel_rooms_wait_for_barrier_then_cache_terminal_after_worker_exit(rpc):
    root, rooms = rpc
    stopped, calls, pending = threading.Event(), [], {}
    thread = threading.Thread(target=worker, args=(root, rooms, stopped, calls), kwargs={'pending': pending})
    thread.start()
    a, b = [NativePoolProxy(root, room, row['identity'], timeout_seconds=1.) for room, row in rooms.items()]
    try:
        assert a.observe() == IMAGES
        with ThreadPoolExecutor(2) as executors:
            first = executors.submit(a.action, left='UP', right='STILL', step_mm=2., rotation_deg=1.)
            time.sleep(.03)
            assert not first.done()
            second = executors.submit(b.action, left='STILL', right='UP', step_mm=2., rotation_deg=1.)
            assert first.result()['step_after'] == second.result()['step_after'] == 1
        a.seal()
        before = len(calls)
        stopped.set()
        thread.join(1.)
        assert a.evaluate()['success'] is False
        assert a.observe() == IMAGES
        a.close()
        assert len(calls) == before  # No request to a departed Kit, no pool close.
        assert a.public_feedback()['coordinate_frame'] == 'task'
        with pytest.raises(RuntimeError, match='sealed'):
            a.action(left='UP')
        assert [x['action_index'] for x in calls if x['op'] == 'action'] == [0, 0]
    finally:
        stopped.set()
        thread.join(1.)


def test_unscored_terminal_is_never_recovered_as_failure_zero(rpc):
    root, rooms = rpc
    proxy = NativePoolProxy(root, 'one', rooms['one']['identity'])
    atomic(root / 'terminal/one.private.json', dict(room_id='one', identity=rooms['one']['identity'], images=IMAGES, receipt=dict(native=dict(success=False))))
    atomic(root / 'terminal/one.unscored.json', dict(scored=False, code='native_action_batch_error'))
    with pytest.raises(RuntimeError, match='infrastructure-unscored'):
        proxy.evaluate()


def test_response_identity_types_are_strict(rpc):
    root, rooms = rpc
    stopped, calls = threading.Event(), []
    thread = threading.Thread(target=worker, args=(root, rooms, stopped, calls), kwargs={'corrupt': True})
    thread.start()
    try:
        with pytest.raises(RuntimeError, match='identity mismatch'):
            NativePoolProxy(root, 'one', rooms['one']['identity'], timeout_seconds=1.).observe()
    finally:
        stopped.set()
        thread.join(1.)


def test_terminal_file_from_another_room_cannot_be_rewrapped(rpc):
    root, rooms = rpc
    proxy = NativePoolProxy(root, 'one', rooms['one']['identity'])
    atomic(root / 'terminal/one.private.json', dict(room_id='two', identity=rooms['two']['identity'],
        images=IMAGES, receipt=dict(native=dict(success=True))))
    with pytest.raises(RuntimeError, match='terminal room identity mismatch'):
        proxy.evaluate()


def test_cross_pod_file_rpc_is_rejected_before_starting_a_model(rpc,monkeypatch):
    root,rooms = rpc
    path=root/'ready.json';data=json.loads(path.read_text());data['hostname']='native-pod'
    path.write_text(json.dumps(data))
    monkeypatch.setattr('vic_sdk.embodied_environment.pool.socket.gethostname',lambda:'gui-pod')
    with pytest.raises(ValueError,match='same pod'):
        NativePoolProxy(root,'one',rooms['one']['identity'])


def test_timeout_does_not_replay_an_uncertain_action(rpc):
    root, rooms = rpc
    proxy = NativePoolProxy(root, 'one', rooms['one']['identity'], timeout_seconds=.03)
    with pytest.raises(RuntimeError, match='do not replay'):
        proxy.action(left='UP')
    with pytest.raises(RuntimeError, match='infrastructure-unscored'):
        proxy.action(left='UP')
    requests = list((root / 'requests/one').glob('*.json'))
    assert len(requests) == 1
    assert json.loads(requests[0].read_text())['identity'] == rooms['one']['identity']


@pytest.mark.parametrize('room', ['../one', '/one', 'one/../two'])
def test_room_path_must_be_registered_and_safe(rpc, room):
    root, rooms = rpc
    with pytest.raises(ValueError):
        NativePoolProxy(root, room, rooms['one']['identity'])


def test_multiroom_render_queue_timeout_scales_and_is_validated():
    from vic_sdk.embodied_environment.pool import native_response_timeout
    assert native_response_timeout(300, 7, 64) == 1140
    assert native_response_timeout(300, 6, 64) == 1020
    assert native_response_timeout(300, 1, 8) == 420
    for args in [(float('nan'), 7, 64), (300, 0, 64), (300, 7, 129), (300, True, 64)]:
        with pytest.raises(ValueError): native_response_timeout(*args)


def test_proxy_uses_ready_render_queue_metadata(rpc):
    root, rooms = rpc
    ready_path = root/'ready.json'
    ready = json.loads(ready_path.read_text())
    ready['metadata'] = dict(capture_passes=64)
    ready_path.write_text(json.dumps(ready))
    proxy = NativePoolProxy(root, 'one', rooms['one']['identity'])
    assert proxy.timeout == .1 + len(rooms)*120


def wait_ready(root):
    path=root/'ready.json';ready=json.loads(path.read_text())
    ready.update(barrier_policy='wait',pid=1234,native_process_start_ticks=5678)
    atomic(path,ready)


def test_wait_policy_ignores_request_deadline_and_counts_inflight_infrastructure(rpc,monkeypatch):
    root,rooms=rpc;wait_ready(root)
    monkeypatch.setattr('vic_sdk.embodied_environment.pool.native_process_alive',lambda *_:True)
    proxy=NativePoolProxy(root,'one',rooms['one']['identity'],timeout_seconds=.001)
    assert proxy.timeout is None
    stopped,calls=threading.Event(),[]
    with ThreadPoolExecutor(1) as executor:
        future=executor.submit(proxy.action,left='UP')
        deadline=time.monotonic()+1.
        while not list((root/'requests/one').glob('*.json')) and time.monotonic()<deadline:time.sleep(.001)
        before=proxy.infrastructure_wait_seconds();time.sleep(.04)
        intervals=proxy.infrastructure_wait_intervals()
        assert len(intervals)==1 and intervals[0][1]>intervals[0][0]
        assert not future.done() and proxy.infrastructure_wait_seconds()>=before+.03
        thread=threading.Thread(target=worker,args=(root,rooms,stopped,calls));thread.start()
        try:assert future.result(timeout=1.)['step_after']==1
        finally:stopped.set();thread.join(1.)
    duration=proxy.infrastructure_wait_seconds();time.sleep(.02)
    assert proxy.infrastructure_wait_seconds()==duration and duration>=.04
    intervals=proxy.infrastructure_wait_intervals()
    assert len(intervals)==1
    assert abs(sum(b-a for a,b in intervals)-duration)<1e-6
    assert proxy.last_infrastructure_request['operation']=='action'
    assert len(calls)==1  # No resubmission while waiting.


def test_wait_policy_detects_dead_or_reused_native_pid_without_replay(rpc,monkeypatch):
    root,rooms=rpc;wait_ready(root);alive=[True]
    monkeypatch.setattr('vic_sdk.embodied_environment.pool.native_process_alive',lambda *_:alive[0])
    proxy=NativePoolProxy(root,'one',rooms['one']['identity'])
    with ThreadPoolExecutor(1) as executor:
        future=executor.submit(proxy.action,left='UP')
        deadline=time.monotonic()+1.
        while not list((root/'requests/one').glob('*.json')) and time.monotonic()<deadline:time.sleep(.001)
        alive[0]=False
        with pytest.raises(RuntimeError,match='exited or its PID was reused'):
            future.result(timeout=1.)
    assert len(list((root/'requests/one').glob('*.json')))==1 and proxy.failed


def test_wait_policy_requires_process_incarnation(rpc):
    root,rooms=rpc;wait_ready(root)
    path=root/'ready.json';ready=json.loads(path.read_text());ready['native_process_start_ticks']=None;atomic(path,ready)
    with pytest.raises(ValueError,match='PID incarnation'):NativePoolProxy(root,'one',rooms['one']['identity'])


def test_native_liveness_checks_process_incarnation_and_zombie(monkeypatch):
    from vic_sdk.embodied_environment.pool import native_process_alive
    def proc(state='S',ticks=5678):
        fields=[state]+['0']*18+[str(ticks)];return '1234 (kit with spaces) '+' '.join(fields)
    monkeypatch.setattr(Path,'read_text',lambda *_args,**_kwargs:proc())
    assert native_process_alive(1234,5678)
    assert not native_process_alive(1234,9999)
    monkeypatch.setattr(Path,'read_text',lambda *_args,**_kwargs:proc('Z'))
    assert not native_process_alive(1234,5678)


def test_private_native_timing_does_not_enter_public_receipt_or_feedback(rpc,monkeypatch):
    root,rooms=rpc
    timing=dict(schema='videoicl-native-rpc-timing-v1',total_service_seconds=8.,
        peer_wait_seconds=4.,native_execution_seconds=1.,render_queue_seconds=2.,render_seconds=1.)
    proxy=NativePoolProxy(root,'one',rooms['one']['identity'],timeout_seconds=1.)
    def respond():
        deadline=time.monotonic()+1.
        while time.monotonic()<deadline:
            paths=list((root/'requests/one').glob('*.json'))
            if paths:
                req=json.loads(paths[0].read_text())
                atomic(root/'responses/one'/paths[0].name,dict(request_id=req['request_id'],room_id='one',
                    identity=rooms['one']['identity'],ok=True,timing=timing,
                    result=dict(receipt=dict(step_after=1),images=IMAGES,robot_feedback=dict(arms={}))))
                return
            time.sleep(.001)
        raise AssertionError('No native request')
    thread=threading.Thread(target=respond);thread.start()
    try:receipt=proxy.action(left='UP')
    finally:thread.join(1.)
    assert receipt==dict(step_after=1) and proxy.public_feedback()==dict(arms={})
    assert proxy.last_native_timing==timing
    assert proxy.last_infrastructure_request['native_timing']==timing


def test_wait_terminal_cache_remains_available_after_native_normal_exit(rpc,monkeypatch):
    root,rooms=rpc;wait_ready(root)
    monkeypatch.setattr('vic_sdk.embodied_environment.pool.native_process_alive',lambda *_:False)
    proxy=NativePoolProxy(root,'one',rooms['one']['identity'])
    atomic(root/'terminal/one.private.json',dict(room_id='one',identity=rooms['one']['identity'],
        images=IMAGES,receipt=dict(native=dict(success=False))))
    assert proxy.evaluate()==dict(success=False)
    assert proxy.observe()==IMAGES and proxy.infrastructure_wait_seconds()==0.
