"""Real Chrome GUI inputs against synthetic images/APIs; no model or simulator."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import time

from PIL import Image
import pytest

from vic_sdk.embodied_gui_mcp import GuiBrowser, make_server

IDENTITY = dict(run_id='test-run', task_id='E05', variant='A', seed=7,
                suite='embodied', epoch='test-epoch')
ASSETS = Path(__file__).resolve().parents[1] / 'apps/portal/public/embodied'


@pytest.fixture(scope='session')
def chrome_path():
    path = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if path.is_file():
        return str(path)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        path = Path(p.chromium.executable_path)
    if not path.is_file():
        pytest.skip('A Chrome/Playwright browser is required for actual GUI checks')
    return str(path)


@pytest.fixture
def gui_controller():
    buffer = io.BytesIO()
    Image.new('RGB', (320, 240), '#dfe7f3').save(buffer, format='PNG')
    image = base64.b64encode(buffer.getvalue()).decode()
    data = dict(condition='real', calls=[], evaluation_identity=dict(IDENTITY),
                observation_error=False, seal_error=False, reject_next_action=False, fail_next_action=False,
                status='running', steps=0, max_actions=6, frame=0)

    def state():
        public = dict(title='SYNTHETIC GUI TEST — NO SIMULATION',
            frame_id='native-frame-' + str(data['frame']),
            instruction='Synthetic test. Operate the visible controls.',
            status=data['status'], condition=data['condition'], steps=data['steps'],
            max_actions=data['max_actions'], rule_reported=False, diagnostics_enabled=False,
            action_schema=dict(tokens=['STILL','FWD','BACK','LEFT','RIGHT','UP','DOWN',
                'GRASP','RELEASE','ROTATE_CCW','ROTATE_CW','PITCH_UP','PITCH_DOWN','ROLL_LEFT','ROLL_RIGHT'],
                step_mm=dict(minimum=.5, maximum=50, default=20),
                rotation_deg=dict(minimum=.5, maximum=20, default=10)),
            demo_available=data['condition'] != 'text_rule',
            robot_feedback=dict(coordinate_frame='task', units={'position':'m'},
                arms={s:dict(tcp_position=[.1,.2,.3]) for s in ('left','right')}),
            object_truth='PRIVATE_OBJECTS_MUST_NOT_LEAK', score=.99,
            private_rule='PRIVATE_RULE_MUST_NOT_LEAK')
        if data['condition'] == 'text_rule':
            public['text_rule'] = 'PUBLIC EXPLICIT TEXT RULE'
        return public

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def response(self, value, status=200, mime='application/json'):
            payload = json.dumps(value).encode() if mime == 'application/json' else value
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            private = self.path.startswith('/api/private/')
            if self.headers.get('Authorization') != 'Bearer ' + ('admin-test' if private else 'actor-test'):
                self.response({}, 403)
                return False
            return True

        def do_GET(self):
            if self.path in ('/', '/app.js', '/style.css'):
                name = 'index.html' if self.path == '/' else self.path[1:]
                mime = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript','style.css':'text/css'}[name]
                return self.response((ASSETS / name).read_bytes(), mime=mime)
            if not self.authorized():
                return
            data['calls'].append(('GET', self.path, self.headers.get('Authorization'), None))
            if self.path == '/api/private/state':
                value=dict(identity=IDENTITY, state=state())
                if data.get('support_recovery'):
                    value['owner_barrier']=dict(schema='videoicl-owner-action-barrier-v1',
                        action_count=data['steps'],status=data['status'],
                        api_timing_log=data.get('api_timing_log'),
                        recovery_id=data.get('recovery_id'),model_stop=data.get('model_stop'),
                        terminal_snapshot_ready=data.get('sealed',False))
                return self.response(value)
            if self.path == '/api/state':
                return self.response(state())
            if self.path == '/api/observe':
                if data['observation_error']:
                    return self.response({}, 503)
                data['frame'] += 1
                return self.response(dict(frame_id='native-frame-' + str(data['frame']),
                    state=state(), images={n:image for n in ('head','left_wrist','right_wrist')}))
            if self.path == '/demo.mp4' and data['condition'] != 'text_rule':
                return self.response(data.get('demo_bytes', b'SYNTHETIC INVALID VIDEO'), mime='video/mp4')
            return self.response({}, 404)

        def do_POST(self):
            if not self.authorized():
                return
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            data['calls'].append(('POST', self.path, self.headers.get('Authorization'), body))
            if self.path=='/api/actor-activity':
                return self.response({'recorded':True})
            if self.path.startswith('/api/private/') and body.get('identity') != IDENTITY:
                return self.response({}, 409)
            if self.path == '/api/private/evaluate':
                return self.response({**data['evaluation_identity'], 'success':False,
                                      'score':0., 'progress_score':None, 'steps':data['steps'],
                                      'evidence':{'synthetic':True}})
            if self.path == '/api/private/seal' and data['seal_error']:
                return self.response({}, 503)
            if self.path == '/api/private/close' and data.get('close_error'):
                return self.response({}, 503)
            if data.get('support_recovery'):
                if self.path in ('/api/private/recovery/begin','/api/private/recovery/end'):
                    data['recovery_id']=body['recovery_id'] if self.path.endswith('/begin') else None
                    return self.response(dict(identity=IDENTITY,state=state(),owner_barrier=dict(
                        schema='videoicl-owner-action-barrier-v1',action_count=data['steps'],status=data['status'],
                        recovery_id=data['recovery_id'],model_stop=data.get('model_stop'),
                        terminal_snapshot_ready=data.get('sealed',False))))
                if self.path=='/api/private/seal':
                    data['sealed']=True
                    if data['status']=='running':data['status']='finished'
            if self.path.startswith('/api/private/'):
                return self.response({'ok':True})
            if self.path == '/api/action':
                if data.get('uncertain_next_action'):
                    data['uncertain_next_action'] = False
                    return self.response({'error':'api_timing_uncertain'}, 503)
                if data.get('pending_next_action'):
                    data['pending_next_action'] = False
                    return self.response({'error':'operation_pending'}, 409)
                if data['fail_next_action']:
                    data['fail_next_action'] = False
                    return self.response({'error':'action_execution_failed'}, 503)
                if data['reject_next_action']:
                    data['reject_next_action'] = False
                    return self.response({'error':'stale_frame'}, 409)
                if body.get('frame_id') != 'native-frame-' + str(data['frame']):
                    return self.response({'error':'stale_frame'}, 409)
                data['steps'] += 1
                if data['steps'] >= data['max_actions']:
                    data['status'] = 'budget_exhausted'
                return self.response({'state':state()})
            if self.path in ('/api/done', '/api/giveup'):
                data['status'] = 'done' if self.path == '/api/done' else 'give_up'
                data['model_stop']=data['status'];data['sealed']=True
                return self.response(dict(state=state(), score=.99, success=True))
            return self.response({}, 404)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    data['url'] = 'http://127.0.0.1:' + str(server.server_port)
    try:
        yield data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def browser(tmp_path, gui_controller, chrome_path):
    gui_controller['condition'] = 'text_rule'
    config = dict(control_url=gui_controller['url'], actor_token='actor-test',
        run_id='test-run', output_dir=str(tmp_path), condition='text_rule',
        max_actions=6, timeout_seconds=90, browser_path=chrome_path,
        gui_observation_timeout_ms=3000, gui_settle_timeout_ms=3000)
    result = GuiBrowser(config)
    try:
        yield result
    finally:
        result.close()


def metadata(result):
    assert [c.type for c in result.content] == ['text', 'image']
    return json.loads(result.content[0].text)


@pytest.mark.parametrize('terminal_status',['budget_exhausted','finished'])
def test_effective_budget_ignores_old_deadline_and_polls_terminal_without_resetting_edit(
        tmp_path,gui_controller,chrome_path,terminal_status):
    from vic_sdk.native_stop_hook import decision
    gui_controller['condition']='text_rule'
    config=dict(control_url=gui_controller['url'],actor_token='actor-test',run_id='test-run',
        output_dir=str(tmp_path),condition='text_rule',max_actions=6,timeout_seconds=1,
        deadline_unix=time.time()-100,budget_policy='effective_time_graceful_v1',
        browser_path=chrome_path,gui_observation_timeout_ms=0,gui_settle_timeout_ms=0)
    robot=GuiBrowser(config)
    try:
        robot.check()
        assert metadata(robot.observe())['remaining_seconds'] is None
        robot.page.locator('#step-mm').fill('17')
        robot.page.wait_for_timeout(1200)
        assert robot.page.locator('#step-mm').input_value()=='17'
        assert decision(config).get('decision')=='block'  # Old deadline is ignored.
        gui_controller['status']=terminal_status
        robot.page.wait_for_function("status=>document.body.dataset.episodeStatus===status",arg=terminal_status,timeout=3500)
        assert robot.page.locator('#step-mm').input_value()=='17'
        assert robot.page.locator('#commit').is_disabled()
        assert metadata(robot.observe())['episode_status']==terminal_status
        robot.observe()
        records=[json.loads(x) for x in (tmp_path/'computer.jsonl').read_text().splitlines()]
        assert len([x for x in records if x['type']=='environment_terminal'])==1
        assert decision(config)=={}
        assert not (tmp_path/'environment-error.json').exists()
        assert not any(x[1] in ('/api/action','/api/done','/api/giveup') for x in gui_controller['calls'])
    finally:
        robot.close()


def test_zero_gui_wait_timeout_is_not_enabled_for_legacy_policy(tmp_path):
    with pytest.raises(ValueError,match='GUI timeouts'):
        GuiBrowser(dict(control_url='http://127.0.0.1:1',actor_token='test',run_id='test',
            output_dir=str(tmp_path),condition='text_rule',max_actions=2,
            gui_settle_timeout_ms=0,gui_observation_timeout_ms=0))


def click(browser, selector):
    box = browser.page.locator(selector).bounding_box()
    return dict(kind='click', x=box['x']+box['width']/2, y=box['y']+box['height']/2)


def action_posts(controller):
    return [entry for entry in controller['calls'] if entry[1] == '/api/action']


def test_actual_chrome_screenshot_and_six_gui_inputs_are_one_native_commit(browser, gui_controller):
    first = metadata(browser.observe())
    assert (first['width'], first['height']) == (1440, 1280)
    assert first['remaining_gui_inputs'] == 30 and first['max_robot_actions'] == 6
    assert set(first) == {'frame_id','width','height','remaining_seconds',
        'remaining_gui_inputs','max_robot_actions','episode_status','observation',
        'public_observation','camera_views'}
    assert first['public_observation']['robot_feedback']['arms']['left']['tcp_position'] == [.1,.2,.3]
    assert 'PRIVATE_' not in json.dumps(first)
    assert first['public_observation']['action_schema']['step_mm']['maximum'] == 50
    result = browser.act(first['frame_id'], [click(browser, '#left-actions [data-token="UP"]'),
        click(browser, '#step-mm'), dict(kind='key',key='ControlOrMeta+A'),
        dict(kind='text',text='7.5'), click(browser, '#right-actions [data-token="STILL"]'),
        click(browser, '#commit')])
    after = metadata(result)
    assert after['remaining_gui_inputs'] == 24
    assert len(action_posts(gui_controller)) == 1 and gui_controller['steps'] == 1
    assert action_posts(gui_controller)[0][3]['step_mm'] == 7.5
    assert action_posts(gui_controller)[0][3]['left'] == 'UP'
    assert 'PRIVATE_' not in browser.page.locator('body').inner_text()
    with pytest.raises(ValueError, match='most recent'):
        browser.act(first['frame_id'], [dict(kind='wait',wait_ms=0)])


def test_common_key_spellings_and_eleven_edits_are_one_physical_commit(browser,gui_controller):
    first = metadata(browser.observe())
    inputs = [click(browser,'#left-actions [data-token="UP"]'),
        click(browser,'#right-actions [data-token="STILL"]'),
        click(browser,'#step-mm'),dict(kind='key',key='CTRL+A'),
        dict(kind='key',key='BACKSPACE'),dict(kind='text',text='7.5'),
        click(browser,'#rotation-deg'),dict(kind='key',key='Control+A'),
        dict(kind='key',key='DELETE'),dict(kind='text',text='5'),click(browser,'#commit')]
    browser.act(first['frame_id'],inputs)
    posts = action_posts(gui_controller)
    assert len(posts)==1 and posts[0][3]['step_mm']==7.5 and posts[0][3]['rotation_deg']==5.
    assert browser.actions==11


@pytest.mark.parametrize('key', ['Enter', 'Space'])
def test_keyboard_cannot_bypass_one_commit_per_act(browser, gui_controller, key):
    first = metadata(browser.observe())
    with pytest.raises(ValueError, match='at most one robot commit'):
        browser.act(first['frame_id'], [click(browser, '#commit'),
            click(browser, '#rotation-deg'), dict(kind='key',key='Tab'), dict(kind='key',key=key)])
    assert len(action_posts(gui_controller)) == 1
    assert browser.frame is None
    fresh = metadata(browser.observe())
    browser.act(fresh['frame_id'], [dict(kind='key',key=key)])
    assert len(action_posts(gui_controller)) == 2


def test_double_click_commit_is_rejected_before_execution(browser, gui_controller):
    first = metadata(browser.observe())
    value = {**click(browser, '#commit'), 'kind':'double_click'}
    with pytest.raises(ValueError, match='at most one robot commit'):
        browser.act(first['frame_id'], [value])
    assert action_posts(gui_controller) == []


def test_native_action_transport_failure_requires_refresh_without_replay(browser, gui_controller):
    first = metadata(browser.observe())
    gui_controller['fail_next_action'] = True
    result = browser.act(first['frame_id'], [click(browser, '#commit')])
    assert metadata(result)['episode_status'] == 'running'
    assert not (browser.output / 'environment-error.json').exists()
    assert len(action_posts(gui_controller)) == 1
    assert browser.page.locator('#commit').is_disabled()
    gui_controller['status'] = 'faulted'
    browser.page.locator('#refresh').click();browser._settled()
    assert metadata(browser.observe())['episode_status'] == 'faulted'
    assert (browser.output / 'environment-error.json').exists()
    assert len(action_posts(gui_controller)) == 1


@pytest.mark.parametrize('field', ['#step-mm', '#rotation-deg'])
def test_enter_inside_numeric_form_counts_as_physical_commit(browser, gui_controller, field):
    first = metadata(browser.observe())
    with pytest.raises(ValueError, match='at most one robot commit'):
        browser.act(first['frame_id'], [click(browser, field), dict(kind='key',key='Enter'),
            click(browser, field), dict(kind='key',key='Enter')])
    assert len(action_posts(gui_controller)) == 1 and gui_controller['steps'] == 1


@pytest.mark.parametrize('kind,status', [('done','done'), ('giveup','give_up')])
def test_terminal_uses_visible_gui_and_is_idempotent(browser, gui_controller, kind, status):
    browser.observe()
    result = browser.terminal(kind, 'Synthetic stop reason', browser.frame)
    assert metadata(result)['episode_status'] == status
    stops = [x for x in gui_controller['calls'] if x[1] in ('/api/done','/api/giveup')]
    assert len(stops) == 1 and stops[0][1] == '/api/' + kind
    assert stops[0][3] == ({'frame_id':'native-frame-1','summary':'Synthetic stop reason'} if kind == 'done'
                            else {'frame_id':'native-frame-1','reason':'Synthetic stop reason'})
    assert metadata(browser.observe())['episode_status'] == status
    browser.terminal(kind, 'Already terminal', browser.frame)
    assert len([x for x in gui_controller['calls'] if x[1] in ('/api/done','/api/giveup')]) == 1
    assert browser.page.locator('#done').is_disabled()


@pytest.mark.parametrize('kind,status', [('done','done'), ('giveup','give_up')])
@pytest.mark.parametrize('enlarged', [False, True])
def test_terminal_restores_enlarged_camera_with_visible_click(browser, gui_controller, kind, status, enlarged):
    browser.observe()
    if enlarged:
        browser.page.locator('figure.camera:has(#camera-left_wrist) .camera-zoom').click()
    browser.page.evaluate('''() => {
        window.terminalTestClicks = [];
        document.addEventListener('click', event => {
            if (event.target.matches('.camera-zoom, #done, #giveup'))
                window.terminalTestClicks.push(event.target.id || 'camera-zoom');
        }, true);
    }''')
    result = browser.terminal(kind, 'Close the visible enlarged camera first', browser.frame)
    assert metadata(result)['episode_status'] == status
    assert browser.page.locator('.camera.camera-enlarged').count() == 0
    assert browser.page.evaluate('window.terminalTestClicks') == (['camera-zoom'] if enlarged else []) + [kind]
    stops = [row for row in gui_controller['calls'] if row[1] in ('/api/done', '/api/giveup')]
    assert len(stops) == 1 and stops[0][1] == '/api/' + kind
    assert action_posts(gui_controller) == []
    assert not (browser.output / 'gui-input-pending.private.json').exists()


@pytest.mark.parametrize('kind', ['done', 'giveup'])
def test_terminal_camera_restore_failure_has_no_terminal_intent(browser, gui_controller, kind):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    browser.observe()
    browser.page.locator('figure.camera:has(#camera-left_wrist) .camera-zoom').click()
    browser.page.add_style_tag(content='.camera-enlarged .camera-zoom { pointer-events: none; }')
    browser.page.set_default_timeout(250)
    with pytest.raises(PlaywrightTimeoutError):
        browser.terminal(kind, 'The restore control is obstructed', browser.frame)
    assert browser.page.locator('.camera.camera-enlarged').count() == 1
    assert not (browser.output / 'gui-input-pending.private.json').exists()
    assert not any(row[1] in ('/api/action', '/api/done', '/api/giveup')
                   for row in gui_controller['calls'])


@pytest.mark.parametrize('status', ['budget_exhausted','faulted'])
def test_already_terminal_acknowledged_without_disabled_click(browser, gui_controller, status):
    gui_controller['status'] = status
    browser.page.locator('#refresh').click()
    browser._settled()
    browser.closed = True
    browser.config['deadline_unix'] = time.time() - 10
    assert metadata(browser.observe())['episode_status'] == status
    assert metadata(browser.terminal('done', 'Acknowledge stop', browser.frame))['episode_status'] == status
    assert not any(x[1] in ('/api/done','/api/giveup') for x in gui_controller['calls'])


def test_gui_budget_does_not_consume_physical_budget_or_block_stop(browser, gui_controller):
    browser.max_gui_inputs = 2
    first = metadata(browser.observe())
    result = browser.act(first['frame_id'], [dict(kind='wait',wait_ms=0)] * 2)
    assert metadata(result)['remaining_gui_inputs'] == 0
    with pytest.raises(ValueError, match='GUI input budget'):
        browser.act(browser.frame, [dict(kind='wait',wait_ms=0)])
    assert action_posts(gui_controller) == []
    assert metadata(browser.terminal('giveup','GUI budget used', browser.frame))['episode_status'] == 'give_up'


def test_stale_native_frame_is_not_replayed_and_gui_requires_refresh(browser, gui_controller):
    first = metadata(browser.observe())
    gui_controller['reject_next_action'] = True
    result = browser.act(first['frame_id'], [click(browser, '#commit')])
    assert metadata(result)['episode_status'] == 'running'
    assert len(action_posts(gui_controller)) == 1 and gui_controller['steps'] == 0
    assert browser.page.locator('#commit').is_disabled()
    result = browser.act(browser.frame, [click(browser,'#refresh')])
    assert browser.page.locator('#commit').is_enabled()
    browser.act(metadata(result)['frame_id'], [click(browser,'#commit')])
    assert len(action_posts(gui_controller)) == 2 and gui_controller['steps'] == 1


def test_native_action_budget_stops_even_with_gui_budget_remaining(browser, gui_controller):
    gui_controller['max_actions'] = 1
    first = metadata(browser.observe())
    after = metadata(browser.act(first['frame_id'], [click(browser,'#commit')]))
    assert after['episode_status'] == 'budget_exhausted'
    assert after['remaining_gui_inputs'] == 29
    assert metadata(browser.terminal('giveup','Budget reached', browser.frame))['episode_status'] == 'budget_exhausted'
    assert gui_controller['steps'] == 1


def test_only_gui_and_assigned_video_tools_are_exposed(browser):
    with ThreadPoolExecutor() as executor:
        tools = executor.submit(asyncio.run, make_server(browser).list_tools()).result()
    assert {t.name for t in tools} == {'observe','act','done','giveup','depth_points'}
    browser.condition = 'real'
    with ThreadPoolExecutor() as executor:
        tools = executor.submit(asyncio.run, make_server(browser).list_tools()).result()
    assert {t.name for t in tools} == {'observe','act','done','giveup','depth_points','demo_info','demo_frame','demo_frames'}


@pytest.mark.parametrize('kind', ['done', 'giveup'])
def test_batch_commit_cannot_terminate_before_returning_new_observation(browser, gui_controller, kind):
    first = metadata(browser.observe())
    with pytest.raises(ValueError, match='Observe the completed operation'):
        browser.act(first['frame_id'], [click(browser, '#commit'), click(browser, '#' + kind)])
    assert len(action_posts(gui_controller)) == 1
    assert not any(x[1] in ('/api/done', '/api/giveup') for x in gui_controller['calls'])
    with pytest.raises(ValueError, match='Observe first'):
        browser.terminal(kind, 'No new observation yet', first['frame_id'])
    browser.observe()
    browser.terminal(kind, 'Decision after observing the result', browser.frame)
    assert len([x for x in gui_controller['calls'] if x[1] == '/api/' + kind]) == 1


def test_rejected_text_does_not_create_an_uncertain_input(browser, gui_controller):
    first = metadata(browser.observe())
    with pytest.raises(ValueError, match='editable field'):
        browser.act(first['frame_id'], [dict(kind='text', text='invalid focus')])
    assert not (browser.output / 'gui-input-pending.private.json').exists()
    browser.observe()
    assert not action_posts(gui_controller)


@pytest.mark.parametrize('method', ['observe', 'act', 'terminal'])
def test_live_browser_cannot_overwrite_an_uncertain_pending_input(browser, method):
    first = metadata(browser.observe())
    marker = browser.output / 'gui-input-pending.private.json'
    original = b'{"input_id":"unreconciled"}'
    marker.write_bytes(original)
    args = {'observe': (), 'act': (first['frame_id'], [dict(kind='wait', wait_ms=0)]),
            'terminal': ('done', 'claim', first['frame_id'])}[method]
    with pytest.raises(RuntimeError, match='controller reconciliation'):
        getattr(browser, method)(*args)
    assert marker.read_bytes() == original


@pytest.mark.parametrize('kind', ['done', 'giveup'])
def test_terminal_requires_exact_latest_returned_frame(browser, gui_controller, kind):
    old = metadata(browser.observe())['frame_id']
    # Simulate a new screenshot completing after the caller cancelled its wait:
    # it exists in the browser, but the caller still only knows the old id.
    fresh = metadata(browser.observe())['frame_id']
    for invalid in (None, '', old):
        with pytest.raises(ValueError, match='most recent GUI frame_id'):
            browser.terminal(kind, 'No current observation acknowledgement', invalid)
    assert not any(x[1] in ('/api/done', '/api/giveup') for x in gui_controller['calls'])
    browser.terminal(kind, 'Decision based on current observation', fresh)


def test_terminal_mcp_schema_requires_frame_acknowledgement(browser):
    with ThreadPoolExecutor() as executor:
        tools = executor.submit(asyncio.run, make_server(browser).list_tools()).result()
    for tool in tools:
        if tool.name in ('done', 'giveup'):
            assert 'frame_id' in tool.inputSchema['required']


def test_public_pending_notice_is_not_a_fault_or_terminal_decision(browser, gui_controller):
    first = metadata(browser.observe())
    gui_controller['pending_next_action'] = True
    result = browser.act(first['frame_id'], [click(browser, '#commit')])
    assert metadata(result)['episode_status'] == 'running'
    assert 'An operation is pending' in browser.page.locator('#notice').inner_text()
    assert browser.page.locator('#done').is_disabled()
    assert browser.page.locator('#giveup').is_disabled()
    assert not (browser.output / 'environment-error.json').exists()
    with pytest.raises(ValueError, match='refresh the GUI observation'):
        browser.terminal('done', 'No native observation yet', browser.frame)
    assert not (browser.output / 'gui-input-pending.private.json').exists()
    browser.act(browser.frame, [click(browser, '#refresh')])
    assert browser.page.locator('#done').is_enabled()
    assert gui_controller['steps'] == 0


def test_observation_waits_for_visible_camera_decode(browser):
    browser.page.evaluate("""() => {
        window.testImageReady = false;
        Object.defineProperty(document.getElementById('camera-head'), 'complete',
            {configurable:true, get:() => window.testImageReady});
        setTimeout(() => {window.testImageReady = true;}, 200);
    }""")
    started = time.monotonic()
    result = browser.observe()
    assert time.monotonic() - started >= .15
    assert metadata(result)['episode_status'] == 'running'


@pytest.mark.parametrize('failure',['timing','http500','network'])
def test_transport_error_preserves_native_status_and_requires_refresh(browser, gui_controller, failure):
    first=metadata(browser.observe())
    if failure=='timing':gui_controller['uncertain_next_action']=True
    elif failure=='http500':browser.page.route('**/api/action',lambda route:route.fulfill(status=500,body='{}',content_type='application/json'))
    else:browser.page.route('**/api/action',lambda route:route.abort('failed'))
    result=browser.act(first['frame_id'],[click(browser,'#commit')])
    assert metadata(result)['episode_status']=='running'
    assert gui_controller['steps']==0
    assert not (browser.output/'environment-error.json').exists()
    assert browser.page.locator('#commit').is_disabled()
    count=len(action_posts(gui_controller))
    browser.page.unroute('**/api/action')
    browser.page.locator('#refresh').click();browser._settled()
    assert metadata(browser.observe())['episode_status']=='running'
    assert len(action_posts(gui_controller))==count
    assert not browser.page.locator('#commit').is_disabled()
