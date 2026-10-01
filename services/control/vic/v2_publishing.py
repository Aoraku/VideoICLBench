"""Private checks for chosen manuscripts, publications, index and author receipts."""

def desired(initial,variant):
    w=initial['world'];objects=initial['domain']['objects'];expected={}
    for project in w['projects']:
        ids=sorted(project['candidates'],key=lambda x:objects[x]['record_code'])
        if initial['task_id']==40:
            key=(lambda x:len(objects[x]['text'])) if variant=='C' else (lambda x:objects[x]['updated_at'])
            chosen=sorted(ids,key=key,reverse=variant=='A')[:1]
            for key in chosen:expected[key]=dict(column=project['column'],cover=project['cover'],summary=project['summary'],publish_at=project['publish_at'])
        else:
            for key in ids:
                obj=objects[key]
                if {'A':len(obj['tags'])>2,'B':len(obj['tags'])==0,'C':initial['source']['letter'] in obj['name']}[variant]:
                    plan=next(p for p in w['plan'] if p['draft']==key)
                    expected[key]={k:plan[k] for k in ('column','cover','summary','publish_at')}
    return expected


def evaluate(initial,final,variant,events):
    checks=[]
    def check(name,value):checks.append(dict(id=name,passed=bool(value)))
    for key in initial.keys()-{'world','next_publication','next_notice'}:check('input:'+key,initial[key]==final.get(key))
    start=initial['world'];w=final['world'];expected=desired(initial,variant)
    for key in start.keys()-{'edits','publications','index','notifications','discussion'}:check('input:world:'+key,start[key]==w.get(key))
    check('published_count',len(w['publications'])==len(expected))
    check('published_drafts',{p['draft'] for p in w['publications'].values()}==set(expected))
    check('index_columns',set(w['index'])=={p['column'] for p in expected.values()})
    indexed=[]
    for column,rows in w['index'].items():
        for i,row in enumerate(rows):
            post=w['publications'].get(row['publication'],{})
            check(f'index:{column}:{i}:column',post.get('column')==column)
            check(f'index:{column}:{i}:link',row['link']==post.get('link'))
            indexed.append(row['publication'])
    check('indexed_once',len(indexed)==len(w['publications']) and set(indexed)==set(w['publications']))
    for key,post in w['publications'].items():
        obj=initial['domain']['objects'].get(post['draft'],{})
        meta=expected.get(post['draft'],{})
        for field in ('column','cover','summary','publish_at'):check(key+':'+field,post[field]==meta.get(field))
        for field,source in [('title','name'),('body','text'),('author','author')]:check(key+':'+field,post[field]==obj.get(source))
        check(key+':link',post['link']=='posts/'+key)
        check(key+':saved_metadata',w['edits'].get(post['draft'])==meta)
        notices=[n for n in w['notifications'] if n['publication']==key]
        if initial['task_id']==42:
            check(key+':author_notified',bool(notices))
            for i,notice in enumerate(notices):
                check(f'{key}:notice:{i}:recipient',notice['recipient']==obj.get('author'))
                for field in ('title','summary','link','publish_at'):check(f'{key}:notice:{i}:'+field,notice[field]==post[field])
    check('no_unrelated_notices',all(n['publication'] in w['publications'] for n in w['notifications']) if initial['task_id']==42 else not w['notifications'])
    check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
