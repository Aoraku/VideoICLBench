"""Trip API tests independently verify identity, feasible sequences and receipts."""
import base64,json
from cross_platform_helpers import with_handoffs, apply_command, redeliver
from copy import deepcopy
import pytest
from vic import v2
from vic_apps import travel_projects as travel
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def selected(initial,variant):
    w=initial['world'];objects=initial['domain']['objects']
    if initial['task_id']==51:
        codes={'A':['G101','G201','G301'],'B':['G102','G202','G302'],'C':['G103','G203','G303']}[variant]
        return {f'leg-{i+1}':next(x['id'] for x in initial['items'] if x['record_code']==code) for i,code in enumerate(codes)}
    if initial['task_id']==44:return {r['id']:r['candidates'][0] for r in w['legs']}
    return {r['id']:r['route'] for r in w['requests'] if (objects[r['route']]['price']<250 if variant=='A' else objects[r['route']]['price']>250 if variant=='B' else objects[r['route']]['transfers']%2==0)}


def passenger(initial,id,variant):
    person=next(p for p in initial['world']['people'] if p['id']==id)
    profile=deepcopy(initial['world']['profiles'][id])
    if initial['task_id']==44:
        profile['full_name']=person['surname']+('-' if variant=='B' else ' ')+person['given_name']
        if variant=='C':profile['full_name']=profile['full_name'].upper()
    return dict(id=id,**profile)


@with_handoffs(travel.apply,3)
def plan(initial,variant):
    w=initial['world'];bookings=[]
    if initial['task_id']==44:
        for id in w['legs'][0]['passengers']:yield 'profile.save',id,dict(full_name=passenger(initial,id,variant)['full_name'])
    for index,(slot,route) in enumerate(selected(initial,variant).items(),1):
        source=next(r for r in (w['requests'] if initial['task_id']==54 else w['legs']) if r['id']==slot)
        id=f'BOOK-{index:03d}';bookings.append(id)
        yield 'booking.create',slot,dict(route=route)
        ids=[source['person']] if initial['task_id']==54 else source['passengers']
        yield 'booking.passengers',id,dict(passengers=[passenger(initial,pid,variant) for pid in ids],cost_center=source['cost_center'],contact=source['contact'])
        yield 'booking.save',id,{}
        if initial['task_id']!=44:yield 'booking.confirm',id,{}
        if initial['task_id']==54:
            yield 'approval.record',slot,dict(booking=id)
            yield 'receipt.send',id,dict(recipient=source['recipient'])
    yield 'itinerary.save','',dict(bookings=bookings)


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data in plan(initial,variant):
        value=json.dumps(data);state=apply_command(travel.apply,state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[44,51,54])
@pytest.mark.parametrize('variant',list('ABC'))
def test_trip_api_deliveries_downloads_reset_and_idempotency(clients,task_id,variant):
    c,w=clients;r=c.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',interaction='human'))
    assert r.status_code==201,r.text
    run=r.json();path='/api/runs/'+run['id'];headers=credential(run);initial=w.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'variants' not in json.dumps(initial)
    for i,(op,target,data) in enumerate(plan(initial,variant)):
        body=dict(epoch=0,action_id=str(i),op=op,target=target,value=json.dumps(data))
        r=w.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        duplicate=w.post(path+'/commands',headers=headers,json=body);assert duplicate.json()['state']==r.json()['state']
    final=w.get(path,headers=headers).json()['state']
    for id,file in final['domain']['files'].items():
        r=w.get(path+'/files/'+id,headers=headers);assert r.status_code==200 and r.content==base64.b64decode(file['content'])
        assert w.get(path+'/files/'+id).status_code==403
    result=c.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    reset=c.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert w.get(path,headers=credential(reset.json())).json()['state']==initial
    assert w.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[44,51,54])
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_trip_rules_produce_distinct_complete_deliveries(task_id,seed):
    initial=v2.generate(task_id,seed,'eval');assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant);result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
        assert final['domain']['objects']==initial['domain']['objects']
        for id,b in final['world']['bookings'].items():
            content=base64.b64decode(final['domain']['files']['booking-'+id]['content']).decode()
            assert all(p['document'] in content and p['full_name'] in content for p in b['passengers'])
            assert initial['domain']['objects'][b['route']]['record_code'] in content


def test_route_feasibility_needs_lookahead_and_depends_on_prior_choice():
    from vic.v2_travel_projects import eligible_routes
    s=v2.generate(51,10001,'eval');codes={x['record_code']:x['id'] for x in s['items']}
    assert codes['G104'] not in eligible_routes(s,[])  # Local cheap, short and late route cannot finish the trip.
    assert codes['G201'] in eligible_routes(s,[codes['G101']])
    assert codes['G201'] not in eligible_routes(s,[codes['G102']])
    assert eligible_routes(s,[codes['G103']])==[codes['G203']]
    assert codes['G204'] not in eligible_routes(s,[codes['G101']])
    assert codes['G305'] not in eligible_routes(s,[codes['G102'],codes['G202']])


@pytest.mark.parametrize('task_id',[44,51,54])
def test_wrong_identity_booking_route_cost_or_itinerary_is_rejected(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'A')
    for field in ('name','person','document','contact','center','route','status','confirmation','saved','missing','extra','itinerary','file','input'):
        wrong=deepcopy(final);b=wrong['world']['bookings']['BOOK-001']
        if field=='name':b['passengers'][0]['full_name']='wrong'
        elif field=='person':b['passengers'][0]['id']='TR-005'
        elif field=='document':b['passengers'][0]['document']='wrong'
        elif field=='contact':b['contact']='wrong@example.test'
        elif field=='center':b['cost_center']='CC-设计'
        elif field=='route':b['route']=initial['items'][-1]['id'] if initial['items'][-1]['id']!=b['route'] else initial['items'][0]['id']
        elif field=='status':b['status']='confirmed' if task_id==44 else 'draft'
        elif field=='confirmation':b['confirmation']='fake'
        elif field=='saved':b['saved']=None
        elif field=='missing':del wrong['world']['bookings']['BOOK-001']
        elif field=='extra':wrong['world']['bookings']['extra']=deepcopy(b)
        elif field=='itinerary':wrong['world']['itinerary']['body']='placeholder'
        elif field=='file':wrong['domain']['files']['travel-itinerary']['content']='ZmFrZQ=='
        else:wrong['world']['people'][0]['document']='changed'
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field


def test_approval_boundary_actual_reference_and_notification():
    initial=v2.generate(54,10001,'eval');a=selected(initial,'A');b=selected(initial,'B');c=selected(initial,'C')
    boundary=next(r for r in initial['world']['requests'] if initial['domain']['objects'][r['route']]['price']==250)
    assert boundary['id'] not in a and boundary['id'] not in b
    final,events=complete(initial,'C')
    for field in ('recipient','body','link','approval','missing_notice'):
        wrong=deepcopy(final)
        if field=='approval':wrong['world']['approvals']['AP-001']='BOOK-002'
        elif field=='missing_notice':wrong['world']['receipts'].pop()
        else:wrong['world']['receipts'][0][field]='wrong'
        assert not v2.evaluate(initial,wrong,'C',events)['success'],field
    with pytest.raises(ValueError):travel.apply(final,'booking.delete','BOOK-001')
    with pytest.raises(ValueError):travel.apply(final,'booking.confirm','BOOK-001')
    receipt=final['world']['receipts'][0]
    with pytest.raises(ValueError):travel.apply(final,'receipt.send','BOOK-001',json.dumps(dict(recipient=receipt['recipient'])))
    changed=travel.apply(final,'receipt.withdraw',receipt['id']);changed=travel.apply(changed,'receipt.send',receipt['booking'],json.dumps(dict(recipient=receipt['recipient'])))
    assert v2.evaluate(initial,changed,'C',events)['success']


def test_editing_requires_resaving_and_preserves_unrelated_traveler():
    initial=v2.generate(44,10001,'eval');final,events=complete(initial,'B')
    assert final['world']['profiles']['TR-005']==initial['world']['profiles']['TR-005']
    with pytest.raises(ValueError):travel.apply(final,'booking.confirm','BOOK-001')
    data={k:deepcopy(final['world']['bookings']['BOOK-001'][k]) for k in ('passengers','cost_center','contact')};data['passengers'][0]['full_name']='other'
    changed=travel.apply(final,'booking.passengers','BOOK-001',json.dumps(data))
    with pytest.raises(ValueError):travel.apply(changed,'itinerary.save','',json.dumps(dict(bookings=['BOOK-001','BOOK-002'])))
    assert not v2.evaluate(initial,changed,'B',events)['success']
