"""Replay a privileged author's accepted token trajectory; NOT an agent baseline."""
import argparse
import json
import sys
from .protocol import TOKENS

def main():
    p=argparse.ArgumentParser();p.add_argument('--actions',required=True);a=p.parse_args()
    with open(a.actions) as f: actions=json.load(f)
    if not isinstance(actions,list) or len(actions)>1000:raise ValueError('Invalid author trajectory')
    for row in actions:
        if set(row)!={'left','right'} or any(v not in TOKENS for v in row.values()):raise ValueError('Invalid action')
    for i,line in enumerate(sys.stdin):
        json.loads(line)  # Protocol input; author replay does not infer goals from images.
        print(json.dumps(dict(actions[i],submit=False) if i<len(actions) else {'submit':True}),flush=True)
if __name__=='__main__':main()
