"""Common author-side launcher; never expose backend/task flags to the model."""
import argparse
from pathlib import Path
import os
import sys

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',required=True,choices=['mujoco-stack','robocasa-mug'])
    p.add_argument('--mode',default='gui',choices=['gui','hosted'])
    args,rest=p.parse_known_args()
    root=Path(__file__).resolve().parent
    if args.backend=='mujoco-stack':
        script=root/('run_hosted.py' if args.mode=='hosted' else 'run.py')
    else:
        # RoboCasa hosted mode connects to an already running GUI server.
        script=root/'backends/robocasa'/('hosted/hosted_operator.py' if args.mode=='hosted' else 'server.py')
    os.execv(sys.executable,[sys.executable,str(script),*rest])

if __name__=='__main__':main()
