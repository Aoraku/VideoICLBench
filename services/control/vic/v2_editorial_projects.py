"""Private checks for research selections, citations and saved knowledge pages."""
from collections import Counter


def desired(initial,variant):
    w=initial['world'];objects=initial['domain']['objects'];quota=Counter();selected={}
    for scope in w['scopes']:
        ids=list(dict.fromkeys(x for key in scope['sources'] for x in next(s['members'] for s in w['sources'] if s['id']==key)))
        if initial['task_id']==29:
            ids=[x for x in ids if quota[objects[x]['publisher']]<2]
            key={'A':lambda x:objects[x]['timestamp'],'B':lambda x:objects[x]['timestamp'],'C':lambda x:len(objects[x]['name'])}[variant]
            ids=sorted(ids,key=lambda x:objects[x]['record_code'])
            chosen=sorted(ids,key=key,reverse=variant!='B')[:1]
            quota.update(objects[x]['publisher'] for x in chosen)
        else:
            ids=[x for x in ids if scope['date_from']<=objects[x]['created_at'][:10]<=scope['date_to']]
            if variant=='C':chosen=[x for x in ids if objects[x]['comments']%2==0]
            else:
                extreme=(max if variant=='A' else min)(objects[x]['tag_count'] for x in ids)
                chosen=[x for x in ids if objects[x]['tag_count']==extreme]
        selected[scope['id']]=chosen
    return selected


def evaluate(initial,final,variant,events):
    checks=[]
    def check(name,value):checks.append(dict(id=name,passed=bool(value)))
    for key in initial.keys()-{'world','next_document'}:check('input:'+key,final.get(key)==initial[key])
    start=initial['world'];w=final['world'];expected=desired(initial,variant);t=initial['task_id']
    for key in start.keys()-{'documents','selections','directory'}:check('input:world:'+key,w.get(key)==start[key])
    check('personal_document',w['documents'].get('personal')==start['documents']['personal'])
    check('selection_scopes',set(w['selections'])==set(expected))
    for scope,ids in expected.items():check(scope+':selection',len(w['selections'].get(scope,[]))==len(ids) and set(w['selections'].get(scope,[]))==set(ids))
    bundles=[dict(id='weekly',title=start['report_title'],sections=[s['id'] for s in start['scopes']])] if t==29 else [dict(id=s['id'],title=s['document_title'],sections=[s['id']]) for s in start['scopes']]
    check('document_count',len(w['documents'])==len(bundles)+1)
    check('directory_scopes',not w['directory'] if t==29 else set(w['directory'])==set(expected))
    for bundle in bundles:
        docs=[d for d in w['documents'].values() if d['scope']==bundle['id']]
        prefix=bundle['id'];check(prefix+':one_document',len(docs)==1)
        if len(docs)!=1:continue
        document=docs[0];check(prefix+':title',document['title']==bundle['title'])
        check(prefix+':sections',set(document['sections'])==set(bundle['sections']))
        check(prefix+':saved',document['saved']=={k:v for k,v in document.items() if k!='saved'})
        for key in bundle['sections']:
            section=document['sections'].get(key,{})
            rows=section.get('rows',[]);ids=expected[key]
            check(key+':heading',section.get('heading')==next(s['name'] for s in start['scopes'] if s['id']==key))
            check(key+':articles',len(rows)==len(ids) and {r['article'] for r in rows}==set(ids))
            for i,row in enumerate(rows):
                obj=initial['domain']['objects'].get(row['article'],{})
                check(f'{key}:{i}:summary',row['summary']==obj.get('summary'))
                check(f'{key}:{i}:link',row['link']==f'news/articles/{row["article"]}')
        if t==30:
            entry=w['directory'].get(prefix,{})
            check(prefix+':directory_document',entry.get('document')==document['id'])
            check(prefix+':directory_link',entry.get('link')==f'documents/{document["id"]}')
            check(prefix+':directory_count',entry.get('count')==len(expected[prefix]))
    check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
