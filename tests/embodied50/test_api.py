"""Real worker integration, including offscreen rendering. Run outside Mac sandbox."""
import json
import pytest
pytest.importorskip('robosuite')
from fastapi.testclient import TestClient
from simulator.benchmark import server

def test_actor_boundary_and_real_worker(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    server.SESSIONS.clear()
    with TestClient(server.app) as c:
        auth={'Authorization':'Bearer '+server.ADMIN}
        assert c.get('/admin/catalog').status_code==401
        assert c.post('/admin/sessions',headers=auth,json={'task':'rt12','condition':'human_frames'}).status_code==409
        stale=tmp_path/'demos/rt07/sim';stale.mkdir(parents=True)
        (stale/'manifest.json').write_text(json.dumps(dict(task='rt07',variant='A',author_verified=True,task_revision=1)))
        assert c.post('/admin/sessions',headers=auth,json={'task':'rt07','condition':'sim_frames'}).status_code==409
        r=c.post('/admin/sessions',headers=auth,json={'task':'rt12','action_budget':1})
        assert r.status_code==200,r.text
        sid=r.json()['session']; base=f'/actor/{sid}'
        manifest=json.loads((tmp_path/'runs'/sid/'manifest.json').read_text())
        assert len(manifest['harness_sha256'])==64 and len(manifest['catalog_sha256'])==64
        o=c.get(base+'/observe').json()
        assert len(o['images'])==3
        assert set(o)=={'images','actions','remaining','seconds_remaining'}
        assert '夹杯' not in c.get('/s/'+sid).text
        assert c.post(base+'/action',json={'left':'UP','right':'STILL','goal':'leak'}).status_code==422
        assert c.post(base+'/action',json={'left':'UP'}).status_code==200
        assert c.post(base+'/action',json={}).status_code==409
        assert c.post(base+'/submit',json={}).json()=={'ended':True}
        assert c.get('/admin/results/'+sid).status_code==401
        result=c.get('/admin/results/'+sid,headers=auth).json()
        assert result['success'] is False and result['actions']==1
        assert result['trial_kind']=='manual_author'
        assert c.get(base+'/observe').status_code==410
