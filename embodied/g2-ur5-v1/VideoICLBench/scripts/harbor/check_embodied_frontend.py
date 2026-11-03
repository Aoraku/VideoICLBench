"""Browser contract checks using a SYNTHETIC transport, never a simulator.

Run with the workspace's Playwright/Pillow Python. Images and optional demo
are artificial fixtures labelled in the page; passing is not native evidence.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2] / 'apps/portal/public/embodied'
TOKEN = 'synthetic-test-token-not-a-credential'


@contextmanager
def fixture_server(condition='text_rule'):
    image = Image.new('RGB', (320, 240), '#dfe7f3')
    draw = ImageDraw.Draw(image)
    draw.text((18, 90), 'SYNTHETIC UI FIXTURE', fill='#32445f')
    draw.text((18, 115), 'NO SIMULATION', fill='#32445f')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    encoded = base64.b64encode(buffer.getvalue()).decode()
    temporary = tempfile.TemporaryDirectory(prefix='videoicl-frontend-fixture-')
    folder = Path(temporary.name)
    image.save(folder / 'frame.png')
    subprocess.run(['ffmpeg', '-v', 'error', '-loop', '1', '-i', str(folder/'frame.png'),
                    '-t', '1', '-r', '2', '-pix_fmt', 'yuv420p', str(folder/'demo.mp4')], check=True)
    log = []
    state = dict(run_id='synthetic-test-run', task_id='E05',
                 title='合成界面测试 — 非仿真',
                 instruction='【合成界面测试，无仿真】按分配的方法完成任务。',
                 status='running', steps=0, max_actions=100, condition=condition,
                 rule_reported=False, diagnostics_enabled=False, frame_id='frame-0',
                 demo_available=condition != 'text_rule',
                 action_schema=dict(tokens=['STILL', 'FWD', 'BACK', 'LEFT', 'RIGHT', 'UP', 'DOWN', 'GRASP', 'RELEASE', 'ROTATE_CCW', 'ROTATE_CW', 'PITCH_UP', 'PITCH_DOWN', 'ROLL_LEFT', 'ROLL_RIGHT'],
                                    step_mm=dict(minimum=.5, maximum=50, default=20),
                                    rotation_deg=dict(minimum=.5, maximum=20, default=10)),
                 robot_feedback=dict(coordinate_frame='task', units={'position':'m','joints':'rad'},
                     arms={side:dict(tcp_position=[.12,.24,.61],tcp_quaternion_wxyz=[1.,0.,0.,0.],
                         joint_names=['panda_joint1','panda_joint2'],joint_positions_rad=[.1,-.2],
                         gripper_open_fraction=.5,object_truth='DO_NOT_RENDER_ARM_OBJECT_TRUTH')for side in ['left','right']},
                     object_truth='DO_NOT_RENDER_FEEDBACK_OBJECT_TRUTH',score='DO_NOT_RENDER_ROBOT_SCORE'),
                 private_rule='DO_NOT_RENDER_PRIVATE_RULE', object_truth='DO_NOT_RENDER_OBJECT_TRUTH', success=True, score=.99)
    if condition == 'text_rule':
        state['text_rule'] = '这是本次文字条件分配的明确方法说明。'
    counter = 0
    reject_next_action = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, data, status=200, mime='application/json'):
            payload = json.dumps(data, ensure_ascii=False).encode() if mime == 'application/json' else data
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                self.reply(dict(error='unauthorized', message='DO_NOT_RENDER_PRIVATE_ERROR'), 401)
                return False
            return True

        def do_GET(self):
            nonlocal counter
            if self.path in ('/', '/app.js', '/style.css'):
                name = 'index.html' if self.path == '/' else self.path[1:]
                mime = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript', 'style.css': 'text/css'}[name]
                return self.reply((ROOT/name).read_bytes(), mime=mime)
            if not self.authorized():
                return
            log.append(dict(method='GET', path=self.path, authorized=True))
            if self.path == '/api/state':
                return self.reply(state)
            if self.path == '/api/observe':
                counter += 1
                state['frame_id'] = 'frame-' + str(counter)
                return self.reply(dict(frame_id=state['frame_id'], state=state,
                                       images={k: encoded for k in ['head', 'left_wrist', 'right_wrist']}))
            if self.path == '/demo.mp4' and condition != 'text_rule':
                return self.reply((folder/'demo.mp4').read_bytes(), mime='video/mp4')
            return self.reply(dict(error='not_found'), 404)

        def do_POST(self):
            nonlocal reject_next_action
            if not self.authorized():
                return
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            log.append(dict(method='POST', path=self.path, body=body, authorized=True))
            if self.path == '/api/report-inferred-rule':
                state['rule_reported'] = True
                return self.reply(dict(state=state))
            if self.path == '/api/action':
                if reject_next_action:
                    reject_next_action = False
                    return self.reply(dict(error='stale_frame', message='DO_NOT_RENDER_PRIVATE_ERROR'), 409)
                assert body['frame_id'] == state['frame_id']
                state['steps'] += 1
                state['robot_feedback']['arms']['left']['tcp_position'][2] = .625
                state['robot_feedback']['last_action'] = {**body,'tracking_error_m':{'left':.001,'right':.002},'hidden_objects':'DO_NOT_RENDER_LAST_ACTION_OBJECTS'}
                time.sleep(.05)
                return self.reply(dict(state=state))
            if self.path in ('/api/done','/api/giveup'):
                state['status'] = 'done' if self.path == '/api/done' else 'give_up'
                return self.reply(dict(status=state['status'], state=state, success=True, score=.99,private_score='DO_NOT_RENDER_TERMINAL_SCORE'))
            return self.reply(dict(error='not_found'), 404)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def reject():
        nonlocal reject_next_action
        reject_next_action = True
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), state, log, reject
    finally:
        server.shutdown()
        server.server_close()
        temporary.cleanup()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser-path', type=Path)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **({'executable_path': str(args.browser_path)} if args.browser_path else {}))
        try:
            with fixture_server() as (base, state, log, reject):
                page = browser.new_page(viewport=dict(width=1440, height=1000), device_scale_factor=1)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/#token=' + TOKEN)
                page.wait_for_function("document.querySelector('#camera-head').naturalWidth > 0 && document.body.getAttribute('aria-busy') === 'false'")
                assert page.evaluate('location.hash') == ''
                assert page.evaluate('localStorage.length + sessionStorage.length') == 0
                assert page.locator('#commit').is_enabled() and state['rule_reported'] is False
                assert page.locator('#rule-panel').is_hidden()
                assert page.locator('#text-reference').is_visible() and page.locator('#video-reference').is_hidden()
                assert page.locator('#done').is_enabled() and page.locator('#giveup').is_enabled()
                assert 'DO_NOT_RENDER' not in page.locator('body').inner_text()
                assert page.locator('body').get_attribute('data-episode-status') == 'running'
                checks.append('token fragment removed; no storage/private object or score fields; text condition has no video and no diagnostic gate')
                feedback = page.locator('#robot-feedback').inner_text()
                assert 'task' in feedback and '0.61' in feedback and '50.0%' in feedback
                page.locator('#robot-feedback .arm-feedback details').first.locator('summary').click()
                assert 'panda_joint1' in page.locator('#robot-feedback').inner_text()
                assert 'DO_NOT_RENDER' not in page.locator('#robot-feedback').inner_text()
                checks.append('robot-only TCP/quaternion/joint/gripper feedback is visible; arbitrary object/score fields are suppressed')
                assert page.locator('#left-actions .action-button').count() == 15
                assert page.locator('#right-actions .action-button').count() == 15
                page.locator('#action-guide summary').click()
                guide = page.locator('#action-guide-content').inner_text()
                for token in state['action_schema']['tokens']:
                    assert token in guide
                assert 'task +X' in guide and 'task +Y' in guide and 'task +Z' in guide
                assert '0.5–50 mm' in page.locator('#parameter-help').inner_text()
                assert '0.5–20°' in page.locator('#parameter-help').inner_text()
                checks.append('all15 native controls have bilingual help and dynamic millimetre/degree limits; public task axes are documented')
                page.locator('#action-guide summary').click()
                page.locator('#left-actions [data-token="UP"]').click()
                page.locator('#right-actions [data-token="GRASP"]').click()
                page.locator('#step-mm').fill('15')
                page.locator('#rotation-deg').fill('5')
                assert not any(item['path'] == '/api/action' for item in log)
                assert state['steps'] == 0
                page.screenshot(path=str(output/'synthetic-text-initial.png'), full_page=True)
                page.locator('#commit').click()
                page.wait_for_function("document.querySelector('#budget').textContent.startsWith('1 /') && document.body.getAttribute('aria-busy') === 'false'")
                actions = [item for item in log if item['path'] == '/api/action']
                assert len(actions) == 1
                assert actions[0]['body'] == dict(frame_id='frame-1', left='UP', right='GRASP', step_mm=15, rotation_deg=5)
                assert '0.625' in page.locator('#robot-feedback').inner_text()
                assert 'UP / GRASP' in page.locator('#robot-feedback').inner_text()
                assert not any(item['path'] == '/api/report-inferred-rule' for item in log)
                checks.append('GUI click/type/select does not step physics until a single Commit; native paired-action request and feedback are preserved')
                reject()
                page.locator('#commit').click()
                page.wait_for_function("document.querySelector('#notice').textContent.includes('本次动作未执行') && document.body.getAttribute('aria-busy') === 'false'")
                assert page.locator('#commit').is_disabled()
                assert len([item for item in log if item['path'] == '/api/action']) == 2
                page.locator('#refresh').click()
                page.wait_for_function("!document.querySelector('#commit').disabled && document.body.getAttribute('aria-busy') === 'false'")
                assert len([item for item in log if item['path'] == '/api/action']) == 2
                checks.append('stale-frame action is not replayed; refresh is required and never adds a physical action')
                page.set_viewport_size(dict(width=390, height=844))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output/'synthetic-mobile.png'), full_page=True)
                checks.append('390px viewport has no horizontal overflow with15 controls and robot feedback')
                page.locator('#stop-reason').fill('合成接口 Done 检查，不是任务成功证据。')
                page.locator('#done').click()
                page.wait_for_function("document.body.dataset.episodeStatus === 'done' && document.body.getAttribute('aria-busy') === 'false'")
                assert page.locator('#commit').is_disabled() and page.locator('#done').is_disabled() and page.locator('#giveup').is_disabled()
                done = next(item for item in log if item['path'] == '/api/done')
                assert done['body'] == {'summary':'合成接口 Done 检查，不是任务成功证据。'}
                assert 'DO_NOT_RENDER' not in page.locator('body').inner_text()
                assert not any(item['path'] == '/api/finish' for item in log)
                checks.append('visible Done button posts done and locks both action and stop controls without displaying a score')
                page.close()
            for condition in ('real','sim'):
                with fixture_server(condition) as (base, state, log, _):
                    page = browser.new_page(viewport=dict(width=1440, height=1000))
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base+'/#token='+TOKEN)
                    page.wait_for_function("document.querySelector('#demo').readyState >= 2 && document.body.getAttribute('aria-busy') === 'false'")
                    assert page.locator('#commit').is_enabled() and state['rule_reported'] is False
                    assert page.locator('#rule-panel').is_hidden()
                    assert page.locator('#video-reference').is_visible() and page.locator('#text-reference').is_hidden()
                    assert page.locator('#demo').get_attribute('src').startswith('blob:')
                    assert page.evaluate("document.querySelector('#demo').muted")
                    assert any(item['path'] == '/demo.mp4' and item['authorized'] for item in log)
                    assert not any(item['path'] == '/api/report-inferred-rule' for item in log)
                    assert page.locator('#left-actions .action-button').count() == 15
                    page.screenshot(path=str(output/('synthetic-'+condition+'-condition.png')), full_page=True)
                    page.locator('#stop-reason').fill('合成接口 Give up 检查。')
                    page.locator('#giveup').click()
                    page.wait_for_function("document.body.dataset.episodeStatus === 'give_up' && document.body.getAttribute('aria-busy') === 'false'")
                    assert page.locator('#commit').is_disabled() and page.locator('#done').is_disabled() and page.locator('#giveup').is_disabled()
                    giveup = next(item for item in log if item['path'] == '/api/giveup')
                    assert giveup['body'] == {'reason':'合成接口 Give up 检查。'}
                    assert 'DO_NOT_RENDER' not in page.locator('body').inner_text()
                    checks.append(condition+' video is bearer-fetched/muted with no mandatory diagnosis; visible Give up posts distinct stop reason and returns no score')
                    page.close()
            with fixture_server('real') as (base,state,log,_):
                state['diagnostics_enabled'] = True
                page = browser.new_page(viewport=dict(width=1440,height=1000))
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#token='+TOKEN)
                page.wait_for_function("document.body.getAttribute('aria-busy') === 'false' && document.querySelector('#camera-head').naturalWidth > 0")
                assert page.locator('#rule-panel').is_visible() and page.locator('#commit').is_enabled()
                page.locator('#inferred-rule').fill('可选记录，未检查正确性。')
                page.locator('#evidence-seconds').fill('0.1,0.8')
                page.locator('#report-rule').click()
                page.wait_for_function("document.body.getAttribute('aria-busy') === 'false' && document.querySelector('#report-rule').disabled")
                assert page.locator('#commit').is_enabled()
                assert next(item for item in log if item['path']=='/api/report-inferred-rule')['body']['evidence_seconds'] == [.1,.8]
                checks.append('explicit optional diagnostic panel never gates real-video physical controls')
                page.close()
            assert errors == [], errors
        finally:
            browser.close()
    result = dict(scope='SYNTHETIC GUI transport and layout checks; no native simulator/model/scientific score tested',
                  agent_protocol='roboprobe_gui_v1',passed=True,checks=checks,browser_errors=errors)
    (output/'browser-contract.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
