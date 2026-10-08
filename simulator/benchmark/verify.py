"""Author smoke test. This is NOT an agent solvability or success evaluation."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from .catalog import TASKS, task_spec
from .environment import DesktopDual

def main():
    p=argparse.ArgumentParser(); p.add_argument('--variants',nargs='+',default=['A','B','C']); p.add_argument('--render',action='store_true')
    p.add_argument('--output',type=Path,default=Path('.local/embodied50-smoke.json')); a=p.parse_args()
    rows=[]
    for tid in TASKS:
        for variant in a.variants:
            start=time.monotonic(); env=None
            try:
                env=DesktopDual(task_spec(tid,variant),render=a.render)
                assert env.action_dim==14
                assert not env.score()['success'],'Unfinished reset must not pass'
                env.action('UP','UP'); env.action('STILL','STILL')
                s=env.snapshot()
                assert all(np.isfinite(v['pos']).all() and .76<v['pos'][2]<1.2 for v in s.values()),'Unstable initial scene'
                assert not env.score()['success'],'Unfinished actions must not pass'
                if a.render:
                    assert len(env.images())==3
                rows.append(dict(task=tid,variant=variant,ok=True,seconds=round(time.monotonic()-start,2)))
            except Exception as exc:
                rows.append(dict(task=tid,variant=variant,ok=False,error=str(exc)))
            finally:
                if env: env.close()
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(dict(kind='physics-load-action-negative-submit-smoke',agent_solvability_test=False,
                rendered=a.render,rows=rows),indent=2))
            print(f'{tid}/{variant}: {rows[-1]}',flush=True)
    if not all(r['ok'] for r in rows): raise SystemExit(1)
if __name__=='__main__': main()
