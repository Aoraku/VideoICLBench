"""Project delivery checks exercise real records, identity and preservation."""
from copy import deepcopy
import base64
import json
import pytest
from vic import v2
from vic_apps import communications
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def commands(initial, variant):
    w=initial['world'];items=initial['items'];t=initial['task_id']
    if t==11:
        for request in w['requests']:
            candidates=[x for x in items if x['project']==request['project'] and x['file_type']==request['file_type'] and x['version']==request['version']]
            key=(lambda x:len(base64.b64decode(initial['world']['materials'][x['id']]['content']))) if variant!='C' else (lambda x:len(x['name']))
            chosen=sorted(candidates,key=key,reverse=variant=='B')[0]
            yield 'document.import',chosen['id'],{}
            yield 'file.send','',dict(file=chosen['id'],recipient=request['requester'],request=request['id'])
    elif t==13:
        for item in items:
            if item['project'] not in {p['id'] for p in w['projects']} or item['batch']!='晚班-0115' or '紧急' not in item['text']:continue
            yield 'action',item['id'],{'A':'转发','B':'收藏','C':'归档'}[variant]
            yield 'handover.line',item['id'],dict(status={'A':'已转发','B':'已收藏','C':'已归档'}[variant])
        yield 'handover.save','',{}
        yield 'handover.send','',dict(recipient=2)
    else:
        for i,project in enumerate(w['projects']):
            candidates=[x for x in items if x['project']==project['id']]
            key={'A':lambda x:len(x['name']),'B':lambda x:x['last_contact_at'],'C':lambda x:x['unread']}[variant]
            chosen=sorted(candidates,key=key,reverse=variant!='A')[:3]
            yield 'group.create','',dict(name=project['group_name'],members=[x['id'] for x in chosen])
            yield 'group.announcement',str(100+i),dict(text=project['announcement'])
            yield 'project.brief',project['id'],dict(group=str(100+i))
            yield 'group.message',str(100+i),dict(text=project['material_link'])


def apply_all(initial,variant):
    state=initial;events=[]
    for op,target,data in commands(initial,variant):
        value=data if isinstance(data,str) else json.dumps(data,ensure_ascii=False)
        state=communications.apply(state,op,target,value);events.append(dict(op=op,target=target,value=value))
    return state,events


@pytest.mark.parametrize('task_id',[11,13,15])
@pytest.mark.parametrize('variant',list('ABC'))
def test_project_delivery_api_identity_persistence_and_reset(clients,task_id,variant):
    control,worker=clients
    created=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert created.status_code==201,created.text
    run=created.json();path='/api/runs/'+run['id']
    initial=worker.get(path,headers=credential(run)).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'expected' not in json.dumps(initial) and 'variants' not in json.dumps(initial)
    for i,(op,target,data) in enumerate(commands(initial,variant)):
        value=data if isinstance(data,str) else json.dumps(data,ensure_ascii=False)
        body=dict(op=op,target=target,value=value,epoch=run['epoch'],action_id=str(i))
        response=worker.post(path+'/commands',headers=credential(run),json=body)
        assert response.status_code==200,response.text
        # A retry of the same command must not duplicate a send or a group.
        repeat=worker.post(path+'/commands',headers=credential(run),json=body)
        assert repeat.status_code==200 and repeat.json()['state']==response.json()['state']
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json={'run_id':run['id']})
    assert result.status_code==200 and result.json()['success'],result.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial


@pytest.mark.parametrize('task_id',[11,13,15])
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_project_variants_and_immutable_inputs(task_id,seed):
    initial=v2.generate(task_id,seed,'eval')
    assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        state,events=apply_all(initial,variant)
        result=v2.evaluate(initial,state,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,state,other,events)['success']
        wrong=deepcopy(state);wrong['world']['projects'][0]['name']='different'
        assert not v2.evaluate(initial,wrong,variant,events)['success']


def test_attachment_deliveries_check_request_recipient_version_and_bytes():
    initial=v2.generate(11,10001,'eval');state,events=apply_all(initial,'A')
    for field in ('recipient','reference','attachment','duplicate','bytes'):
        wrong=deepcopy(state);msgs=wrong['domain']['messages']
        if field=='duplicate':msgs.append(deepcopy(msgs[0]))
        elif field=='bytes':wrong['domain']['files'][msgs[0]['attachment']]['content']='bm90IHRoZSBmaWxl'
        else:msgs[0][field]=msgs[1][field]
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field
    for item in initial['items']:
        assert item['size']==len(base64.b64decode(initial['world']['materials'][item['id']]['content']))


@pytest.mark.parametrize('variant',list('ABC'))
def test_handover_needs_actual_actions_and_an_accurate_sent_document(variant):
    initial=v2.generate(13,10001,'eval');state,events=apply_all(initial,variant)
    for field in ('link','status','recipient','file','history','missing_document'):
        wrong=deepcopy(state);doc=wrong['world']['documents']['handover-001']
        row=next(iter(doc['rows'].values()))
        if field=='link':row['link']='/chat?open=50&msg=100'
        if field=='status':row['status']='待处理'
        if field=='recipient':doc['recipient']=50
        if field=='file':wrong['domain']['files']['handover-001']['content']=''
        if field=='missing_document':wrong['world']['documents']={}
        if field=='history':
            item=next(x for x in initial['items'] if x['batch']=='早班-0115')
            wrong=communications.apply(wrong,'action',item['id'],'归档')
        assert not v2.evaluate(initial,wrong,variant,events)['success'],field
    with pytest.raises(ValueError):communications.apply(state,'handover.send','',json.dumps({'recipient':2}))
    target=next(iter(state['world']['handover']['rows']))
    with pytest.raises(ValueError):communications.apply(state,'handover.remove',target)


def test_groups_require_all_materials_announcements_and_correct_member_accounts():
    initial=v2.generate(15,10001,'eval');state,events=apply_all(initial,'A')
    for field in ('name','members','announcement','messages','duplicate'):
        wrong=deepcopy(state);g=wrong['world']['groups']['100']
        if field=='duplicate':g['messages']*=2
        else:g[field]=deepcopy(wrong['world']['groups']['101'][field])
        assert not v2.evaluate(initial,wrong,'A',events)['success'],field
    extra=communications.apply(state,'group.create','',json.dumps({'name':'temporary','members':state['world']['groups']['100']['members']}))
    assert not v2.evaluate(initial,extra,'A',events)['success']
    restored=communications.apply(extra,'group.delete','103')
    assert v2.evaluate(initial,restored,'A',events)['success']
    changed=communications.apply(state,'group.members','100',json.dumps({'members':state['world']['groups']['101']['members']}))
    assert not v2.evaluate(initial,changed,'A',events)['success']


def test_project_files_and_briefs_have_necessary_cross_application_dependencies():
    initial=v2.generate(11,10001,'eval')
    request=initial['world']['requests'][0]
    original=next(x for x in initial['items'] if x['project']==request['project'])
    with pytest.raises(ValueError):
        communications.apply(initial,'file.send','',json.dumps(dict(file=original['id'],recipient=request['requester'],request=request['id'])))
    imported=communications.apply(initial,'document.import',original['id'])
    assert imported['domain']['files'][original['id']]==initial['world']['materials'][original['id']]
    state,_=apply_all(v2.generate(15,10001,'eval'),'A')
    project=state['world']['projects'][0]
    changed=communications.apply(state,'group.announcement','100',json.dumps({'text':'Updated meeting time'}))
    with pytest.raises(ValueError,match='Studio'):
        communications.apply(changed,'group.message','100',json.dumps({'text':project['material_link']}))
    assert state['world']['documents']['brief-'+project['id']]['roster']
