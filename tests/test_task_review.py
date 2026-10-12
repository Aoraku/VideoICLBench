import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from vic.main import create_app

SECRET='review-test-'+'x'*40
AUTH={'Authorization':'Bearer '+SECRET}

@pytest.fixture
def review(tmp_path,monkeypatch):
    osroot=tmp_path/'os';osroot.mkdir()
    (osroot/'cases.py').write_text('CASES = [Case("OS-SEL-01", "Selection", "Files", "selection", "L1", "Choose the file", ("red", "green", "blue"))]')
    (osroot/'data/manifests').mkdir(parents=True)
    (osroot/'demo.webm').write_bytes(b'abcdefghij')
    (osroot/'data/manifests/os-icl-1.0.0.json').write_text(json.dumps({'entries':[{'case_id':'OS-SEL-01','rule':0,'video':'demo.webm'}]}))
    monkeypatch.setenv('VIC_OS_SOURCE',str(osroot))
    monkeypatch.setenv('VIC_EMBODIED_SOURCE',str(Path(__file__).resolve().parents[1]/'simulator'))
    def make():return create_app(database_url=f'sqlite:///{tmp_path}/db',data_dir=tmp_path,secret=SECRET)
    return TestClient(make()),make


def test_catalog_rules_auth_and_videos(review):
    c,_=review
    assert c.get('/review-api/tasks').status_code==401
    assert c.get('/review-api/tasks',headers={'Authorization':'Bearer actor'}).status_code==403
    d=c.get('/review-api/tasks',headers=AUTH).json()
    assert d['warnings']==[]
    assert len([t for t in d['tasks'] if t['kind']=='web'])==75
    assert len([t for t in d['tasks'] if t['kind']=='embodied'])==8
    assert len([t for t in d['tasks'] if t['kind']=='os'])==1
    for t in d['tasks']:
        assert all(t['rules'].get(v) for v in 'ABC')
        assert t['instruction']
    assert c.get('/review').status_code==200
    assert c.get('/review-api/media/os/OS-SEL-01/A').status_code==401
    r=c.post('/review-api/access',headers=AUTH)
    assert 'HttpOnly' in r.headers['set-cookie']
    r=c.get('/review-api/media/os/OS-SEL-01/A',headers={'Range':'bytes=2-5'})
    assert r.status_code==206 and r.content==b'cdef'
    assert c.get('/review-api/media/embodied/F01/A',headers={'Range':'bytes=0-100'}).status_code==206
    assert c.get('/review-api/media/os/OS-SEL-01/D').status_code==422
    c.cookies.set('vic-review','9999999999.invalid')
    assert c.get('/review-api/media/os/OS-SEL-01/A').status_code==401


def test_comments_persist_and_are_task_scoped(review):
    c,make=review
    path='/review-api/tasks/web/1/comments'
    body=dict(author='审阅者',status='revise',variant='B',text='规则清楚，执行描述需要明确交付物。')
    assert c.post(path,json=body).status_code==401
    assert c.post(path,headers=AUTH,json={**body,'text':'  '}).status_code==422
    assert c.post('/review-api/tasks/web/999/comments',headers=AUTH,json=body).status_code==404
    saved=c.post(path,headers=AUTH,json=body)
    assert saved.status_code==201
    c2=TestClient(make())
    rows=c2.get(path,headers=AUTH).json()
    assert len(rows)==1 and rows[0]['text']==body['text'] and rows[0]['variant']=='B'
    assert c2.get('/review-api/tasks/web/2/comments',headers=AUTH).json()==[]
    assert c2.get('/review-api/tasks',headers=AUTH).json()['tasks'][0]['comment_count']==1


def test_embodied_gateway_keeps_key_server_side_and_preserves_busy(tmp_path,monkeypatch):
    import vic.embodied_integration as mod
    from fastapi import FastAPI,HTTPException
    app=FastAPI()
    def access(request):
        if request.headers.get('Authorization')!='Bearer portal' and request.cookies.get('test-auth')!='yes':raise HTTPException(401)
    app.state.review_access=access
    upstream_key='upstream-secret-not-for-browser'
    monkeypatch.setenv('VIC_EMBODIED_KEY',upstream_key)
    real_client=httpx.AsyncClient;calls=[]
    async def handler(request):
        calls.append(request)
        if request.url.path=='/':return httpx.Response(200,text=(Path(__file__).resolve().parents[1]/'simulator/delivery8/dashboard.html').read_text())
        if request.url.path=='/control/sessions':return httpx.Response(409,stream=httpx.ByteStream(b'{"detail":"another session is active"}'))
        return httpx.Response(200,stream=httpx.ByteStream(b'[]'))
    monkeypatch.setattr(mod.httpx,'AsyncClient',lambda **kw:real_client(base_url=kw['base_url'],transport=httpx.MockTransport(handler)))
    mod.install_embodied(app);c=TestClient(app)
    assert c.get('/embodied-sim/control/tasks').status_code==401
    auth={'Authorization':'Bearer portal'}
    assert c.get('/embodied-sim/control/tasks',headers=auth).status_code==200
    assert calls[-1].headers['Authorization']=='Bearer '+upstream_key
    page=c.get('/embodied-sim/',headers=auth)
    script=c.get('/embodied-sim/dashboard.js',headers=auth)
    assert '<script>' not in page.text and upstream_key not in page.text+script.text
    assert 'Authorization' not in script.text
    assert "api('/actor/'" in script.text and "fetch('/embodied-sim'+path" in script.text
    assert c.post('/embodied-sim/control/sessions',headers=auth,json={}).status_code==409
    assert c.get('/embodied-sim/actor/capability/observe').status_code==200
    assert 'Authorization' not in calls[-1].headers
    assert c.get('/embodied-sim/release.private.json',headers=auth).status_code==404
    assert c.post('/embodied-sim/control/status',headers=auth).status_code==405


def test_review_lists_historical_colleague_video(review,tmp_path):
    from test_recording_library import save_take
    c,_=review
    run=c.post('/v1/runs',headers=AUTH,json={'task_id':1,'variant':'C','seed':0,'mode':'demo','runtime':'web-dev'}).json()
    save_take(tmp_path,run)
    assert c.post('/v1/runs/'+run['id']+'/reset',headers=AUTH).status_code==200
    row=c.get('/review-api/tasks',headers=AUTH).json()['tasks'][0]
    video=row['videos']['C'][0]
    assert video['historical'] and 'Recorder' in video['label'] and video['approved']
    assert c.get(video['url']).status_code==401
    c.post('/review-api/access',headers=AUTH)
    assert c.get(video['url']).content==b'saved-video-fixture'
