"""Opt-in, episode-local program macros over the existing visible GUI tools.

This is a bounded Python subset, not a host Python shell. It cannot read files,
network, controller state or simulator objects. Browser transport is unchanged.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from mcp.types import CallToolResult, TextContent
from .embodied_program_runtime import EmbodiedProgramRuntime, CallbackRejected, CallbackUnknown, CallbackPartial
from .embodied_program_geometry import project_pixel

PROGRAM_VERSION = 'episode-local-gui-program-simulator-depth-v4'
PROGRAM_INSTRUCTIONS = '''
You also have an episode-local program(source, submission_id) tool. It interprets
bounded Python syntax: assignments, JSON values, arithmetic, if, bounded for/range,
functions and return. No imports, attributes/methods, filesystem, network, shell,
exceptions, classes, or arbitrary Python execution. Use print(value), len, range,
and memory["key"] = value. Functions/variables persist in the current tool process;
only JSON memory and submission receipts survive a reconnect. No prior episode
memory, task recipes, development practice, resets or cross-episode skill transfer.

Callbacks: observe() returns latest GUI metadata and screenshot; act(inputs) uses
that latest GUI frame and performs screenshot-coordinate clicks/keys/text exactly
like the direct act tool. A program may contain at most ONE act call, itself with
1–12 GUI inputs and at most one physical Commit. Define reusable button/edit
functions to batch what is already decided; after the action, return to inspect
its screenshot before choosing another motion. There is no programmatic visual
recognition in this interpreter. Do not loop robot motions without inspecting
images. done/giveup remain separate tools requiring your latest observed frame.
For video conditions demo_info(), demo_frame(seconds), demo_frames([seconds]) are
available. Total callbacks per submission <=8; at most12 demo frames per program.
Program output contains the last GUI screenshot and requested demo frames.

Use a new unique submission_id for new code. Repeating the SAME id and source
retrieves its recorded receipt without executing again; cached screenshots are
not current observations. If interrupted or outcome unknown, do not resubmit
with a new id or replay earlier inputs. Obtain a fresh observe after recovery.
Already accepted GUI work continues if a client stops waiting.

observe() returns public_observation with native_frame_id, robot_feedback,
action_schema and observation_contract alongside the GUI image. Read those
structured records directly; you do not need to expand GUI text panels.
depth_points(camera, pixels) queries selected native-image [row, col] pixels
for the current GUI frame. It returns structured depth measurements with
camera_calibration; it does not move the robot or fetch a dense map by default.
backproject(measurement) or project_pixel(measurement["camera_calibration"], measurement)
performs pure arithmetic on explicitly supplied same-frame public records.
Only simulator depth measurements are accepted; no estimated-depth fallback is
available. Invalid depth, stale frames, missing transforms or calibration must not be
replaced by guesses. Task coordinates and world coordinates differ unless an
explicit public transform says otherwise. Hidden object poses, semantic masks and
evaluator state remain unavailable. A surface point is not a grasp target.
Store useful observations and reusable code only within this current episode.
Use memory["working_note"] for a compact current objective, frame-referenced facts,
uncertain hypotheses, requested/actual motion, failed approach and next check.
Keep observed facts separate from hypotheses; revise stale facts after actions.
Before compaction, preserve this note without duplicating the full image/history
stream. Reconnect restores JSON memory, not an unverified current world state.
A fresh observe and its image are required before acting on remembered geometry.
'''


def _text(value):
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(value, ensure_ascii=False))])


class ProgramGuiSession:
    def __init__(self, browser, config):
        self.browser = browser
        self.lock = threading.Lock()
        self.frame = None
        self.observation_generation = 0
        self.gui_images = []
        self.demo_images = []
        self.last_observation = None
        self.act_calls = 0
        self.demo_count = 0
        identity = config.get('program_episode_identity')
        fields = ('run_id', 'task_id', 'variant', 'seed', 'suite', 'epoch')
        if not isinstance(identity, dict) or any(k not in identity for k in fields):
            raise ValueError('Program mode requires the full episode identity')
        identity = {k: identity[k] for k in fields}
        self.episode_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.directory = Path(config['output_dir']) / 'program'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.owner_path = self.directory / 'owner'
        self.owner_nonce = uuid.uuid4().hex
        try:
            self.owner_path.mkdir(mode=0o700)
        except FileExistsError:
            raise ValueError('A program owner exists; wait for drain or externally reconcile. Never steal its lease.') from None
        (self.owner_path / 'identity.private.json').write_text(json.dumps(dict(
            episode_id=self.episode_id, nonce=self.owner_nonce, pid=os.getpid())))
        self.closed = False
        snapshot = None
        self.checkpoint_sequence = 0
        try:
            records = list(self.directory.glob('submission-*.private.json'))
            if records:
                ledger, latest, seen_sequences = {}, None, set()
                for record in records:
                    item = json.loads(record.read_text())
                    if item['episode_id'] != self.episode_id:
                        raise ValueError('Submission episode mismatch')
                    sequence = item['sequence']
                    if type(sequence) is not int or sequence < 1 or sequence in seen_sequences:
                        raise ValueError('Checkpoint sequence is invalid or ambiguous')
                    seen_sequences.add(sequence)
                    ledger[item['submission_id']] = item['submission']
                    if latest is None or sequence > latest['sequence']:
                        latest = item
                self.checkpoint_sequence = latest['sequence']
                snapshot = {k: latest[k] for k in ('schema', 'episode_id', 'memory', 'halted')}
                snapshot['submissions'] = ledger
            callbacks = dict(observe=self._observe, act=self._act, project_pixel=self._project_pixel,
                             backproject=self._backproject, depth_points=self._depth_points)
            if config['condition'] in ('real', 'sim'):
                callbacks.update(demo_info=self._demo_info, demo_frame=self._demo_frame, demo_frames=self._demo_frames)
            self.runtime = EmbodiedProgramRuntime(self.episode_id, callbacks,
                checkpoint_delta=self._checkpoint, snapshot=snapshot)
        except BaseException:
            self._release_owner()
            raise

    def _release_owner(self):
        record = self.owner_path / 'identity.private.json'
        if json.loads(record.read_text())['nonce'] != self.owner_nonce:
            raise RuntimeError('Program owner changed; refusing to remove its lease')
        record.unlink()
        self.owner_path.rmdir()
        self.closed = True

    def close(self):
        # Wait for accepted work; never release the owner while a program runs.
        with self.lock:
            if not self.closed:
                if self.runtime.halted:
                    # Preserve the owner marker when action/persistence is unknown.
                    # Reopening requires explicit external reconciliation.
                    self.closed = True
                else:
                    self._release_owner()

    def require_fresh_observation(self):
        self.observation_generation += 1
        self.frame = None
        self.last_observation = None
        mark = getattr(self.browser, 'require_fresh_observation', None)
        if mark is not None:
            mark()

    def _depth_points(self, camera, pixels):
        if self.frame is None or (self.last_observation or {}).get('frame_id') != self.frame:
            raise CallbackRejected('A fresh GUI observe is required before depth_points')
        try:
            result = self.browser.depth_points(self.frame, camera, pixels)
        except ValueError as exc:
            raise CallbackRejected(str(exc)) from None
        except Exception:
            # A read-only query cannot leave an unacknowledged robot action.
            return {'valid': False, 'reason': 'depth_query_unavailable', 'physical_action': False}
        expected = (self.last_observation or {}).get('public_observation', {}).get('native_frame_id')
        if not isinstance(result, dict) or result.get('frame_id') != self.frame or (
                expected is not None and result.get('native_frame_id') != expected):
            raise CallbackRejected('Depth response does not match the observed frame')
        for measurement in result.get('measurements', []):
            if isinstance(measurement, dict) and measurement.get('valid') is True and measurement.get('measurement_source') != 'simulator_depth':
                return {'valid': False, 'reason': 'simulator_depth_required', 'physical_action': False}
        return result

    def _project_pixel(self, calibration, measurement):
        if self.frame is None or (self.last_observation or {}).get('frame_id') != self.frame:
            return {'valid': False, 'reason': 'fresh_observation_required'}
        expected = (self.last_observation or {}).get('public_observation', {}).get('native_frame_id')
        if not isinstance(measurement, dict) or expected is None or measurement.get('frame_id') != expected:
            return {'valid': False, 'reason': 'stale_public_measurement'}
        if measurement.get('measurement_source') != 'simulator_depth':
            return {'valid': False, 'reason': 'simulator_depth_required'}
        return project_pixel(calibration, measurement)

    def _backproject(self, measurement):
        if not isinstance(measurement, dict):
            return {'valid': False, 'reason': 'explicit_simulator_measurement_required'}
        return self._project_pixel(measurement.get('camera_calibration'), measurement)


    def _atomic_json(self, destination, snapshot):
        temporary = self.directory / ('.checkpoint-' + uuid.uuid4().hex)
        try:
            with open(temporary, 'x', encoding='utf-8') as handle:
                os.chmod(temporary, 0o600)
                json.dump(snapshot, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)

    def _checkpoint(self, delta):
        # One atomic envelope contains the current submission AND memory. No
        # split checkpoint can combine completed work with an older memory.
        submission_id = delta['submission_id']
        name = hashlib.sha256(submission_id.encode()).hexdigest()
        self.checkpoint_sequence += 1
        self._atomic_json(self.directory / ('submission-' + name + '.private.json'),
                          dict(delta, sequence=self.checkpoint_sequence))

    def _capture(self, result, *, demo=False):
        if not isinstance(result, CallToolResult):
            return result
        records = []
        images = []
        for content in result.content:
            if content.type == 'image':
                images.append(content)
            elif content.type == 'text':
                try:
                    item = json.loads(content.text)
                except (ValueError, TypeError):
                    item = {'text': content.text[:8192]}
                records.append(item)
                if not demo and isinstance(item, dict):
                    if item.get('status') in {'operation_pending', 'fresh_observation_required'}:
                        self.frame = None
                        self.last_observation = None
                        self.gui_images = []
                        raise CallbackRejected('GUI requires fresh observation; no input accepted')
                    if 'frame_id' in item:
                        self.frame = item['frame_id']
                        self.last_observation = item
        if result.isError:
            self.frame = None
            raise CallbackUnknown('GUI returned an error; do not replay inputs')
        if demo:
            self.demo_images.extend(images)
        else:
            self.gui_images = images
        return records[0] if len(records) == 1 else {'records': records}

    def _call(self, method, *args):
        try:
            return self._capture(method(*args))
        except (CallbackUnknown, CallbackRejected):
            raise
        except ValueError as exc:
            self.frame = None
            self.last_observation = None
            self.gui_images = []
            raise CallbackPartial('Input sequence stopped; prior inputs may have executed. Observe before further action. ' + str(exc)) from None
        except Exception:
            self.frame = None
            self.last_observation = None
            self.gui_images = []
            raise CallbackUnknown('GUI transport outcome unknown; do not replay inputs') from None

    def _observe(self):
        return self._call(self.browser.observe)

    def _act(self, inputs):
        if self.act_calls >= 1:
            raise CallbackRejected('Return to the model to inspect the new image before another act')
        if self.frame is None:
            raise CallbackRejected('A fresh GUI observe is required before act')
        self.act_calls += 1
        return self._call(self.browser.act, self.frame, inputs)

    def _demo_info(self):
        self.browser.check()
        return self.browser.demo_info()

    def _demo_frame(self, seconds):
        if self.demo_count >= 12:
            raise CallbackRejected('At most twelve demo frames per program')
        self.demo_count += 1
        self.browser.check()
        return self._capture(self.browser.demo_frame(seconds), demo=True)

    def _demo_frames(self, seconds):
        if not isinstance(seconds, list) or not 1 <= len(seconds) <= 12 or self.demo_count + len(seconds) > 12:
            raise CallbackRejected('Choose one to twelve timestamps total')
        return [self._demo_frame(t) for t in sorted(seconds)]

    def direct(self, method, *args):
        # Serialize direct calls with programs, rejecting overlap instead of
        # enqueueing an action whose source image can become stale while waiting.
        if not self.lock.acquire(blocking=False):
            return _text(dict(status='operation_pending', accepted=False, queued=False))
        generation = self.observation_generation
        try:
            if self.closed:
                raise ValueError('Program owner has closed')
            result = method(*args)
            if isinstance(result, CallToolResult):
                # Direct demo pictures must never replace the GUI frame.
                name = getattr(method, '__name__', '')
                if name in {'observe', 'act', 'terminal'}:
                    try:
                        self._capture(result)
                    except CallbackRejected:
                        pass
            return result
        except BaseException:
            self.frame = None
            self.last_observation = None
            raise
        finally:
            if generation != self.observation_generation:
                self.frame = None
                self.last_observation = None
            self.lock.release()

    def execute(self, source, submission_id):
        if not self.lock.acquire(blocking=False):
            return _text(dict(status='operation_pending', accepted=False, queued=False,
                              instruction='Wait for the original program; do not replay it'))
        generation = self.observation_generation
        try:
            if self.closed:
                raise ValueError('Program owner has closed')
            self.gui_images, self.demo_images = [], []
            self.act_calls = self.demo_count = 0
            cached = submission_id in self.runtime.ledger if isinstance(submission_id, str) else False
            receipt = self.runtime.execute(source, submission_id)
            receipt['cached_receipt'] = cached
            if cached:
                receipt['current_observation'] = False
            # Source is private evidence only; it is never loaded into another episode.
            name = hashlib.sha256(submission_id.encode()).hexdigest()
            artifact = self.directory / (name + '.private.json')
            if not artifact.exists():
                with open(artifact, 'x', encoding='utf-8') as handle:
                    os.chmod(artifact, 0o600)
                    json.dump({'source': source, 'receipt': receipt}, handle, ensure_ascii=False)
            receipt['memory_keys'] = list(receipt.pop('memory', {}))[:128]
            if not cached and self.gui_images:
                receipt['observation'] = self.last_observation
                if receipt['result'] == self.last_observation:
                    receipt['result'] = {'observation_returned': True}
            receipt['callback_calls'] = [{k: row[k] for k in ('name', 'status', 'error') if k in row}
                                         for row in receipt['callback_calls']]
            return CallToolResult(content=[*_text(receipt).content,
                *([] if cached else self.gui_images + self.demo_images)])
        finally:
            if generation != self.observation_generation:
                self.frame = None
                self.last_observation = None
            self.lock.release()
