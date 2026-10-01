import json
from copy import deepcopy
from collections import Counter
import pytest
from vic import v2
from vic_apps import procurement
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def test_contracts_cover_75_concrete_assignments():
    tasks=v2.catalog()['tasks']
    assert [t['id'] for t in tasks] == list(range(1,76))
    assert Counter(t['difficulty'] for t in tasks)=={'low':25,'medium':25,'hard':25}
    for t in tasks:
        assert t['assignment'] and t['delivery'] and t['demo']['instructions'] and t['inference']['instructions']
        assert set(t['variants']) == {'A','B','C'}


def purchase_lines(initial):
    """Independent test calculation: revisions replace, supplemental IDs accumulate."""
    latest={}
    for request in sorted(initial['world']['requests'],key=lambda r:r['revision']):
        latest[request['number']]=request
    quantities={}
    for request in latest.values():
        for line in request['lines']:
            key=request['department'],line['sku']
            quantities[key]=quantities.get(key,0)+line['quantity']
    return quantities


def operate(client,run,op,target='',data=None,action_id=None):
    from uuid import uuid4
    response=client.post('/api/runs/'+run['id']+'/commands',headers=credential(run),
        json=dict(epoch=run['epoch'],action_id=action_id or uuid4().hex,op=op,target=target,value=json.dumps(data or {})))
    return response


@pytest.mark.parametrize('variant',['A','B','C'])
def test_procurement_real_records_evaluate_and_reset(clients,variant):
    control,worker=clients
    r=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=45,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert r.status_code==201,r.text
    run=r.json();path='/api/runs/'+run['id']
    initial=worker.get(path,headers=credential(run)).json()['state']
    assert 'variants' not in json.dumps(initial) and 'expected' not in json.dumps(initial)
    quantities=purchase_lines(initial)
    for index,dep in enumerate(initial['world']['departments'],1):
        assert operate(worker,run,'order.create',data={'department':dep['id']}).status_code==200
        order=f'PO-{index:03d}'
        assert operate(worker,run,'order.address',order,{'address':dep['address']}).status_code==200
        for (department,sku),quantity in quantities.items():
            if department!=dep['id']:continue
            name=next(p['name'] for p in initial['world']['products'] if p['id']==sku)
            note={'A':f'{quantity}{name}','B':f'{name}{quantity}','C':'零一二三四五六七八九'[quantity]+name}[variant]
            response=operate(worker,run,'order.line',order,dict(sku=sku,quantity=quantity,note=note))
            assert response.status_code==200,response.text
        assert operate(worker,run,'order.save',order).status_code==200
    final=worker.get(path,headers=credential(run)).json()['state']
    assert v2.evaluate(initial,final,variant,[])['success']
    # Wrong addresses, duplicate orders, stale notes and unsaved edits must all fail.
    for bad in ['address','quantity','note','status','duplicate']:
        changed=deepcopy(final);o=changed['world']['orders']['PO-001'];sku=next(iter(o['lines']))
        if bad=='address':o['address']='另一地址'
        if bad=='quantity':o['lines'][sku]['quantity']+=1
        if bad=='note':o['lines'][sku]['note']='1'+o['lines'][sku]['note']
        if bad=='status':o['status']='draft'
        if bad=='duplicate':changed['world']['orders']['PO-099']=deepcopy(o)
        assert not v2.evaluate(initial,changed,variant,[])['success'],bad
    assert control.post('/v1/tasks/45/eval',headers=admin(),json={'run_id':run['id']}).status_code==409
    result=control.post('/v2/tasks/45/eval',headers=admin(),json={'run_id':run['id']})
    assert result.status_code==200 and result.json()['success'],result.text
    assert operate(worker,run,'order.create',data={'department':'design'}).status_code==409
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin())
    assert reset.status_code==200,reset.text
    assert worker.get(path,headers=credential(run)).status_code==403
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial


def test_v2_credentials_unimplemented_guard_and_demo(clients):
    control,worker=clients
    assert control.get('/v2/tasks').status_code==401
    assert len(control.get('/v2/tasks',headers=admin()).json()['tasks'])==75
    assert control.get('/v2/tasks/76/contract',headers=admin()).status_code==404
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=46,variant='A',seed=10001))
    assert response.status_code==409
    demo=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=45,variant='C',seed=0,mode='demo',interaction='human',teaching=True))
    assert demo.status_code==201,demo.text
    run=demo.json();state=worker.get('/api/runs/'+run['id'],headers=credential(run)).json()['state']
    assert 'domain' in state and 'workflow' not in state
    from vic.business import transform
    result=worker.post('/api/runs/'+run['id']+'/commands',headers=credential(run),json=dict(epoch=0,action_id='demo-save',op='save',target='target',value=transform(45,2,state)))
    assert result.status_code==200,result.text


def test_procurement_validation_and_inputs_immutable():
    state=procurement.fixture(10001)
    with pytest.raises(ValueError):procurement.apply(state,'order.create','','{"department":"unknown"}')
    with pytest.raises(ValueError):procurement.apply(state,'order.create','','{"department":"design","status":"saved"}')
    changed=procurement.apply(state,'order.create','','{"department":"design"}')
    assert state['world']['orders']=={}
    with pytest.raises(ValueError):procurement.apply(changed,'order.save','PO-001','{}')
    with pytest.raises(ValueError):procurement.apply(changed,'order.line','PO-001',json.dumps(dict(sku='lamp',quantity=True,note='')))
    for seed in range(1000,1030):
        fixture=procurement.fixture(seed)
        assert fixture==procurement.fixture(seed)
        assert all(1<=quantity<=9 for quantity in purchase_lines(fixture).values())


@pytest.mark.parametrize('task_id',sorted(v2.ATOMIC_TASKS))
@pytest.mark.parametrize('seed',[1000,10001])
def test_atomic_delivery_persists_and_requires_real_result(task_id,seed,tmp_path):
    from vic.schemas import Mutation
    from vic_apps.store import ApplicationStore
    from test_applications import reference
    initial=v2.generate(task_id,seed,'eval')
    assert initial==v2.generate(task_id,seed,'eval')
    assert initial['execution']['delivery']
    store=ApplicationStore(tmp_path)
    for variant in 'ABC':
        store.initialize('atomic',initial)
        actions=reference(initial,variant)
        for index,(op,target,value,ids) in enumerate(actions):
            store.mutate('atomic',Mutation(epoch=0,action_id=str(index),op=op,target=target,value=value,ids=ids))
        if task_id in (10,27,59):
            assert not v2.evaluate(initial,store.snapshot('atomic'),variant,store.events('atomic'))['success']
            if task_id==59:op,target='answer.submit','target'
            else:
                from vic.business import expected_effect
                op='shortcut.add' if task_id==10 else 'favorite.add'
                target=expected_effect(task_id,variant,initial)['selection'][0]
            store.mutate('atomic',Mutation(epoch=0,action_id='delivery',op=op,target=target))
        # Reopen the persisted store, as a refresh or a new worker would.
        persisted=ApplicationStore(tmp_path)
        result=v2.evaluate(initial,persisted.snapshot('atomic'),variant,persisted.events('atomic'))
        assert result['success'],(task_id,variant,result)


@pytest.mark.parametrize('task_id',sorted(v2.ATOMIC_TASKS))
@pytest.mark.parametrize('variant',list('ABC'))
def test_atomic_delivery_api_eval_and_reset(clients,task_id,variant):
    from test_applications import reference
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id']
    initial=worker.get(path,headers=credential(run)).json()['state']
    for i,(op,target,value,ids) in enumerate(reference(initial,variant)):
        response=worker.post(path+'/commands',headers=credential(run),json=dict(epoch=run['epoch'],action_id=f'action-{i}',op=op,target=target,value=value,ids=ids))
        assert response.status_code==200,response.text
    if task_id in (10,27,59):
        if task_id==59:op,target='answer.submit','target'
        else:
            from vic.business import expected_effect
            op='shortcut.add' if task_id==10 else 'favorite.add'
            target=expected_effect(task_id,variant,initial)['selection'][0]
        assert operate(worker,run,op,target).status_code==200
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json={'run_id':run['id']})
    assert result.status_code==200 and result.json()['success'],result.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin())
    assert reset.status_code==200,reset.text
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial


@pytest.mark.parametrize('variant',list('ABC'))
def test_reversi_six_rounds_real_api(clients,variant):
    from vic.games import expected
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=74,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id']
    initial=worker.get(path,headers=credential(run)).json()['state'];state=initial
    for turn in range(6):
        assert not state['stopped']
        point=expected(74,variant,state)
        response=operate(worker,run,'choose',','.join(map(str,point)))
        assert response.status_code==200,response.text
        state=response.json()['state']
        assert len(state['turns'])==turn+1
        if turn<5:assert not v2.evaluate(initial,state,variant,[])['success']
    assert state['stopped']
    assert operate(worker,run,'choose','0,0').status_code==422
    result=control.post('/v2/tasks/74/eval',headers=admin(),json={'run_id':run['id']})
    assert result.status_code==200 and result.json()['success'],result.text


def test_reversi_rule_evaluation_checks_every_round_and_replay():
    from vic_apps import reversi_training
    from vic.games import expected
    for seed in range(1000,1010):
        initial=v2.generate(74,seed,'eval')
        assert initial==v2.generate(74,seed,'eval')
        for variant in 'ABC':
            state=initial;events=[]
            for turn in range(6):
                p=expected(74,variant,state)
                event=dict(op='choose',target=','.join(map(str,p)),value='')
                state=reversi_training.apply(state,**event);events.append(event)
            assert v2.evaluate(initial,state,variant,events)['success']
            # All rules differ on the first position; using another rule fails.
            for other in set('ABC')-{variant}:
                assert not v2.evaluate(initial,state,other,events)['success']
            changed=deepcopy(state);changed['turns'][0]['player']=[9,9]
            assert not v2.evaluate(initial,changed,variant,events)['success']


@pytest.mark.parametrize('task_id',sorted(v2.EXECUTABLE))
@pytest.mark.parametrize('variant',list('ABC'))
def test_v2_demo_all_episodes_advance_and_final_eval(clients,task_id,variant):
    from test_lessons import operate as perform, advance
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=0,mode='demo',interaction='human',teaching=True))
    assert response.status_code==201,response.text
    run=response.json()
    for episode in range(run['lesson']['total']):
        state=perform(worker,run,variant)
        assert not state.get('v2_atomic') and not state.get('v2_reversi')
        if task_id == 43 and variant == 'B':
            from test_lessons import actor
            current=worker.get('/api/runs/'+run['id'],headers=actor(run)).json()['state']
            response=control.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),json=dict(epoch=run['epoch'],index=episode,clipboard=current['domain']['clipboard_history'][-1]['text']))
            assert response.status_code==200,response.text
            run={**run,**response.json()}
        else:
            run={**run,**advance(control,run,episode)}
    assert run['lesson']['finished']
    response=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json={'run_id':run['id']})
    assert response.status_code==200 and response.json()['success'],response.text
