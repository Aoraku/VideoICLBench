"""A full tutorial consists of isolated, auditable episodes in one recording."""
import json
import pytest
from vic.models import Run
from vic.app_client import ApplicationClient
from vic.teaching import BATCH_TASKS
from test_application_api import clients
from test_api import admin
from test_applications import reference


def create_lesson(control, task=1, variant='A'):
    result=control.post('/v1/runs',headers=admin(),json=dict(task_id=task,variant=variant,
        seed=0,mode='demo',interaction='human',teaching=True))
    assert result.status_code==201,result.text
    return result.json()


def actor(run):
    return {'Authorization':'Bearer '+run['application_url'].split('#')[1]}


def operate(worker, run, variant):
    path='/api/runs/'+run['id']
    state=worker.get(path,headers=actor(run)).json()['state']
    for index,(op,target,value,ids) in enumerate(reference(state,variant)):
        result=worker.post(path+'/commands',headers=actor(run),json=dict(epoch=run['epoch'],
            action_id=f'command-{index}',op=op,target=target,value=value,ids=ids))
        assert result.status_code==200,result.text
    return state


def advance(control, run, index):
    response=control.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),
        json={'epoch':run['epoch'],'index':index})
    assert response.status_code==200,response.text
    data=response.json()
    assert not {'variant','result','manifest','rule','seeds'} & data.keys()
    return data


@pytest.mark.parametrize('task', [task for task in range(1,76) if task not in BATCH_TASKS])
@pytest.mark.parametrize('variant', ['A','B','C'])
def test_complete_lesson_requires_six_independent_episodes(clients, task, variant):
    control,worker=clients
    run=create_lesson(control,task,variant)
    assert run['lesson']['total']==6
    evidence=[]
    for index in range(6):
        state=operate(worker,run,variant)
        evidence.append(state)
        previous=run.copy()
        result=advance(control,run,index)
        again=advance(control,previous,index)
        assert result==again
        assert result['lesson']['completed']==index+1
        run={**run,**result}
        if index<5:
            stale=worker.post('/api/runs/'+run['id']+'/commands',headers=actor(previous),
                json=dict(epoch=run['epoch'],action_id='stale',op='save',target='target',value='old page'))
            assert stale.status_code==403
    assert run['lesson']['finished']
    result=control.post('/v1/runs/'+run['id']+'/evaluate',headers=admin())
    assert result.status_code==200,result.text
    assert result.json()['success'] and len(result.json()['episodes'])==6
    for item in result.json()['episodes']:
        archived=control.get(item['evidence_ref'],headers=admin()).json()
        assert archived['result']['success'] and archived['events']
    assert len({json.dumps(s,sort_keys=True) for s in evidence})==6


def test_wrong_episode_remains_editable_and_cannot_advance(clients):
    c,w=clients;run=create_lesson(c)
    response=c.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),json=dict(epoch=0,index=0))
    assert response.status_code==409
    assert w.get('/api/runs/'+run['id'],headers=actor(run)).json()['status']=='active'
    operate(w,run,'A')
    assert advance(c,run,0)['lesson']['index']==1


def test_failed_episode_check_preserves_editable_workspace(clients, monkeypatch):
    from vic import application_eval
    c,w=clients;run=create_lesson(c)
    original=application_eval.evaluate
    def fail(*_, **__):raise RuntimeError('temporary evaluation failure')
    monkeypatch.setattr(application_eval,'evaluate',fail)
    response=c.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),json=dict(epoch=0,index=0))
    assert response.status_code==503
    assert w.get('/api/runs/'+run['id'],headers=actor(run)).json()['status']=='active'
    monkeypatch.setattr(application_eval,'evaluate',original)
    operate(w,run,'A')
    assert advance(c,run,0)['lesson']['index']==1


def test_lesson_aggregation_keeps_clipboard_evidence_metadata():
    from vic.lessons import aggregate, plan
    result=aggregate(plan(43,0),dict(success=True,completion=1,checks=[],violations=[],
                                   clipboard_evidence_source='human_paste'))
    assert result['success']
    assert result['clipboard_evidence_source']=='human_paste'


def test_early_finish_does_not_pass_or_hide_missing_episodes(clients):
    c,w=clients;run=create_lesson(c)
    operate(w,run,'A')
    result=c.post('/v1/runs/'+run['id']+'/evaluate',headers=admin()).json()
    assert not result['success']
    assert result['completion']==pytest.approx(1/6)
    assert len(result['checks'])==6


def test_progress_survives_failed_next_prepare_and_retry(clients, monkeypatch):
    c,w=clients;run=create_lesson(c)
    operate(w,run,'A')
    original=ApplicationClient.prepare
    def fail(*_):raise RuntimeError('worker temporarily unavailable')
    monkeypatch.setattr(ApplicationClient,'prepare',fail)
    response=c.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),json=dict(epoch=0,index=0))
    assert response.status_code==503
    monkeypatch.setattr(ApplicationClient,'prepare',original)
    current=advance(c,run,0)
    assert current['lesson']['index']==1 and current['lesson']['completed']==1
    operate(w,{**run,**current},'A')


def test_reset_restores_first_episode_and_preserves_archives(clients):
    c,w=clients;run=create_lesson(c)
    operate(w,run,'A');following=advance(c,run,0)
    reset=c.post('/v1/runs/'+run['id']+'/reset',headers=admin()).json()
    assert reset['epoch']==1 and reset['lesson']['index']==0 and reset['lesson']['completed']==0
    assert w.get('/api/runs/'+run['id'],headers=actor(following)).status_code==403
    assert c.get('/v1/runs/'+run['id']+'/lesson/evidence/0/0',headers=admin()).status_code==200
    stale=c.post('/v1/runs/'+run['id']+'/lesson/next',headers=actor(run),json=dict(epoch=0,index=0))
    assert stale.status_code==409


def test_application_has_rule_free_lesson_control(clients):
    c,w=clients;run=create_lesson(c)
    metadata=w.get('/api/runs/'+run['id'],headers=actor(run)).json()['lesson']
    assert metadata=={'index':0,'total':6,'completed':0,'finished':False}
    page=w.get('/native/chat/'+run['id']+'/').text
    assert '<script src="/lesson-controls.js"></script>' in page
    assert '首字母小写' not in page
    script=w.get('/lesson-controls.js').text
    assert 'location.replace(data.application_url)' in script
    assert 'getDisplayMedia' not in script and '首字母小写' not in script


def test_teaching_is_not_enabled_for_inference(clients):
    c,w=clients
    response=c.post('/v1/runs',headers=admin(),json=dict(task_id=1,variant='A',seed=1000,
        mode='eval',interaction='human',teaching=True))
    assert response.status_code==422


def test_native_proxy_persists_finished_progress_and_reports_connection_failures(clients, monkeypatch):
    import httpx
    c,w=clients;run=create_lesson(c)
    for index in range(6):
        operate(w,run,'A')
        run={**run,**advance(c,run,index)}
    class Controller:
        def __init__(self, **_):pass
        async def __aenter__(self):return self
        async def __aexit__(self, *_):pass
        async def post(self, url, *, headers, json):
            assert headers==actor(run)
            assert json==dict(epoch=0,index=5)
            return httpx.Response(200,json={key:run[key] for key in ('lesson','epoch','application_url')})
    monkeypatch.setattr(httpx,'AsyncClient',Controller)
    path='/api/runs/'+run['id']
    response=w.post(path+'/lesson/next',headers=actor(run),json=dict(epoch=0,index=5))
    assert response.status_code==200
    assert w.get(path,headers=actor(run)).json()['lesson']['finished']
    async def unavailable(*_, **__):raise httpx.ConnectError('controller offline')
    monkeypatch.setattr(Controller,'post',unavailable)
    response=w.post(path+'/lesson/next',headers=actor(run),json=dict(epoch=0,index=5))
    assert response.status_code==503 and '已保存的进度仍保留' in response.json()['detail']


@pytest.mark.parametrize('base_seed', [0,10,20])
def test_2048_lesson_eliminates_fixed_direction_explanations(base_seed):
    from vic.lessons import seeds_for
    from vic.games import fixture, expected
    seeds=seeds_for(68,base_seed)
    series={v:tuple(expected(68,v,fixture(68,s)) for s in seeds) for v in 'ABC'}
    assert len(set(series.values()))==3
    assert len(set(series['A']))>=2 and len(set(series['B']))>=2
    assert len(set(series['C']))>=3


def test_renaming_teaches_different_structures_and_held_out_names():
    import ast
    from vic.business import generate, transform
    demo=[generate(60,seed) for seed in range(6)]
    query=[generate(60,1000+seed) for seed in range(6)]
    demo_names={name for s in demo for name in s['source']['rename_targets']}
    query_names={name for s in query for name in s['source']['rename_targets']}
    assert not demo_names & query_names
    shapes={tuple(type(n).__name__ for n in ast.walk(ast.parse(s['source']['text']))) for s in demo}
    assert len(shapes)==6
    for state in demo+query:
        for variant in range(3):
            ast.parse(transform(60,variant,state))


def test_2048_queries_do_not_encode_rule_in_a_constant_direction():
    from vic.games import fixture, expected
    for variant in 'ABC':
        directions={expected(68,variant,fixture(68,s)) for s in range(1000,1040)}
        assert len(directions)>=2


def test_editing_lessons_have_six_distinct_sources():
    from vic.business import generate
    from vic.lessons import seeds_for
    for task in (1,2,3,4,17,18,19,20,21,36,37,44,45,46,58,59,60):
        values=[generate(task,seed)['source'] for seed in seeds_for(task,0)]
        assert len({json.dumps(s,sort_keys=True) for s in values})==6,task
