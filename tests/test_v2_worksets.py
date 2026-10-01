"""Native grouped work must preserve unrelated records and save real delivery."""
from copy import deepcopy
import subprocess
import sys
import pytest
from vic import v2, v2_worksets
from vic.schemas import Mutation
from vic_apps.store import ApplicationStore
from vic_apps import worksets
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


@pytest.mark.parametrize('task_id',sorted(worksets.TASKS))
@pytest.mark.parametrize('variant',list('ABC'))
def test_scope_api_delivery_evaluation_and_reset(clients,task_id,variant):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id']
    initial=worker.get(path,headers=credential(run)).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    for i,(op,target,value,ids) in enumerate(v2_worksets.reference_commands(initial,variant)):
        r=worker.post(path+'/commands',headers=credential(run),json=dict(epoch=run['epoch'],action_id=str(i),op=op,target=target,value=value,ids=ids))
        assert r.status_code==200,r.text
    final=worker.get(path,headers=credential(run)).json()['state']
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json={'run_id':run['id']})
    assert result.status_code==200 and result.json()['success'],result.text
    # Editing an unrelated object must fail even after all target work is done.
    wrong=deepcopy(final);outside=next(x for x in initial['items'] if x['scope_id']==initial['scopes'][-1]['id'])
    wrong['domain']['objects'][outside['id']]['label']='不应改动'
    assert not v2.evaluate(initial,wrong,variant,[{'op':'label'}])['success']
    if task_id in worksets.SNAPSHOT_TASKS|worksets.SINGLE_TASKS:
        wrong=deepcopy(final);scope=initial['scopes'][0]
        wrong['domain']['collections']['scope:'+scope['id']]=[]
        assert not v2.evaluate(initial,wrong,variant,[{'op':'workset.collect'}])['success']
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial


@pytest.mark.parametrize('task_id',sorted(worksets.TASKS))
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_worksets_are_discriminative_persisted_and_local_to_each_scope(task_id,seed,tmp_path):
    initial=v2.generate(task_id,seed,'eval')
    assert initial==v2.generate(task_id,seed,'eval')
    store=ApplicationStore(tmp_path)
    for variant in 'ABC':
        store.initialize('scope',initial)
        for i,(op,target,value,ids) in enumerate(v2_worksets.reference_commands(initial,variant)):
            store.mutate('scope',Mutation(epoch=0,action_id=str(i),op=op,target=target,value=value,ids=ids))
        final=ApplicationStore(tmp_path).snapshot('scope');events=store.events('scope')
        assert v2.evaluate(initial,final,variant,events)['success']
        for other in set('ABC')-{variant}:
            assert not v2.evaluate(initial,final,other,events)['success']
        # The same-name, other-month/specification rows must stay unchanged.
        requested=[s for s in initial['scopes'] if s['requested']]
        targets={x['id'] for scope in requested for x in worksets.members(initial,scope)}
        for obj in initial['domain']['objects'].values():
            if obj['id'] not in targets:assert final['domain']['objects'][obj['id']]==obj


def test_receipt_mapping_channel_and_snapshot_are_checked(tmp_path):
    for task in (26,31,47,48,53,57):
        initial=v2.generate(task,10001,'eval');state=initial
        for op,target,value,ids in v2_worksets.reference_commands(initial,'A'):
            state=worksets.apply(state,op,target,value,ids)
        if task==57:
            target=next(x for x in state['domain']['objects'].values() if x.get('reminder'))
            target['reminder_channel']='短信'
        elif task==53:
            state['domain']['artifacts'][0]['account']='错误账户'
        else:
            # Correct IDs placed in the wrong destination do not satisfy work.
            c=state['domain']['collections'];c['scope:scope-1'],c['scope:scope-2']=c['scope:scope-2'],c['scope:scope-1']
        assert not v2.evaluate(initial,state,'A',[{'op':'completed'}])['success']


@pytest.mark.parametrize('variant',list('ABC'))
def test_course_requires_persisted_ordered_delivery_and_checks_topic_identity(variant):
    initial=v2.generate(63,10001,'eval');state=initial
    commands=v2_worksets.reference_commands(initial,variant)
    for op,target,value,ids in commands[:-1]:state=worksets.apply(state,op,target,value,ids)
    assert not v2.evaluate(initial,state,variant,[{'op':'course.add'}])['success']
    correct=list(state['domain']['orders']['course'])
    state=worksets.apply(state,'course.order',ids=list(reversed(correct)))
    state=worksets.apply(state,'course.save')
    assert not v2.evaluate(initial,state,variant,[{'op':'course.save'}])['success']
    state=worksets.apply(state,'course.order',ids=correct)
    assert not v2.evaluate(initial,state,variant,[{'op':'course.order'}])['success']
    state=worksets.apply(state,'course.save')
    assert v2.evaluate(initial,state,variant,[{'op':'course.save'}])['success']
    state=worksets.apply(state,'course.remove',correct[1])
    assert not v2.evaluate(initial,state,variant,[{'op':'course.remove'}])['success']
    with pytest.raises(ValueError):worksets.apply(state,'course.order',ids=[correct[0],correct[0]])
    wrong=worksets.apply(state,'course.add',initial['items'][-1]['id'])
    wrong=worksets.apply(wrong,'course.save')
    assert not v2.evaluate(initial,wrong,variant,[{'op':'course.save'}])['success']


def test_historical_submission_sources_support_the_shown_verdicts():
    initial=v2.generate(61,10001,'eval');seen=set()
    for item in initial['items']:
        key=(item['problem_title'],item['verdict'])
        if key in seen:continue
        seen.add(key)
        compile(item['code'],'historical-submission','exec')
        for case in item['test_results']:
            if item['verdict']=='TLE':
                with pytest.raises(subprocess.TimeoutExpired):
                    subprocess.run([sys.executable,'-I','-c',item['code']],input=case['input'],text=True,capture_output=True,timeout=1)
                break
            result=subprocess.run([sys.executable,'-I','-c',item['code']],input=case['input'],text=True,capture_output=True,timeout=2)
            if item['verdict']=='RE':
                assert result.returncode!=0 and 'IndexError' in result.stderr
            else:
                assert result.returncode==0
                assert result.stdout.strip()==case['actual'].strip()
                assert (result.stdout.strip()==case['expected'].strip())==(item['verdict']=='AC')


def test_chat_notifications_require_correct_recipient_body_and_no_duplicates():
    initial=v2.generate(9,10001,'eval');state=initial
    for op,target,value,ids in v2_worksets.reference_commands(initial,'A'):
        state=worksets.apply(state,op,target,value,ids)
    assert len(state['domain']['messages'])==3
    for field in ('recipient','body','reference','duplicate'):
        wrong=deepcopy(state);messages=wrong['domain']['messages']
        if field=='duplicate':messages.append(deepcopy(messages[0]))
        else:messages[0][field]=messages[1][field]
        assert not v2.evaluate(initial,wrong,'A',[{'op':'message.send'}])['success']


def test_project_receipts_keep_notification_identity_and_reject_duplicates():
    initial=v2.generate(16,10001,'eval');state=initial
    assert len([s for s in initial['scopes'] if s['requested']])==4
    assert len({item['notification_number'] for item in initial['items']})==len(initial['items'])
    for op,target,value,ids in v2_worksets.reference_commands(initial,'C'):
        state=worksets.apply(state,op,target,value,ids)
    assert v2.evaluate(initial,state,'C',[{'op':'action'}])['success']
    for reply in state['domain']['messages']:
        if reply['sender']!='self':continue
        item=state['domain']['objects'][reply['reference']]
        assert reply['recipient']==item['scope_id']
        assert item['notification_batch']=='N2026-0115'
        assert reply['body']==state['source']['fixed_reply']
    reply=next(m for m in state['domain']['messages'] if m['sender']=='self')
    wrong=deepcopy(state);wrong['domain']['messages'].append(deepcopy(reply))
    assert not v2.evaluate(initial,wrong,'C',[{'op':'action'}])['success']
    wrong=deepcopy(state)
    next(m for m in wrong['domain']['messages'] if m['sender']=='self')['recipient']='scope-5'
    assert not v2.evaluate(initial,wrong,'C',[{'op':'action'}])['success']
    old=next(item for item in state['items'] if item['notification_batch']=='N2025-1220' and '收到' in item['text'])
    wrong=worksets.apply(state,'action',old['id'],'回复')
    assert not v2.evaluate(initial,wrong,'C',[{'op':'action'}])['success']


def test_chat_groups_members_and_workspace_order_are_real_scoped_records():
    groups=v2.generate(8,10001,'eval')
    assert all(len(x['group_members'])==x['members'] for x in groups['items'])
    assert all(len({u['user_id'] for u in x['group_members']})==x['members'] for x in groups['items'])
    contacts=v2.generate(6,10001,'eval')
    assert len(worksets.members(contacts,contacts['scopes'][0]))==8
    assert all(x['surname']==x['name'].split()[-1] for x in contacts['items'])
    initial=v2.generate(12,10001,'eval');state=initial
    for op,target,value,ids in v2_worksets.reference_commands(initial,'A'):state=worksets.apply(state,op,target,value,ids)
    assert v2.evaluate(initial,state,'A',[{'op':'order'}])['success']
    wrong=deepcopy(state);order=wrong['domain']['orders']['main'];order[0],order[6]=order[6],order[0]
    assert not v2.evaluate(initial,wrong,'A',[{'op':'order'}])['success']


def test_conversation_state_toggles_are_reversible_and_restricted():
    state=v2.generate(14,10001,'eval');target=state['items'][0]['id']
    enabled=worksets.apply(state,'conversation.settings',target,'{"pinned":true,"muted":true,"archived":true}')
    assert all(enabled['domain']['objects'][target][key] for key in ('pinned','muted','archived'))
    restored=worksets.apply(enabled,'conversation.settings',target,'{"pinned":false,"muted":false,"archived":false}')
    assert restored==state
    for bad in ('{"name":"different"}','{"pinned":"false"}','[]','{}'):
        with pytest.raises(ValueError):worksets.apply(state,'conversation.settings',target,bad)


@pytest.mark.parametrize('variant',list('ABC'))
def test_each_project_member_gets_their_own_formatted_name(variant):
    initial=v2.generate(2,10001,'eval');state=initial
    requested=worksets.members(initial,initial['scopes'][0]);assert len(requested)==5
    for op,target,value,ids in v2_worksets.reference_commands(initial,variant):state=worksets.apply(state,op,target,value,ids)
    for item in requested:
        name=item['name'];wanted={'A':name.replace(' ',''),'B':name.replace(' ','_'),'C':name.lower()}[variant]
        assert state['domain']['objects'][item['id']]['nickname']==wanted
    first,second=requested[:2]
    state['domain']['objects'][first['id']]['nickname']=state['domain']['objects'][second['id']]['nickname']
    assert not v2.evaluate(initial,state,variant,[{'op':'contact.nickname'}])['success']
