#!/usr/bin/env python3
"""Audit visible-instance confounds and teaching coverage, without claiming human acceptance."""
from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import re

from vic import business, games
from vic.catalog import catalog
from vic_apps.domain import initialize

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (0, 1, 2, 1000, 1001, 1002)
BOUNDARIES = {8:('members',5),22:('duration',240),25:('duration',600),
              32:('rating',50),38:('words',50),48:('rating',50),
              49:('text_length',15),54:('price',50),57:('balance',50),65:('code_length',25)}
# Observable rival rules that a single selected object cannot distinguish.
NUMERIC = ('unread','contact_time','timestamp','size','duration','rating','plays',
           'comments','words','tag_count','price','context','sales','stock',
           'amount','balance','transactions','departure','transfers','number',
           'samples','lines','runtime_ms','pass_rate','name_length','like_rate')


def selected(effect):
    if 'labels' in effect:return [key for key,value in effect['labels'].items() if value]
    if 'selection' in effect:return effect['selection']
    if 'members' in effect:return effect['members']
    if 'actions' in effect:return [row[0] for row in effect['actions']]
    return None


def audit():
    feedback={}
    for line in (ROOT/'docs/reviews/2026-09-28.md').read_text().splitlines():
        match=re.match(r'^(\d{1,3})[. ：:]+(.*)',line)
        if match:feedback.setdefault(int(match[1]),[]).append(match[2])
    records=[]
    for task in catalog()['tasks'][:75]:
        task_id=task['id']
        states=[]
        for seed in SEEDS:
            try: states.append(initialize(business.generate(task_id,seed)))
            except Exception as exc: states.append({'generation_error':str(exc)})
        batches=[]
        for seed,state in zip(SEEDS,states):
            if 'generation_error' in state:
                batches.append({'seed':seed,**state});continue
            effects={v:games.expected(task_id,v,state) if task_id>=66 else business.expected_effect(task_id,v,state) for v in 'ABC'}
            if task_id==69:effects=games.stopping_paths(state)
            row={'seed':seed,'split':'demo' if seed<1000 else 'eval',
                 'objects':len(state.get('items',state.get('candidates',[]))),
                 'distinct_ABC':len(set(json.dumps(e,sort_keys=True) for e in effects.values()))==3}
            if task_id<66:
                items=state['items'];ids=[x['id'] for x in items]
                row['selected_positions']={v:[ids.index(i)+1 for i in selected(e)] for v,e in effects.items() if selected(e) is not None}
                row['single_example_rival_extrema']={}
                for v,effect in effects.items():
                    chosen=selected(effect)
                    if not chosen or len(chosen)!=1:continue
                    row['single_example_rival_extrema'][v]=[
                        f'{field}:{direction}' for field in NUMERIC for direction in ('min','max')
                        if sorted(items,key=lambda x:x[field],reverse=direction=='max')[0]['id']==chosen[0]]
                if task_id in BOUNDARIES:
                    field,value=BOUNDARIES[task_id]
                    values=[len(x['text']) if field=='text_length' else len(x['code']) if field=='code_length' else x[field] for x in items]
                    row['boundary']={'field':field,'threshold':value,'observed':sorted(set(values)),
                                     'missing':[x for x in (value-1,value,value+1) if x not in values]}
                row['source_digest']=hashlib.sha256(json.dumps(state['source'],sort_keys=True).encode()).hexdigest()
            batches.append(row)
        risks=[]
        if any('generation_error' in x for x in batches):risks.append('fixture_generation_failure')
        if any(not x.get('distinct_ABC',True) for x in batches):risks.append('counterfactual_collision')
        if task['type']=='T' or task_id>=66 or task['type']=='S' or task_id in (7,15,26,35,47,50,61,62):
            risks.append('single_episode_cannot_disambiguate_rule')
        elif any(demo.get('objects', 0) <= query.get('objects', 0) for demo,query in zip(batches[:3],batches[3:])):
            risks.append('demo_object_count_not_greater_than_eval')
        if any(x.get('boundary',{}).get('missing') for x in batches[:3]):risks.append('missing_threshold_neighbors')
        for v in 'ABC':
            signatures=[tuple(x.get('selected_positions',{}).get(v,[])) for x in batches[:3]]
            if task_id != 10 and signatures[0] and len(set(signatures))==1:
                risks.append(f'fixed_demo_positions_{v}')
        records.append({'task_id':task_id,'title':task['title'],'app':task['app'],
                        'review_comments':feedback.get(task_id,[]),'measured_risks':risks,
                        'status':'requires_fixture_and_ui_acceptance','samples':batches})
    return {'scope':list(range(1,76)),'seeds':SEEDS,
            'limits':'Rival extrema are candidate explanations, not claims that all listed fields are visible. UI and human video checks remain required.',
            'cases':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/reviews/teaching-baseline.json')
    args=parser.parse_args()
    result=audit();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'cases':len(result['cases']),'risk_counts':dict(Counter(r.split('_A')[0].split('_B')[0].split('_C')[0] for case in result['cases'] for r in set(case['measured_risks']))),'output':str(args.output)},ensure_ascii=False))
