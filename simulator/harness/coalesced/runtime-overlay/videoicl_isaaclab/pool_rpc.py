"""Controller-private file RPC for a single-wave synchronous room pool.

This module has no simulator imports. ``poll_once`` must run on the Kit owner
thread. It never restores body/joint state, chooses task goals or returns a
score to a model-facing interface. The CPU sidecar is responsible for keeping
this directory private and exposing only the assigned room's RGB/GUI routes.
"""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import socket
import time
import traceback
import uuid


def atomic_json(path, value):
    path = Path(path)
    try:
        raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    except ValueError as exc:
        # Private maintainer diagnostic; never replace unknown state with zeros.
        paths=[]
        def inspect(item, field='$'):
            if isinstance(item,float) and not math.isfinite(item): paths.append(field)
            elif isinstance(item,dict):
                for key,entry in item.items(): inspect(entry,field+'.'+str(key))
            elif isinstance(item,(list,tuple)):
                for index,entry in enumerate(item): inspect(entry,field+'['+str(index)+']')
        inspect(value)
        raise ValueError('Nonfinite private RPC fields: '+', '.join(paths[:32])) from exc

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(raw)
    temporary.replace(path)


def process_start_ticks(pid):
    """Linux process incarnation; None on non-Linux CPU test hosts."""
    try:
        return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
    except (OSError,ValueError,IndexError):
        return None


class PoolRPCWorker:
    def __init__(self, pool, root, rooms, capture, *, barrier_timeout_seconds,
                 metadata=None, feedback=None, clock=time.monotonic, barrier_policy="fail_after_timeout",
                 coalesce_window_seconds=None):
        if type(barrier_timeout_seconds) not in (int, float) or not math.isfinite(barrier_timeout_seconds) or barrier_timeout_seconds <= 0:
            raise ValueError('An explicit positive action barrier timeout is required')
        if barrier_policy not in ('wait','fail_after_timeout'):
            raise ValueError('Unknown action barrier policy')
        if coalesce_window_seconds is not None and (
                type(coalesce_window_seconds) not in (int, float)
                or not math.isfinite(coalesce_window_seconds)
                or not 0 < coalesce_window_seconds <= .25
                or barrier_policy != 'wait' or not pool.supports_partial_actions):
            raise ValueError('Coalescing requires a validated idle hold, wait policy and a window in (0, .25]')
        self.barrier_policy=barrier_policy
        self.coalesce_window = coalesce_window_seconds
        self.request_started={}
        if set(rooms) != set(pool.controllers):
            raise ValueError('Every native room requires exactly one RPC identity')
        self.pool, self.root, self.rooms, self.capture = pool, Path(root), deepcopy(rooms), capture
        self.feedback = feedback
        self.timeout, self.clock = float(barrier_timeout_seconds), clock
        self.pending, self.terminal, self.failures = {}, {}, {}
        self.stopped = False
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        for name in ('requests', 'responses', 'processed', 'duplicates', 'terminal'):
            (self.root/name).mkdir(mode=0o700)
        for room in rooms:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', room):
                raise ValueError('Path-safe room IDs required')
            identity = rooms[room].get('identity')
            if not isinstance(identity, dict) or set(identity) != {'run_id', 'task_id', 'variant', 'seed', 'suite', 'epoch'} or \
                    any(type(identity.get(key)) is not str or not identity[key] for key in ('run_id', 'task_id', 'variant', 'suite', 'epoch')) or \
                    type(identity.get('seed')) is not int or identity['seed'] < 0:
                raise ValueError('Each room requires a strict six-field case identity')
            for name in ('requests', 'responses', 'processed', 'duplicates'):
                (self.root/name/room).mkdir(mode=0o700)
        boot=Path('/proc/sys/kernel/random/boot_id')
        try:boot_id=boot.read_text().strip()
        except OSError:boot_id=None
        execution=dict(metadata or {},execution_topology='same_pod_kit_gui_cli_file_rpc')
        if self.coalesce_window is not None:
            execution.update(action_schedule='coalesce', coalesce_window_seconds=self.coalesce_window,
                             idle_physics='restore_native_rigid_and_joint_state_each_tick')
        atomic_json(self.root/'ready.json', dict(schema='videoicl-room-pool-rpc-v1',
            pid=os.getpid(),hostname=socket.gethostname(),host_boot_id=boot_id,
            rooms=rooms, metadata=execution,
            barrier_timeout_seconds=self.timeout,barrier_policy=self.barrier_policy,
            native_process_start_ticks=process_start_ticks(os.getpid()),
            physical_worlds_independently_paused=False,
            operations=['observe', 'action', 'seal', 'evaluate', 'close'],
            single_wave_no_replacement=True))

    def _active(self):
        return set(self.pool.controllers)-set(self.terminal)-set(self.failures)

    def _response(self, request, result=None, error=None, timing=None):
        target = self.root/'responses'/request['room_id']/(request['request_id']+'.json')
        if target.exists():
            return  # Immutable cached response: duplicate IDs do not execute twice.
        value = dict(request_id=request['request_id'], room_id=request['room_id'],
                     identity=self.rooms[request['room_id']]['identity'], ok=error is None)
        value['result' if error is None else 'error'] = deepcopy(error if error is not None else result)
        now=self.clock();accepted=self.request_started.pop((request['room_id'],request['request_id']),now)
        parts=dict(peer_wait_seconds=0.,native_execution_seconds=0.,render_queue_seconds=0.,render_seconds=0.)
        parts.update(timing or {})
        elapsed=max(0.,now-accepted)
        if timing is None:parts['native_execution_seconds']=elapsed
        value['timing']=dict(schema='videoicl-native-rpc-timing-v1',
            request_accepted_monotonic=accepted,response_ready_monotonic=now,
            total_service_seconds=elapsed,**parts)
        atomic_json(target, value)

    def _seal(self, room, reason):
        if room not in self.terminal:
            receipt = self.pool.seal(room)
            images = self.capture(room)
            self.terminal[room] = dict(room_id=room, identity=deepcopy(self.rooms[room]['identity']),
                receipt=receipt, images=deepcopy(images), reason=reason,
                fingerprints=deepcopy(self.rooms[room].get('fingerprints', {})))
            if self.feedback is not None:
                self.terminal[room]['robot_feedback'] = deepcopy(self.feedback(room))
            atomic_json(self.root/'terminal'/(room+'.private.json'), self.terminal[room])
        return deepcopy(self.terminal[room])

    def _fail_room(self, room, code):
        self.failures[room] = dict(kind='infrastructure_error', code=code, scored=False)
        if self.coalesce_window is None:
            try:
                self._seal(room, code)
            except Exception as exc:
                self.failures[room]['terminal_capture_error'] = type(exc).__name__
        atomic_json(self.root/'terminal'/(room+'.unscored.json'), self.failures[room])

    def _archive(self, path, request_id, room):
        destination = self.root/'processed'/room/(request_id+'.json')
        if destination.exists():
            destination = self.root/'duplicates'/room/(request_id+'-'+uuid.uuid4().hex+'.json')
        path.replace(destination)

    def _accept(self, path):
        room = path.parent.name
        request_id = path.stem
        if room not in self.rooms or not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise ValueError('RPC request filename is not a registered room/UUID')
        if path.stat().st_size > 65536:
            raise ValueError('RPC request exceeds the bounded JSON size')
        def reject_nonfinite(value):
            raise ValueError('Nonfinite RPC JSON is invalid')
        request = json.loads(path.read_text(), parse_constant=reject_nonfinite)
        if not isinstance(request, dict) or request.get('request_id') != request_id or request.get('room_id') != room:
            raise ValueError('RPC identity disagrees with request path')
        self._archive(path, request_id, room)
        if (self.root/'responses'/room/(request_id+'.json')).exists():
            return
        if room in self.pending and self.pending[room]['request']['request_id'] == request_id:
            return
        if 'identity' in request:
            expected = self.rooms[room]['identity']
            actual = request['identity']
            if not isinstance(actual, dict) or set(actual) != set(expected) or any(
                    type(actual[k]) is not type(v) or actual[k] != v for k, v in expected.items()):
                return self._response(request, error=dict(kind='request_error', code='identity_mismatch', scored=False))
        self.request_started[(room,request_id)]=self.clock()
        op = request.get('op')
        if op == 'close':
            for active in sorted(self._active()):
                self._fail_room(active, 'controller_closed_pool')
            for row in self.pending.values():
                self._response(row['request'], error=dict(kind='infrastructure_error', code='pool_closed', scored=False))
            self.pending.clear()
            self.stopped = True
            return self._response(request, dict(closed=True))
        if room in self.failures:
            return self._response(request, error=self.failures[room])
        if op == 'observe':
            capture_started=self.clock()
            images = self.terminal[room]['images'] if room in self.terminal else self.capture(room)
            result = dict(images=images, terminal=room in self.terminal,
                shared_tick=self.terminal[room]['receipt']['terminal_shared_tick'] if room in self.terminal else self.pool.physics_ticks)
            if self.feedback is not None:
                result['robot_feedback'] = self.terminal[room]['robot_feedback'] if room in self.terminal else self.feedback(room)
            return self._response(request, result,timing=dict(render_seconds=max(0.,self.clock()-capture_started)))
        if op == 'seal':
            if room in self.pending:
                pending = self.pending.pop(room)['request']
                self._response(pending, error=dict(kind='request_error', code='sealed_before_action', scored=False))
            return self._response(request, self._seal(room, request.get('reason', 'controller_seal')))
        if op == 'evaluate':
            if room not in self.terminal:
                return self._response(request, error=dict(kind='request_error', code='seal_required', scored=False))
            return self._response(request, self.terminal[room]['receipt']['native'])
        if op == 'action':
            if room in self.terminal:
                return self._response(request, error=dict(kind='request_error', code='episode_stopped', scored=False))
            if room in self.pending:
                return self._response(request, error=dict(kind='request_error', code='action_pending', scored=False))
            action = request.get('action')
            if not isinstance(action, dict) or set(action)-{'left', 'right', 'step_mm', 'rotation_deg'}:
                return self._response(request, error=dict(kind='request_error', code='invalid_action', scored=False))
            if 'action_index' in request and (type(request['action_index']) is not int or
                    request['action_index'] != self.pool.controllers[room].steps):
                return self._response(request, error=dict(kind='request_error', code='stale_action_index', scored=False))
            try:
                self.pool.controllers[room].validate_action(**action)
            except (TypeError, ValueError):
                return self._response(request, error=dict(kind='request_error', code='invalid_action', scored=False))
            self.pending[room] = dict(request=request, started=self.clock())
            return
        self._response(request, error=dict(kind='request_error', code='unknown_operation', scored=False))

    def poll_once(self):
        """Process requests and advance one scheduled batch."""
        if self.stopped:
            return False
        for path in sorted((self.root/'requests').glob('*/*.json')):
            try:
                self._accept(path)
            except Exception as exc:
                # Invalid controller transport is not native task failure.
                atomic_json(self.root/'transport-error.private.json', dict(
                    kind='infrastructure_error', path=str(path), error=repr(exc), scored=False))
                self.stopped = True
                return False
        active = self._active()
        if self.barrier_policy=='fail_after_timeout' and self.pending and active-set(self.pending):
            earliest = min(row['started'] for row in self.pending.values())
            if self.clock()-earliest >= self.timeout:
                for room in sorted(active-set(self.pending)):
                    self._fail_room(room, 'action_barrier_timeout')
                active = self._active()
        ready = set(self.pending) & active
        if ready and (ready == active or (self.coalesce_window is not None and
                self.clock() - min(self.pending[room]['started'] for room in ready) >= self.coalesce_window)):
            batch = {room: self.pending[room]['request']['action'] for room in ready}
            try:
                batch_started=self.clock()
                peer_wait={room:max(0.,batch_started-self.pending[room]['started']) for room in ready}
                receipts = self.pool.action_batch(batch)
                batch_finished=self.clock()
                images={};render_seconds={}
                for room in sorted(ready):
                    started=self.clock();images[room]=self.capture(room)
                    render_seconds[room]=max(0.,self.clock()-started)
                renders_finished=self.clock()
                feedback = {room: self.feedback(room) for room in ready} if self.feedback is not None else {}
                for room in sorted(ready):
                    request = self.pending[room]['request']
                    result = dict(receipt=receipts[room], images=images[room])
                    if self.feedback is not None:result['robot_feedback'] = feedback[room]
                    self._response(request, result,timing=dict(peer_wait_seconds=peer_wait[room],
                        native_execution_seconds=max(0.,batch_finished-batch_started),
                        render_seconds=render_seconds[room],
                        render_queue_seconds=max(0.,renders_finished-batch_finished-render_seconds[room])))
                    self.pending.pop(room)
            except Exception as exc:
                # A native tick may have partially executed: every affected
                # request stays unscored. Never replay this action batch.
                atomic_json(self.root/'native-error.private.json',dict(
                    kind='infrastructure_error',scored=False,rooms=sorted(active),
                    shared_tick=self.pool.physics_ticks,traceback=traceback.format_exc()))
                for room in sorted(active):
                    if room in self.terminal:
                        continue
                    self._fail_room(room, 'native_action_batch_error')
                    row = self.pending.pop(room, None)
                    if row is not None:
                        self._response(row['request'], error=dict(self.failures[room], error_class=type(exc).__name__))
                self.stopped = True
        if not self._active():
            self.stopped = True
            atomic_json(self.root/'all-rooms-terminal.json', dict(
                shared_tick=self.pool.physics_ticks, terminal_rooms=sorted(self.terminal),
                unscored_rooms=sorted(self.failures), replacement_started=False))
        return not self.stopped
