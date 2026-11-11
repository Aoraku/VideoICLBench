"""Private CPU-side adapter for a native single-wave room pool.

Only the trusted environment process reads this transport. Model tools see the
assigned GUI. Requests are sent once. Model pools wait without a wall deadline;
legacy probe timeouts and native process death are infrastructure failure, never
permission to replay a movement.
"""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import socket
import threading
import time
import uuid

from .episode import IDENTITY_FIELDS


def exact_identity(actual, expected):
    return (isinstance(actual, dict) and set(actual) == set(IDENTITY_FIELDS)
            and all(type(actual[k]) is type(expected[k]) and actual[k] == expected[k]
                    for k in IDENTITY_FIELDS))


def native_response_timeout(barrier_seconds, room_count, capture_passes=64):
    """Conservative queue allowance, not a measured render throughput claim.

    A request may wait for every room's serial render after the action barrier.
    Reserve two minutes per room at 64 passes until native probes calibrate this.
    """
    if (type(barrier_seconds) not in (int, float) or not math.isfinite(barrier_seconds)
            or barrier_seconds <= 0 or type(room_count) is not int or room_count < 1
            or type(capture_passes) is not int or not 1 <= capture_passes <= 128):
        raise ValueError('Invalid native queue timeout inputs')
    return barrier_seconds + max(120., room_count * 120. * capture_passes / 64.)


def native_process_alive(pid, start_ticks):
    """Check Linux PID incarnation, including zombie termination, not age."""
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return fields[0] not in ('Z','X') and int(fields[19])==start_ticks
    except (OSError,ValueError,IndexError):
        return False


class NativePoolProxy:
    def __init__(self, root, room_id, identity, *, timeout_seconds=None):
        self.root = Path(root).resolve(strict=True)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', room_id):
            raise ValueError('Invalid native room ID')
        ready = json.loads((self.root / 'ready.json').read_text())
        if ready.get('schema') != 'videoicl-room-pool-rpc-v1':
            raise ValueError('Unsupported native pool transport')
        if ready.get('hostname') and ready['hostname'] != socket.gethostname():
            raise ValueError('File RPC requires Kit, GUI and CLI in the same pod; cross-pod shared-filesystem polling is unsupported')
        self.native_hostname = ready.get('hostname')
        self.room_id, self.identity = room_id, dict(identity)
        self.room = ready.get('rooms', {}).get(room_id)
        if not self.room or not exact_identity(self.room.get('identity'), self.identity):
            raise ValueError('Native pool room identity mismatch')
        self.barrier_policy=ready.get('barrier_policy','fail_after_timeout')
        if self.barrier_policy not in ('wait','fail_after_timeout'):
            raise ValueError('Unknown native action barrier policy')
        self.native_pid,self.native_start_ticks=ready.get('pid'),ready.get('native_process_start_ticks')
        if self.barrier_policy=='wait' and (type(self.native_pid) is not int or self.native_pid<=0 or
                type(self.native_start_ticks) is not int or self.native_start_ticks<=0):
            raise ValueError('Indefinite native wait requires a PID incarnation')
        self.timeout = timeout_seconds if timeout_seconds is not None else native_response_timeout(
            ready['barrier_timeout_seconds'], len(ready['rooms']),
            ready.get('metadata', {}).get('capture_passes', 64))
        if self.barrier_policy=='wait':self.timeout=None
        if self.timeout is not None and (type(self.timeout) not in (int, float) or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ValueError('Finite positive native response timeout required')
        self.barrier_timeout_seconds = ready['barrier_timeout_seconds']
        self.images, self.feedback, self.terminal = None, None, None
        self.sensor_depth = {}
        self.steps, self.failed = 0, False
        self.lock = threading.RLock()
        # One immutable tuple gives budget readers a consistent lock-free view.
        self._infrastructure_clock=(0.,None)
        self._infrastructure_intervals=((),None)
        self.last_native_timing=None
        self.last_infrastructure_request=None

    def infrastructure_wait_seconds(self):
        total,started=self._infrastructure_clock
        return total+(max(0.,time.monotonic()-started) if started is not None else 0.)

    def infrastructure_wait_intervals(self, now=None):
        """Same-host monotonic service intervals, including the in-flight RPC."""
        completed, started = self._infrastructure_intervals
        now = time.monotonic() if now is None else now
        return [list(pair) for pair in completed] + ([[started, max(started, now)]] if started is not None else [])

    def _failure(self):
        if self.failed or (self.root / 'terminal' / (self.room_id + '.unscored.json')).exists():
            self.failed = True
            raise RuntimeError('Native room is infrastructure-unscored')
        if (self.root / 'transport-error.private.json').exists():
            self.failed = True
            raise RuntimeError('Native pool transport failed')

    def _read_terminal(self):
        self._failure()
        path = self.root / 'terminal' / (self.room_id + '.private.json')
        if path.exists():
            self.terminal = json.loads(path.read_text())
            if (self.terminal.get('room_id') != self.room_id
                    or not exact_identity(self.terminal.get('identity'), self.identity)):
                self.failed = True
                raise RuntimeError('Native terminal room identity mismatch')
            self._cache(self.terminal)
        return self.terminal

    def _cache(self, result):
        if isinstance(result, dict):
            if 'images' in result:
                self.images = deepcopy(result['images'])
            if 'robot_feedback' in result:
                self.feedback = deepcopy(result['robot_feedback'])
                self.sensor_depth = self.feedback.pop('_sensor_depth', {})
                from .sensor_depth import depth_packet_metadata
                if self.sensor_depth:
                    self.feedback['depth_sensors'] = {k:depth_packet_metadata(v) for k,v in self.sensor_depth.items()}

    def _request(self, op, **fields):
        self.last_native_timing=None
        started=time.monotonic();total,_=self._infrastructure_clock
        self._infrastructure_clock=(total,started)
        completed,_=self._infrastructure_intervals
        self._infrastructure_intervals=(completed,started)
        try:
            return self._request_once(op,**fields)
        finally:
            ended=time.monotonic()
            duration=max(0.,ended-started)
            self._infrastructure_clock=(total+duration,None)
            self._infrastructure_intervals=(completed+((started,ended),),None)
            self.last_infrastructure_request=dict(operation=op,service_seconds=duration,
                cumulative_seconds=total+duration,native_timing=deepcopy(self.last_native_timing))

    def _request_once(self, op, **fields):
        self._failure()
        self.last_native_timing=None
        if self.barrier_policy=='wait' and not native_process_alive(self.native_pid,self.native_start_ticks):
            self.failed=True
            raise RuntimeError('Native Kit process exited or its PID was reused; do not replay this request')
        identifier = uuid.uuid4().hex
        body = dict(request_id=identifier, room_id=self.room_id, identity=self.identity, op=op, **fields)
        request = self.root / 'requests' / self.room_id / (identifier + '.json')
        temporary = request.with_suffix('.tmp')
        raw = json.dumps(body, allow_nan=False).encode()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        temporary.replace(request)
        response = self.root / 'responses' / self.room_id / request.name
        deadline = None if self.timeout is None else time.monotonic()+self.timeout
        while not response.exists():
            self._failure()
            if self.barrier_policy=='wait' and not native_process_alive(self.native_pid,self.native_start_ticks):
                # The last response may be atomically published between the
                # loop's file check and Kit's normal terminal exit.
                if response.exists():break
                self.failed=True
                raise RuntimeError('Native Kit process exited or its PID was reused; do not replay this request')
            if deadline is not None and time.monotonic() >= deadline:
                self.failed = True
                raise RuntimeError('Native pool response timed out; do not replay this request')
            time.sleep(.02)
        value = json.loads(response.read_text())
        if (value.get('request_id') != identifier or value.get('room_id') != self.room_id
                or not exact_identity(value.get('identity'), self.identity)):
            self.failed = True
            raise RuntimeError('Native pool response identity mismatch')
        if value.get('ok') is not True:
            self.failed = True
            raise RuntimeError('Native pool did not confirm the requested operation')
        timing=value.get('timing')
        if timing is not None:
            if (not isinstance(timing,dict) or timing.get('schema')!='videoicl-native-rpc-timing-v1'
                    or any(type(timing.get(k)) not in (int,float) or not math.isfinite(timing[k]) or timing[k]<0
                           for k in ('total_service_seconds','peer_wait_seconds','native_execution_seconds','render_queue_seconds','render_seconds'))):
                self.failed=True
                raise RuntimeError('Invalid native private timing evidence')
            self.last_native_timing=deepcopy(timing)
        self._cache(value.get('result'))
        return value['result']

    def observe(self):
        with self.lock:
            if not self._read_terminal():
                self._request('observe')
            if not isinstance(self.images, dict) or set(self.images) != {'head', 'left_wrist', 'right_wrist'}:
                raise RuntimeError('Native pool observation is incomplete')
            return deepcopy(self.images)

    def rgb_measurement_snapshot(self):
        """Cached camera pixels and same-capture calibration; no RPC or physics."""
        with self.lock:
            return dict(images=deepcopy(self.images or {}),
                        camera_calibration=deepcopy((self.feedback or {}).get('camera_calibration', {})),
                        observation_tick=(self.feedback or {}).get('observation_tick'))

    def sensor_depth_snapshot(self):
        with self.lock:
            return dict(self.rgb_measurement_snapshot(), depth=deepcopy(self.sensor_depth))

    def public_feedback(self):
        # The worker whitelists robot proprioception; never return its private
        # ready manifest, physical objects, evaluator or terminal receipt.
        return deepcopy(self.feedback) if self.feedback is not None else {}

    def action(self, **action):
        with self.lock:
            if self._read_terminal():
                raise RuntimeError('Native room is sealed')
            value = self._request('action', action=action, action_index=self.steps)
            self.steps += 1
            return deepcopy(value['receipt'])

    def seal(self):
        with self.lock:
            if not self._read_terminal():
                self.terminal = self._request('seal', reason='gui_episode_terminal')
            if (self.terminal.get('room_id') != self.room_id
                    or not exact_identity(self.terminal.get('identity'), self.identity)):
                self.failed = True
                raise RuntimeError('Native terminal room identity mismatch')
            self._failure()

    def evaluate(self):
        with self.lock:
            if not self._read_terminal():
                raise RuntimeError('Seal the native room before scoring')
            receipt = self.terminal['receipt']
            native = deepcopy(receipt['native'])
            for source, target in [('terminal_controller_tick', 'terminal_physics_step'),
                                   ('terminal_shared_tick', 'terminal_shared_tick')]:
                if type(receipt.get(source)) is int:
                    native.setdefault(target, receipt[source])
            return native

    def close(self):
        # A room closing must never terminate other rooms in this pool. The
        # native worker exits itself when every room is sealed or unscored.
        return None
