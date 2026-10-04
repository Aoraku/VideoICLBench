"""Real native-workflow artifacts must reach the correct versioned request."""
from copy import deepcopy
import base64,json
import pytest
from vic import v2
from vic_apps import cross_platform as inbox
from test_v2_screening import complete as screening_complete
from test_v2_publishing import complete as publishing_complete
from test_v2_studio_projects import complete as studio_complete
from test_v2_travel_projects import complete as travel_complete
from test_v2_shop_projects import complete as shop_complete
from test_v2_code_projects import complete as code_complete


def complete_native(task,variant):
    start=inbox.attach(v2.generate(task,10001,'eval'),10001)
    complete={35:screening_complete,40:publishing_complete,41:studio_complete,43:studio_complete,51:travel_complete,52:shop_complete}.get(task,code_complete)
    final,events=complete(inbox.without_extension(start),variant)
    final['cross_platform']=deepcopy(start['cross_platform']);final['linked_apps']=deepcopy(start['linked_apps'])
    return start,final,events


def reply_all(state):
    for request in state['cross_platform']['requests']:
        if request['revision']!=2:continue
        ids=[r['id'] for r in inbox.resources(state) if r['scope']==request['scope']]
        state=inbox.apply(state,'handoff.send',request['id'],json.dumps(dict(recipient=request['recipient'],resources=ids)))
    return state


@pytest.mark.parametrize('task',sorted(inbox.TASKS))
@pytest.mark.parametrize('variant',list('ABC'))
def test_actual_saved_artifacts_link_source_recipient_and_content(task,variant):
    start,final,events=complete_native(task,variant)
    assert not inbox.evaluate(start,final)['success']
    assert inbox.resources(final)
    delivered=reply_all(final)
    result=inbox.evaluate(start,delivered)
    assert result['success'],result['violations']
    # Extending delivery must not mutate existing native files or business records.
    assert inbox.without_extension(delivered)==inbox.without_extension(final)
    assert len(delivered['linked_apps'])>=2
    for receipt in delivered['cross_platform']['receipts']:
        for attachment in receipt['attachments']:
            assert len(base64.b64decode(attachment['file']['content']))==attachment['file']['size']
    # A success marker without the actual artifact snapshot is insufficient.
    forged=deepcopy(delivered);forged['cross_platform']['receipts'][0]['attachments'][0]['file']['content']=''
    assert not inbox.evaluate(start,forged)['success']
    wrong=deepcopy(delivered);wrong['cross_platform']['receipts'][0]['recipient']=799
    assert not inbox.evaluate(start,wrong)['success']
    wrong=deepcopy(delivered);wrong['cross_platform']['receipts'][0]['request']+='-v1'
    assert not inbox.evaluate(start,wrong)['success']
    wrong=deepcopy(delivered);wrong['cross_platform']['requests'][0]['body']='edited input'
    assert not inbox.evaluate(start,wrong)['success']


@pytest.mark.parametrize('task',sorted(inbox.TASKS))
def test_initial_cannot_deliver_and_scope_changes_invalidate_snapshot(task):
    start,final,_=complete_native(task,'A')
    request=next(r for r in start['cross_platform']['requests'] if r['revision']==2)
    with pytest.raises(ValueError,match='附件未保存'):
        inbox.apply(start,'handoff.send',request['id'],json.dumps(dict(recipient=request['recipient'],resources=['invented'])))
    delivered=reply_all(final)
    receipt=delivered['cross_platform']['receipts'][0]
    if task==40:
        delivered['world']['publications'][next(iter(delivered['world']['publications']))]['summary']='Changed after delivery'
    elif task==43:
        target=next(iter(delivered['world']['delivery']['saved']))
        delivered['world']['delivery']['saved'][target]['reference']='files/changed-source'
    else:
        file_id={35:'screening-timetable',51:'travel-itinerary'}.get(task,'course-delivery')
        if task==52:file_id='order-'+next(iter(delivered['world']['orders']))
        if task==41:file_id=next(iter(delivered['world']['archives'].values()))['file']
        delivered['domain']['files'][file_id]=inbox.text_record('replacement.txt','New content')
    assert not inbox.evaluate(start,delivered)['success']
    delivered=inbox.apply(delivered,'handoff.withdraw',receipt['id'])
    assert len(delivered['cross_platform']['receipts'])==len(final['cross_platform']['receipts'])+len([r for r in start['cross_platform']['requests'] if r['revision']==2])-1


def test_native_inbox_read_receipt_is_persistent_and_does_not_change_deliveries():
    start=v2.generate(35,10001,'eval')
    person=start['cross_platform']['people'][0]
    marked=inbox.apply(start,'handoff.read',str(person['id']))
    assert marked['cross_platform']['read']=={str(person['id']):True}
    assert marked['cross_platform']['requests']==start['cross_platform']['requests']
    assert marked['cross_platform']['receipts']==[]
    assert inbox.apply(marked,'handoff.read',str(person['id']))==marked
    with pytest.raises(ValueError):inbox.apply(start,'handoff.read','unknown')
