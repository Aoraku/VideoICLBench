#!/usr/bin/env python3
"""Run isolated author worlds concurrently; retain every failed recording."""
import argparse,concurrent.futures,json,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=6);p.add_argument('--tasks',nargs='+');a=p.parse_args()
repo=Path(__file__).resolve().parents[2];sys.path.insert(0,str(repo))
from simulator.benchmark.catalog import TASKS
from simulator.benchmark.provenance import harness_sha256
expected=harness_sha256();a.output.mkdir(parents=True,exist_ok=False)
(repo_script:=a.output/'controller.snapshot.py').write_bytes((repo/'scripts/embodied50/record-all.py').read_bytes())
# The executed controller remains at its repository location; do not edit it during a batch.
def run(task):
    with (a.output/f'{task}.log').open('w') as log:
        r=subprocess.run([sys.executable,str(repo/'scripts/embodied50/record-all.py'),'--tasks',task,'--output',str(a.output),'--record'],cwd=repo,stdout=log,stderr=subprocess.STDOUT)
    path=a.output/f'{task}-A-0/result.private.json'
    proof=json.loads(path.read_text()) if path.exists() else {}
    return dict(task=task,exit_code=r.returncode,success=bool(proof.get('score',{}).get('success')),
        error=proof.get('error'),video_end_success=proof.get('video_end_success',False),actions=proof.get('actions'))
rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
    for f in concurrent.futures.as_completed([pool.submit(run,t) for t in a.tasks or TASKS]):
        r=f.result();rows.append(r);print(json.dumps(r),flush=True)
        (a.output/'batch.private.json').write_text(json.dumps(dict(harness_sha256=expected,rows=rows),indent=2))
assert harness_sha256()==expected,'Harness changed while recording'
if any(r['exit_code'] or not r['success'] or not r['video_end_success'] for r in rows):sys.exit(1)
