"""Payments must match invoices and conserve money, with actual receipts and links."""
from copy import deepcopy
import base64,json
import pytest
from vic import v2
from vic_apps import payment_projects as bank
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def expected_ids(task,variant):
    return ['INV-'+str(i).zfill(3) for i in (range(1,5) if task==46 else {'A':[1,2,4],'B':[1,3,5],'C':[1,4,6]}[variant])]


def plan(initial,variant,reverse=False):
    bills={b['id']:b for b in initial['world']['bills']};ids=expected_ids(initial['task_id'],variant)
    if reverse:ids=ids[::-1]
    links={}
    for index,id in enumerate(ids,1):
        bill=bills[id];account=initial['domain']['objects'][bill['payee']]['account']
        memo={'A':account[-4:],'B':account[:4],'C':account[:4]+'*'*(len(account)-8)+account[-4:]}[variant] if initial['task_id']==46 else bill['note']
        yield 'transfer.execute','',dict(bill=id,payer=bill['payer'],payee=bill['payee'],cents=bill['cents'],memo=memo)
        links[id]=f'PAY-{index:04d}'
        yield 'bill.link',id,dict(transfer=links[id])
    if initial['task_id']==56:
        rows=[dict(bill=id,transfer=links.get(id,''),reason='' if id in links else '未达到视频规定的付款条件') for id in initial['world']['batch_bills']]
        yield 'report.save','',dict(rows=rows)
        yield 'report.send','',dict(recipient=10)


def complete(initial,variant,reverse=False):
    state=initial;events=[]
    for op,target,data in plan(initial,variant,reverse):
        value=json.dumps(data);state=bank.apply(state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[46,56])
@pytest.mark.parametrize('variant',list('ABC'))
def test_invoice_payment_api_actual_ledger_files_idempotency_and_reset(clients,task_id,variant):
    control,worker=clients
    r=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',interaction='human'))
    assert r.status_code==201,r.text
    run=r.json();path='/api/runs/'+run['id'];headers=credential(run);initial=worker.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'variants' not in json.dumps(initial)
    for i,(op,target,data) in enumerate(plan(initial,variant,True)):
        body=dict(epoch=0,action_id=str(i),op=op,target=target,value=json.dumps(data))
        r=worker.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        assert worker.post(path+'/commands',headers=headers,json=body).json()['state']==r.json()['state']
        if op=='transfer.execute':
            duplicate=worker.post(path+'/commands',headers=headers,json={**body,'action_id':str(i)+'-duplicate'})
            assert duplicate.status_code==422,duplicate.text
            assert worker.get(path,headers=headers).json()['state']==r.json()['state']
    final=worker.get(path,headers=headers).json()['state']
    assert sum(final['domain']['balances'].values())==sum(initial['domain']['balances'].values())
    assert sum(leg['cents'] for leg in final['domain']['ledger'])==0
    for id,file in final['domain']['files'].items():
        r=worker.get(path+'/files/'+id,headers=headers);assert r.status_code==200 and r.content==base64.b64decode(file['content'])
        assert worker.get(path+'/files/'+id).status_code==403
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial
    assert worker.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[46,56])
@pytest.mark.parametrize('seed',[1000,10001,27483])
def test_payment_variants_are_distinct_with_visible_boundaries(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    assert len({len(p['account']) for p in initial['items']})>3
    same_name=[p for p in initial['items'] if p['name']=='Avery Lin'];assert len(same_name)==2 and len({p['account'] for p in same_name})==2
    for variant in 'ABC':
        final,events=complete(initial,variant,True);result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
    if task_id==56:
        boundary=next(b for b in initial['world']['bills'] if b['id']=='INV-003')
        assert boundary['cents']==initial['world']['threshold'] and boundary['id'] not in expected_ids(56,'C')


@pytest.mark.parametrize('task_id',[46,56])
def test_payment_final_state_cannot_forge_or_mismatch_delivery(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'A')
    for field in ['amount','payer','payee','memo','time','bill','missing','extra','balance','ledger','link','file','historical','source']+(['report','recipient','notice','reason','report_file'] if task_id==56 else []):
        wrong=deepcopy(final);w=wrong['world'];payment=w['transfers']['PAY-0001']
        if field=='amount':payment['cents']+=1
        elif field=='payer':payment['payer']='own-reserve'
        elif field=='payee':payment['payee']=next(p['id'] for p in initial['items'] if p['record_code']=='SUP-007')
        elif field=='memo':payment['memo']='wrong'
        elif field=='time':payment['occurred_at']='2026-10-01T09:00:00+08:00'
        elif field=='bill':payment['bill']='INV-NEXT'
        elif field=='missing':del w['transfers']['PAY-0001']
        elif field=='extra':w['transfers']['PAY-9999']=deepcopy(payment)
        elif field=='balance':wrong['domain']['balances']['own-research']-=1
        elif field=='ledger':wrong['domain']['ledger'].pop()
        elif field=='link':w['bill_links']['INV-001']='PAY-H001'
        elif field=='file':wrong['domain']['files']['transfer-PAY-0001']['content']='ZmFrZQ=='
        elif field=='historical':w['transfers']['PAY-H001']['memo']='modified'
        elif field=='source':w['bills'][0]['cents']+=1
        elif field=='report':w['report']['rows'].reverse()
        elif field=='recipient':w['receipts'][0]['recipient']=11
        elif field=='notice':w['receipts'].append(deepcopy(w['receipts'][0]))
        elif field=='reason':w['report']['rows'][-1]['reason']='wrong reason'
        else:del wrong['domain']['files']['payment-report']
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field


def test_bad_payment_is_rejected_without_mutating_state_and_duplicate_is_blocked():
    initial=v2.generate(46,10001,'eval');before=deepcopy(initial);op,target,data=next(plan(initial,'A'))
    for change in [dict(cents=0),dict(cents=-1),dict(cents=True),dict(cents=120.05),dict(cents=2000000),dict(payer='none'),dict(payee='none'),dict(memo=''),dict(bill='none')]:
        with pytest.raises(ValueError):bank.apply(initial,op,target,json.dumps({**data,**change}))
        assert initial==before
    paid=bank.apply(initial,op,target,json.dumps(data))
    with pytest.raises(ValueError):bank.apply(paid,op,target,json.dumps(data))
    with pytest.raises(ValueError):bank.apply(paid,'transfer.cancel','PAY-0001')
    history={k:initial['world']['transfers']['PAY-H001'][k] for k in data}
    with pytest.raises(ValueError):bank.apply(initial,op,target,json.dumps(history))


def test_wrong_posted_payment_fails_even_with_a_matching_link():
    initial=v2.generate(46,10001,'eval');steps=list(plan(initial,'A'))
    for field,value in [('cents',12006),('payer','own-reserve'),('payee',next(p['id'] for p in initial['items'] if p['record_code']=='SUP-007')),('memo','bad')]:
        state=initial;events=[]
        for i,(op,target,data) in enumerate(steps):
            data={**data,field:value} if i==0 else data
            state=bank.apply(state,op,target,json.dumps(data));events.append(dict(op=op,target=target,value=json.dumps(data)))
        assert not v2.evaluate(initial,state,'A',events)['success']


def test_payment_links_and_stale_reports_can_be_corrected_without_repaying():
    initial=v2.generate(56,10001,'eval');final,events=complete(initial,'C')
    with pytest.raises(ValueError):bank.apply(final,'report.delete')
    final=bank.apply(final,'receipt.withdraw',final['world']['receipts'][0]['id'])
    final=bank.apply(final,'bill.link','INV-001',json.dumps(dict(transfer='PAY-H001')))
    with pytest.raises(ValueError):bank.apply(final,'report.send','',json.dumps(dict(recipient=10)))
    final=bank.apply(final,'bill.unlink','INV-001')
    assert not v2.evaluate(initial,final,'C',events)['success']
    final=bank.apply(final,'bill.link','INV-001',json.dumps(dict(transfer='PAY-0001')))
    final=bank.apply(final,'report.delete')
    assert 'payment-report' not in final['domain']['files']
    final=bank.apply(final,'report.save','',json.dumps(dict(rows=bank.report_rows(final))))
    final=bank.apply(final,'report.send','',json.dumps(dict(recipient=11)))
    assert not v2.evaluate(initial,final,'C',events)['success']
    final=bank.apply(final,'receipt.withdraw',final['world']['receipts'][0]['id'])
    final=bank.apply(final,'report.send','',json.dumps(dict(recipient=10)))
    assert v2.evaluate(initial,final,'C',events)['success']
    assert len(final['world']['transfers'])==4
