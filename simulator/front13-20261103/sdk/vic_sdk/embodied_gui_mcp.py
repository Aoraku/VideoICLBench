"""RoboProbe-style observe/act/done/giveup over the visible VideoICL GUI.

All environment inputs are real browser clicks, keys or text entry. This MCP
does not call robot-action HTTP endpoints and never reads hidden scene state.
The native CLI still owns model inference, context and tool iteration.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import contextmanager
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import math
import re
import signal
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlsplit
import httpx

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

from .computer_mcp import Computer


ALLOWED_KEYS = frozenset(('Enter', 'Tab', 'Shift+Tab', 'Backspace', 'Delete', 'Escape',
    'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'Space',
    'ControlOrMeta+A', 'ControlOrMeta+Z', 'ControlOrMeta+Y'))


def normalize_key(key):
    if not isinstance(key,str):
        return key
    value = key.strip().lower().replace(' ','')
    for modifier in ('ctrl+','control+','cmd+','command+','meta+','controlormeta+'):
        if value in {modifier+letter for letter in ('a','z','y')}:
            return 'ControlOrMeta+'+value[-1].upper()
    aliases = {k.lower():k for k in ALLOWED_KEYS}
    aliases.update({'return':'Enter','esc':'Escape','spacebar':'Space'})
    return aliases.get(value,key)
TERMINAL_STATUSES = frozenset(('done', 'give_up', 'giveup', 'finished', 'stopped',
    'sealed', 'submitted', 'aborted', 'budget_exhausted', 'budget_paused', 'closed', 'faulted'))


class GuiBrowser(Computer):
    def __init__(self, config, *, page=None):
        super().__init__(config)
        self.http.close()  # Browser owns authenticated environment transport.
        self.lock = threading.RLock()
        from .rule_qa_gate import RuleQAGate
        self.qa_gate = RuleQAGate(config) if config.get("rule_qa") else None
        if self.qa_gate and config["condition"] == "text_rule":
            self.qa_gate.delivered(source_sha256=config["rule_qa"]["source_sha256"])
        self.frame = None
        self.native_frame = None
        self.decision_observation_required = False
        self.page = page
        self.page_errors = []
        self.api_statuses = []
        self.browser = self.playwright = None
        self.transport_failed = False
        if (self.output / 'gui-input-pending.private.json').exists():
            # A new MCP/browser cannot adopt an orphaned input. Only the private
            # owner barrier can confirm it before the controller resumes.
            self.unavailable('UnreconciledPendingInput')
            raise RuntimeError('A prior GUI input requires controller reconciliation before reopening')
        self.graceful_budget = config.get('budget_policy') == 'effective_time_graceful_v1'
        self._environment_terminal_logged = False
        self.max_gui_inputs = config.get('max_gui_inputs', 5 * config['max_actions'])
        if type(self.max_gui_inputs) is not int or self.max_gui_inputs <= 0:
            raise ValueError('GUI input budget must be a positive integer')
        self.settle_timeout_ms = config.get('gui_settle_timeout_ms', 120000)
        self.observation_timeout_ms = config.get('gui_observation_timeout_ms', 60000)
        if any(type(v) is not int or v < (0 if self.graceful_budget else 1) for v in
               (self.settle_timeout_ms, self.observation_timeout_ms)):
            raise ValueError('GUI timeouts must be positive, or zero for the graceful budget policy')
        self.condition = config['condition']
        if self.condition not in ('real', 'sim', 'text_rule'):
            raise ValueError('Unknown input condition')
        if self.condition == 'text_rule' and config.get('demo_video'):
            raise ValueError('Text condition must not have a demonstration')
        width, height = config.get('gui_viewport', [1440, 1280])
        if not all(type(v) is int and 600 <= v <= 3000 for v in (width, height)):
            raise ValueError('Invalid GUI viewport')
        self.viewport = dict(width=width, height=height)
        if self.page is None:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            options = dict(headless=True)
            if config.get('browser_path'):
                options['executable_path'] = str(config['browser_path'])
            try:
                self.browser = self.playwright.chromium.launch(**options)
                context = self.browser.new_context(viewport=self.viewport, device_scale_factor=1,
                                                   accept_downloads=False)
                self.page = context.new_page()
                self.page.on('pageerror',lambda exc:self.page_errors.append(str(exc).replace(config['actor_token'],'[REDACTED]')))
                self.page.on('response',lambda response:self.api_statuses.append(dict(
                    path=urlsplit(response.url).path,status=response.status))
                    if urlsplit(response.url).path.startswith('/api/') else None)
                self.page.goto(config['control_url'].rstrip('/') + '/#token=' + config['actor_token'],
                               wait_until='domcontentloaded', timeout=60000)
                self.page.wait_for_function(
                    "['camera-head','camera-left_wrist','camera-right_wrist'].every(id => document.getElementById(id)?.naturalWidth > 0)",
                    timeout=self.observation_timeout_ms)
                self._settled()
            except Exception as exc:
                diagnostic = dict(error_class=type(exc).__name__,page_errors=self.page_errors,
                                  api_statuses=self.api_statuses)
                try:
                    diagnostic['visible_gui'] = self.page.evaluate("""() => ({
                        status:document.body?.dataset.episodeStatus,
                        busy:document.body?.getAttribute('aria-busy'),
                        notice:document.getElementById('notice')?.textContent,
                        cameras:['head','left_wrist','right_wrist'].map(n=>{
                            const image=document.getElementById('camera-'+n);
                            return {name:n,width:image?.naturalWidth,height:image?.naturalHeight,
                                    complete:image?.complete};})})""")
                    self.page.screenshot(path=str(self.output/'gui-preflight-failure.png'),timeout=5000)
                except Exception:
                    diagnostic['browser_diagnostic_unavailable'] = True
                (self.output/'gui-preflight-diagnostic.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2))
                self.close()
                self.unavailable(type(exc).__name__)
                raise RuntimeError('The GUI environment could not provide a complete observation') from None

    def demo_frame(self, seconds):
        result = super().demo_frame(seconds)
        if self.qa_gate:
            self.qa_gate.delivered(source_sha256=self.config['rule_qa']['source_sha256'], seconds=seconds)
        return result

    def qa_question(self):
        if not self.qa_gate: raise ValueError('QA is not enabled')
        return self.qa_gate.question()

    def qa_answer(self, answer):
        if not self.qa_gate: raise ValueError('QA is not enabled')
        return self.qa_gate.submit(answer)

    def unavailable(self, error_class):
        self.transport_failed = True
        self.closed = True
        self.frame = None
        value = dict(
            type='gui_transport_error', error_class=error_class,
            message='GUI interaction failed; stop without replaying an uncertain input.')
        pending = self.output / 'gui-input-pending.private.json'
        if pending.exists():
            value['pending_marker_sha256'] = hashlib.sha256(pending.read_bytes()).hexdigest()
        (self.output / 'environment-error.json').write_text(json.dumps(value))

    def check(self):
        if self.graceful_budget:
            if self.closed:
                raise ValueError('This session is finished')
            return
        return super().check()

    def remaining_seconds(self):
        # Effective elapsed time excludes controller waits; the old absolute
        # CLI deadline cannot be used as this budget's source of truth.
        return None if self.graceful_budget else super().remaining_seconds()

    def close(self):
        errors = []
        for name, method in (('browser', 'close'), ('playwright', 'stop')):
            value = getattr(self, name)
            if value:
                try:
                    getattr(value, method)()
                except Exception as exc:
                    errors.append(dict(resource=name, error_class=type(exc).__name__))
                finally:
                    setattr(self, name, None)
        if errors:
            with (self.output / 'gui-cleanup-errors.private.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(time=time.time(), errors=errors)) + '\n')

    def _visible_action_count(self):
        # The same counter the model sees; no private API or hidden scene reads.
        value = self.page.locator('#budget').text_content() or ''
        match = re.match(r'^\s*(\d+)\s*/', value)
        return int(match[1]) if match else None

    def _actor_activity(self):
        if self.config.get('api_failure_budget_policy') == 'per_episode_failed_request_and_retry_wait_v1':
            # Harness metering only: no action fields, scene state, or score response.
            response = httpx.post(self.config['control_url'].rstrip('/') + '/api/actor-activity',
                headers={'Authorization':'Bearer ' + self.config['actor_token']}, json={},
                trust_env=False, timeout=None if self.graceful_budget else 30.)
            response.raise_for_status()

    def _check_pending_input(self):
        if (self.output / 'gui-input-pending.private.json').exists():
            raise RuntimeError('A prior GUI input requires controller reconciliation before further interaction')

    def _settled(self):
        self.page.wait_for_function("document.body.getAttribute('aria-busy') !== 'true'", timeout=self.settle_timeout_ms)
        self.page.wait_for_function("""() => ['head','left_wrist','right_wrist'].every(name => {
            const image = document.getElementById('camera-' + name);
            return image && image.complete && image.naturalWidth > 0;
        })""", timeout=self.observation_timeout_ms)
        self.page.wait_for_timeout(80)

    def _status(self):
        return self.page.locator('body').get_attribute('data-episode-status') or 'unknown'

    def _picture(self):
        from .embodied_public_observation import public_observation
        raw = self.page.evaluate('() => window.videoiclPublicObservation || null')
        camera_views = self.page.evaluate("""() => Object.fromEntries(
            ['head','left_wrist','right_wrist'].map(name => {
                const img = document.getElementById('camera-'+name);
                if (!img || !img.naturalWidth || !img.naturalHeight) return [name,{available:false}];
                const r=img.getBoundingClientRect();
                const scale=Math.min(r.width/img.naturalWidth,r.height/img.naturalHeight);
                const width=img.naturalWidth*scale,height=img.naturalHeight*scale;
                return [name,{available:true,native_width:img.naturalWidth,native_height:img.naturalHeight,
                    image_rect:{x:r.x+(r.width-width)/2,y:r.y+(r.height-height)/2,width,height},
                    pixel_mapping:'col=(x-image_rect.x)*native_width/image_rect.width; row=(y-image_rect.y)*native_height/image_rect.height'}];
            }))""")
        data = self.page.screenshot(type='png', full_page=False)
        after = self.page.evaluate('() => window.videoiclPublicObservation?.frame_id || null')
        try:
            public = public_observation(raw)
        except ValueError:
            public = dict(schema='videoicl-structured-observation-v1',
                          available=False, reason='no_synchronized_public_observation')
        if public.get('native_frame_id') != after:
            public = dict(schema='videoicl-structured-observation-v1',
                          available=False, reason='observation_changed_during_capture')
        self.native_frame = public.get('native_frame_id')
        self.decision_observation_required = False
        self.frame = uuid.uuid4().hex
        name = 'frame-gui-' + self.frame + '.png'
        (self.output / name).write_bytes(data)
        self.log(dict(type='observation', frame_id=self.frame, file=name, interaction='gui_only'))
        status = self._status()
        if status in {'budget_exhausted','budget_paused','finished'}:
            if not self._environment_terminal_logged:
                self.log(dict(type='environment_terminal',termination=status,
                              interaction='gui_only',summary='The visible GUI reports the episode has stopped.'))
                self._environment_terminal_logged = True
            self.closed = True
        if status == 'faulted':
            self.closed = True
            (self.output / 'environment-error.json').write_text(json.dumps(dict(
                type='native_environment_error', error_class='EnvironmentFaulted',
                message='The visible GUI reports an unavailable environment. Stop without replaying inputs.')))
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(dict(
            public_observation=public,
            camera_views=camera_views,
            frame_id=self.frame, width=self.viewport['width'], height=self.viewport['height'],
            remaining_seconds=self.remaining_seconds(),
            remaining_gui_inputs=max(0, self.max_gui_inputs - self.actions),
            max_robot_actions=self.config['max_actions'],
            episode_status=status, observation='complete visible GUI screenshot'))),
            ImageContent(type='image', mimeType='image/png', data=base64.b64encode(data).decode())])

    def depth_points(self, frame_id, camera, pixels):
        """Read selected sensor pixels for the displayed frame; never advance physics."""
        from .embodied_public_observation import public_depth_measurement
        with self.lock:
            self._check_pending_input()
            if self.transport_failed:
                raise ValueError('GUI transport is unavailable')
            if (not self.frame or frame_id != self.frame or
                    self.decision_observation_required or not self.native_frame):
                raise ValueError('A fresh GUI observation is required')
            if camera not in ('head', 'left_wrist', 'right_wrist'):
                raise ValueError('Unknown camera')
            if not isinstance(pixels, list) or not 1 <= len(pixels) <= 16:
                raise ValueError('Choose one to sixteen native-image [row, col] pixels')
            for point in pixels:
                if (not isinstance(point, list) or len(point) != 2 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
                    raise ValueError('Each pixel must be a finite [row, col] pair')
            current = self.page.evaluate('() => window.videoiclPublicObservation?.frame_id || null')
            if current != self.native_frame:
                raise ValueError('The displayed observation has changed; call observe again')
            measurements = []
            with httpx.Client(trust_env=False, timeout=30.) as client:
                for row, col in pixels:
                    try:
                        response = client.post(self.config['control_url'].rstrip('/') + '/api/depth-point',
                            headers={'Authorization': 'Bearer ' + self.config['actor_token']},
                            json=dict(frame_id=self.native_frame, camera=camera, row=row, col=col))
                        if response.status_code != 200:
                            measurements.append(dict(valid=False, reason='sensor_read_unavailable',
                                http_status=response.status_code, frame_id=self.native_frame, camera=camera))
                            break
                        item = public_depth_measurement(response.json())
                        if item.get('frame_id') != self.native_frame or item.get('camera') != camera:
                            item = dict(valid=False, reason='sensor_response_frame_mismatch')
                        measurements.append(item)
                    except (httpx.HTTPError, ValueError):
                        measurements.append(dict(valid=False, reason='sensor_read_transport_error'))
                        break
            result = dict(schema='videoicl-depth-points-v1', frame_id=self.frame,
                native_frame_id=self.native_frame, camera=camera,
                physical_action=False, measurements=measurements)
            self.log(dict(type='depth_points', frame_id=self.frame,
                native_frame_id=self.native_frame, camera=camera, pixels=pixels,
                valid_points=sum(m.get('valid') is True for m in measurements)))
            return result

    def observe(self):
        with self.lock:
            # Read-only evidence remains available after an explicit stop or a
            # native action/time budget. A failed transport must never replay.
            if self.transport_failed:
                raise ValueError('GUI transport is unavailable; stop this trial')
            self._check_pending_input()
            self._actor_activity()
            self._settled()
            return self._picture()

    def _input_button(self, value):
        if value['kind'] in ('click', 'double_click'):
            return self.page.evaluate(
                "p => document.elementFromPoint(p.x,p.y)?.closest('button')?.id || null",
                {'x': value['x'], 'y': value['y']})
        if value['kind'] == 'key' and value['key'] in ('Enter', 'Space'):
            # Enter inside a numeric form field activates its default submit
            # button too. Counting only focused buttons misses that route.
            return self.page.evaluate("""key => {
                const element = document.activeElement;
                const button = element?.closest('button');
                if (button) return button.id || null;
                if (key === 'Enter' && element?.tagName === 'INPUT' && element.form)
                    return element.form.querySelector('button[type=submit]')?.id || null;
                return null;
            }""", value['key'])
        return None

    def _validate(self, value):
        if not isinstance(value, dict) or value.get('kind') not in ('click', 'double_click', 'text', 'key', 'scroll', 'wait'):
            raise ValueError('Unknown GUI input')
        allowed = {'kind', 'x', 'y', 'text', 'key', 'delta_y', 'wait_ms'}
        if set(value) - allowed:
            raise ValueError('Only visible GUI input parameters are accepted')
        kind = value['kind']
        if kind in ('click', 'double_click', 'scroll'):
            for axis in ('x', 'y'):
                bound = self.viewport['width' if axis == 'x' else 'height']
                if type(value.get(axis)) not in (int, float) or not math.isfinite(value[axis]) or not 0 <= value[axis] < bound:
                    raise ValueError('Use coordinates inside the current GUI screenshot')
        if kind == 'text' and (not isinstance(value.get('text'), str) or len(value['text']) > 10000):
            raise ValueError('Use a bounded text value for the focused visible field')
        if kind == 'key' and value.get('key') not in ALLOWED_KEYS:
            raise ValueError('Use an environment GUI editing key: '+', '.join(sorted(ALLOWED_KEYS)))
        if kind == 'scroll' and (type(value.get('delta_y')) not in (int, float) or not math.isfinite(value['delta_y']) or abs(value['delta_y']) > 3000):
            raise ValueError('Scroll by at most 3000 pixels')
        if kind == 'wait' and (type(value.get('wait_ms')) is not int or not 0 <= value['wait_ms'] <= 2000):
            raise ValueError('Wait between 0 and 2000 milliseconds')

    def act(self, frame_id, inputs):
        with self.lock:
            if getattr(self, 'qa_gate', None): self.qa_gate.require_answer()
            self.check()
            self._check_pending_input()
            self._actor_activity()
            if self._status() in TERMINAL_STATUSES:
                raise ValueError('The GUI episode has stopped; observe its final screenshot')
            if not isinstance(frame_id, str) or frame_id != self.frame:
                raise ValueError('Observe first; use the most recent GUI frame_id')
            if not isinstance(inputs, list) or not 1 <= len(inputs) <= 12:
                raise ValueError('Plan one to twelve visible GUI inputs with at most one physical Commit')
            inputs = [{**value,'key':normalize_key(value['key'])}
                      if isinstance(value,dict) and value.get('kind')=='key' and 'key' in value
                      else value for value in inputs]
            if self.actions + len(inputs) > self.max_gui_inputs:
                raise ValueError('GUI input budget exhausted')
            for value in inputs:
                self._validate(value)
            self.frame = None
            self.decision_observation_required = True
            commits = 0
            refreshed = False
            for value in inputs:
                started = time.monotonic()
                kind = value['kind']
                # Only the public control receiving this input is inspected;
                # no DOM, robot state or selectors are exposed to the agent.
                target = self._input_button(value)
                if target in ('done', 'giveup') and (commits or refreshed):
                    raise ValueError('Observe the completed operation before a terminal decision; prior inputs may have executed')
                if kind == 'text' and not self.page.evaluate("['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)"):
                    raise ValueError('Click a visible editable field before typing')
                if target == 'commit':
                    commits += 1
                    if commits > 1 or kind == 'double_click':
                        self.frame = None
                        raise ValueError('Use at most one robot commit per act; prior inputs may have executed, so observe again')
                pending = self.output/'gui-input-pending.private.json'
                input_id = uuid.uuid4().hex
                pending.write_text(json.dumps(dict(input_id=input_id,started_unix=time.time(),gui_input=value,
                    physical_commit=target=='commit',before_action_count=self._visible_action_count(),
                    phase='awaiting_visible_gui_acknowledgement')))
                if kind in ('click', 'double_click'):
                    if kind == 'double_click':
                        self.page.mouse.dblclick(value['x'], value['y'])
                    else:
                        self.page.mouse.click(value['x'], value['y'])
                elif kind == 'text':
                    self.page.keyboard.insert_text(value['text'])
                elif kind == 'key':
                    self.page.keyboard.press(value['key'])
                elif kind == 'scroll':
                    self.page.mouse.move(value['x'], value['y'])
                    self.page.mouse.wheel(0, value['delta_y'])
                else:
                    self.page.wait_for_timeout(value['wait_ms'])
                self._settled()
                self.actions += 1
                self.log(dict(type='action', interaction='gui_only', frame_id=frame_id,
                    input_id=input_id, gui_input=value, physical_commit=target == 'commit',
                    duration_seconds=time.monotonic()-started))
                pending.unlink(missing_ok=True)
                refreshed = refreshed or target == 'refresh'
                # Log every input, but persist the screenshot returned to the
                # model at the batch end. Unreturned widget-edit frames would
                # duplicate unchanged camera pixels across a large campaign.
                status = self._status()
                if status in TERMINAL_STATUSES:
                    self.log(dict(type='finish' if status in {'done','give_up','giveup'} else 'environment_terminal',
                                  summary='The visible GUI acknowledged termination',
                                  termination=status, interaction='gui_only'))
                    self.closed = True
                    break
            return self._picture()

    def terminal(self, kind, summary, frame_id):
        with self.lock:
            if getattr(self, 'qa_gate', None): self.qa_gate.require_answer()
            if kind not in ('done', 'giveup') or not isinstance(summary, str) or len(summary) > 10000:
                raise ValueError('Invalid GUI terminal request')
            if self.transport_failed:
                raise ValueError('GUI transport is unavailable; stop this trial')
            self._check_pending_input()
            if not isinstance(frame_id, str) or frame_id != self.frame:
                raise ValueError('Observe first; use the most recent GUI frame_id for a terminal decision')
            self._actor_activity()
            self._settled()
            status = self._status()
            if status in TERMINAL_STATUSES:
                self.log(dict(type='finish' if status in {'done','give_up','giveup'} else 'environment_terminal',
                              summary=summary, termination=status,requested_termination=kind,
                              interaction='gui_only', already_terminal=True))
                self.closed = True
                return self._picture()
            self.check()
            if self.decision_observation_required:
                raise ValueError('Observe again before a terminal decision; the previous batch did not return an observation')
            if not self.page.locator('#' + kind).is_enabled():
                raise ValueError('The visible terminal control is unavailable; refresh the GUI observation before deciding')
            # Enlarged cameras cover the stop controls. Restore them through
            # their visible buttons before recording any terminal intent.
            enlarged = self.page.locator('.camera.camera-enlarged .camera-zoom')
            for remaining in range(enlarged.count(), 0, -1):
                enlarged.last.click()
                if enlarged.count() != remaining - 1:
                    raise ValueError('The enlarged camera did not close; restore its view before deciding')
            field = '#stop-reason'
            if self.page.locator(field).count():
                self.page.locator(field).fill(summary)
            pending = self.output/'gui-input-pending.private.json'
            input_id = uuid.uuid4().hex
            pending.write_text(json.dumps(dict(input_id=input_id,started_unix=time.time(),terminal_request=kind,
                before_action_count=self._visible_action_count(),
                phase='awaiting_visible_gui_termination')))
            self.page.locator('#' + kind).click()
            self._settled()
            status = self._status()
            if status not in TERMINAL_STATUSES:
                raise RuntimeError('The visible GUI did not acknowledge termination')
            self.log(dict(type='finish' if status in {'done','give_up','giveup'} else 'environment_terminal', summary=summary,
                          input_id=input_id, termination=status, interaction='gui_only'))
            pending.unlink(missing_ok=True)
            result = self._picture()
            self.closed = True
            return result


def make_server(browser):
    server = FastMCP('vic-embodied-gui')
    # Text formatting happens after the original receipt/audit handling.
    projection = None
    if browser.config.get('lean_text_projection') is True:
        from .embodied_token_projection import TextProjection
        projection = TextProjection(Path(browser.config['output_dir']) / 'lean-text',
                                    browser.config['run_id'], mode='compact')

    def project_response(result):
        return projection.mcp_result(result) if projection is not None else result

    program_session = None
    if getattr(browser, 'config', {}).get('embodied_harness') == 'program_gui':
        from .embodied_program_gui import ProgramGuiSession
        program_session = ProgramGuiSession(browser, browser.config)
        server._episode_program_session = program_session

        @server.tool()
        async def program(source: str, submission_id: str) -> CallToolResult:
            """Run bounded episode-local Python macros and memory over visible GUI tools.

            No imports, attributes, filesystem or network. Call observe(), act(inputs),
            depth_points(camera, pixels), backproject(measurement), or
            project_pixel(calibration, measurement); video conditions also have demo tools.
            At most one act (one Commit) and eight callbacks per program. Return to
            inspect its screenshot before choosing another motion. Same id/source
            retrieves the receipt without replay. Use memory["key"] for notes.
            """
            try:
                return project_response(await asyncio.to_thread(program_session.execute, source, submission_id))
            except asyncio.CancelledError:
                program_session.require_fresh_observation()
                raise

    def protected(method, *args):
        try:
            return program_session.direct(method, *args) if program_session else method(*args)
        except ValueError:
            raise
        except Exception as exc:
            browser.unavailable(type(exc).__name__)
            raise RuntimeError('GUI transport failed; stop this trial without replaying inputs') from None

    async def gui_call(method, *args):
        try:
            return project_response(await asyncio.to_thread(protected, method, *args))
        except asyncio.CancelledError:
            # Cancelling the MCP wait does not cancel the accepted browser
            # operation. Its returned screenshot may never reach the model.
            mark = (program_session.require_fresh_observation if program_session else
                    getattr(browser, 'require_fresh_observation', None))
            if mark is not None:
                mark()
            raise

    if browser.config.get('rule_qa'):
        @server.tool()
        async def qa_question() -> dict:
            """After reading the supplied rule or inspecting demo frames, read this episode's four-option question."""
            return await gui_call(browser.qa_question)

        @server.tool()
        async def qa_answer(answer: str) -> dict:
            """Submit exactly one A/B/C/D answer. First valid answer is final; correctness is never returned."""
            return await gui_call(browser.qa_answer, answer)

    @server.tool()
    async def observe() -> CallToolResult:
        """See the current GUI screenshot and structured public robot/camera state for that frame."""
        return await gui_call(browser.observe)

    @server.tool()
    async def depth_points(frame_id: str, camera: str, pixels: list[list[float]]) -> dict:
        """Read 1–16 [row,col] pixels in the camera's native image, using the latest GUI frame_id.

        Returns axial depth in metres and same-frame K/T, for your coordinate
        calculation. Read-only: no robot action, object pose or score. Invalid
        pixels return no estimate. GUI screenshot pixels must first be mapped
        to native-image pixels using that camera's displayed image rectangle.
        """
        return await gui_call(browser.depth_points, frame_id, camera, pixels)

    @server.tool()
    async def act(frame_id: str, inputs: list[dict]) -> CallToolResult:
        """Operate visible GUI controls with one to twelve screenshot-coordinate inputs.

        Each input has kind click/double_click (x,y), text (text), key (key),
        scroll (x,y,delta_y), or wait (wait_ms<=2000).
        Batch arm selections and field edits, followed by one Commit, in this
        same call. Selections alone do not move the robot; a second selection
        for the same arm replaces the first. Commit executes both arms together.
        At most one robot commit per act call; its returned screenshot is the
        next observation, so no extra observe is needed after each field edit.
        Editing keys: Enter, Tab, Shift+Tab, Backspace, Delete, Escape,
        ArrowLeft/Right/Up/Down, Home, End, Space, ControlOrMeta+A/Z/Y.
        Common spellings such as CTRL+A and BACKSPACE are accepted.
        No robot-object selectors, world-coordinate query, shell or DOM access.
        """
        return await gui_call(browser.act, frame_id, inputs)

    @server.tool()
    async def done(frame_id: str, summary: str = '') -> CallToolResult:
        """End the episode only when the latest returned GUI observation supports your belief that all requested goals are complete. A successful tool call or partial progress alone is insufficient."""
        return await gui_call(browser.terminal, 'done', summary, frame_id)

    @server.tool()
    async def giveup(frame_id: str, reason: str) -> CallToolResult:
        """End the episode without claiming success when observed task state or attempts show it cannot be completed. Pending operations, temporary waiting and API failures are not task failure evidence."""
        return await gui_call(browser.terminal, 'giveup', reason, frame_id)

    if browser.condition != 'text_rule':
        def read_demo_info():
            browser.check()
            return browser.demo_info()

        @server.tool()
        async def demo_info() -> dict:
            """Inspect the assigned demonstration's video information; no expert state or audio."""
            return await gui_call(read_demo_info)

        def read_demo_frame(seconds):
            browser.check()
            return browser.demo_frame(seconds)

        @server.tool()
        async def demo_frame(seconds: float) -> CallToolResult:
            """Inspect one frame of the assigned real/sim demonstration at the chosen timestamp."""
            return await gui_call(read_demo_frame, seconds)

        def read_demo_frames(seconds):
            browser.check()
            if not 1 <= len(seconds) <= 12:
                raise ValueError('Choose one to twelve timestamps')
            return CallToolResult(content=[c for t in sorted(seconds) for c in browser.demo_frame(t).content])

        @server.tool()
        async def demo_frames(seconds: list[float]) -> CallToolResult:
            """Inspect one to twelve chronological video frames; no trajectory or rule annotation."""
            return await gui_call(read_demo_frames, seconds)
    return server


class ThreadOwnedBrowser:
    """Keep Playwright's sync event loop outside the MCP async owner thread.

    Creation, every GUI/demo call, and shutdown share one dedicated thread.
    This is a transport implementation detail; model tool schemas stay equal.
    """
    def __init__(self, config):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vic-gui')
        self.operation_lock = threading.Lock()
        self.operation = None
        self.fresh_observation_required = False
        self.pending_generation = 0
        try:
            self.browser = self.executor.submit(GuiBrowser, config).result()
        except BaseException:
            self.executor.shutdown(wait=True)
            raise

    def _operation_notice(self, status, operation=None):
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(dict(
            status=status, operation=operation, accepted=False, queued=False,
            physical_input_replayed=False,
            message=('An earlier GUI operation is still in flight. This is infrastructure waiting, not task failure. '
                     'Wait for that original call; do not terminate it, duplicate input, or give up because it is pending. '
                     'After it completes, call observe again before deciding the next action.'
                     if status == 'operation_pending' else
                     'The previous pending operation has finished. Call observe now before another action or terminal decision.'))))])

    def require_fresh_observation(self):
        with self.operation_lock:
            self.fresh_observation_required = True
            self.pending_generation += 1

    def _call_gui(self, name, *args, **kwargs):
        with self.operation_lock:
            if self.operation is not None and not self.operation[1].done():
                self.fresh_observation_required = True
                self.pending_generation += 1
                return self._operation_notice('operation_pending', self.operation[0])
            if name != 'observe' and self.fresh_observation_required:
                return self._operation_notice('fresh_observation_required')
            generation = self.pending_generation
            future = self.executor.submit(getattr(self.browser, name), *args, **kwargs)
            self.operation = (name, future)
        try:
            result = future.result()
            if name == 'observe':
                with self.operation_lock:
                    if generation == self.pending_generation:
                        self.fresh_observation_required = False
            return result
        finally:
            with self.operation_lock:
                if self.operation is not None and self.operation[1] is future:
                    self.operation = None

    def observe(self):
        return self._call_gui('observe')

    def act(self, frame_id, inputs):
        return self._call_gui('act', frame_id, inputs)

    def depth_points(self, frame_id, camera, pixels):
        return self._call_gui('depth_points', frame_id, camera, pixels)

    def terminal(self, kind, summary, frame_id):
        return self._call_gui('terminal', kind, summary, frame_id)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        value = getattr(self.browser, name)
        if not callable(value):
            return value

        def call(*args, **kwargs):
            return self.executor.submit(value, *args, **kwargs).result()
        return call

    def close(self):
        try:
            self.executor.submit(self.browser.close).result()
        finally:
            self.executor.shutdown(wait=True)


@contextmanager
def graceful_stdio_shutdown():
    """Let SIGTERM unwind stdio serving through the existing drain/close path.

    The session's lock and halted-state checks still decide whether its owner
    may be released. A repeated TERM must not interrupt that cleanup. SIGKILL,
    a crash, or an unknown action still require external reconciliation.
    """
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    with graceful_stdio_shutdown():
        browser = ThreadOwnedBrowser(json.loads(args.config.read_text()))
        server = None
        try:
            server = make_server(browser)
            server.run(transport='stdio')
        finally:
            session = getattr(server, '_episode_program_session', None)
            try:
                if session is not None:
                    session.close()
            finally:
                browser.close()


if __name__ == '__main__':
    main()
