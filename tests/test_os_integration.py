import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from vic.os_integration import install_os_routes

AUTH={'Authorization':'Bearer manager'}
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def os_client(tmp_path,monkeypatch):
    import vic.os_integration as mod
    source=tmp_path/'source';source.mkdir();release=json.loads((ROOT/'tasks/os/catalog.json').read_text())
    (source/'videoicl-catalog.json').write_text(json.dumps(release));data=tmp_path/'data';calls=[];sessions={};state={'success':False}
    class Upstream:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def request(self,method,path,**kwargs):
            calls.append((method,path,kwargs));payload=kwargs.get('json') or {}
            if path=='/api/v2/cases':out={'benchmark_version':release['benchmark_version'],'cases':release['cases']}
            elif path=='/api/v2/sessions':
                sid=f'osl_{len(sessions)+1}';out={'id':sid,'case':{'task':'Use the demonstrated file naming format.','title':'Naming'},'compatible':True,'benchmark_version':release['benchmark_version'],'status':'active'};sessions[sid]=out
            elif path.endswith('/judge'):out={'result':{'success':state['success'],'failed_checks':[] if state['success'] else ['goal.1']}}
            elif path.endswith('/finish'):
                out={**sessions[path.split('/')[-2]],'status':'finished','result':{'success':state['success'],'agent_steps':2}}
            elif path.startswith('/api/v2/sessions/'):out={**sessions.get(path.split('/')[-1],{}),'state':state.get('desktop',{})}
            else:out={}
            content=b"const r = await fetch(url, {}); const label=`${btn('task-info','Task instructions')}`;"
            if path=='/':content=b'<html><body><script src="/desktop.js"></script></body></html>'
            return SimpleNamespace(status_code=200,json=lambda:out,content=content,headers={'Content-Type':'text/javascript'})
    monkeypatch.setattr(mod.httpx,'AsyncClient',Upstream)
    class Browser:
        def __init__(self):self.sessions={};self.limits={}
        async def ensure(self,sid,url):self.sessions[sid]={}
        async def screenshot(self,*a):return {'image':'data:image/png;base64,cGl4ZWxz','frame':1,'width':1280,'height':720}
        async def close_run(self,sid):self.sessions.pop(sid,None)
    browser=Browser()
    def manager(authorization:str=Header(default='')):
        if authorization!='Bearer manager':raise HTTPException(403)
    app=FastAPI();install_os_routes(app,manager,'manager',data,source=source,runtime=browser)
    return TestClient(app),calls,browser,state,data


def create(client,**kwargs):
    response=client.post('/os-api/runs',headers=AUTH,json={'case_id':'OS-E-01',**kwargs});assert response.status_code==200,response.text;return response.json()


def test_catalogue_three_levels_and_actor_isolation(os_client):
    c,calls,_,_,_=os_client
    rows=c.get('/os-api/cases',headers=AUTH).json()['cases']
    assert len(rows)==36
    for level in ('easy','medium','hard'):assert sum(t['difficulty']==level for t in rows)==12
    run=create(c);sid=run['id'];actor={'Authorization':'Bearer '+run['actor_token']}
    assert c.get('/os-api/cases',headers=actor).status_code==403
    assert c.post(f'/os-api/runs/{sid}/check',headers=actor).status_code==403
    assert c.post(f'/os-sim/{sid}/api/v2/sessions/{sid}/action',headers=actor,json={}).status_code==403
    assert c.post('/os-api/runs',headers=AUTH,json={'case_id':'OS-E-01','interaction':'agent'}).status_code==409


def test_browser_scoped_transport_and_goal_hidden(os_client):
    c,*_=os_client;run=create(c);sid=run['id']
    r=c.get(run['application_url'],follow_redirects=False);assert r.status_code==303 and 'HttpOnly' in r.headers['set-cookie']
    script=c.get(f'/os-sim/{sid}/desktop.js');assert script.status_code==200 and 'Task instructions' not in script.text
    for path in ('api/v2/sessions','api/v2/sessions/osl_other',f'api/v2/sessions/{sid}/reset','tasks36.py'):
        assert c.get(f'/os-sim/{sid}/{path}').status_code==404
    assert c.post(f'/os-sim/{sid}/lesson-next').status_code==404


def test_eval_finalizes_but_check_does_not(os_client):
    c,calls,*_=os_client;run=create(c);sid=run['id']
    assert c.post(f'/os-api/runs/{sid}/check',headers=AUTH).json()['success'] is False
    assert not any(p.endswith('/finish') for _,p,_ in calls)
    for _ in range(2):assert c.post(f'/os-api/runs/{sid}/eval',headers=AUTH).json()['success'] is False
    assert sum(p.endswith('/finish') for _,p,_ in calls)==1


def test_same_rule_three_demo_examples_and_single_query(os_client):
    c,calls,_,state,_=os_client
    run=create(c,case_id='OS-H-11',mode='demo');lesson=run['lesson'];assert lesson['seeds']==[509,73,258]
    creates=[k['json'] for _,p,k in calls if p=='/api/v2/sessions']
    assert len(creates)==3 and all(d['plan_variant']=='module-demo' and d['mode']=='practice' and d['convention']==0 for d in creates)
    sid=run['id'];c.get(run['application_url'])
    assert c.post(f'/os-sim/{sid}/lesson-next').status_code==409
    state['success']=True
    for child in lesson['sessions']:
        current=c.get(f'/os-api/runs/{sid}',headers=AUTH).json();c.get(current['application_url'])
        response=c.post(f'/os-sim/{child}/lesson-next');assert response.status_code==200,response.text
    assert response.json()['finished']
    assert c.get(f'/os-api/runs/{sid}',headers=AUTH).json()['lesson']['finished']
    assert not create(c,case_id='OS-H-11')['lesson']


def test_upload_review_persists_and_demo_is_pinned(os_client,monkeypatch):
    from vic import human_recording
    c,calls,browser,state,data=os_client
    def convert(src,out,*a):out.write_bytes(b'mp4');return {'frames':30,'duration':1}
    monkeypatch.setattr(human_recording,'convert',convert)
    run=create(c,mode='demo');base=f"/os-api/runs/{run['id']}/recordings"
    r=c.post(base+'/upload',headers={**AUTH,'Content-Type':'video/webm'},content=b'uploaded');assert r.status_code==200
    assert c.post(base+'/review',headers=AUTH,json={'reviewer':'Human'}).status_code==409
    state['success']=True
    assert c.post(base+'/review',headers=AUTH,json={'reviewer':'Human','note':'all examples clear'}).json()['approved']
    assert c.get('/os-api/cases',headers=AUTH).json()['cases'][0]['recording_status']['A']=='已完成录制'
    assert c.get(base+'/video',headers=AUTH).content==b'mp4'
    assert c.get('/os-api/cases/OS-E-01/demo',headers=AUTH).content==b'mp4'
    assert c.post('/os-api/runs',headers=AUTH,json={'case_id':'OS-E-01','seed':1001}).status_code==422
    actor_run=create(c,interaction='agent');actor={'Authorization':'Bearer '+actor_run['actor_token']}
    assert c.get(actor_run['demonstrations'][0]['url'],headers=actor).content==b'mp4'
    assert c.get(f"/os-api/runs/{actor_run['id']}/observation",headers=actor).status_code==200
    browser.sessions.clear()
    assert c.get(f"/os-api/runs/{actor_run['id']}/observation",headers=actor).status_code==409
    # Uploading another take cannot change a demo already selected for a run.
    c.post(base+'/upload',headers={**AUTH,'Content-Type':'video/mp4'},content=b'new')
    assert c.get(actor_run['demonstrations'][0]['url'],headers=actor).content==b'mp4'
    assert len(list((data/'os-recordings').glob('*.json')))==2
    assert c.get(f"/os-api/runs/{run['id']}",headers=AUTH).json()['recording']['approved'] is False


def test_demo_check_and_next_explain_saved_json_error(os_client):
 c,_,_,state,_=os_client
 run=create(c,case_id='OS-M-10',mode='demo');sid=run['id']
 state['desktop']={'files':[
  {'id':'p','parent':None,'name':'Projects'},
  {'id':'proj','parent':'p','name':'Project-1001'},
  {'id':'out','parent':'proj','name':'Output'},
  {'id':'result','parent':'out','name':'Example result.txt','content':'[{"decision":Approved}]'}]}
 checked=c.post(f'/os-api/runs/{sid}/check',headers=AUTH).json()
 assert checked['passed']==0 and checked['total']==3
 assert 'JSON 第 1 行' in checked['groups'][0]['feedback'][0]
 c.get(run['application_url'])
 response=c.post(f'/os-sim/{sid}/lesson-next')
 assert response.status_code==409 and 'JSON 第 1 行' in response.json()['detail']
 # Feedback must not finalize a session or turn a failed score into success.
 assert not c.get(f'/os-api/runs/{sid}',headers=AUTH).json()['lesson']['finished']
