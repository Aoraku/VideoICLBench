"""Demo-only hosted VLM operator. Standard library; no browser extension or source tools."""
import argparse
import base64
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
CAMERAS = ('overhead', 'agentview', 'wrist_left', 'wrist_right')
TOKENS = frozenset('MV_FWD MV_BACK MV_LEFT MV_RIGHT MV_UP MV_DOWN ROTATE_CW ROTATE_CCW ROLL_POS ROLL_NEG PITCH_POS PITCH_NEG GRASP RELEASE STILL'.split())
PROMPT = (HERE / 'prompt.txt').read_text()


def request(url, body=None, headers=None, timeout=180):
    req = Request(url, data=None if body is None else json.dumps(body).encode(),
                  headers={'Content-Type': 'application/json', **(headers or {})})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def public_state(state):
    # Independent whitelist, even if the environment later adds privileged fields.
    return {k: state[k] for k in ('status', 'steps', 'max_pairs', 'gripper_closed')}


def decision(text):
    d = json.loads(text)
    if not isinstance(d, dict) or set(d) != {'left', 'right', 'step_m', 'finish', 'summary'}:
        raise ValueError('Invalid decision fields')
    if any(not isinstance(d[a], str) or d[a] not in TOKENS for a in ('left', 'right')):
        raise ValueError('Invalid action')
    if type(d['step_m']) not in (int, float) or d['step_m'] not in (.005, .01, .02):
        raise ValueError('Invalid step size')
    if type(d['finish']) is not bool or not isinstance(d['summary'], str) or len(d['summary']) > 400:
        raise ValueError('Invalid finish/summary')
    if d['left'] != 'STILL':
        raise ValueError('This backend has only a right arm')
    if d['finish'] and (d['left'] != 'STILL' or d['right'] != 'STILL'):
        raise ValueError('Finish cannot contain movement')
    return d


def payload(model, demos, observation, history):
    content = []
    def picture(label, b64):
        content.extend([{'type': 'text', 'text': label},
                        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + b64}}])
    for i, data in enumerate(demos):
        picture(f'Demonstration frame {i+1}/16 (chronological)', data)
    for name in CAMERAS:
        picture('Current camera: ' + name, observation['images'][name])
    content.append({'type': 'text', 'text': json.dumps({
        'feedback': public_state(observation['state']), 'recent_history': history[-8:]})})
    return {'model': model, 'messages': [{'role': 'system', 'content': PROMPT},
                                       {'role': 'user', 'content': content}],
            'max_completion_tokens': 2048}


class Operator:
    def __init__(self, target, base_url, model, key, log_root, max_calls=400):
        self.target, self.base_url, self.model, self.key = target.rstrip('/'), base_url.rstrip('/'), model, key
        self.lock = threading.RLock()
        self.mode = 'paused'
        self.busy = False
        self.generation = 0
        self.calls, self.max_calls = 0, max_calls
        self.events, self.history, self.demos = [], [], []
        self.latest = None
        self.input = None
        self.run_dir = Path(log_root) / uuid.uuid4().hex[:12]
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / 'prompt.txt').write_text(PROMPT)
        self.event('ready', mode='hosted_http', model=model, configured=self.configured)

    @property
    def configured(self):
        return bool(self.base_url and self.model and self.key)

    def event(self, kind, **data):
        with self.lock:
            e = {'id': len(self.events), 'time': time.time(), 'kind': kind, **data}
            self.events.append(e)
            with (self.run_dir / 'events.jsonl').open('a') as f:
                f.write(json.dumps(e) + '\n')

    def env(self, path, body):
        result = json.loads(request(self.target + path, body))
        if not result.get('ok'):
            raise ValueError('Environment rejected request; refresh before retrying')
        return result

    def observe(self):
        obs = self.env('/api/observe', {})
        clean = {'observation_id': obs['observation_id'], 'state': public_state(obs['state']),
                 'images': {k: obs['images'][k] for k in CAMERAS}}
        with self.lock:
            self.latest = clean
        return clean

    def status(self):
        with self.lock:
            return {'mode': self.mode, 'busy': self.busy, 'configured': self.configured,
                    'model': self.model, 'calls': self.calls, 'max_calls': self.max_calls,
                    'events': self.events[-100:], 'input': self.input, 'prompt': PROMPT,
                    'protocol': 'hosted_http', 'demo_frames': self.demos,
                    'configuration_hint': '' if self.configured else 'Set VLM_BASE_URL, VLM_MODEL and VLM_API_KEY on the server.'}

    def control(self, command):
        with self.lock:
            if command in ('pause', 'stop'):
                self.generation += 1
                self.mode = 'stopped' if command == 'stop' else ('stopped' if self.mode == 'stopped' else 'paused')
                self.event(command)
                return
            if command not in ('run', 'once'):
                raise ValueError('Unknown control')
            if self.mode == 'stopped' or self.busy:
                raise ValueError('Stopped or busy; wait for the pending call')
            if not self.configured:
                raise ValueError('Configure the server model credentials first')
            if self.calls >= self.max_calls:
                raise ValueError('Model call budget exhausted')
            self.mode = 'running' if command == 'run' else 'single'
            self.busy = True
            generation = self.generation
            threading.Thread(target=self.loop, args=(generation,), daemon=True).start()

    def loop(self, generation):
        try:
            while True:
                with self.lock:
                    if generation != self.generation or self.calls >= self.max_calls:
                        break
                self.turn(generation)
                with self.lock:
                    if self.mode != 'running' or generation != self.generation:
                        break
        except Exception as e:
            # Provider errors may echo headers or credentials. Never log their bodies/str().
            self.event('error', error_type=type(e).__name__, message='Paused after failed request or invalid response. No automatic retry.')
        finally:
            with self.lock:
                self.busy = False
                if self.mode != 'stopped':
                    self.mode = 'paused'

    def turn(self, generation):
        obs = self.observe()
        with self.lock:
            if generation != self.generation:
                return
            if obs['state']['status'] == 'submitted':
                self.mode = 'stopped'
                return
            if obs['state']['status'] == 'ready':
                self.env('/api/start', {'expected_observation': obs['observation_id']})
        obs = self.observe()
        if not self.demos:
            self.demos = [base64.b64encode(request(self.target + f'/demo-frame/{i:02}.jpg')).decode() for i in range(16)]
        p = payload(self.model, self.demos, obs, self.history)
        with self.lock:
            if generation != self.generation:
                return
            self.input = {'state': obs['state'], 'images': obs['images']}
            self.calls += 1
            call = self.calls
        # Exact image inputs + public history, no API keys or source/state truth.
        (self.run_dir / f'{call:04}_request.json').write_text(json.dumps(p))
        self.event('observed', call=call, steps=obs['state']['steps'])
        started = time.monotonic()
        raw = json.loads(request(self.base_url + '/chat/completions', p,
                                 {'Authorization': 'Bearer ' + self.key}))
        text = raw['choices'][0]['message']['content']
        # Deliberately do not persist provider reasoning_content or raw response metadata.
        d = decision(text)
        self.event('decision', call=call, decision=d, latency_s=round(time.monotonic()-started, 2))
        with self.lock:
            if generation != self.generation:
                self.event('discarded', call=call, message='Paused/stopped while model was responding')
                return
            if not d['finish'] and obs['state']['steps'] >= obs['state']['max_pairs']:
                raise ValueError('Action budget exhausted')
            body = {'expected_observation': obs['observation_id']}
            path = '/api/stop' if d['finish'] else '/api/step'
            if not d['finish']:
                body.update(left=[d['left']], right=[d['right']], step_m=d['step_m'])
            # Serialize control/dispatch. Pause cannot undo an already dispatched pair.
            result = self.env(path, body)
            feedback = public_state(result['state'])
            self.history.append({'decision': d, 'feedback': feedback})
            self.event('executed', call=call, endpoint=path, decision=d, feedback=feedback)
            if d['finish']:
                self.mode = 'stopped'


def serve(op, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, data, mime='application/json', code=200):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def environment_proxy(self, path, body=None):
            allowed_get = {'/api/state', '/recorder.js', '/demo.mp4'} | {
                '/stream/'+name for name in CAMERAS} | {'/snapshot/'+name for name in CAMERAS} | {f'/demo-frame/{i:02}.jpg' for i in range(16)}
            allowed_post = {'/api/start', '/api/step', '/api/stop', '/api/ui-event'}
            if path not in (allowed_get if body is None else allowed_post):
                return self.reply({}, code=404)
            if body is not None:
                with op.lock:
                    if path != '/api/ui-event' and (op.busy or op.mode in ('running', 'single')):
                        return self.reply({'ok':False,'message':'Pause Hosted operator before using GUI controls.'})
                    data=json.loads(request(op.target+path, body))
                    if path != '/api/ui-event':
                        op.event('gui_action', endpoint=path, ok=data.get('ok',False),
                                 actions={k:body[k] for k in ('left','right','step_m') if k in body})
                    return self.reply(data)
            if path == '/api/state':
                data=json.loads(request(op.target+path))
                data['controls_locked']=op.busy or op.mode in ('running','single')
                return self.reply(data)
            headers={'Range':self.headers['Range']} if self.headers.get('Range') else {}
            with urlopen(Request(op.target+path,headers=headers),timeout=30) as source:
                self.send_response(source.status)
                for key in ('Content-Type','Content-Length','Content-Range','Accept-Ranges'):
                    if source.headers.get(key):self.send_header(key,source.headers[key])
                self.send_header('Cache-Control','no-store');self.end_headers()
                try:
                    while chunk := source.read1(65536):
                        self.wfile.write(chunk);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == '/':
                    return self.reply((HERE/'dashboard.html').read_bytes(), 'text/html; charset=utf-8')
                if path == '/environment':
                    html=request(op.target+'/').decode()
                    for prefix in ('/api/', '/stream/', '/snapshot/', '/demo', '/recorder.js'):
                        html=html.replace('"'+prefix, '"/env'+prefix).replace("'"+prefix, "'/env"+prefix)
                    html=html.replace('</head>', '<style>.screenbar{display:none}</style></head>')
                    return self.reply(html.encode(), 'text/html; charset=utf-8')
                if path.startswith('/env/'):
                    return self.environment_proxy(path[4:])
                if path == '/api/status':
                    return self.reply(op.status())
                if path == '/api/view':
                    return self.reply(op.observe())
                if path == '/demo.mp4':
                    headers = {'Range': self.headers['Range']} if self.headers.get('Range') else {}
                    with urlopen(Request(op.target+'/demo.mp4', headers=headers), timeout=30) as source:
                        self.send_response(source.status)
                        for key in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
                            if source.headers.get(key):
                                self.send_header(key, source.headers[key])
                        self.end_headers()
                        try:
                            while chunk := source.read(65536):
                                self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                    return
                return self.reply({}, code=404)
            except Exception:
                return self.reply({'error': 'Environment unavailable'}, code=502)

        def do_POST(self):
            # Same-origin dashboard over an SSH tunnel. No permissive CORS.
            if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                return self.reply({}, code=403)
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                return self.reply({}, code=403)
            if self.path.startswith('/env/'):
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if not 0<n<=4096:raise ValueError('Invalid size')
                    body=json.loads(self.rfile.read(n))
                    if not isinstance(body,dict):raise ValueError('Invalid body')
                    return self.environment_proxy(self.path[4:],body)
                except (ValueError,TypeError):return self.reply({'ok':False},code=400)
                except Exception:return self.reply({'ok':False,'message':'Environment unavailable'},code=502)
            if self.path != '/api/control':
                return self.reply({}, code=404)
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 < n <= 256:
                    raise ValueError('Invalid body size')
                op.control(json.loads(self.rfile.read(n))['command'])
                self.reply({'ok': True})
            except (ValueError, KeyError, TypeError):
                self.reply({'ok': False, 'message': 'Control unavailable; check configuration, busy state and budget.'}, code=409)
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-url', default='http://127.0.0.1:18631')
    parser.add_argument('--port', type=int, default=18632)
    parser.add_argument('--max-calls', type=int, default=400)
    parser.add_argument('--log-dir', default=str(HERE/'runs'))
    args = parser.parse_args()
    if args.max_calls < 1:
        parser.error('--max-calls must be positive')
    op = Operator(args.target_url, os.environ.get('VLM_BASE_URL', ''), os.environ.get('VLM_MODEL', ''),
                  os.environ.get('VLM_API_KEY', ''), args.log_dir, args.max_calls)
    print(f'Hosted HTTP operator: http://127.0.0.1:{args.port} configured={op.configured}', flush=True)
    serve(op, args.port).serve_forever()


if __name__ == '__main__':
    main()
