"""Single-world authenticated launcher for the original GUMI button console."""
import argparse
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from videoicl_isaaclab.runtime_catalog import ready_tasks


class AdoptedWorker:
    """Keep the existing owned Kit world through a coordinator deployment."""
    def __init__(self,group,child):self.pid=group;self.child=child
    def poll(self):
        try:
            state=(Path('/proc')/str(self.child)/'stat').read_text().split(') ',1)[1].split()[0]
            return 0 if state=='Z' else None
        except OSError:return 0
    def wait(self,timeout=None):
        start=time.monotonic()
        while self.poll() is None:
            if timeout is not None and time.monotonic()-start>timeout:raise subprocess.TimeoutExpired('owned IsaacLab world',timeout)
            time.sleep(.05)
        return 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--port',type=int,default=18850)
    parser.add_argument('--worker-port',type=int,default=18851)
    args=parser.parse_args()
    token=args.token_file.read_text().strip()
    registry=json.loads((ROOT/'configs/task_registry.json').read_text())
    tasks={t['id']:t for t in registry['tasks']}
    lock=threading.RLock();worker=None;log=None;selected=None;folder=None
    base=f'http://127.0.0.1:{args.worker_port}'
    world_file=ROOT/'.local/workbench-world.json'
    if world_file.is_file():
        try:
            saved=json.loads(world_file.read_text());child=int(saved['child_pid'])
            raw=(Path('/proc')/str(child)/'cmdline').read_bytes()
            output=Path(saved['folder']).resolve()
            if (str(ROOT/'artifacts/workbench-live')+'/' in str(output)
                and str(output).encode() in raw and b'--serve' in raw):
                worker=AdoptedWorker(int(saved['group_pid']),child)
                selected=saved['selection'];folder=output
                print('Adopted existing IsaacLab world '+str(output),flush=True)
        except (OSError,ValueError,KeyError):pass

    def rpc(path,body=None,timeout=10):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

    def state():
        empty=dict(steps=0,max_pairs=600,gripper_closed=dict(left=False,right=False),recording=False)
        if worker is None:return dict(empty,status='unloaded',message='请选择任务并载入场景。')
        if worker.poll() is not None:return dict(empty,status='error',message='IsaacLab worker 已退出；可以重新载入场景。',selection=selected)
        try:
            result=rpc('/api/state',timeout=2)
            result.update(selection=selected,mode='author_preview',backend='isaaclab_physx')
            if not world_file.exists() and folder:
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit():continue
                    try:raw=(proc/'cmdline').read_bytes()
                    except OSError:continue
                    if b'build_scene.py' in raw and str(folder).encode() in raw and b'--serve' in raw:
                        world_file.parent.mkdir(exist_ok=True)
                        world_file.write_text(json.dumps(dict(group_pid=worker.pid,child_pid=int(proc.name),selection=selected,folder=str(folder))))
                        break
            return result
        except (OSError,urllib.error.URLError):
            return dict(empty,status='loading',message='正在启动真实 IsaacLab 场景…',selection=selected)

    def close():
        nonlocal worker,log
        if worker:
            # Kit may keep its Python child alive after python.sh exits on
            # SIGTERM. Reap the entire owned group before reusing its port.
            try:
                os.killpg(worker.pid,signal.SIGTERM)
                worker.wait(timeout=12)
            except (subprocess.TimeoutExpired,ProcessLookupError):pass
            finally:
                try:os.killpg(worker.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                worker.wait(timeout=10)
        worker=None
        if log:log.close();log=None
        world_file.unlink(missing_ok=True)

    def load(body):
        nonlocal worker,log,selected,folder
        task=body.get('task');variant=body.get('variant','A');seed=body.get('seed',7)
        if task not in tasks or variant not in ('A','B','C') or seed not in (0,7):
            raise ValueError('Unknown task, ABC variant or exported seed')
        if task not in ready_tasks():
            raise ValueError('本题专属环境正在进行 IsaacLab 物理和控制验证，通过后即可载入。')
        old=state()
        if old['status'] in ('running','budget_paused'):
            raise ValueError('请先提交或取消当前操作，再切换场景；不会自动结束已有任务。')
        if old['status']=='loading':raise ValueError('当前场景仍在载入，请等待。')
        # Author recording and interactive worlds share this GPU. Never kill
        # an unrelated or still-running recorder to satisfy a load request.
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:raw=(p/'cmdline').read_bytes()
            except OSError:continue
            if b'build_scene.py' in raw and b'--record-' in raw:
                raise ValueError('GPU 正在录制作者示范，请等待录制结束后载入。')
        close()
        selected=dict(task=task,variant=variant,seed=seed,title=tasks[task]['name'])
        folder=ROOT/'artifacts/workbench-live'/f'{task}-{variant}-{seed}-{time.time_ns()}'
        folder.parent.mkdir(parents=True,exist_ok=True)
        log=folder.with_suffix('.log').open('w')
        command=['bash',str(ROOT/'scripts/run_gpu.sh'),str(ROOT/'scripts/build_scene.py'),
                 '--task',task,'--variant',variant,'--seed',str(seed),'--out',str(folder),
                 '--serve','--author-preview','--port',str(args.worker_port),
                 '--budget','600','--headless','--enable_cameras',
                 '--kit_args','--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0']
        worker=subprocess.Popen(command,cwd=ROOT,env=dict(os.environ),stdout=log,
                                stderr=subprocess.STDOUT,start_new_session=True)
        # The group leader is python.sh. Its Kit child is discovered on the
        # next successful state read before a future coordinator deployment.
        return dict(ok=True,state=state())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value,status=200):
            data=json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(data)
        def authorized(self):
            if hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return True
            self.reply(dict(ok=False,message='Workbench gateway authorization required'),401);return False
        def do_GET(self):
            if not self.authorized():return
            path=self.path.split('?',1)[0]
            if path=='/api/catalog':
                available=ready_tasks()
                return self.reply(dict(tasks=[dict(id=t['id'],name=t['name'],status=t['status'],
                    loadable=t['id'] in available,instructions=t['variants']) for t in tasks.values()]))
            if path in ('/health','/api/state'):return self.reply(state())
            if path in ('/api/observe','/api/protocol'):
                try:return self.reply(rpc(path))
                except OSError:return self.reply(dict(ok=False,message='World not ready'),503)
            if path.startswith('/stream/') and path.rsplit('/',1)[-1] in ('head','wrist_left','wrist_right'):
                try:
                    upstream=urllib.request.urlopen(base+path,timeout=15)
                    self.send_response(200);self.send_header('Content-Type',upstream.headers['Content-Type']);self.end_headers()
                    with upstream:
                        while chunk:=upstream.read1(65536):self.wfile.write(chunk);self.wfile.flush()
                except (OSError,urllib.error.URLError):pass
                return
            self.reply(dict(ok=False,message='Unknown endpoint'),404)
        def do_POST(self):
            if not self.authorized():return
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<=n<=65536:raise ValueError('Request too large')
                body=json.loads(self.rfile.read(n) or b'{}')
                with lock:
                    if self.path=='/api/load':return self.reply(load(body))
                    if self.path in ('/api/start','/api/step','/api/stop','/api/abort','/api/ui-event'):
                        return self.reply(rpc(self.path,body,timeout=180))
                    self.reply(dict(ok=False,message='Unknown endpoint'),404)
            except (ValueError,OSError,urllib.error.URLError) as exc:
                self.reply(dict(ok=False,message=str(exc),state=state()),409)

    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    try:server.serve_forever()
    finally:server.server_close();close()


if __name__=='__main__':main()
