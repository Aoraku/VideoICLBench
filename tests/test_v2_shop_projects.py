"""Actual order and handover contracts, including preservation and stale delivery."""
from copy import deepcopy
import base64,json
import pytest
from vic import v2
from vic_apps import shop_projects as shop
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def choices(initial,variant):
    codes={p['record_code']:p['id'] for p in initial['items']}
    return {n['id']:codes[f'F{index+1}-{ord(variant)-ord("A")+1:02d}'] for index,n in enumerate(initial['world']['needs'])}


def plan(initial,variant):
    w=initial['world']
    if initial['task_id']==52:
        selected=choices(initial,variant)
        for n in w['needs']:yield 'cart.set',selected[n['id']],dict(quantity=n['quantity'])
        for dep in w['departments']:
            lines={selected[n['id']]:n['quantity'] for n in w['needs'] if n['department']==dep['id']}
            yield 'order.place','',dict(department=dep['id'],address=dep['address'],lines=lines)
    else:
        cart=deepcopy(w['cart']);favorites=set(w['favorites'])
        for r in w['requests']:
            for index in (0,1,3):
                id=r['products'][index]
                if variant=='A' and id not in cart:
                    cart[id]=r['quantities'][id];yield 'cart.set',id,dict(quantity=cart[id])
                elif variant=='B' and id in cart:del cart[id];yield 'cart.remove',id,{}
                elif variant=='C' and id not in favorites:favorites.add(id);yield 'favorite.add',id,{}
        for r in w['requests']:
            rows=[dict(sku=id,cart_quantity=cart.get(id,0),favorite=id in favorites) for id in r['products']]
            yield 'handover.save',r['id'],dict(rows=rows)
            yield 'handover.send',r['id'],dict(recipient=r['recipient'])


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data in plan(initial,variant):
        value=json.dumps(data);state=shop.apply(state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[52,55])
@pytest.mark.parametrize('variant',list('ABC'))
def test_shop_api_real_deliveries_downloads_reset_and_idempotency(clients,task_id,variant):
    control,worker=clients
    r=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',interaction='human'))
    assert r.status_code==201,r.text
    run=r.json();path='/api/runs/'+run['id'];headers=credential(run);initial=worker.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'variants' not in json.dumps(initial)
    for i,(op,target,data) in enumerate(plan(initial,variant)):
        body=dict(epoch=0,action_id=str(i),op=op,target=target,value=json.dumps(data))
        r=worker.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        repeat=worker.post(path+'/commands',headers=headers,json=body);assert repeat.json()['state']==r.json()['state']
    final=worker.get(path,headers=headers).json()['state']
    for id,file in final['domain']['files'].items():
        r=worker.get(path+'/files/'+id,headers=headers);assert r.status_code==200 and r.content==base64.b64decode(file['content'])
        assert worker.get(path+'/files/'+id).status_code==403
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial
    assert worker.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[52,55])
@pytest.mark.parametrize('seed',[1000,10001,27483])
def test_shop_variants_have_distinct_correct_deliveries(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant);result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
        outside=next(p['id'] for p in initial['items'] if p['record_code']=='U-001')
        assert final['world']['cart'][outside]==initial['world']['cart'][outside]
        if task_id==55:
            for request in initial['world']['requests']:
                body=final['world']['handovers'][request['id']]['body']
                assert all(f'[查看商品](?product={id})' in body for id in request['products'])


def test_purchase_filters_and_reserves_actual_inventory_and_cancels():
    initial=v2.generate(52,10001,'eval');objects=initial['domain']['objects']
    for index,n in enumerate(initial['world']['needs'],1):
        eligible=[p['record_code'] for p in initial['items'] if p['category']==n['category'] and p['spec']==n['spec'] and p['price']<=n['budget'] and p['stock']>=n['quantity']]
        assert set(eligible)=={f'F{index}-01',f'F{index}-02',f'F{index}-03'}
        short=next(p['id'] for p in initial['items'] if p['record_code']==f'F{index}-06')
        with pytest.raises(ValueError):shop.apply(initial,'cart.set',short,json.dumps(dict(quantity=n['quantity'])))
    final,events=complete(initial,'A');order=final['world']['orders']['ORDER-001']
    changed=shop.apply(final,'order.cancel','ORDER-001')
    assert 'order-ORDER-001' not in changed['domain']['files']
    for id,q in order['lines'].items():assert changed['world']['cart'][id]==q and changed['world']['stock'][id]==initial['world']['stock'][id]
    changed=shop.apply(changed,'order.place','',json.dumps({k:order[k] for k in ('department','address','lines')}))
    assert v2.evaluate(initial,changed,'A',events)['success']
    body=base64.b64decode(changed['domain']['files']['order-ORDER-004']['content']).decode()
    assert 'SIM-ORDER-004' in body and order['address'] in body
    total=sum(objects[id]['price']*q for id,q in order['lines'].items())
    assert f'合计：{total} 元' in body


@pytest.mark.parametrize('task_id',[52,55])
def test_incorrect_scope_state_receipt_or_file_fails(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'A')
    fields=['cart','favorites','stock','file','source']+(['address','quantity','missing','extra','confirmation'] if task_id==52 else ['recipient','body','rows','missing','extra'])
    for field in fields:
        wrong=deepcopy(final);w=wrong['world'];id=next(iter(w['cart']))
        if field=='cart':w['cart'][id]+=1
        elif field=='favorites':w['favorites']=[]
        elif field=='stock':w['stock'][id]-=1
        elif field=='source':w['brief']='other'
        elif field=='file':wrong['domain']['files'][next(iter(wrong['domain']['files']))]['content']='ZmFrZQ=='
        elif task_id==52:
            order=w['orders']['ORDER-001']
            if field=='address':order['address']='wrong address'
            elif field=='quantity':order['lines'][next(iter(order['lines']))]+=1
            elif field=='confirmation':order['confirmation']='fake'
            elif field=='missing':del w['orders']['ORDER-001']
            else:w['orders']['extra']=deepcopy(order)
        else:
            if field=='rows':w['handovers']['LIST-001']['rows'][0]['cart_quantity']+=1
            elif field=='missing':w['receipts'].pop()
            elif field=='extra':w['receipts'].append(deepcopy(w['receipts'][0]))
            else:w['receipts'][0][field]='wrong'
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field


def test_handover_staleness_withdrawal_and_wrong_recipient_recovery():
    initial=v2.generate(55,10001,'eval');final,events=complete(initial,'C');request=initial['world']['requests'][0]
    with pytest.raises(ValueError):shop.apply(final,'handover.delete',request['id'])
    with pytest.raises(ValueError):shop.apply(final,'handover.send',request['id'],json.dumps(dict(recipient=request['recipient'])))
    receipt=next(r for r in final['world']['receipts'] if r['request']==request['id'])
    changed=shop.apply(final,'receipt.withdraw',receipt['id'])
    id=request['products'][1];changed=shop.apply(changed,'cart.set',id,json.dumps(dict(quantity=1)))
    with pytest.raises(ValueError):shop.apply(changed,'handover.send',request['id'],json.dumps(dict(recipient=request['recipient'])))
    changed=shop.apply(changed,'cart.remove',id)
    changed=shop.apply(changed,'handover.send',request['id'],json.dumps(dict(recipient=12)))
    assert not v2.evaluate(initial,changed,'C',events)['success']
    changed=shop.apply(changed,'receipt.withdraw',changed['world']['receipts'][-1]['id'])
    changed=shop.apply(changed,'handover.send',request['id'],json.dumps(dict(recipient=request['recipient'])))
    assert v2.evaluate(initial,changed,'C',events)['success']


def test_wrong_order_eligibility_is_not_hidden_by_correct_department():
    initial=v2.generate(52,10001,'eval');correct,events=complete(initial,'A')
    for code in ('F1-04','F1-05'):
        wrong=deepcopy(correct);order=wrong['world']['orders']['ORDER-001'];old=choices(initial,'A')['NEED-001'];replacement=next(p['id'] for p in initial['items'] if p['record_code']==code)
        order['lines'][replacement]=order['lines'].pop(old)
        assert not v2.evaluate(initial,wrong,'A',events)['success']
