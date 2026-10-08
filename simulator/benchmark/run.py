"""Author orchestrator; policy subprocess sees only the actor observation contract."""
import argparse
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import time
import httpx
from .protocol import TOKENS, CONDITIONS

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://127.0.0.1:18660')
    p.add_argument('--admin-token-file',type=Path,required=True)
    p.add_argument('--task',required=True); p.add_argument('--variant',choices=['A','B','C'],default='A')
    p.add_argument('--condition',choices=CONDITIONS,default='human_frames')
    p.add_argument('--trial-kind',choices=['agent','author_replay','protocol_smoke'],required=True)
    p.add_argument('--seed',type=int,default=0); p.add_argument('--budget',type=int,default=1000)
    p.add_argument('--wall-seconds',type=int,default=1800)
    p.add_argument('--policy',required=True,help='Persistent JSON-lines process; no shell evaluation')
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    auth={'Authorization':'Bearer '+a.admin_token_file.read_text().strip()}
    sid=None; proc=None; ended=False
    with httpx.Client(base_url=a.url,timeout=360) as c:
        try:
            r=c.post('/admin/sessions',headers=auth,json=dict(task=a.task,variant=a.variant,seed=a.seed,
                condition=a.condition,action_budget=a.budget,wall_seconds=a.wall_seconds,trial_kind=a.trial_kind));r.raise_for_status(); sid=r.json()['session']
            base=f'/actor/{sid}'
            demo=c.get(base+'/demo');demo.raise_for_status();demo=demo.json()
            if 'video' in demo: demo['video']=a.url.rstrip('/')+demo['video']
            proc=subprocess.Popen(shlex.split(a.policy),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=(a.output/'policy.stderr').open('w'),text=True,bufsize=1)
            (a.output/'manifest.json').write_text(json.dumps(dict(task=a.task,variant=a.variant,seed=a.seed,
                condition=a.condition,session=sid,policy=a.policy,budget=a.budget,wall_seconds=a.wall_seconds,trial_kind=a.trial_kind),indent=2))
            index=0
            with (a.output/'policy.jsonl').open('w') as log:
                while True:
                    obs=c.get(base+'/observe');obs.raise_for_status();obs=obs.json()
                    payload=dict(observation=obs,demonstration=demo if index==0 else None,actions=list(TOKENS),
                        protocol='dual-tokens-v1',interface='Choose left/right token or submit. Images and demonstration are the only task evidence. FWD is +X; LEFT is +Y; UP is +Z. 2 cm / 10 deg per token, 0.4 s simulation. Both arms execute simultaneously. GRASP/RELEASE persist.')
                    proc.stdin.write(json.dumps(payload)+'\n');proc.stdin.flush()
                    if not select.select([proc.stdout],[],[],min(120,max(1,obs['seconds_remaining'])))[0]: raise RuntimeError('Policy timeout')
                    line=proc.stdout.readline()
                    if not line: raise RuntimeError('Policy exited without decision')
                    decision=json.loads(line)
                    if not isinstance(decision,dict) or set(decision)-{'left','right','submit'}: raise ValueError('Policy output must contain only left, right, submit')
                    if 'submit' in decision and not isinstance(decision['submit'],bool): raise ValueError('submit must be boolean')
                    log.write(json.dumps(dict(index=index,decision=decision))+'\n');log.flush()
                    if decision.get('submit') or obs['remaining']==0:
                        r=c.post(base+'/submit',json={});r.raise_for_status();ended=True;break
                    cmd={arm:decision.get(arm,'STILL') for arm in ('left','right')}
                    if any(t not in TOKENS for t in cmd.values()): raise ValueError('Invalid policy token')
                    r=c.post(base+'/action',json=cmd);r.raise_for_status();index+=1
        finally:
            if proc:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()
            if sid:
                if not ended: c.post('/admin/cancel/'+sid,headers=auth)
                r=c.get('/admin/results/'+sid,headers=auth)
                if r.is_success: (a.output/'result.private.json').write_text(json.dumps(r.json(),indent=2))
    print(a.output)
if __name__=='__main__': main()
