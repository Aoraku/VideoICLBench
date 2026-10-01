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
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=51,variant='A',seed=10001))
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
