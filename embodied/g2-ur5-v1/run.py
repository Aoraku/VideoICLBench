#!/usr/bin/env python3
"""Run one original G2 task/variant using the bundled native GUI harness."""
from pathlib import Path
import argparse,hashlib,json,os,shlex,shutil,stat,subprocess,sys
ROOT=Path(__file__).resolve().parent
TASKS=('E04','E05','E06','E07','E09','E11','E20','E36','E41','E49')

def prepare_launch(directory, files):
 """Reuse byte-identical command previews, never overwrite another launch."""
 directory.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  if set(os.listdir(fd))-set(files):
   raise ValueError('Unexpected files in existing launch directory; use a new --out')
  missing=[]
  for name, data in files.items():
   try:source=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
   except FileNotFoundError:missing.append((name,data));continue
   with os.fdopen(source,'rb') as stream:
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or stream.read()!=data:
     raise ValueError('Existing launch configuration differs; use a new --out')
  for name, data in missing:
   target=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
   with os.fdopen(target,'wb') as stream:stream.write(data)
 finally:os.close(fd)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--task',choices=TASKS,required=True)
 p.add_argument('--variant',choices=list('ABC'),required=True)
 p.add_argument('--condition',choices=['real','sim','text_rule'],default='sim')
 p.add_argument('--native-python',required=True,type=Path,help='Python with Isaac Sim5.0 and IsaacLab')
 p.add_argument('--gui-python',type=Path,default=Path(sys.executable))
 p.add_argument('--credentials',type=Path,required=True,help='External private provider JSON, never committed')
 p.add_argument('--binary',default='codex')
 p.add_argument('--model',default='gpt-6-astra')
 p.add_argument('--model-catalog',type=Path,default=ROOT/'config/model-catalog.json')
 p.add_argument('--ca-bundle',type=Path,help='Provider TLS CA bundle; defaults to certifi')
 p.add_argument('--browser-path',type=Path)
 p.add_argument('--experience',type=Path,help='Optional installed IsaacSim5.0 .kit experience')
 p.add_argument('--out',required=True,type=Path,help='New output directory for this independent run')
 p.add_argument('--max-actions',type=int,default=500)
 p.add_argument('--context-window',type=int,default=1050000)
 p.add_argument('--compact-tokens',type=int,default=945000)
 p.add_argument('--print-command',action='store_true',help='Prepare launch files and print command only; no GPU/model/API')
 a=p.parse_args()
 if a.max_actions<1:p.error('max-actions must be positive')
 out=a.out.expanduser().resolve()
 if out.exists():p.error('Use a new output directory; existing runs are never restarted or overwritten')
 launch=out.parent/('.'+out.name+'-launch')
 env=dict(os.environ,VIDEOICL_G2_ROOT=str(ROOT),VIC_UR5_WSG_USD=str(ROOT/'runtime/assets/embodiments/robotwin-r5/ur5-wsg/robot.usd'))
 for key in ('VIC_INFERENCE_ASSETS','VIC_FULL50_RIGID_ASSETS','VIC_MECHANISM_ASSETS','VIC_UPSTREAM_ASSETS'):
  env[key]=str(ROOT/'assets'/key)
 env['PYTHONPATH']=str(ROOT/'VideoICLBench/packages/sdk')+os.pathsep+env.get('PYTHONPATH','')
 profile=ROOT/'runtime/configs/inference-generalization-ur5-wsg-ik-smooth-v1.json'
 case=dict(episode_id=f'g2-{a.task.lower()}-{a.variant.lower()}-{a.condition}-s4201',task=a.task,variant=a.variant,seed=4201,
           input_condition=a.condition,bindings=str(ROOT/'runtime/inference-generalization-v1/g2-bindings.json'),robot=str(profile))
 cases=launch/'cases.json'
 binary=shutil.which(a.binary)or str(Path(a.binary).expanduser().resolve())
 ca=a.ca_bundle
 if ca is None:
  import certifi
  ca=Path(certifi.where())
 cmd=[str(a.gui_python.expanduser().resolve()),str(ROOT/'VideoICLBench/scripts/harbor/run_embodied_pool.py'),
      '--native-python',str(a.native_python.expanduser().resolve()),'--gui-python',str(a.gui_python.expanduser().resolve()),
      '--runtime-root',str(ROOT/'runtime'),'--task-root',str(ROOT/'tasks'),'--cases',str(cases),
      '--credentials',str(a.credentials.expanduser().resolve()),'--binary',binary,'--model',a.model,
      '--condition',a.condition,'--engine','codex','--embodied-harness','program_gui','--effort','high',
      '--max-actions',str(a.max_actions),'--timeout','0','--unknown-api-policy','preserve_world',
      '--provider-ca-bundle',str(ca.expanduser().resolve()),'--embodied-auto-recover',
      '--codex-context-window',str(a.context_window),'--codex-compact-tokens',str(a.compact_tokens),
      '--codex-model-catalog',str(a.model_catalog.resolve()),'--codex-model-catalog-sha256',hashlib.sha256(a.model_catalog.read_bytes()).hexdigest(),
      '--epoch','g2-ur5-original-handoff-v1','--out',str(out),'--allow-unvalidated-environment',
      '--native-kit-args','--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/persistent/physics/useLocalMeshCache=false --/physics/cooking/ujitsoCollisionCooking=false --/physics/cooking/ujitsoRemoteCacheEnabled=false --/app/settings/persistent=false']
 if a.browser_path:cmd+=['--browser-path',str(a.browser_path.resolve())]
 if a.experience:cmd+=['--experience',str(a.experience.resolve())]
 launch_record=dict(command=cmd,environment_paths={k:env[k]for k in env if k.startswith('VIC_')and k.endswith(('ASSETS','USD'))},seed=4201,task=a.task,variant=a.variant,condition=a.condition,automatic_compact='native',credentials_included=False)
 try:
  prepare_launch(launch,{name:(json.dumps(value,indent=2)+'\n').encode() for name,value in
    [('cases.json',dict(cases=[case])),('launch.json',launch_record)]})
 except (OSError,ValueError) as exc:p.error(str(exc))
 if a.print_command:
  print(shlex.join(cmd));return 0
 return subprocess.call(cmd,env=env,cwd=ROOT)

if __name__=='__main__':raise SystemExit(main())
