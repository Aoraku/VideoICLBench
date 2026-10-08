#!/usr/bin/env python3
"""Author workflow: verified physical trajectories -> demos -> actor API replay.
This intentionally uses privileged author trajectories, never agent baselines.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shlex
import sys
import time

PILOT=('rt12','rt07','rt02','rc10','rc22','rc11')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pilot-folder',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--url',default='http://127.0.0.1:18660')
    p.add_argument('--author-reviewed',action='store_true',required=True,
                   help='Author has checked initial/final frames and success evidence for all six recordings')
    a=p.parse_args();repo=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(repo))
    from simulator.benchmark.provenance import harness_sha256
    from simulator.benchmark.catalog import TASKS
    expected_hash=harness_sha256()
    for task in PILOT:
        folder=a.pilot_folder/f'{task}-A-0'
        proof=json.loads((folder/'result.private.json').read_text())
        assert proof['score']['success'] and not proof['error'],(task,proof['error'])
        assert proof['independent_agent'] is False and proof['seed']==0 and proof['variant']=='A'
        assert proof['task_revision']==TASKS[task].get('task_revision',1)
        assert proof['harness_sha256']==expected_hash,'Code changed during recording; rerun with frozen source'
        assert (folder/'video.mp4').is_file()
    a.output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for task in PILOT:
        folder=a.pilot_folder/f'{task}-A-0';root=a.data/'demos'/task/'sim'
        reused=(root/'manifest.json').exists()
        if not reused:
            subprocess.run([sys.executable,'-m','simulator.benchmark.demos',task,'sim',str(folder/'video.mp4'),
                '--data',str(a.data),'--author-verified'],cwd=repo,check=True)
        m=json.loads((root/'manifest.json').read_text())
        assert m.get('task_revision',1)==TASKS[task].get('task_revision',1),'Stale demo revision'
        # Preserve existing immutable demos; current recording remains in the pilot bundle.
        command=[sys.executable,'-m','simulator.benchmark.run','--url',a.url,
            '--admin-token-file',str(a.data/'admin.token'),'--task',task,'--variant','A','--seed','0',
            '--condition','sim_frames','--trial-kind','author_replay','--budget','1000',
            '--policy',shlex.join([sys.executable,'-m','simulator.benchmark.replay_policy','--actions',str(folder/'actions.json')]),
            '--output',str(a.output/task)]
        subprocess.run(command,cwd=repo,check=True)
        result=json.loads((a.output/task/'result.private.json').read_text())
        assert result['trial_kind']=='author_replay' and result['success'],(task,result)
        proof=json.loads((folder/'result.private.json').read_text())
        assert result['actions']==proof['actions']
        rows.append(dict(task=task,task_revision=proof['task_revision'],variant='A',seed=0,
            author_acceptance=True,actor_api_replay_success=True,actions=result['actions'],
            simulation_demo_available=True,demo_reused=reused,demo_video_sha256=m['video_sha256'],
            author_actions_sha256=proof['actions_sha256'],independent_agent=False))
        (a.output/'summary.public.json').write_text(json.dumps(dict(
            kind='privileged-author-pilot-acceptance',date_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            harness_sha256=expected_hash,catalog_sha256=hashlib.sha256((repo/'simulator/benchmark/tasks.json').read_bytes()).hexdigest(),
            independent_agent_trials=0,human_demonstrations_collected=0,rows=rows),indent=2))
    print(a.output/'summary.public.json')

if __name__=='__main__':main()
