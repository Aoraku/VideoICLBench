"""Private evaluation of project configuration and concrete checked deliveries."""
from vic_apps.studio_projects import generate_text,check_output,digest,manifest_text
from vic_apps.communications import file_record


def chosen_model(initial,project,variant):
    objects=initial['domain']['objects']
    ids=[x for x in project['available_models'] if objects[x]['context']>=project['min_context']]
    ids=sorted(ids,key=lambda x:objects[x]['model_code'])
    key={'A':lambda x:objects[x]['context'],'B':lambda x:objects[x]['price'],'C':lambda x:len(objects[x]['name'])}[variant]
    return sorted(ids,key=key,reverse=variant=='A')[0]


def evaluate(initial,final,variant,events):
    checks=[]
    def check(name,value):checks.append(dict(id=name,passed=bool(value)))
    for key in initial.keys()-{'domain','world','next_generation','next_archive','next_receipt'}:check('input:'+key,final.get(key)==initial[key])
    start=initial['world'];w=final['world'];objects=initial['domain']['objects'];files=dict(initial['domain']['files'])
    for key in initial['domain'].keys()-{'files'}:check('input:domain:'+key,final['domain'].get(key)==initial['domain'][key])
    mutable={'configs','generations','archives','checks','saved','copies','receipts','discussion','delivery'}
    for key in start.keys()-mutable:check('input:world:'+key,w.get(key)==start[key])
    if initial['task_id']==41:
        check('project_configurations',set(w['configs'])=={p['id'] for p in start['projects']})
        check('archive_count',len(w['archives'])==len(start['projects']))
        for project in start['projects']:
            prefix=project['id'];config=dict(model=chosen_model(initial,project,variant),template=project['template'],document=project['document'])
            check(prefix+':configuration',w['configs'].get(prefix)==config)
            archives=[a for a in w['archives'].values() if a['project']==prefix];check(prefix+':one_archive',len(archives)==1)
            if len(archives)!=1:continue
            archive=archives[0];generation=w['generations'].get(archive['generation'],{})
            body=generate_text(initial,project,config)
            check(prefix+':generation_project',generation.get('project')==prefix)
            check(prefix+':generation_config',generation.get('config')==config)
            check(prefix+':generation_body',generation.get('body')==body)
            check(prefix+':generation_digest',generation.get('digest')==digest(body))
            check(prefix+':archive_config',archive['config']==config)
            check(prefix+':archive_link',archive['link']=='files/'+archive['file'])
            files[archive['file']]=file_record(project['name']+'.md',body)
        for key in ('checks','saved','copies','receipts'):check('no_unrelated:'+key,not w[key])
        check('no_delivery',w['delivery']==start['delivery'])
    else:
        targets=[x for project in start['projects'] for x in project['outputs']]
        passed={target for target in targets if check_output(objects[target]['code'])['passed']}
        for target in targets:check(target+':check',w['checks'].get(target)==check_output(objects[target]['code']))
        check('saved_set',set(w['saved'])==(passed if variant=='A' else set()))
        check('copied_set',set(w['copies'])==(passed if variant=='B' else set()))
        check('sent_set',{r['target'] for r in w['receipts']}==(passed if variant=='C' else set()))
        rows=w['delivery']['rows'];check('delivery_rows',set(rows)==passed)
        check('delivery_saved',w['delivery']['saved']==rows and bool(rows))
        for target in passed:
            item=objects[target];row=rows.get(target,{})
            check(target+':kind',row.get('kind')=={'A':'saved','B':'copied','C':'sent'}[variant])
            if variant=='A':
                file=w['saved'].get(target,'')
                check(target+':file_reference',row.get('reference')=='files/'+file and bool(file))
                if file:files[file]=file_record(item['record_code']+'-'+item['name'],item['code'])
            elif variant=='B':
                check(target+':copy',w['copies'].get(target)==dict(body=item['code'],digest=digest(item['code'])))
                check(target+':paste_reference',row.get('reference')=='copies/'+target)
                check(target+':pasted_body',row.get('body')==item['code'])
            else:
                receipts=[r for r in w['receipts'] if r['target']==target]
                recipient=next(p['recipient'] for p in start['projects'] if p['id']==item['project'])
                check(target+':receipt_reference',row.get('reference') in ['receipts/'+r['id'] for r in receipts])
                for i,receipt in enumerate(receipts):
                    for key,value in dict(recipient=recipient,name=item['name'],record_code=item['record_code'],body=item['code'],digest=digest(item['code']),link='outputs/'+target).items():check(f'{target}:receipt:{i}:'+key,receipt[key]==value)
        # Render the persisted manifest only after its row identities are valid.
        if set(rows)<=set(targets) and all(r.get('kind') in ('saved','copied','sent') and isinstance(r.get('reference'),str) and (r['kind']!='copied' or isinstance(r.get('body'),str)) for r in rows.values()):
            files['delivery-manifest']=file_record('生成结果交付清单.md',manifest_text(initial,rows))
        for key in ('configs','generations','archives'):check('no_unrelated:'+key,not w[key])
    check('file_contents',final['domain']['files']==files)
    check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
