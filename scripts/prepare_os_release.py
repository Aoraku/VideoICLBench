"""Build the pinned 36-task OS desktop, refined fixtures and recorder catalogue."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from os_refinement import refine, design
from os_recording_guide import make_guide
from os_output_contracts import demo_format

REPO = 'peilin717/OS-ICL'
COMMIT = '97a47cf491f8d8793b7b78aa4b814b77e246cac8'
ROOT = Path(__file__).resolve().parents[1]


def catalogue(source):
    code = '''import json, workflows, tasks36
rows=[]
for spec in tasks36.SPEC:
 demos=[tasks36.generate(spec['id'],i,1001,'module-demo') for i in range(3)]
 query=tasks36.generate(spec['id'],0,4201)
 rows.append(dict(spec=spec, methods={v:d['_brief36']['method'] for v,d in zip('ABC',demos)},
  demo_instruction=demos[0]['_brief36']['instruction'], task=query['case']['task']))
print(json.dumps(dict(version=workflows.VERSION, implementation=workflows.IMPLEMENTATION, rows=rows)))'''
    raw=json.loads(subprocess.check_output([sys.executable,'-c',code],cwd=source,text=True))
    rows=[design(row) for row in raw['rows']]
    guidance_code='''import json,copy,sys,workflows,tasks36
requests=json.load(sys.stdin);out={}
for spec in requests:
 examples={}
 for c,v in enumerate('ABC'):
  groups=[]
  for seed in spec['demo_seeds']:
   ep=tasks36.generate(spec['id'],c,seed,'module-demo');steps=[]
   context={'files':[dict(path=workflows.path(ep['state'],f['id']),name=f['name'],log_channel=f.get('log_channel'),approved=f.get('approved'),revision=f['revision'],bytes=len(f['content'].encode()),resource_key=f.get('resource_key')) for f in ep['state']['files'] if f['kind']!='folder' and not f.get('deleted')]}
   for a in ep['reference']:
    state=ep['state']
    def label(identifier):
     if identifier is None:return ''
     f=next((f for f in state['files'] if f['id']==identifier),None)
     if f:return workflows.path(state,identifier)
     for key in ('jobs','devices','processes','print_queue'):
      item=next((x for x in state.get(key,[]) if x['id']==identifier),None)
      if item:return item.get('name',identifier)
     return identifier
    step={k:label(value) if k in ('target','parent','input','output') else value for k,value in a.items()}
    steps.append(step);workflows.transition(ep,copy.deepcopy(a))
   groups.append({'seed':seed,'instruction':ep['_brief36']['instruction'],'steps':steps,'context':context})
  examples[v]=groups
 out[spec['id']]=examples
print(json.dumps(out))'''
    guidance=json.loads(subprocess.check_output([sys.executable,'-c',guidance_code],cwd=source,input=json.dumps(rows),text=True))
    for row in rows:
        row['demo_examples']=guidance[row['id']]
        for variant,groups in row['demo_examples'].items():
            for group in groups:
                group['guide']=make_guide(group)
                group['guide']['output_format']=demo_format(row['id'],variant)
                del group['context']
        row['demo_apps']=list(dict.fromkeys(app for groups in row['demo_examples'].values() for group in groups for app in group['guide']['apps']))
    return {'repository':REPO,'commit':COMMIT,'design_version':'videoicl-os36-human-1',
            'benchmark_version':raw['version'],'implementation':raw['implementation'],
            'recording_compatibility':json.loads((ROOT/'tasks/os/recording-compatibility.json').read_text()),
            'recording_variant_compatibility':json.loads((ROOT/'tasks/os/recording-variant-compatibility.json').read_text()),
            'cases':rows}


def prepare(destination, checkout=None):
    if destination.exists() and any(destination.iterdir()):raise ValueError('Use an empty destination; never overwrite runtime data')
    with tempfile.TemporaryDirectory(prefix='videoicl-os-source-') as temporary:
        source=Path(checkout).resolve() if checkout else Path(temporary)/'source'
        if not checkout:subprocess.run(['git','clone','--depth','1','https://github.com/'+REPO+'.git',str(source)],check=True)
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=COMMIT:raise ValueError('OS source does not match pinned commit')
        subprocess.run(['git','diff','--exit-code','HEAD','--'],cwd=source,check=True)
        files=subprocess.check_output(['git','ls-files','-z'],cwd=source).decode().split('\0')
        destination.mkdir(parents=True,exist_ok=True)
        for name in filter(None,files):
            if name.startswith(('benchmark_videos/','data/')):continue
            target=destination/name
            if not target.resolve().is_relative_to(destination.resolve()):raise ValueError('Invalid source path')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,target)
        refine(destination)
        # Docker mounts the persistent data volume beneath a read-only source mount.
        (destination/'data').mkdir(exist_ok=True)
        result=catalogue(destination)
        (destination/'videoicl-catalog.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        (destination/'videoicl-provenance.json').write_text(json.dumps({'repository':REPO,'commit':COMMIT,
            'design_version':result['design_version'],'implementation_fingerprint':result['implementation']['fingerprint'],
            'demonstrations':'human browser capture; independent persistent library'},indent=2)+'\n')
        print(f"Prepared {len(result['cases'])} OS tasks; 12 easy / 12 medium / 12 hard; human demos.")
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True);p.add_argument('--checkout',type=Path)
    p.add_argument('--catalog-output',type=Path)
    args=p.parse_args();result=prepare(args.destination.resolve(),args.checkout)
    if args.catalog_output:
        args.catalog_output.parent.mkdir(parents=True,exist_ok=True);args.catalog_output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
