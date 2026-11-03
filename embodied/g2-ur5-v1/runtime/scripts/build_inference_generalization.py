#!/usr/bin/env python3
"""Compile the opt-in inference bindings; never modify demo/source bindings."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'inference-generalization-v1'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def read(path):return json.loads(Path(path).read_text())

def validate_catalog(catalog):
    tasks=catalog.get('tasks',{})
    if set(tasks)!={f'E{i:02}' for i in range(1,51)}:raise ValueError('All 50 task identities required')
    counts={g:sum(t.get('group')==g for t in tasks.values()) for g in ('G0','G1','G2')}
    if counts!={'G0':20,'G1':20,'G2':10}:raise ValueError('Expected disjoint 20/20/10 partition')
    for task,t in tasks.items():
        if t.get('task_id')!=task or t.get('variants')!=['A','B','C']:raise ValueError('ABC identity mismatch')
        p=t.get('inference_prompt')
        if not isinstance(p,str) or not p.strip() or any(x in p for x in ('**A：','**B：','**C：','验收边界')):raise ValueError('Public prompt must not contain answer table')
    return counts

def compile_bindings(base,catalog,patches,*,g2_profile,g2_profile_sha256):
    validate_catalog(catalog)
    if not g2_profile or len(g2_profile_sha256)!=64:raise ValueError('Explicit pinned G2 robot/table profile required')
    result=deepcopy(base);checks=[];merged={}
    for patch in patches:
        for task,binding in patch['tasks'].items():
            if task in merged:raise ValueError('Duplicate task patch '+task)
            merged[task]=binding
    expected={t for t,d in catalog['tasks'].items() if d['group']!='G0'}
    if set(merged)!=expected:raise ValueError('Exactly 30 specified G1/G2 task patches required: '+str(sorted(expected^set(merged))))
    for task,item in catalog['tasks'].items():
        old=base['tasks'][task]
        if item['group']=='G0':
            checks.append(dict(task_id=task,group='G0',unchanged=True,binding_sha256=digest(old)));continue
        new=deepcopy(merged[task])
        comparison_variants=deepcopy(new.get('variants'))
        if task=='E08' and isinstance(comparison_variants,dict):
            for variant in comparison_variants.values():
                semantic=variant.get('semantic',{})
                if semantic.get('source_acceptance_geometry')=='E08-source-geometry-v1':
                    semantic.pop('source_acceptance_geometry')
        if comparison_variants!=old.get('variants'):
            raise ValueError(task+': replacement may not silently change ABC semantics, goals or initial poses')
        if set(new.get('objects',{}))!=set(old.get('objects',{})):
            raise ValueError(task+': preserve semantic object identities')
        changed=[name for name in old.get('objects',{}) if new['objects'][name]!=old['objects'][name]]
        mechanism_changed=new.get('mechanisms',[])!=old.get('mechanisms',[])
        if not changed and not mechanism_changed:raise ValueError(task+': object replacement missing')
        for name,obj in new.get('objects',{}).items():
            prior=old['objects'][name]
            if obj.get('identity',name)!=prior.get('identity',name):raise ValueError(task+': semantic identity renamed')
            if name in changed:
                a=obj.get('source_asset') or obj.get('mechanical_asset')
                if not isinstance(a,dict) or not a.get('sha256'):raise ValueError(task+': pinned asset required')
        if item['group']=='G1':
            for field in ('embodiment','head_view'):
                if new.get(field)!=old.get(field):raise ValueError(task+': G1 environment changed')
        else:new['embodiment']='ur5_wsg'
        new['inference_generalization']=dict(schema='videoicl-inference-task-v1',group=item['group'],
            instruction=item['inference_prompt'],demo_unchanged=True,
            robot_profile=g2_profile if item['group']=='G2' else None,
            robot_profile_sha256=g2_profile_sha256 if item['group']=='G2' else None,
            source_task_binding_sha256=digest(old))
        if task=='E24':
            new['inference_generalization']['rule_profile']='e24-yarn-insertion-v1'
        result['tasks'][task]=new
        checks.append(dict(task_id=task,group=item['group'],changed_objects=changed,mechanism_changed=mechanism_changed,
            abc_semantics_preserved=True,binding_sha256=digest(new)))
    result['inference_generalization_catalog']=dict(schema=catalog['schema'],source_sha256=catalog['source_sha256'],
        groups={task:item['group'] for task,item in catalog['tasks'].items()},demo_assets_modified=False,
        base_bindings_sha256=digest(base),g2_profile=g2_profile,g2_profile_sha256=g2_profile_sha256)
    return result,checks

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,default=ROOT/'configs/initial-admission-e13-e25-20261030/e13-hframe-v2-bindings.candidate.json')
    p.add_argument('--catalog',type=Path,default=DEFAULT/'catalog.private.json')
    p.add_argument('--g1-patch',type=Path,default=DEFAULT/'g1-bindings-patch.json')
    p.add_argument('--g2-patch',type=Path,default=DEFAULT/'g2-bindings-patch.json')
    p.add_argument('--g2-profile',type=Path,required=True)
    p.add_argument('--geometry-acceptance-v2',dest='geometry_acceptance_v2',action='store_true',default=True,help='E08/E33 source geometry acceptance (default)')
    p.add_argument('--legacy-acceptance-geometry',dest='geometry_acceptance_v2',action='store_false',help='Reproduce the historical AABB acceptance; never use for new runs')
    p.add_argument('--out',type=Path,default=DEFAULT/'acceptance-v2/inference-bindings.json')
    a=p.parse_args();profile=read(a.g2_profile)
    original_profile=read(ROOT/'configs/franka-workspace-v4-front100.json')
    if profile.get('name')!='ur5_wsg' or profile['asset']==original_profile['asset']:
        raise ValueError('G2 requires a different physical robot')
    if profile['layout']['table']==original_profile['layout']['table'] and profile['layout']['background'].get('table_color')==original_profile['layout']['background'].get('table_color'):
        raise ValueError('G2 requires a changed table')
    out,checks=compile_bindings(read(a.base),read(a.catalog),[read(a.g1_patch),read(a.g2_patch)],
        g2_profile=str(a.g2_profile.resolve().relative_to(ROOT.resolve())),g2_profile_sha256=hashlib.sha256(a.g2_profile.read_bytes()).hexdigest())
    if a.geometry_acceptance_v2:
        if a.out.parent.resolve()==DEFAULT.resolve():
            raise ValueError('Acceptance upgrade requires a new candidate output path in a separate directory')
        from videoicl_isaaclab.e08_source_geometry import augment_e08_bindings
        from videoicl_isaaclab.e33_source_geometry import augment_e33_bindings
        out=augment_e33_bindings(augment_e08_bindings(out,ROOT),ROOT)
        for check in checks:
            if check['task_id'] in ('E08','E33'):
                check['binding_sha256']=digest(out['tasks'][check['task_id']])
                check['acceptance_geometry_upgrade']=True
                check['physical_scene_unchanged_by_acceptance_upgrade']=True
                if check['task_id']=='E33':
                    check['unchanged']=False
        out['acceptance_geometry_revision']='source-geometry-v2-E08-E33'
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    (a.out.parent/'binding-compilation-checks.json').write_text(json.dumps(dict(checked_tasks=50,variants=150,checks=checks),indent=2)+'\n')
    public={task:dict(task_id=task,group=x['group'],instruction=x['inference_prompt']) for task,x in read(a.catalog)['tasks'].items() if x['group']!='G0'}
    (a.out.parent/'public-prompts.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(tasks=50,variants=150,g0_unchanged=19 if a.geometry_acceptance_v2 else 20,g0_physical_scenes_unchanged=20,changed_tasks=30,acceptance_geometry_upgrade=a.geometry_acceptance_v2,output=str(a.out))))
if __name__=='__main__':main()
