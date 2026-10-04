"""Screening verifies the real queue, replacement editions and timed CSV artifact."""
import base64,csv,io,json
from cross_platform_helpers import with_handoffs, apply_command, redeliver
from copy import deepcopy
from datetime import datetime,timedelta
import pytest
from vic import v2
from vic_apps import screening
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def expected_order(initial,variant):
    w=initial['world'];event=w['event'];ids=[]
    for f in w['folders']:
        for id in f['members']:
            if id not in ids:ids.append(id)
    ids=[id for id in ids if id not in {r['video'] for r in event['exclude']}]
    for r in event['replacements']:ids[ids.index(r['old'])]=r['new']
    groups=[[],[]]
    for id in ids:
        obj=initial['domain']['objects'][id]
        first=(obj['category']=='甲') if variant=='C' else (obj['duration']<600 if variant=='A' else obj['duration']>=600)
        groups[0 if first else 1].append(id)
    result=[]
    while any(groups):
        for group in groups:
            if group:result.append(group.pop(0))
    return result


@with_handoffs(screening.apply,4)
def operations(initial,variant):
    event=initial['world']['event']
    for f in initial['world']['folders']:yield 'queue.import',f['id'],{},[]
    for r in event['exclude']:yield 'queue.remove',r['video'],{},[]
    for r in event['replacements']:yield 'queue.replace',r['old'],dict(replacement=r['new']),[]
    yield 'queue.order','',{},expected_order(initial,variant)
    yield 'queue.name','',dict(name=event['title']),[]
    yield 'queue.save','',{},[]
    yield 'timing.save','',dict(starts_at=event['starts_at'],turnaround_seconds=event['turnaround_seconds'],breaks={r['after']:r['seconds'] for r in event['breaks']}),[]
    yield 'schedule.save','',{},[]


def complete(initial,variant):
    state=initial;events=[]
    for op,target,data,ids in operations(initial,variant):
        value=json.dumps(data);state=apply_command(screening.apply,state,op,target,value,ids);events.append(dict(op=op,target=target,value=value,ids=ids))
    return state,events


@pytest.mark.parametrize('variant',list('ABC'))
def test_screening_api_real_csv_idempotency_reset(clients,variant):
    c,w=clients;r=c.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=35,variant=variant,seed=10001,mode='eval',interaction='human'))
    assert r.status_code==201,r.text
    run=r.json();path='/api/runs/'+run['id'];headers=credential(run)
    initial=w.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'variants' not in json.dumps(initial)
    for i,(op,target,data,ids) in enumerate(operations(initial,variant)):
        body=dict(epoch=0,action_id=str(i),op=op,target=target,value=json.dumps(data),ids=ids)
        r=w.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        duplicate=w.post(path+'/commands',headers=headers,json=body);assert duplicate.json()['state']==r.json()['state']
    final=w.get(path,headers=headers).json()['state']
    file=w.get(path+'/files/screening-timetable',headers=headers);assert file.status_code==200
    assert file.content==base64.b64decode(final['domain']['files']['screening-timetable']['content'])
    rows=list(csv.reader(io.StringIO(file.content.decode())))
    assert len(rows)==11 and [r[1] for r in rows[1:-1]]==[initial['domain']['objects'][id]['record_code'] for id in expected_order(initial,variant)]
    assert w.get(path+'/files/screening-timetable').status_code==403
    result=c.post('/v2/tasks/35/eval',headers=admin(),json=dict(run_id=run['id']))
    assert result.status_code==200 and result.json()['success'],result.text
    reset=c.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert w.get(path,headers=credential(reset.json())).json()['state']==initial
    assert w.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_replacements_order_and_times_independently_computed(seed):
    initial=v2.generate(35,seed,'eval');assert initial==v2.generate(35,seed,'eval')
    signatures=[]
    for variant in 'ABC':
        final,events=complete(initial,variant);assert v2.evaluate(initial,final,variant,events)['success']
        w=final['world'];signatures.append(tuple(w['queue']['members']))
        current=datetime.fromisoformat(initial['world']['event']['starts_at'])
        for i,row in enumerate(w['schedule']['rows']):
            assert datetime.fromisoformat(row['starts_at'])==current
            current+=timedelta(seconds=initial['domain']['objects'][row['video']]['duration'])
            assert datetime.fromisoformat(row['ends_at'])==current
            assert row['turnaround_seconds']==(30 if i<8 else 0)
            current+=timedelta(seconds=row['turnaround_seconds']+row['break_seconds'])
        assert current.isoformat()==w['schedule']['ends_at']
        assert sum(r['break_seconds'] for r in w['schedule']['rows'])==900
        assert len(w['queue']['members'])==len(set(w['queue']['members']))==9
        assert all(r['new'] in w['queue']['members'] and r['old'] not in w['queue']['members'] for r in w['event']['replacements'])
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']
    assert len(set(signatures))==3


def test_wrong_order_versions_intervals_and_stale_files_fail():
    initial=v2.generate(35,10001,'eval');final,events=complete(initial,'A')
    for field in ('order','missing','old_version','queue_name','unsaved_queue','starts','gap','break','row','ends','file','input'):
        wrong=deepcopy(final);w=wrong['world']
        if field=='order':w['queue']['members'].reverse()
        elif field=='missing':w['queue']['members'].pop()
        elif field=='old_version':
            r=w['event']['replacements'][0];w['queue']['members'][w['queue']['members'].index(r['new'])]=r['old']
        elif field=='queue_name':w['queue']['name']='other event'
        elif field=='unsaved_queue':w['queue']['saved']=None
        elif field=='starts':w['timing']['starts_at']='2026-02-21T18:00:00+08:00'
        elif field=='gap':w['timing']['turnaround_seconds']=0
        elif field=='break':w['timing']['breaks']={}
        elif field=='row':w['schedule']['rows'][1]['starts_at']=w['schedule']['rows'][0]['starts_at']
        elif field=='ends':w['schedule']['ends_at']='wrong'
        elif field=='file':wrong['domain']['files']['screening-timetable']['content']='ZmFrZQ=='
        else:w['folders'][0]['members'].reverse()
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field
    changed=screening.apply(final,'queue.order',ids=list(reversed(final['world']['queue']['members'])))
    with pytest.raises(ValueError):screening.apply(changed,'schedule.save')
    changed=screening.apply(changed,'queue.save');changed=screening.apply(changed,'schedule.save')
    assert not v2.evaluate(initial,changed,'A',events)['success']
    changed=screening.apply(changed,'queue.order',ids=expected_order(initial,'A'));changed=screening.apply(changed,'queue.save');changed=screening.apply(changed,'schedule.save')
    assert v2.evaluate(initial,changed,'A',events)['success']


def test_queue_validation_and_import_deduplication():
    initial=v2.generate(35,10001,'eval');state=screening.apply(initial,'queue.import','folder-1')
    again=screening.apply(state,'queue.import','folder-1');assert again==state
    for ids in [[],[state['world']['queue']['members'][0]]*4,['absent']]:
        with pytest.raises(ValueError):screening.apply(state,'queue.order',ids=ids)
    with pytest.raises(ValueError):screening.apply(initial,'schedule.save')
    for data in [dict(starts_at='invalid',turnaround_seconds=30,breaks={}),dict(starts_at='2026-02-21T19:00',turnaround_seconds=30,breaks={}),dict(starts_at='2026-02-21T19:00+08:00',turnaround_seconds=30,breaks={'absent':300})]:
        with pytest.raises(ValueError):screening.apply(state,'timing.save',value=json.dumps(data))
