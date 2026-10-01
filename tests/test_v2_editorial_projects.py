"""Independent editorial delivery checks, including quotas and linked content."""
from copy import deepcopy
from collections import Counter
import json
import pytest
from vic import v2
from vic_apps import editorial_projects
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def select(initial,variant):
    objects=initial['domain']['objects'];selected={};counts=Counter()
    for scope in initial['world']['scopes']:
        candidates=[x for x in initial['items'] if x['scope_id']==scope['id']]
        if initial['task_id']==29:
            candidates=[x for x in candidates if counts[x['publisher']]<2]
            field='name' if variant=='C' else 'created_at'
            chosen=sorted(candidates,key=lambda x:len(x[field]) if field=='name' else x[field],reverse=variant!='B')[:1]
            counts.update(x['publisher'] for x in chosen)
        else:
            candidates=[x for x in candidates if scope['date_from']<=x['created_at'][:10]<=scope['date_to']]
            if variant=='C':chosen=[x for x in candidates if x['comments']%2==0]
            else:
                bound=(max if variant=='A' else min)(x['tag_count'] for x in candidates)
                chosen=[x for x in candidates if x['tag_count']==bound]
        selected[scope['id']]=[x['id'] for x in chosen]
    return selected


def plan(initial,variant):
    w=initial['world'];selected=select(initial,variant)
    for scope,ids in selected.items():yield 'reading.select',scope,dict(articles=ids)
    bundles=[('weekly',w['report_title'],list(selected))] if initial['task_id']==29 else [(s['id'],s['document_title'],[s['id']]) for s in w['scopes']]
    for n,(scope,title,sections) in enumerate(bundles,1):
        key=f'doc-{n:03d}'
        yield 'document.create','',dict(scope=scope,title=title)
        for section in sections:
            for article in selected[section]:
                yield 'document.article',key,dict(section=section,article=article,link='news/articles/'+article,summary=initial['domain']['objects'][article]['summary'])
        yield 'document.save',key,{}
        if initial['task_id']==30:yield 'directory.entry',scope,dict(document=key,link='documents/'+key,count=len(selected[scope]))


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data in plan(initial,variant):
        value=json.dumps(data);state=editorial_projects.apply(state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[29,30])
@pytest.mark.parametrize('variant',list('ABC'))
def test_editorial_saved_citations_delivery_and_reset(clients,task_id,variant):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id'];headers=credential(run)
    initial=worker.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    for i,(op,target,data) in enumerate(plan(initial,variant)):
        body=dict(op=op,target=target,value=json.dumps(data),epoch=0,action_id=str(i))
        r=worker.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        repeat=worker.post(path+'/commands',headers=headers,json=body);assert repeat.status_code==200 and repeat.json()['state']==r.json()['state']
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    assert worker.get(f'/native/product/blog/{run["id"]}').status_code==200
    assert worker.get(f'/native/product/bank/{run["id"]}').status_code==404
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial


@pytest.mark.parametrize('task_id',[29,30])
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_variants_public_constraints_and_seed_determinism(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant);result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
        selected=select(initial,variant)
        if task_id==29:
            counts=Counter(initial['domain']['objects'][id]['publisher'] for ids in selected.values() for id in ids)
            assert max(counts.values())<=2 and len(counts)>1
        else:assert all('2026-01-01'<=initial['domain']['objects'][id]['created_at'][:10]<='2026-01-31' for ids in selected.values() for id in ids)


@pytest.mark.parametrize('task_id',[29,30])
def test_incorrect_citations_unsaved_documents_and_stale_directory_fail(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'C')
    fields=['title','saved','summary','link','missing_article','selection','personal','inputs']+(['directory_link','directory_count','directory_document'] if task_id==30 else [])
    for field in fields:
        wrong=deepcopy(final);doc=wrong['world']['documents']['doc-001'];section=next(iter(doc['sections'].values()))
        if field=='title':doc['title']='错误标题'
        elif field=='saved':doc['saved']=None
        elif field in ('summary','link'):section['rows'][0][field]='错误引用'
        elif field=='missing_article':section['rows'].pop()
        elif field=='selection':wrong['world']['selections']['topic-1']=[]
        elif field=='personal':wrong['world']['documents']['personal']['title']='changed'
        elif field=='inputs':wrong['world']['scopes'][0]['date_from']='2020-01-01'
        elif field=='directory_link':wrong['world']['directory']['topic-1']['link']='documents/personal'
        elif field=='directory_count':wrong['world']['directory']['topic-1']['count']+=1
        elif field=='directory_document':wrong['world']['directory']['topic-1']['document']='personal'
        assert not v2.evaluate(initial,wrong,'C',events)['success'],field


def test_editing_and_removal_are_real_reversible_document_operations():
    initial=v2.generate(30,10001,'eval');state,events=complete(initial,'A');key='doc-001'
    scope='topic-1';row=state['world']['documents'][key]['sections'][scope]['rows'][0]
    changed=editorial_projects.apply(state,'document.remove',key,json.dumps(dict(section=scope,article=row['article'])))
    with pytest.raises(ValueError):editorial_projects.apply(changed,'document.save',key)
    restored=editorial_projects.apply(changed,'document.article',key,json.dumps(dict(section=scope,**row)))
    assert v2.evaluate(initial,restored,'A',events)['success']
    with pytest.raises(ValueError):editorial_projects.apply(restored,'document.delete',key)
    cleared=editorial_projects.apply(restored,'directory.remove',scope)
    deleted=editorial_projects.apply(cleared,'document.delete',key)
    assert key not in deleted['world']['documents']
