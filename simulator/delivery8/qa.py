"""Deployment QA: actual Chromium controls and mock-provider HTTP transport.

All episodes are protocol_smoke or manual, never independent model results.
Requires server-side Chromium and websockets for the optional dashboard check.
"""
import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

from .hosted import request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    url = 'http://127.0.0.1:18664'
    key = (args.data/'platform.key').read_text().strip()
    headers = {'Authorization': 'Bearer '+key}
    calls = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            assert self.path == '/v1/chat/completions'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            content = payload['messages'][1]['content']
            assert sum(x['type']=='image_url' for x in content) == 15
            public = json.loads(content[-1]['text'])
            assert not {'task','variant','goals','object_positions'} & set(public['observation'])
            finish = len(calls) == 1
            calls.append(dict(images=15, step_mm=3.5, finish=finish))
            d = dict(left='STILL' if finish else 'UP',right='STILL',step_mm=3.5,
                     rotation_deg=2.5,finish=finish,summary='Transport test, not a model task solution')
            data = json.dumps({'choices':[{'message':{'content':json.dumps(d)}}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    provider = ThreadingHTTPServer(('127.0.0.1',0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True); thread.start()
    sid = request(url+'/control/sessions',dict(task='F44',variant='B',seed=7,
        trial_kind='protocol_smoke'),headers)['session']
    try:
        env = dict(os.environ,VLM_BASE_URL='http://127.0.0.1:'+str(provider.server_port)+'/v1',
                   VLM_MODEL='mock-protocol-provider',VLM_API_KEY='test-only-not-a-secret')
        result = subprocess.run([sys.executable,str(Path(__file__).parent/'hosted.py'),
            '--url',url,'--session',sid,'--max-calls','2','--log-dir',str(args.output/'hosted')],
            env=env,capture_output=True,text=True,timeout=360)
        if result.returncode: raise AssertionError('Hosted runner failed')
        score = request(url+'/control/results/'+sid,headers=headers)
        assert score['trial_kind']=='protocol_smoke' and score['actions']==1 and len(calls)==2
    finally:
        provider.shutdown(); provider.server_close(); thread.join(timeout=5)
        # Close if the runner failed before finishing.
        status = request(url+'/control/status',headers=headers)
        if any(s['session']==sid and not s['closed'] for s in status): request(url+'/actor/'+sid+'/submit',{})

    from websockets.sync.client import connect
    with tempfile.TemporaryDirectory(prefix='tabletop8-browser-') as profile:
        log = (args.output/'chromium.log').open('w')
        browser = subprocess.Popen(['/usr/bin/chromium','--headless','--no-sandbox',
            '--disable-dev-shm-usage','--disable-gpu','--remote-debugging-port=0',
            '--remote-allow-origins=*','--user-data-dir='+profile,'about:blank'],stdout=log,stderr=log)
        manual_sid = None
        try:
            portfile = Path(profile)/'DevToolsActivePort'
            for _ in range(100):
                if portfile.exists(): break
                time.sleep(.1)
            port = int(portfile.read_text().splitlines()[0])
            with urlopen('http://127.0.0.1:'+str(port)+'/json/list') as response:
                target = json.load(response)[0]
            with connect(target['webSocketDebuggerUrl']) as socket:
                counter = 0
                def cdp(method,params=None):
                    nonlocal counter
                    counter += 1
                    socket.send(json.dumps(dict(id=counter,method=method,params=params or {})))
                    while True:
                        response = json.loads(socket.recv(timeout=360))
                        if response.get('id') == counter:
                            if 'error' in response: raise RuntimeError('CDP failed')
                            return response.get('result',{})
                def evaluate(expression):
                    result = cdp('Runtime.evaluate',dict(expression=expression,awaitPromise=True,returnByValue=True))
                    if 'exceptionDetails' in result: raise RuntimeError('Dashboard JS failed')
                    return result.get('result',{}).get('value')
                cdp('Emulation.setDeviceMetricsOverride',dict(width=1280,height=1100,deviceScaleFactor=1,mobile=False))
                cdp('Page.navigate',dict(url=url))
                for _ in range(100):
                    if evaluate("Boolean(document.getElementById('connect'))"): break
                    time.sleep(.1)
                evaluate("document.getElementById('key').value="+json.dumps(key))
                evaluate("document.getElementById('connect').click()")
                for _ in range(100):
                    if evaluate("document.getElementById('task').options.length") == 8: break
                    time.sleep(.1)
                assert evaluate("document.getElementById('task').options.length") == 8
                evaluate("document.getElementById('task').value='F44'; document.getElementById('variant').value='C'; document.getElementById('create').click()")
                for _ in range(600):
                    if evaluate("Boolean(document.getElementById('fpv').naturalWidth) && !document.getElementById('create').disabled"): break
                    time.sleep(.1)
                manual_sid = evaluate("sid")
                assert evaluate("document.getElementById('fpv').naturalWidth") == 640
                evaluate("document.getElementById('left').value='UP'; document.getElementById('distance').value='7.5'; document.getElementById('move').click()")
                for _ in range(100):
                    if evaluate("document.getElementById('session').textContent.includes('已执行 1 次')"): break
                    time.sleep(.1)
                assert evaluate("document.getElementById('session').textContent.includes('已执行 1 次')")
                screenshot = cdp('Page.captureScreenshot',dict(format='png',captureBeyondViewport=True))
                (args.output/'dashboard.png').write_bytes(base64.b64decode(screenshot['data']))
                evaluate("document.getElementById('submit').click()")
                for _ in range(300):
                    if evaluate("document.getElementById('result').textContent.includes('执行视频已保存')"): break
                    time.sleep(.1)
                assert evaluate("document.getElementById('result').textContent.includes('执行视频已保存')")
        finally:
            if manual_sid:
                status = request(url+'/control/status',headers=headers)
                if any(s['session']==manual_sid and not s['closed'] for s in status):
                    request(url+'/actor/'+manual_sid+'/submit',{})
            browser.terminate()
            try: browser.wait(timeout=10)
            except subprocess.TimeoutExpired: browser.kill(); browser.wait()
            log.close()
    report = dict(kind='transport-and-dashboard-qa-not-model-benchmark',independent_agent=False,
        hosted_mock_calls=calls, dashboard=dict(tasks=8,task='F44',variant='C',
        camera_width=640,entered_step_mm=7.5,executed_actions=1,submission_saved=True))
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__ == '__main__': main()
