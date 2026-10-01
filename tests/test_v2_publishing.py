"""Publishing tests inspect real articles, index links and author messages."""
from copy import deepcopy
import json
import pytest
from vic import v2
from vic_apps import publishing
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def selected(initial,variant):
    w=initial['world'];items=initial['domain']['objects'];result={}
    for project in w['projects']:
        candidates=[items[id] for id in project['candidates']]
        if initial['task_id']==40:
            key=(lambda item:len(item['text'])) if variant=='C' else (lambda item:item['updated_at'])
            chosen=sorted(candidates,key=key,reverse=variant=='A')[:1]
        else:
            chosen=[item for item in candidates if (len(item['tags'])>2 if variant=='A' else not item['tags'] if variant=='B' else initial['source']['letter'] in item['name'])]
        for item in chosen:
            source=project if initial['task_id']==40 else next(p for p in w['plan'] if p['draft']==item['id'])
            result[item['id']]={k:source[k] for k in ('column','cover','summary','publish_at')}
    return result


def plan(initial,variant):
    for n,(draft,meta) in enumerate(selected(initial,variant).items(),1):
        key=f'post-{n:03d}'
        yield 'post.metadata',draft,meta
        yield 'post.publish',draft,{}
        yield 'index.add',meta['column'],dict(publication=key)
        if initial['task_id']==42:yield 'post.notify',key,dict(recipient=initial['domain']['objects'][draft]['author'])


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data in plan(initial,variant):
        value=json.dumps(data);state=publishing.apply(state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[40,42])
@pytest.mark.parametrize('variant',list('ABC'))
def test_native_publications_index_messages_and_reset(clients,task_id,variant):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id'];headers=credential(run)
    initial=worker.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'expected' not in json.dumps(initial) and 'variants' not in json.dumps(initial)
    for i,(op,target,data) in enumerate(plan(initial,variant)):
        body=dict(epoch=0,action_id=str(i),op=op,target=target,value=json.dumps(data))
        r=worker.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        duplicate=worker.post(path+'/commands',headers=headers,json=body)
        assert duplicate.status_code==200 and duplicate.json()['state']==r.json()['state']
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    final=worker.get(path,headers=headers).json()['state']
    assert len(final['world']['publications'])==len(selected(initial,variant))
    for cover in initial['world']['covers']:
        asset=worker.get(cover['url'])
        assert asset.status_code==200 and asset.headers['content-type'].startswith('image/svg+xml') and cover['name'] in asset.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial
    assert worker.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[40,42])
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_publication_choices_distinct_and_initial_drafts_frozen(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant)
        result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
        assert all(initial['domain']['objects'][p['draft']]['batch']=='2026-W06' for p in final['world']['publications'].values())
        assert final['domain']==initial['domain']


@pytest.mark.parametrize('task_id',[40,42])
def test_wrong_content_schedule_or_index_does_not_pass(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'A')
    for field in ('column','cover','summary','publish_at','title','body','author','link','missing','duplicate','index_link','index_column','missing_index','metadata','input'):
        wrong=deepcopy(final);post=wrong['world']['publications']['post-001'];column=post['column']
        if field in ('column','cover','summary','publish_at','title','body','author','link'):post[field]='wrong'
        elif field=='missing':del wrong['world']['publications']['post-001']
        elif field=='duplicate':wrong['world']['publications']['extra']=deepcopy(post)
        elif field=='index_link':wrong['world']['index'][column][0]['link']='posts/absent'
        elif field=='index_column':wrong['world']['index']['other']=wrong['world']['index'].pop(column)
        elif field=='missing_index':wrong['world']['index']={}
        elif field=='metadata':wrong['world']['edits'][post['draft']]['publish_at']='2026-03-01T00:00'
        else:wrong['domain']['objects'][post['draft']]['text']='changed'
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field


def test_author_notifications_require_real_article_and_correct_recipient():
    initial=v2.generate(42,10001,'eval');final,events=complete(initial,'C')
    for field in ('recipient','title','summary','link','publication','publish_at','missing'):
        wrong=deepcopy(final)
        if field=='missing':wrong['world']['notifications']=[]
        else:wrong['world']['notifications'][0][field]='wrong'
        assert not v2.evaluate(initial,wrong,'C',events)['success'],field
    post=final['world']['publications']['post-001']
    with pytest.raises(ValueError):publishing.apply(final,'post.metadata',post['draft'],json.dumps(selected(initial,'C')[post['draft']]))
    with pytest.raises(ValueError):publishing.apply(final,'post.publish',post['draft'])
    with pytest.raises(ValueError):publishing.apply(final,'post.withdraw','post-001')
    # Removing references before withdrawal keeps the remaining links usable.
    changed=publishing.apply(final,'index.remove',post['column'],'{"publication":"post-001"}')
    notice=next(n for n in changed['world']['notifications'] if n['publication']=='post-001')
    changed=publishing.apply(changed,'notice.withdraw',notice['id'])
    changed=publishing.apply(changed,'post.withdraw','post-001')
    assert 'post-001' not in changed['world']['publications']
    restored=publishing.apply(changed,'post.publish',post['draft'])
    key='post-010'
    restored=publishing.apply(restored,'index.add',post['column'],json.dumps(dict(publication=key)))
    restored=publishing.apply(restored,'post.notify',key,json.dumps(dict(recipient=post['author'])))
    assert v2.evaluate(initial,restored,'C',events)['success']


def test_tag_boundary_old_batch_and_missing_metadata():
    initial=v2.generate(42,10001,'eval');selected_a=selected(initial,'A');selected_b=selected(initial,'B');selected_c=selected(initial,'C')
    assert any(len(item['tags'])==2 and item['id'] in selected_c and item['id'] not in selected_a for item in initial['items'])
    assert any(not item['tags'] and item['id'] in selected_b for item in initial['items'])
    first=next(iter(selected_a))
    with pytest.raises(ValueError):publishing.apply(initial,'post.publish',first)
    bad=deepcopy(selected_a[first]);bad['publish_at']='not-a-date'
    with pytest.raises(ValueError):publishing.apply(initial,'post.metadata',first,json.dumps(bad))


def test_only_manuscripts_accept_publication_metadata():
    initial=v2.generate(40,10001,'eval');meta=next(iter(selected(initial,'A').values()))
    for target in ('target','contact-a','unknown'):
        with pytest.raises(ValueError):publishing.apply(initial,'post.metadata',target,json.dumps(meta))
        with pytest.raises(ValueError):publishing.apply(initial,'post.publish',target)
