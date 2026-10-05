"""Regressions from recorder feedback: scope, navigation and visible saved results."""
import importlib.util
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from vic import business, v2, lessons, games
from vic_apps.domain import initialize
from vic_apps.music_native import render_music
from vic_apps import reversi_training
from test_application_api import clients
from test_api import admin


def test_existing_punctuation_is_preserved_in_all_query_items():
    state=v2.generate(3,10001,'eval')
    for unit in state['work_batch']['units']:
        item=unit['state'];source=item['source']['text']
        assert source.endswith(('.', '!', '?'))
        for variant in 'ABC':
            transformed=business.transform(3,'ABC'.index(variant),item)
            assert transformed.startswith(source) and len(transformed)>len(source)


def test_name_editing_demo_has_no_duplicate_contacts():
    for seed in lessons.seeds_for(2,0):
        state=v2.generate(2,seed,'demo')
        names=[state['source']['recipient']]+[x['name'] for x in state['items']]
        normalized=[' '.join(name.split()).casefold() for name in names]
        assert len(set(normalized))==len(names)


def test_only_one_song_is_marked_and_editable_per_demo():
    state=initialize(business.generate(17,0))
    home=render_music('a'*32,state,'')
    assert home.count('本组待整理')==1
    target=render_music('a'*32,state,'songs/target/')
    assert 'id="editName"' in target
    other=render_music('a'*32,state,'songs/'+state['items'][1]['id']+'/')
    assert 'id="editName"' not in other


@pytest.mark.parametrize('task',[19,20])
def test_news_batch_switch_keeps_home_route_available(clients,task):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task,variant='A',seed=10001,mode='eval',runtime='browser',interaction='human'))
    response.raise_for_status();run=response.json();path='/api/runs/'+run['id'];auth={'Authorization':'Bearer '+urlsplit(run['application_url']).fragment}
    for i in range(1,4):
        worker.post(path+'/commands',headers=auth,json=dict(epoch=0,action_id=str(i),op='batch.open',target=f'work-{i}',value='',ids=[])).raise_for_status()
        for suffix in ('','/'):
            page=worker.get('/native/news/'+run['id']+suffix)
            assert page.status_code==200 and 'news-app' in page.text


def test_answer_demo_is_one_multiline_rule_example():
    assert lessons.episode_count(59)==1
    demo=v2.generate(59,0,'demo')
    assert len(demo['source']['text'].splitlines())>=3
    assert not demo.get('v2_atomic')
    query=v2.generate(59,10001,'eval')
    assert len(query['work_batch']['units'])==3
    assert all(u['state']['source']['answer_problem'] for u in query['work_batch']['units'])


def test_rating_scale_retains_visible_boundary_and_distinct_rules():
    state=business.generate(48,0)
    assert {2.4,2.5,2.6}<={x['rating'] for x in state['items']}
    assert all(0<=x['rating']<=5 and round(x['rating'],1)==x['rating'] for x in state['items'])
    assert state['source']['rating_threshold']==2.5
    assert len({str(business.expected_effect(48,v,state)) for v in 'ABC'})==3


def test_reversi_retains_player_position_before_opponent():
    state=v2.generate(74,10001,'eval');point=games.expected(74,'A',state)
    after=reversi_training.apply(state,'choose',','.join(map(str,point)))
    turn=after['turns'][-1]
    assert turn['player_board']==games.reversi_move(state['board'],*point,state['color'])
    board=turn['player_board']
    for move in turn['opponent']:board=games.reversi_move(board,*move,3-state['color'])
    assert board==after['board']


def test_oj_reads_one_snapshot_per_render_and_uses_command_result(monkeypatch):
    path=Path(__file__).resolve().parents[1]/'apps/code/app/benchmark_bridge.py'
    spec=importlib.util.spec_from_file_location('feedback_bridge',path);bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    calls=[]
    class Response:
        ok=True
        def json(self):return {'epoch':0,'state':{'revision':len(calls)}}
    def request(*args,**kwargs):calls.append(args);return Response()
    monkeypatch.setattr(bridge.requests,'request',request)
    monkeypatch.setenv('VIC_NATIVE_SELF_BASE','http://test');monkeypatch.setenv('VIC_NATIVE_RUN','test');monkeypatch.setenv('VIC_NATIVE_TOKEN','test')
    bridge.begin_render()
    for _ in range(40):assert bridge.business()['state']['revision']==1
    assert len(calls)==1
    bridge.command('label','object','AC')
    assert len(calls)==2 and bridge.business()['state']['revision']==2
    bridge.begin_render();bridge.business();assert len(calls)==3
