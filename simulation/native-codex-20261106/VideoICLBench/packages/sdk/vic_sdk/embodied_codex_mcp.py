"""Structured public GUI tools for a real native Codex conversation.

No model client, prompt-history reconstruction, summarizer or compaction loop.
Codex owns its assistant/tool pairing, session history and automatic compaction.
"""
from copy import deepcopy
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from .robodawn_turn_executor import TurnExecutor, TERMINAL
from .robodawn_turn_context import (
    project_public_execution_results, _lean_history_record,
    _lean_public_observation, _PAIR_FEEDBACK_CONTRACT, _model_measurement_projection,
)

NATIVE_MODEL_INSTRUCTIONS = (
    'Control this embodied episode using only its vic structured tools. '
    'You have no coding or workspace task. Follow the assigned public task and demonstration. '
    'Use the latest returned observation; do not infer success from a completed request. '
    'Never repeat an accepted or uncertain physical input. The native CLI owns conversation history and compaction.'
)
NATIVE_TOOL_INSTRUCTIONS = (
    'The attached first GUI and public state are the initial observation. '
    'Use action_batch to arrange up to24 ordered public arm pairs and Commit exactly once; '
    'the tool returns the final GUI/public robot feedback, not intermediate widget edits. '
    'Each pair counts one physical action. Choose a new operation_id for each new batch. '
    'Repeating a confirmed operation_id only retrieves its saved result. An uncertain operation blocks further physical input. '
    'observe, depth_points, demo_frames and history are optional public information tools. '
    'Depth pixels are [row,col] in the specified native camera; use returned camera mappings/calibration. '
    'Demo frames come only from the assigned video. History returns only already-seen public tool events from this episode. '
    'Call done or giveup explicitly; final prose is not a native terminal. No mandatory scene, plan or memory rewrite is required. '
    'Batch feedback display uses this contract: ' + json.dumps(_PAIR_FEEDBACK_CONTRACT, separators=(',', ':'))
)


class ActionPair(BaseModel):
    """One complete ordered pair from the actual public GUI controls."""
    model_config = ConfigDict(extra='forbid', strict=True)
    left: str = Field(min_length=1, max_length=64, description='Exact left-arm token from the current public action_schema.tokens')
    right: str = Field(min_length=1, max_length=64, description='Exact right-arm token from the current public action_schema.tokens')
    step_mm: FiniteFloat = Field(description='Translation distance in millimetres, within the current public action_schema.step_mm bounds')
    rotation_deg: FiniteFloat = Field(description='Rotation angle in degrees, within the current public action_schema.rotation_deg bounds')


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    raw = (_json(value)+'\n').encode()
    temporary = path.with_name(path.name+'.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


class NativeStructuredTools:
    """Serial GUI executor with durable accepted-input claims, not an agent loop."""
    def __init__(self, config, *, executor=None):
        self.config = dict(config)
        self.identity = deepcopy(config['program_episode_identity'])
        self.directory = Path(config['output_dir'])/'native-structured'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.media = self.directory/'media'; self.media.mkdir(exist_ok=True, mode=0o700)
        self.path = self.directory/'state.private.json'
        self.lock = threading.RLock()
        self.initialized = False
        self.state = json.loads(self.path.read_text()) if self.path.exists() else dict(
            schema='native-codex-public-tools-v1', identity=self.identity, operations={}, events=[], bootstrap=None)
        if self.state.get('identity') != self.identity:
            raise ValueError('Native tool checkpoint belongs to a different episode')
        self.executor = executor or TurnExecutor(config, demo_frame_count=0)

    def save(self):
        _write(self.path, self.state)

    def initialize(self):
        if not self.initialized:
            initial = self.executor.initialize()
            self.initialized = True
            if self.state['bootstrap'] is None:
                packet = dict(kind='bootstrap', observation=deepcopy(initial['observation']),
                    demo_info=deepcopy(initial.get('demo_info')), truncated=False)
                saved = self._store_packet(packet)
                self.state['bootstrap'] = saved
                self.state['events'].append(saved)
                self.save()
        return deepcopy(self.state['bootstrap'])

    def _image(self, image):
        if not isinstance(image, dict) or image.get('type') != 'input_image':
            raise ValueError('Existing public image required')
        url = image.get('image_url', '')
        if not isinstance(url, str) or not re.fullmatch(r'data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+', url):
            raise ValueError('Bounded inline PNG/JPEG image required')
        raw = base64.b64decode(url.split(',', 1)[1], validate=True)
        if not 0 < len(raw) <= 16*1024*1024:
            raise ValueError('Public image size limit exceeded')
        name = _sha(raw)+'.image'; path = self.media/name
        if path.is_symlink():
            raise ValueError('Public media must not be a symlink')
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError('Public image hash collision')
        else:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
                stream.write(raw)
        return dict(name=name, sha256=_sha(raw), mime_type=url.split(';')[0][5:])

    def _store_packet(self, packet):
        saved = deepcopy(packet); images = []
        observation = saved.get('observation')
        if isinstance(observation, dict) and observation.get('image'):
            images.append(self._image(observation.pop('image')))
        for anchor in saved.pop('demo_frames', []):
            images.append(dict(**self._image(anchor['image_item']), demo_seconds=anchor['seconds'],
                source_sha256=anchor['source_sha256']))
        saved['images'] = images
        return saved

    def _read_image(self, ref):
        name = ref.get('name')
        if name != ref.get('sha256', '')+'.image' or not re.fullmatch(r'[0-9a-f]{64}\.image', name or ''):
            raise ValueError('Invalid public media reference')
        path = self.media/name
        if path.is_symlink() or _sha(path.read_bytes()) != ref['sha256']:
            raise ValueError('Saved public image changed')
        return ImageContent(type='image', data=base64.b64encode(path.read_bytes()).decode(), mimeType=ref['mime_type'])

    def result(self, saved, *, include_images=True):
        public = deepcopy(saved); refs = public.pop('images', [])
        if isinstance(public.get('observation'), dict):
            public['observation']['public_observation'] = _lean_public_observation(public['observation'].get('public_observation'))
            # The same public pair feedback is already present in results below.
            public['observation'].pop('action_batch', None)
        if 'results' in public:
            if public.get('kind') == 'depth_points':
                calibrations = {}
                public['results'] = _model_measurement_projection(public['results'], calibrations)
                if calibrations:
                    public['measurement_calibrations'] = calibrations
                    public['calibration_reference_contract'] = 'calibration_ref resolves to this packet measurement_calibrations; exact frame/camera'
            else:
                row = _lean_history_record(dict(commands=public.get('commands', []),
                    results=project_public_execution_results(public['results'])), physical=False)
                public['results'] = row.get('results', [])
                if row.get('commands'):
                    public['commands'] = row['commands']
        public['truncated'] = False
        public['history_event_count'] = len(self.state['events'])
        if len(_json(public).encode()) > 24000:
            return CallToolResult(isError=True, content=[TextContent(type='text', text=_json(dict(
                error='public_result_too_large', truncated=False, physical_input_replayed=False,
                operation_id=public.get('operation_id'), message='Full public result is saved. Request fewer history events; never repeat physical input.')))])
        content = [TextContent(type='text', text=_json(public))]
        if include_images:
            content += [self._read_image(ref) for ref in refs]
        return CallToolResult(content=content)

    def bootstrap_files(self):
        with self.lock:
            saved = self.initialize()
            path = self.directory/'initial-gui.png'
            ref = saved['images'][0]
            raw = (self.media/ref['name']).read_bytes()
            if _sha(raw) != ref['sha256']:
                raise ValueError('Initial GUI image hash mismatch')
            if path.exists() and path.read_bytes() != raw:
                raise ValueError('Initial bootstrap image cannot change')
            path.write_bytes(raw); path.chmod(0o600)
            metadata = deepcopy(saved); metadata.pop('images', None)
            metadata['observation']['public_observation'] = _lean_public_observation(metadata['observation'].get('public_observation'))
            return path, metadata

    def _unresolved(self):
        return any(row['state'] != 'completed' for row in self.state['operations'].values())

    def action_batch(self, operation_id, actions):
        with self.lock:
            self.initialize()
            if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', operation_id):
                raise ValueError('Choose a bounded unique operation_id')
            command = dict(type='action_batch', actions=deepcopy(actions))
            pin = _sha(_json(command).encode())
            existing = self.state['operations'].get(operation_id)
            if existing:
                if existing['command_sha256'] != pin:
                    raise ValueError('operation_id cannot name different actions')
                if existing['state'] != 'completed':
                    raise ValueError('Original accepted operation is unresolved; no replay or new physical input')
                cached = deepcopy(existing['result'])
                cached.update(cached_receipt=True, observation_is_current=False)
                # Re-reading an operation is not a fresh observation of the world.
                # The original image remains available via explicit public history.
                return self.result(cached, include_images=False)
            if self._unresolved():
                raise ValueError('An accepted operation needs host reconciliation; no new physical input')
            self.executor._validate([command])
            self.state['operations'][operation_id] = dict(state='pending', command_sha256=pin, command=command)
            self.save()  # Before any widget edit or Commit.
            try:
                result = self.executor.execute([command], decision_id='native-'+_sha(operation_id.encode())[:40])
            except BaseException:
                self.state['operations'][operation_id]['state'] = 'unknown'; self.save()
                raise
            packet = dict(kind='action_batch', operation_id=operation_id, commands=[command], **deepcopy(result), truncated=False)
            saved = self._store_packet(packet)
            self.state['operations'][operation_id].update(state='unknown' if result.get('pending') or result.get('uncertain') else 'completed', result=saved)
            self.state['events'].append(saved); self.save()
            return self.result(saved)

    def information(self, kind, **arguments):
        with self.lock:
            self.initialize()
            if kind == 'observe':
                observed = self.executor._observation(self.executor.bridge.call_tool('observe', {}))
                self.executor.observation = observed
                packet = dict(kind=kind, observation=observed, truncated=False)
            else:
                command = dict(type=kind, **arguments)
                reply = self.executor.execute([command], decision_id='native-read-'+str(len(self.state['events'])))
                packet = dict(kind=kind, commands=[command], **deepcopy(reply), truncated=False)
                # A pure depth/demo call does not resend an unchanged current GUI.
                packet.pop('observation', None)
            saved = self._store_packet(packet); self.state['events'].append(saved); self.save()
            return self.result(saved)

    def history(self, start, count=1, include_images=False):
        with self.lock:
            self.initialize()
            if (type(start) is not int or start < 1 or type(count) is not int or not 1 <= count <= 5
                    or type(include_images) is not bool or include_images and count > 2
                    or start+count-1 > len(self.state['events'])):
                raise ValueError('Choose one to five existing public events, at most two with images')
            content = []
            for number in range(start, start+count):
                saved = deepcopy(self.state['events'][number-1]); saved['historical_event_number'] = number
                saved['observation_is_current'] = False
                content.extend(self.result(saved, include_images=include_images).content)
            if sum(len(block.text.encode()) for block in content if isinstance(block, TextContent)) > 24000:
                raise ValueError('Requested public history is too large; request fewer events. No content was truncated.')
            return CallToolResult(content=content)  # Do not recursively save history lookup results.

    def terminal(self, kind, summary):
        with self.lock:
            self.initialize()
            if self._unresolved():
                raise ValueError('Unresolved physical input blocks terminal calls')
            command = dict(type=kind, **{('summary' if kind=='done' else 'reason'):summary})
            operation_id = 'terminal-'+kind
            existing = self.state['operations'].get(operation_id)
            if existing:
                return self.result(existing['result'])
            self.state['operations'][operation_id] = dict(state='pending', command_sha256=_sha(_json(command).encode()), command=command)
            self.save()
            try:
                reply = self.executor.execute([command], decision_id=operation_id)
            except BaseException:
                self.state['operations'][operation_id]['state'] = 'unknown'; self.save()
                raise
            saved = self._store_packet(dict(kind=kind, commands=[command], **deepcopy(reply), truncated=False))
            self.state['operations'][operation_id].update(state='unknown' if reply.get('pending') or reply.get('uncertain') else 'completed', result=saved)
            self.state['events'].append(saved); self.save()
            return self.result(saved)

    def close(self):
        with self.lock:
            self.executor.close()


def make_server(backend):
    server = FastMCP('vic-native-embodied')
    @server.tool()
    async def action_batch(operation_id: str,
            actions: Annotated[list[ActionPair], Field(min_length=1, max_length=24)]) -> CallToolResult:
        """Commit1..24 ordered {left,right,step_mm,rotation_deg} pairs once; choose a unique stable operation_id."""
        return await asyncio.to_thread(backend.action_batch, operation_id,
            [action.model_dump(mode='json') for action in actions])
    @server.tool()
    async def observe() -> CallToolResult:
        """Actively inspect the existing current GUI and public robot state."""
        return await asyncio.to_thread(backend.information, 'observe')
    @server.tool()
    async def depth_points(camera: str, pixels: list[list[float]]) -> CallToolResult:
        """Read public native-camera depths at1..16 [row,col] pixels; includes calibration/coordinates."""
        return await asyncio.to_thread(backend.information, 'depth_points', camera=camera, pixels=pixels)
    @server.tool()
    async def demo_frames(seconds: list[float]) -> CallToolResult:
        """Read1..12 timestamps only from the assigned demonstration video."""
        return await asyncio.to_thread(backend.information, 'demo_frames', seconds=seconds)
    @server.tool()
    async def history(start: int, count: int = 1, include_images: bool = False) -> CallToolResult:
        """Review existing same-episode public tool events (1-based), without accessing private state."""
        return await asyncio.to_thread(backend.history, start, count, include_images)
    @server.tool()
    async def done(summary: str) -> CallToolResult:
        """Submit Done through the original visible GUI; native terminal/score remain authoritative."""
        return await asyncio.to_thread(backend.terminal, 'done', summary)
    @server.tool()
    async def giveup(reason: str) -> CallToolResult:
        """Give up explicitly via the original GUI, preserving the actual native state."""
        return await asyncio.to_thread(backend.terminal, 'giveup', reason)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--bootstrap', action='store_true'); args = parser.parse_args(argv)
    config = json.loads(args.config.read_text()); backend = NativeStructuredTools(config)
    try:
        if args.bootstrap:
            image, public = backend.bootstrap_files(); print(_json(dict(image_path=str(image), public=public)), flush=True)
        else:
            make_server(backend).run(transport='stdio')
    finally:
        backend.close()


if __name__ == '__main__':
    main()
