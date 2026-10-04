import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from vic.os_integration import install_os_routes


@pytest.fixture
def os_client(tmp_path, monkeypatch):
    import vic.os_integration as mod
    source = tmp_path/'source'; (source/'data/manifests').mkdir(parents=True)
    (source/'demo.webm').write_bytes(b'demo')
    (source/'data/manifests/os-icl-1.0.0.json').write_text(json.dumps({'entries':[{
        'case_id':'OS-SEL-01','rule':0,'seed':1000000,'video':'demo.webm','sha256':hashlib.sha256(b'demo').hexdigest()}]}))
    calls = []
    class Upstream:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def request(self, method, path, **kwargs):
            calls.append((method,path,kwargs))
            data={'id':'vos_123','case':{'task':'Select the correct item.','title':'File selection'},'benchmark_version':'1.0.0','status':'active'}
            if path.endswith('/finish'): data.update(status='finished',result={'success':False,'agent_steps':0})
            return SimpleNamespace(status_code=200,json=lambda:data,content=b'const response = await fetch(url, {});\n  if(state.replay){',headers={'Content-Type':'text/javascript'})
    monkeypatch.setattr(mod.httpx, 'AsyncClient', Upstream)
    class Browser:
        def __init__(self): self.sessions={};self.limits={}
        async def ensure(self,sid,url): self.sessions[sid]={}
        async def screenshot(self,*args): return {'image':'data:image/png;base64,cGl4ZWxz','frame':1,'width':1280,'height':720}
        async def close_run(self,sid): self.sessions.pop(sid,None)
    browser=Browser()
    def manager(authorization: str = Header(default='')):
        if authorization!='Bearer manager': raise HTTPException(403,'Manager credential required')
    app=FastAPI(); install_os_routes(app,manager,'manager',tmp_path/'data',source=source,runtime=browser)
    return TestClient(app), calls, browser


def create(client, **kwargs):
    response=client.post('/os-api/runs',headers={'Authorization':'Bearer manager'},json={'case_id':'OS-SEL-01',**kwargs})
    assert response.status_code==200,response.text
    return response.json()


def test_os_actor_cannot_access_catalog_semantic_actions_or_grade(os_client):
    client,calls,_=os_client
    run=create(client,interaction='agent')
    assert 'rule_text' not in json.dumps(run) and 'expected' not in json.dumps(run)
    actor={'Authorization':'Bearer '+run['actor_token']}
    assert client.get('/os-api/cases',headers=actor).status_code==403
    assert client.post('/os-api/runs/vos_123/eval',headers=actor).status_code==403
    assert client.post('/os-sim/vos_123/api/v1/sessions/vos_123/action',headers=actor,json={}).status_code==403
    observation=client.get('/os-api/runs/vos_123/observation',headers=actor)
    assert observation.status_code==200
    assert observation.json()['height']==720
    assert not any(path.endswith('/action') for _,path,_ in calls)


def test_browser_capability_is_session_scoped_and_no_authoring_routes(os_client):
    client,_,_=os_client;run=create(client)
    page=client.get(run['application_url'],follow_redirects=False)
    assert page.status_code==303 and 'access=' not in page.headers['location']
    assert 'HttpOnly' in page.headers['set-cookie']
    assert client.get('/os-sim/vos_123/app.js').status_code==200
    assert client.post('/os-sim/vos_123/api/v1/sessions',json={}).status_code==404
    assert client.get('/os-sim/vos_123/api/v1/sessions/vos_other').status_code==404
    assert client.get('/os-sim/vos_123/data/episodes/vos_123.json').status_code==404
    assert client.post('/os-sim/vos_123/api/v1/sessions/vos_123/reset',json={}).status_code==404


def test_eval_uses_upstream_result_and_is_idempotent(os_client):
    client,calls,_=os_client;create(client)
    for _ in range(2):
        r=client.post('/os-api/runs/vos_123/eval',headers={'Authorization':'Bearer manager'})
        assert r.status_code==200 and r.json()['success'] is False
    assert sum(path.endswith('/finish') for _,path,_ in calls)==1


def test_no_demo_seed_replay_or_silent_browser_recreation(os_client):
    client,_,browser=os_client
    assert client.post('/os-api/runs',headers={'Authorization':'Bearer manager'},json={'case_id':'OS-SEL-01','seed':1000000}).status_code==422
    run=create(client,interaction='agent');auth={'Authorization':'Bearer '+run['actor_token']}
    assert client.get('/os-api/runs/vos_123/observation',headers=auth).status_code==200
    browser.sessions.clear()
    r=client.get('/os-api/runs/vos_123/observation',headers=auth)
    assert r.status_code==409 and 'interrupted' in r.text
