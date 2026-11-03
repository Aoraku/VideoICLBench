#!/usr/bin/env python3
"""Portable foreground entrypoint. No model/API calls or scheduled work."""
import argparse,json,os,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def assets_env(asset_root):
    env=os.environ.copy();a=Path(asset_root).expanduser().resolve()
    for p in(a/'asset_roots').iterdir()if(a/'asset_roots').is_dir()else[]:
        if p.is_dir():env[p.name]=str(p)
    robot=a/'robot/franka-panda/robot.usd'
    if robot.is_file():env['VIC_FRANKA_ROBOTWIN_USD']=str(robot)
    env['PYTHONPATH']=os.pathsep.join([str(ROOT/'runtime'),str(ROOT/'sdk'),env.get('PYTHONPATH','')])
    env['ACCEPT_EULA']='Y';env['OMNI_KIT_ACCEPT_EULA']='YES';env['VIDEOICL_SENSOR_DEPTH']='1'
    env['VIC_ENGINEERING_STAGE_CHECKPOINTS']='1'
    env['VIC_ENGINEERING_FUNCTIONAL_ACCEPTANCE']='1'
    return env

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','probe','serve'])
    p.add_argument('--task',default='E02',choices=[f'E{i:02}'for i in range(1,14)])
    p.add_argument('--variant',choices=list('ABC'),default='A');p.add_argument('--seed',type=int,default=4201)
    p.add_argument('--all',action='store_true',help='Inspect all39 manifest cases')
    p.add_argument('--verify-assets',action='store_true');p.add_argument('--asset-root',type=Path,default=ROOT/'front13-assets')
    p.add_argument('--out',type=Path);p.add_argument('--runtime-python',default=sys.executable)
    p.add_argument('--experience',default=os.environ.get('VIC_KIT_EXPERIENCE',''));p.add_argument('--dry-run',action='store_true')
    a=p.parse_args();env=assets_env(a.asset_root)
    if a.mode=='inspect':
        os.environ.update(env);sys.path.insert(0,str(ROOT/'runtime'))
        from videoicl_isaaclab.realworld_scenes import load
        cases=json.loads((ROOT/'acceptance.json').read_text())['cases']if a.all else[dict(task=a.task,variant=a.variant,seed=a.seed,condition='R'if a.task=='E12'else'I')]
        rows=[]
        for c in cases:
            s=load(c['task'],c['variant'],c['seed'],ROOT/'bindings'/(c['condition']+'.json'),verify_files=a.verify_assets)
            rows.append(dict(task=c['task'],variant=c['variant'],seed=c['seed'],condition=c['condition'],objects=len(s['objects']),source_files_verified=s['source_files_verified'],assignment=s['execution_design']['assignment_identity_sha256']))
        print(json.dumps(dict(cases=len(rows),assets_verified=a.verify_assets,results=rows),ensure_ascii=False,indent=2));return
    if a.all:p.error('--all is for inspection; launch each case with its own output directory')
    if a.out is None:p.error('--out is required for a native run')
    out=a.out.expanduser().resolve()
    if out.exists():p.error('Use a new --out directory; existing runs are preserved')
    condition='R'if a.task=='E12'else'I';binding=ROOT/'bindings'/(condition+'.json')
    common=['--headless','--device','cpu','--kit_args','--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/persistent/physics/useLocalMeshCache=false --/physics/cooking/ujitsoCollisionCooking=false --/physics/cooking/ujitsoRemoteCacheEnabled=false --/app/settings/persistent=false']
    if a.experience:common+=['--experience',a.experience]
    if a.mode=='probe':
        budget=12000 if a.task=='E09' else 6000 if a.task=='E01' else 3000
        cmd=[a.runtime_python,str(ROOT/'runtime/scripts/probe_realworld_room_pool.py'),'--bindings',str(binding),'--tasks',a.task,'--variant',a.variant,'--seed',str(a.seed),'--robot','franka','--settle-ticks','240','--ticks','25','--execution-control','positive','--execution-action-budget',str(budget),'--execution-settle-ticks','600','--out',str(out),*common]
    else:
        out.parent.mkdir(parents=True,exist_ok=True);casefile=out.parent/(out.name+'-cases.json')
        if casefile.exists():p.error('Generated case file already exists; choose a fresh output name')
        case=[dict(task=a.task,variant=a.variant,seed=a.seed,robot='franka',bindings=str(binding),episode_id='room-00-'+a.task+'-'+a.variant+'-s'+str(a.seed))]
        if not a.dry_run:casefile.write_text(json.dumps(case,indent=2))
        cmd=[a.runtime_python,str(ROOT/'runtime/scripts/serve_realworld_room_pool.py'),'--cases',str(casefile),'--out',str(out),'--suite','front13-delivery-v3','--epoch',uuid.uuid4().hex,'--barrier-timeout','120','--barrier-policy','wait',*common]
    print(json.dumps(dict(mode=a.mode,model_calls=False,command=cmd),ensure_ascii=False),flush=True)
    if not a.dry_run:raise SystemExit(subprocess.call(cmd,env=env,cwd=ROOT/'runtime'))
if __name__=='__main__':main()
