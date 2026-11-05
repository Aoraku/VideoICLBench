"""RoboDawn decision commands executed through the original public GUI.

The model chooses the complete public control selection for one Commit. This
adapter performs its visible widget edits and one original ``act``/Commit, then
returns the new observation before another model decision. No task recipes,
object-state reads, success checks, home motions, or action retries exist here.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .embodied_public_observation import public_observation, public_depth_measurement
from .robodawn_tools import GUIBridge, ToolResult

TERMINAL = {'done', 'give_up', 'giveup', 'finished', 'budget_exhausted', 'budget_paused',
            'stopped', 'sealed', 'closed', 'aborted', 'submitted'}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _payload(result):
    for block in result.text_blocks:
        try:
            value = json.loads(block['text'])
        except (ValueError, KeyError):
            continue
        if isinstance(value, dict):
            return value
    return {}


class TurnExecutor:
    def __init__(self, computer_config, *, bridge=None, demo_frame_count=0,
                 demo_timestamps=None, on_intent=None, on_receipt=None):
        self.config = dict(computer_config)
        self.bridge = bridge if bridge is not None else GUIBridge(self.config)
        self.owns_bridge = bridge is None
        if type(demo_frame_count) is not int or not 0 <= demo_frame_count <= 12:
            raise ValueError('Demo frame count must be 0..12; zero means inspect on demand')
        self.demo_frame_count = demo_frame_count
        self.demo_timestamps = deepcopy(demo_timestamps)
        self.on_intent = on_intent or (lambda record: None)
        self.on_receipt = on_receipt or (lambda record: None)
        self.observation = None
        self.initialized = False
        self.executed_decision_ids = set()
        self.demo_info = None

    def _demo_anchors(self, seconds):
        """Read the assigned video at chosen times without touching the live GUI."""
        info = self.demo_info
        if not info or self.config.get('condition') == 'text_rule':
            raise ValueError('This input condition has no assigned demonstration')
        if not isinstance(seconds, list) or not 1 <= len(seconds) <= 12 or any(
                not _number(t) or not 0 <= t < info['duration_seconds'] for t in seconds):
            raise ValueError('Choose one to twelve finite timestamps inside the assigned video')
        path = Path(self.config['demo_video'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['source_sha256']:
            raise ValueError('Assigned demonstration source changed; do not substitute a video')
        ordered = sorted(seconds)
        frames = self.bridge.call_tool('demo_frames', dict(seconds=ordered))
        if frames.is_error or len(frames.images) != len(ordered) or len(frames.image_sources) != len(ordered):
            raise ValueError('All requested assigned-video frames must be returned')
        anchors = []
        for picture, source, at in zip(frames.images, frames.image_sources, ordered):
            if source.get('kind') != 'demo' or source.get('demo_seconds', at) != at:
                raise ValueError('Demonstration image provenance or timestamp mismatch')
            data = base64.b64decode(picture['image_url'].split(',', 1)[1], validate=True)
            anchors.append(dict(image_item=deepcopy(picture), sha256=hashlib.sha256(data).hexdigest(),
                seconds=at, source_sha256=info['source_sha256'], kind='demo'))
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['source_sha256']:
            raise ValueError('Assigned demonstration changed while reading its frames')
        return anchors

    def _observation(self, result):
        payload = _payload(result)
        if result.is_error or not isinstance(payload.get('frame_id'), str):
            raise ValueError('Actual GUI observation unavailable; preserve the operation')
        raw = payload.get('public_observation')
        status = payload.get('episode_status')
        if isinstance(raw, dict) and raw.get('native_frame_id'):
            clean = public_observation(dict(frame_id=raw['native_frame_id'], state=raw))
        elif status in TERMINAL:
            # The stop GUI can be acknowledged while its final camera/state
            # snapshot is unavailable. Keep the actual terminal image/status;
            # never relabel the preceding robot state as a fresh measurement.
            clean = None
        else:
            raise ValueError('Synchronized public robot observation unavailable')
        sources = result.image_sources
        images = [image for image, source in zip(result.images, sources) if source.get('kind') == 'gui']
        if len(sources) != len(result.images) or len(images) != 1:
            raise ValueError('Exactly one provenance-verified actual GUI image is required')
        image = deepcopy(images[0])
        data = base64.b64decode(image['image_url'].split(',', 1)[1], validate=True)
        count = self.bridge.public_action_count()
        return dict(frame_id=payload['frame_id'], public_observation=clean,
            camera_views=deepcopy(payload.get('camera_views', {})), image=image,
            image_sha256=hashlib.sha256(data).hexdigest(), width=payload.get('width'),
            height=payload.get('height'), episode_status=status,
            step=count, max_robot_actions=payload.get('max_robot_actions'),
            action_batch=deepcopy(payload.get('action_batch')))

    def initialize(self):
        if self.initialized:
            raise ValueError('Executor initialization is once per actual GUI owner')
        result = self.bridge.call_tool('observe', {})
        self.observation = self._observation(result)
        anchors = []
        if self.config.get('condition') != 'text_rule':
            path = self.config.get('demo_video')
            if not path:
                raise ValueError('Video condition requires the originally assigned demonstration')
            source_sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            info_result = self.bridge.call_tool('demo_info', {})
            info = _payload(info_result)
            duration = info.get('duration_seconds')
            if info_result.is_error or info.get('available') is not True or not _number(duration) or duration <= 0:
                raise ValueError('Assigned demonstration metadata is unavailable')
            self.demo_info = dict(available=True, source_sha256=source_sha,
                duration_seconds=duration, on_demand=True)
            for key in ('fps', 'frame_count'):
                if _number(info.get(key)) and info[key] > 0:
                    self.demo_info[key] = info[key]
            if self.demo_timestamps is None:
                fps = info.get('fps')
                endpoint = max(0., duration - (1. / fps if _number(fps) and fps > 0 else .05))
                seconds = [endpoint * i / max(1, self.demo_frame_count - 1) for i in range(self.demo_frame_count)]
            else:
                seconds = deepcopy(self.demo_timestamps)
            if self.demo_timestamps is not None or self.demo_frame_count:
                anchors = self._demo_anchors(seconds)
        self.initialized = True
        return dict(observation=deepcopy(self.observation), demo_anchors=anchors,
            demo_info=deepcopy(self.demo_info))

    def _validate(self, commands):
        if not self.initialized or not self.observation:
            raise ValueError('Initialize the original GUI before a decision')
        if not isinstance(commands, list) or len(commands) != 1 or not isinstance(commands[0], dict):
            raise ValueError('A decision contains exactly one command; select the controls, then Commit once')
        kinds = {c.get('type') for c in commands}
        if kinds not in ({'action'}, {'action_batch'}, {'depth_points'}, {'demo_frames'}, {'done'}, {'giveup'}):
            raise ValueError('Physical actions, sensor-only queries, and terminal decisions must be separate turns')
        schema = (self.observation.get('public_observation') or {}).get('action_schema', {})
        checked = deepcopy(commands)
        for command in checked:
            kind = command['type']
            if kind == 'action_batch':
                if set(command)!={'type','actions'} or not isinstance(command['actions'],list) or not 1<=len(command['actions'])<=24:
                    raise ValueError('One visible Commit requires one to twenty-four ordered action pairs')
                step,limit=self.observation.get('step'),self.observation.get('max_robot_actions')
                if type(step)is int and type(limit)is int and len(command['actions'])>max(0,limit-step):
                    raise ValueError('Batch exceeds the visible remaining physical-action budget; choose fewer pairs before Commit')
                normalized=[]
                for pair in command['actions']:
                    if not isinstance(pair,dict) or set(pair)!={'left','right','step_mm','rotation_deg'}:
                        raise ValueError('Each batch item is one complete public action pair')
                    one=self._validate([dict(type='action',**pair)])[0]
                    one.pop('type');normalized.append(one)
                command['actions']=normalized
            elif kind == 'action':
                if set(command) != {'type', 'left', 'right', 'step_mm', 'rotation_deg'}:
                    raise ValueError('Action needs explicit public pair tokens and both public parameters')
                tokens = schema.get('tokens', [])
                for side in ('left', 'right'):
                    token = command[side]
                    if not isinstance(token, str):
                        raise ValueError('Action token must be text')
                    if token not in tokens and 'MV_' + token in tokens:
                        token = 'MV_' + token
                    if token not in tokens:
                        raise ValueError('Action token is not available in this actual public GUI')
                    command[side] = token
                for name in ('step_mm', 'rotation_deg'):
                    bounds = schema.get(name, {})
                    low = bounds.get('minimum', bounds.get('min'))
                    high = bounds.get('maximum', bounds.get('max'))
                    if not all(_number(x) for x in (command[name], low, high)) or not low <= command[name] <= high:
                        raise ValueError('Action parameter is outside this GUI public bounds: ' + name)
            elif kind == 'depth_points':
                if set(command) != {'type', 'camera', 'pixels'} or command['camera'] not in ('head', 'left_wrist', 'right_wrist'):
                    raise ValueError('Sensor command requires a public camera and native pixels')
                pixels = command['pixels']
                if not isinstance(pixels, list) or not 1 <= len(pixels) <= 16 or any(
                        not isinstance(point, list) or len(point) != 2 or not all(_number(x) for x in point) for point in pixels):
                    raise ValueError('Depth points must be one to sixteen finite native [row,col] pixels')
            elif kind == 'demo_frames':
                if set(command) != {'type', 'seconds'} or not self.demo_info:
                    raise ValueError('Only video conditions can inspect their assigned demonstration')
                seconds = command['seconds']
                if not isinstance(seconds, list) or not 1 <= len(seconds) <= 12 or any(
                        not _number(t) or not 0 <= t < self.demo_info['duration_seconds'] for t in seconds):
                    raise ValueError('Demo timestamps must be inside the originally assigned video')
            else:
                field = 'summary' if kind == 'done' else 'reason'
                if set(command) != {'type', field} or not isinstance(command[field], str) or len(command[field]) > 1500:
                    raise ValueError('Terminal command needs a bounded model-written explanation')
        return checked

    def execute(self, commands, *, decision_id):
        checked = self._validate(commands)
        if not isinstance(decision_id, str) or not decision_id or decision_id in self.executed_decision_ids:
            raise ValueError('Decision identities are one-shot; never replay an accepted decision')
        self.executed_decision_ids.add(decision_id)
        if checked[0]['type']=='action_batch':
            return self._execute_batch(checked[0],commands[0],decision_id)
        outcome = dict(results=[], observation=deepcopy(self.observation), physical_commits=0,physical_action_count=0,
            pending=False, uncertain=False, terminal=False)
        for index, command in enumerate(checked):
            record = dict(decision_id=decision_id, command_index=index, command=deepcopy(command),
                requested_command=deepcopy(commands[index]),
                frame_id=self.observation['frame_id'], physical_commit=command['type'] == 'action')
            if command['type'] == 'demo_frames':
                self.on_intent(deepcopy(record))
                anchors = self._demo_anchors(command['seconds'])
                row = dict(command=deepcopy(command), ok=True, physical_commit=False,
                    frame_id=self.observation['frame_id'],
                    demo_seconds=[a['seconds'] for a in anchors],
                    source_sha256=self.demo_info['source_sha256'])
                outcome['results'].append(row)
                outcome['demo_frames'] = anchors
                outcome['terminal'] = self.observation.get('episode_status') in TERMINAL
                self.on_receipt(dict(**record, result=deepcopy(row), pending=False, uncertain=False))
                continue
            before = self.observation.get('step')
            if command['type'] == 'action':
                # Public controls are located before the write-ahead intent; no mutation occurs here.
                inputs = self.bridge.public_action_inputs(command)
                name, args = 'act', dict(frame_id=self.observation['frame_id'], inputs=inputs)
            elif command['type'] == 'depth_points':
                name, args = 'depth_points', dict(frame_id=self.observation['frame_id'],
                    camera=command['camera'], pixels=command['pixels'])
            else:
                name = command['type']
                args = dict(frame_id=self.observation['frame_id'])
                field = 'summary' if name == 'done' else 'reason'
                args[field] = command[field]
            self.on_intent(deepcopy(record))
            result = self.bridge.call_tool(name, args)
            payload = _payload(result)
            pending = payload.get('status') in ('operation_pending', 'fresh_observation_required')
            uncertain = result.is_error or pending or 'transport failed' in result.text.lower()
            row = dict(command=deepcopy(command), ok=not uncertain, physical_commit=False)
            if name == 'depth_points':
                from .embodied_program_geometry import project_pixel
                measured = []
                for raw in payload.get('measurements', []):
                    item = public_depth_measurement(raw)
                    calibration = item.get('camera_calibration')
                    if item.get('valid') is True and isinstance(calibration, dict):
                        # Exactly the same public arithmetic available in the
                        # original program tool, with an explicit target frame.
                        # No target/object pose or mask is looked up.
                        for target in ('task', 'world'):
                            if 'T_' + target + '_from_camera' not in calibration:
                                continue
                            projected = project_pixel(calibration, {**item, 'target_frame': target})
                            if projected.get('valid') is True:
                                for key in ('xyz_task_m', 'xyz_world_m', 'xyz_camera_m'):
                                    if key in projected:
                                        item[key] = projected[key]
                                item['projection_source'] = 'arithmetic_from_returned_same_frame_depth_and_calibration'
                    measured.append(item)
                row['measurements'] = measured
                row['frame_id'] = self.observation['frame_id']
                row['native_frame_id'] = payload.get('native_frame_id')
            elif not uncertain:
                try:
                    self.observation = self._observation(result)
                except ValueError as exc:
                    uncertain = True
                    row.update(ok=False, error=str(exc))
                if self.observation.get('episode_status') == 'faulted':
                    uncertain = True
                    row.update(ok=False, error='Actual GUI reports an unavailable environment')
                if name == 'act' and not uncertain:
                    after = self.observation.get('step')
                    if type(before) is not int or type(after) is not int or after != before + 1:
                        uncertain = True
                        row.update(ok=False, error='Original GUI did not acknowledge exactly one physical Commit')
                    else:
                        row.update(physical_commit=True, receipt=dict(step_before=before, step_after=after,
                            frame_id=self.observation['frame_id'],
                            last_action=(self.observation.get('public_observation') or {}).get('robot_feedback', {}).get('last_action')))
                        outcome['physical_commits'] += 1
                        outcome['physical_action_count'] += 1
            if uncertain:
                row.update(ok=False, error=row.get('error', result.text[:1500]), pending=pending, uncertain=True)
                outcome.update(pending=pending, uncertain=True, diagnostic='Command outcome needs reconciliation; no replay')
            outcome['results'].append(row)
            outcome['observation'] = deepcopy(self.observation)
            outcome['terminal'] = self.observation.get('episode_status') in TERMINAL
            self.on_receipt(dict(**record, result=deepcopy(row), pending=pending, uncertain=uncertain))
            if uncertain or outcome['terminal']:
                break
        outcome['step'] = self.observation.get('step')
        outcome['tcp'] = {side: arm.get('tcp_position') for side, arm in
            (self.observation.get('public_observation') or {}).get('robot_feedback', {}).get('arms', {}).items()}
        return outcome

    def _execute_batch(self, command, requested_command, decision_id):
        """Build an ordered visible queue, then press the original Commit once."""
        before=self.observation.get('step')
        batch_id='batch-'+hashlib.sha256(decision_id.encode()).hexdigest()[:40]
        record=dict(decision_id=decision_id,command_index=0,command=deepcopy(command),
            requested_command=deepcopy(requested_command),frame_id=self.observation['frame_id'],
            physical_commit=True,batch_id=batch_id)
        outcome=dict(results=[],observation=deepcopy(self.observation),physical_commits=0,
            physical_action_count=0,pending=False,uncertain=False,terminal=False)
        row=dict(command=deepcopy(command),ok=False,physical_commit=False,batch_id=batch_id,
            requested_action_count=len(command['actions']))
        self.on_intent(deepcopy(record))  # Before even queue editing, never replay a partially prepared batch.
        committed=False
        try:
            def stage(inputs, *, commit=False):
                nonlocal committed
                if commit:
                    committed=True
                result=self.bridge.call_tool('act',dict(frame_id=self.observation['frame_id'],inputs=inputs))
                payload=_payload(result)
                if result.is_error or payload.get('status') in ('operation_pending','fresh_observation_required'):
                    raise ValueError('Public batch GUI outcome needs reconciliation; no replay. '+result.text[:500])
                observed=self._observation(result)
                if not commit and observed.get('step')!=before:
                    raise ValueError('Queue editing unexpectedly changed the visible physical action count')
                self.observation=observed
                if observed.get('episode_status')=='faulted':
                    raise ValueError('Actual GUI reports a batch environment fault')
                return payload
            stage(self.bridge.public_queue_inputs('clear'))
            stage(self.bridge.public_queue_inputs('id',batch_id=batch_id))
            for pair in command['actions']:
                # Existing macro compiles the complete pair plus Commit. Replace
                # that final click with the public Add button, never execute it.
                selected=self.bridge.public_action_inputs(dict(type='action',**pair))
                if not selected or selected[-1].get('kind')!='click':
                    raise ValueError('Original public pair macro must end in a visible Commit click')
                stage(selected[:-1]+self.bridge.public_queue_inputs('add'))
            stage(self.bridge.public_queue_inputs('commit'),commit=True)
            metadata=self.observation.get('action_batch')
            after=self.observation.get('step')
            if not isinstance(metadata,dict) or metadata.get('batch_id')!=batch_id or metadata.get('requested_count')!=len(command['actions']):
                raise ValueError('Original GUI did not return this exact submitted batch identity/count')
            count=metadata.get('physical_action_count',metadata.get('completed_count'))
            if type(before)is not int or type(after)is not int or type(count)is not int or not 0<=count<=len(command['actions']) or after-before!=count:
                raise ValueError('Visible batch action count disagrees with its public receipt')
            outcome['physical_commits']=int(metadata.get('accepted')is True)
            outcome['physical_action_count']=count
            receipts=metadata.get('receipts',[])
            confirmed_prefix=(isinstance(receipts,list) and len(receipts)==count and
                all(isinstance(r,dict) and r.get('index')==i and r.get('step')==before+i+1 and r.get('status')=='completed' for i,r in enumerate(receipts)))
            terminal_cutoff=(self.observation.get('episode_status')in TERMINAL and
                metadata.get('status')=='partial' and metadata.get('accepted')is True and
                metadata.get('next_index')==count and metadata.get('uncertain')is not True and
                metadata.get('uncertain_action_index')is None and confirmed_prefix)
            incomplete=(count!=len(command['actions']) or metadata.get('status')not in ('completed','complete','done')) and not terminal_cutoff
            uncertain=metadata.get('uncertain')is True or metadata.get('status')in ('unknown','pending','running')
            row.update(ok=not(incomplete or uncertain),physical_commit=metadata.get('accepted')is True,
                physical_action_count=count,receipt=deepcopy(metadata),
                step_before=before,step_after=after,partial=incomplete,known_public_terminal_cutoff=terminal_cutoff)
            outcome.update(pending=metadata.get('status')in ('pending','running'),uncertain=uncertain or incomplete)
        except Exception as exc:
            row.update(ok=False,error=str(exc)[:1000],uncertain=True,commit_attempted=committed)
            outcome.update(uncertain=True,diagnostic='Batch GUI outcome needs host reconciliation; never replay')
        outcome['observation']=deepcopy(self.observation)
        outcome['step']=self.observation.get('step')
        outcome['terminal']=self.observation.get('episode_status')in TERMINAL
        outcome['results']=[row]
        self.on_receipt(dict(**record,result=deepcopy(row),pending=outcome['pending'],uncertain=outcome['uncertain']))
        return outcome

    def readonly(self, queries, *, decision_id):
        if any(query.get('type') not in ('depth_points', 'demo_frames') for query in queries):
            raise ValueError('Readonly turns may only request public pixel depths or assigned-video frames')
        return self.execute(queries, decision_id=decision_id)

    def close(self):
        if self.owns_bridge:
            self.bridge.close()
