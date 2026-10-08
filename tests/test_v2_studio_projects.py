"""Project tests verify provenance, parsed code and actual delivery bytes."""
import ast
import base64
from cross_platform_helpers import with_handoffs, apply_command, redeliver
from copy import deepcopy
import hashlib
import json
import pytest
from vic import v2
from vic_apps import studio_projects as studio
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def config(initial,project,variant):
    # Independently select within public project eligibility constraints.
    candidates=[x for x in initial['items'] if x['id'] in project['available_models'] and x['context']>=project['min_context']]
    metric={'A':lambda x:-x['context'],'B':lambda x:x['price'],'C':lambda x:len(x['name'])}[variant]
    chosen=min(candidates,key=lambda x:(metric(x),x['model_code']))
    return dict(model=chosen['id'],template=project['template'],document=project['document'])


def valid(code):
    try:ast.parse(code);return True
    except SyntaxError:return False


@with_handoffs(studio.apply,3)
def plan(initial,variant):
    if initial['task_id']==41:
        for i,p in enumerate(initial['world']['projects'],1):
            yield 'config.save',p['id'],config(initial,p,variant)
            yield 'generation.run',p['id'],{}
            yield 'generation.archive',f'generation-{i:03d}',dict(project=p['id'])
    else:
        count=0
        for p in initial['world']['projects']:
            for target in p['outputs']:
                item=initial['domain']['objects'][target]
                yield 'output.check',target,{}
                if not valid(item['code']):continue
                count+=1
                if variant=='A':
                    yield 'output.save',target,{}
                    yield 'delivery.line',target,dict(kind='saved',reference='files/output-'+target)
                elif variant=='B':
                    yield 'output.copy',target,{}
                    yield 'delivery.paste',target,dict(body=item['code'])
                else:
                    yield 'output.send',target,dict(recipient=p['recipient'])
                    yield 'delivery.line',target,dict(kind='sent',reference=f'receipts/receipt-{count:03d}')
        yield 'delivery.save','',{}


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data in plan(initial,variant):
        value=json.dumps(data);state=apply_command(studio.apply,state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[41,43])
@pytest.mark.parametrize('variant',list('ABC'))
def test_project_delivery_apis_downloads_reset_and_idempotency(clients,task_id,variant):
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
    final=worker.get(path,headers=headers).json()['state']
    for id,record in final['domain']['files'].items():
        r=worker.get(path+'/files/'+id,headers=headers)
        assert r.status_code==200 and r.content==base64.b64decode(record['content'])
        assert len(r.content)==record['size'] and hashlib.sha256(r.content).hexdigest()==record['sha256']
        assert worker.get(path+'/files/'+id).status_code==403
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    if task_id==43 and variant=='B':assert result.json()['clipboard_evidence_source']=='application_delivery_paste'
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial
    assert worker.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[41,43])
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_project_rules_distinct_reproducible_and_input_preserved(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant)
        result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
        assert final['domain']['objects']==initial['domain']['objects']
        if task_id==43:assert len(final['world']['checks'])==12 and len(final['world']['delivery']['rows'])==6


def test_project_generation_requires_correct_provenance_and_real_archive():
    initial=v2.generate(41,10001,'eval');final,events=complete(initial,'A')
    for field in ('model','template','document','archive_project','archive_config','body','digest','file','missing','extra','input'):
        wrong=deepcopy(final);w=wrong['world']
        if field in ('model','template','document'):w['configs']['project-1'][field]='wrong'
        elif field=='archive_project':w['archives']['archive-001']['project']='project-2'
        elif field=='archive_config':w['archives']['archive-001']['config']['model']='wrong'
        elif field=='body':w['generations']['generation-001']['body']='unrelated output'
        elif field=='digest':w['generations']['generation-001']['digest']='wrong'
        elif field=='file':wrong['domain']['files']['file-archive-001']['content']='ZmFrZQ=='
        elif field=='missing':del w['archives']['archive-001']
        elif field=='extra':w['archives']['extra']=deepcopy(w['archives']['archive-001'])
        else:w['documents'][0]['records']=['changed']
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field
    project=initial['world']['projects'][0];conf=config(initial,project,'A')
    for model in [x for x in initial['items'] if x['model_code'] in ('M-10','M-11')]:
        with pytest.raises(ValueError):studio.apply(initial,'config.save',project['id'],json.dumps({**conf,'model':model['id']}))
    with pytest.raises(ValueError):studio.apply(initial,'generation.run',project['id'])
    old=studio.apply(initial,'config.save',project['id'],json.dumps({**conf,'template':'template-1-v1','document':'document-1-v1'}))
    old=studio.apply(old,'generation.run',project['id'])
    assert 'v1' in old['world']['generations']['generation-001']['body']
    assert old['world']['generations']['generation-001']['body']!=final['world']['generations']['generation-001']['body']
    removed=studio.apply(final,'archive.remove','archive-001');assert 'file-archive-001' not in removed['domain']['files']
    restored=studio.apply(removed,'generation.archive','generation-001','{"project":"project-1"}')
    assert not v2.evaluate(initial,restored,'A',events)['success']
    restored=redeliver(restored)
    assert v2.evaluate(initial,restored,'A',events)['success']


@pytest.mark.parametrize('variant',list('ABC'))
def test_delivery_requires_checks_identity_content_and_saved_manifest(variant):
    initial=v2.generate(43,10001,'eval');final,events=complete(initial,variant)
    targets=list(final['world']['delivery']['rows']);target=targets[0]
    for field in ('missing_check','fake_check','missing_row','wrong_reference','stale_manifest','file','input','wrong_method'):
        wrong=deepcopy(final);w=wrong['world']
        if field=='missing_check':del w['checks'][target]
        elif field=='fake_check':w['checks'][target]['digest']='fake'
        elif field=='missing_row':del w['delivery']['rows'][target]
        elif field=='wrong_reference':w['delivery']['rows'][target]['reference']=w['delivery']['rows'][targets[1]]['reference']
        elif field=='stale_manifest':w['delivery']['saved']={}
        elif field=='file':wrong['domain']['files']['delivery-manifest']['content']='ZmFrZQ=='
        elif field=='input':wrong['domain']['objects'][target]['code']='pass'
        else:w['delivery']['rows'][target]['kind']='saved' if variant!='A' else 'sent'
        assert not v2.evaluate(initial,wrong,variant,events)['success'],field
    if variant=='B':
        changed=studio.apply(final,'delivery.paste',target,json.dumps(dict(body=initial['domain']['objects'][targets[1]]['code'])))
        changed=studio.apply(changed,'delivery.save')
        assert not v2.evaluate(initial,changed,variant,events)['success']
    elif variant=='C':
        changed=deepcopy(final);changed['world']['receipts'][0]['recipient']=999
        assert not v2.evaluate(initial,changed,variant,events)['success']
    changed=studio.apply(final,'output.clear',target)
    assert not v2.evaluate(initial,changed,variant,events)['success']
    assert target not in changed['world']['delivery']['rows']


def test_syntax_failures_cannot_be_delivered_and_copy_must_precede_paste():
    state=v2.generate(43,10001,'eval');bad=next(x for x in state['items'] if not valid(x['code']))
    good=next(x for x in state['items'] if valid(x['code']) and x['project']!='historical')
    for op,data in [('output.save',{}),('output.copy',{}),('output.send',dict(recipient=10))]:
        with pytest.raises(ValueError):studio.apply(state,op,good['id'],json.dumps(data))
        checked=studio.apply(state,'output.check',bad['id'])
        assert not checked['world']['checks'][bad['id']]['passed']
        with pytest.raises(ValueError):studio.apply(checked,op,bad['id'],json.dumps(data))
    checked=studio.apply(state,'output.check',good['id'])
    with pytest.raises(ValueError):studio.apply(checked,'delivery.paste',good['id'],json.dumps(dict(body=good['code'])))
    assert studio.check_output('import os\nos.system("exit 99")')['passed']  # Parsing does not execute code.


def test_copy_lesson_checks_application_clipboard_without_os_read(clients):
    from test_lessons import create_lesson,operate,actor
    c,w=clients;run=create_lesson(c,43,'B');operate(w,run,'B')
    payload=dict(epoch=run['epoch'],index=0)
    good=c.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),json=payload)
    assert good.status_code==200 and good.json()['lesson']['finished']
    result=c.post('/v1/runs/'+run['id']+'/evaluate',headers=admin())
    assert result.status_code==200 and result.json()['success'],result.text
    assert result.json()['clipboard_evidence_source']=='application_clipboard'
