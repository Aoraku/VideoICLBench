"""Run environment + hosted dashboard as a supervised pair (Linux/macOS)."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variant',choices=['A','B','C'],default='A')
    p.add_argument('--seed',type=int,default=17)
    p.add_argument('--environment-port',type=int,default=18631)
    p.add_argument('--port',type=int,default=18632)
    p.add_argument('--max-pairs',type=int,default=400)
    p.add_argument('--max-calls',type=int,default=400)
    args=p.parse_args()
    if args.port==args.environment_port:p.error('Ports must differ')
    root=Path(__file__).resolve().parent
    children=[]
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        # The physics process does not need model credentials.
        env={k:v for k,v in os.environ.items() if not k.startswith('VLM_')}
        children.append(subprocess.Popen([sys.executable,str(root/'run.py'),'--variant',args.variant,
            '--seed',str(args.seed),'--port',str(args.environment_port),'--max-pairs',str(args.max_pairs)],env=env))
        children.append(subprocess.Popen([sys.executable,str(root/'hosted/hosted_operator.py'),
            '--target-url',f'http://127.0.0.1:{args.environment_port}','--port',str(args.port),
            '--max-calls',str(args.max_calls)]))
        while all(c.poll() is None for c in children):time.sleep(.5)
        return next(c.returncode or 1 for c in children if c.poll() is not None)
    except KeyboardInterrupt:
        return 0
    finally:
        for c in children:
            if c.poll() is None:c.terminate()
        for c in children:
            try:c.wait(timeout=10)
            except subprocess.TimeoutExpired:c.kill();c.wait()

if __name__=='__main__':sys.exit(main())
