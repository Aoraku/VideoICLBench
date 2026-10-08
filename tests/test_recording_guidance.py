"""Recorder instructions must be concrete without changing executable rules."""
from copy import deepcopy
import pytest
from vic import business, recording_guidance, v2
from test_api import client, admin
from test_application_api import clients


def test_recorder_parameters_and_boundaries_are_visible(client):
    tasks = {t['id']: t for t in client.get('/v2/tasks', headers=admin()).json()['tasks']}
    expected = {42:('C','小写“a”'), 43:('B','不需要拼接'), 44:('A','一个英文空格'),
                45:('C','完整商品名前'), 46:('C','倒数第 5 位'),
                54:('A','50 元'), 55:('A','focus'), 56:('C','50 元')}
    for task_id, (variant, text) in expected.items():
        assert text in tasks[task_id]['demo']['rule_explanations'][variant]
    assert '恰好 2 个不发布' in tasks[42]['demo']['rule_explanations']['A']
    assert '区分大小写' in tasks[56]['demo']['rule_explanations']['A']
    assert '等于阈值不' in tasks[54]['demo']['rule_explanations']['B']
    assert '250' in str(tasks[54]['inference'])
    assert '250' in str(tasks[56]['inference'])


def test_guidance_does_not_change_recording_identity_or_inference():
    for task in v2.catalog()['tasks']:
        before=deepcopy(task['inference']);digest=v2.digest(task['id'])
        recording_guidance.apply(task)
        assert task['inference']==before
        assert v2.digest(task['id'])==digest
    for seed in range(6):
        state=business.generate(46,seed);raw=state['source']['text']
        answer=business.transform(46,2,state)
        assert answer==raw[:4]+'*'*(len(raw)-8)+raw[-4:]


@pytest.mark.parametrize('status', ['recorded', 'completed'])
def test_uploaded_clipboard_lesson_can_finish_without_reopening_mutations(clients, status):
    from test_lessons import create_lesson, operate, actor
    from vic.models import Run
    c,w=clients;run=create_lesson(c,43,'B');operate(w,run,'B')
    path='/api/runs/'+run['id']
    state=w.get(path,headers=actor(run)).json()['state']
    history=state['domain']['clipboard_history']
    assert len(history)>1
    # Model the upload's frozen state without creating or recording a video.
    from vic.app_client import ApplicationClient
    from test_api import SECRET
    ApplicationClient(SECRET).seal(run['id'])
    with c.app.state.sessions() as db:
        row=db.get(Run,run['id']);row.status=status
        if status == 'completed':
            row.result = dict(success=False, completion=0, checks=[dict(id='browser_clipboard', passed=False)])
        db.commit()
    endpoint='/v1/runs/'+run['id']+'/lesson/next'
    body=dict(epoch=run['epoch'],index=0)
    response=c.post(endpoint,headers=admin(),json=body)
    assert response.status_code==200,response.text
    assert response.json()['lesson']['finished']
    saved=c.get('/v1/runs/'+run['id'],headers=admin()).json()
    assert saved['status']=='recorded'
    result=c.post('/v1/runs/'+run['id']+'/evaluate',headers=admin())
    assert result.status_code==200 and result.json()['success'],result.text
    assert result.json()['clipboard_evidence_source']=='application_clipboard'
