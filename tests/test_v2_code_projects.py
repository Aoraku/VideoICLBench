"""Native course workflows require real source, tests, submissions and archives."""
from cross_platform_helpers import with_handoffs, apply_command, redeliver
from copy import deepcopy
from io import BytesIO
import base64,json,zipfile
import pytest
from vic import v2,v2_code_projects as rules
from vic_apps import code_projects as course
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


@with_handoffs(course.apply,3)
def commands(initial,variant):
    state=initial
    for e in initial['world']['entries']:
        if initial['task_id']==64:
            op='code.restore';data={'version':f'HIST-{int(e["id"][-2:])}-'+{'A':'2','B':'1','C':'3'}[variant]}
        else:op='code.save';data={'files':rules.target_files(initial,e,variant)}
        yield op,e['id'],data;state=course.apply(state,op,e['id'],json.dumps(data))
        yield 'code.check',e['id'],{};state=course.apply(state,'code.check',e['id'])
        needed=initial['task_id'] in (58,60) or (initial['task_id']==65 and int(e['id'][-2:]) in {'A':{1,2,4},'B':{1,3,5},'C':{1,3,4}}[variant])
        if needed:
            data={'problem':e['problem']};yield 'code.submit',e['id'],data;state=course.apply(state,'code.submit',e['id'],json.dumps(data))
    yield 'delivery.save','',{'rows':course.delivery_rows(state)}
    yield 'delivery.publish','',{}


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data in commands(initial,variant):
        value=json.dumps(data);state=apply_command(course.apply,state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[58,60,64,65])
@pytest.mark.parametrize('variant',list('ABC'))
def test_code_api_real_snapshots_archives_reset_and_idempotency(clients,task_id,variant):
    control,worker=clients
    r=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',interaction='human'))
    assert r.status_code==201,r.text
    run=r.json();path='/api/runs/'+run['id'];headers=credential(run);initial=worker.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    for i,(op,target,data) in enumerate(commands(initial,variant)):
        body=dict(epoch=0,action_id=str(i),op=op,target=target,value=json.dumps(data))
        r=worker.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        assert worker.post(path+'/commands',headers=headers,json=body).json()['state']==r.json()['state']
    final=worker.get(path,headers=headers).json()['state']
    for id,file in final['domain']['files'].items():
        r=worker.get(path+'/files/'+id,headers=headers);assert r.status_code==200 and r.content==base64.b64decode(file['content'])
        assert worker.get(path+'/files/'+id).status_code==403
    with zipfile.ZipFile(BytesIO(base64.b64decode(final['domain']['files']['course-delivery']['content']))) as bundle:
        assert json.loads(bundle.read('manifest.json'))==final['world']['delivery']['rows']
        for e in initial['world']['entries']:
            for name,code in final['world']['drafts'][e['id']].items():assert bundle.read(e['id']+'/'+name).decode()==code
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial
    assert worker.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[58,60,64,65])
@pytest.mark.parametrize('seed',[1000,27483])
def test_rule_versions_have_distinct_deliveries(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant);result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']


@pytest.mark.parametrize('task_id',[58,60,64,65])
def test_forged_code_results_manifest_and_files_fail(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'A');first=initial['world']['entries'][0]['id']
    for field in ['draft','check','source','manifest','published','archive','missing_check','entry_set']+(['submission','problem','extra'] if task_id!=64 else ['version']):
        wrong=deepcopy(final);w=wrong['world']
        if field=='draft':w['drafts'][first][next(iter(w['drafts'][first]))]+='# changed\n'
        elif field=='check':w['checks']['CHK-0001']['tests']['status']='fake'
        elif field=='source':w['entries'][0]['files'][next(iter(w['entries'][0]['files']))]='forged'
        elif field=='manifest':w['delivery']['rows'].reverse();w['delivery']['body']='forged'
        elif field=='published':w['delivery']['published']=False
        elif field=='archive':wrong['domain']['files']['course-delivery']['content']='ZmFrZQ=='
        elif field=='missing_check':del w['checks']['CHK-0001']
        elif field=='entry_set':w['drafts']['unrelated']={'other.py':'pass'}
        elif field=='version':w['restored'][first]='HIST-1-1'
        elif field=='submission':w['submissions']['SUB-0001']['files']['solution.py']='pass'
        elif field=='problem':w['submissions']['SUB-0001']['problem']='9999'
        else:w['submissions']['SUB-9999']=deepcopy(w['submissions']['SUB-0001'])
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field


def test_cross_file_rename_preserves_strings_interfaces_and_actual_behavior():
    initial=v2.generate(60,10001,'eval');final,events=complete(initial,'C');files=final['world']['drafts']['PROJECT-01']
    assert 'from pricing import subtotal, TAX_RATE' in files['invoice.py']
    assert '"label": "total tax_rate tax"' in files['invoice.py']
    assert 'TOTAL += price * quantity' in files['pricing.py']
    assert files['app.py']==initial['world']['entries'][0]['files']['app.py']
    checked=final['world']['checks']['CHK-0001'];assert [r['actual'] for r in checked['tests']['cases']]==[486,0,109]
    wrong=deepcopy(final);wrong['world']['drafts']['PROJECT-01']['invoice.py']=files['invoice.py'].replace('"total tax_rate tax"','"TOTAL TAX_RATE TAX"')
    assert not v2.evaluate(initial,wrong,'C',events)['success']


def test_versions_may_have_real_failures_without_failing_delivery():
    initial=v2.generate(64,10001,'eval')
    for variant,status in [('B','WA'),('C','CE')]:
        final,events=complete(initial,variant)
        assert final['world']['checks']['CHK-0001']['tests']['status']==status
        assert v2.evaluate(initial,final,variant,events)['success']


def test_candidate_conditions_distinguish_syntax_function_and_strict_length():
    initial=v2.generate(65,10001,'eval');assert len(initial['world']['entries'][5]['files']['solution.py'])==90
    for variant,numbers in [('A',{1,2,4}),('B',{1,3,5}),('C',{1,3,4})]:
        final,events=complete(initial,variant)
        assert {int(s['entry'][-2:]) for s in final['world']['submissions'].values()}==numbers
        assert v2.evaluate(initial,final,variant,events)['success']
        if variant=='B':assert any(s['tests']['status']=='CE' for s in final['world']['submissions'].values())


def test_stale_checks_submissions_and_archives_need_refresh():
    initial=v2.generate(58,10001,'eval');final,events=complete(initial,'A')
    with pytest.raises(ValueError):course.apply(final,'code.check','EX-01')
    changed=course.apply(final,'delivery.reopen');files=deepcopy(changed['world']['drafts']['EX-01']);files['solution.py']+='\n'
    changed=course.apply(changed,'code.save','EX-01',json.dumps(dict(files=files)))
    with pytest.raises(ValueError):course.apply(changed,'code.submit','EX-01',json.dumps(dict(problem='2101')))
    with pytest.raises(ValueError):course.apply(changed,'delivery.publish')
    changed=course.apply(changed,'code.save','EX-01',json.dumps(dict(files=final['world']['drafts']['EX-01'])))
    changed=course.apply(changed,'code.withdraw','SUB-0001')
    assert 'submission-SUB-0001' not in changed['domain']['files']
    changed=course.apply(changed,'code.submit','EX-01',json.dumps(dict(problem='2102')))
    assert changed['world']['submissions']['SUB-0004']['tests']['status']=='WA'
    changed=course.apply(changed,'delivery.save','',json.dumps(dict(rows=course.delivery_rows(changed))))
    changed=course.apply(changed,'delivery.publish');assert not v2.evaluate(initial,changed,'A',events)['success']
    changed=course.apply(changed,'delivery.reopen');changed=course.apply(changed,'code.withdraw','SUB-0004')
    changed=course.apply(changed,'code.submit','EX-01',json.dumps(dict(problem='2101')))
    changed=course.apply(changed,'delivery.delete');assert 'course-delivery' not in changed['domain']['files']
    changed=course.apply(changed,'delivery.save','',json.dumps(dict(rows=course.delivery_rows(changed))))
    changed=course.apply(changed,'delivery.publish');assert not v2.evaluate(initial,changed,'A',events)['success']
    changed=redeliver(changed);assert v2.evaluate(initial,changed,'A',events)['success']
