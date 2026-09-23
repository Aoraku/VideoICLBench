"""Human application entry keeps run isolation without the remote input layer."""
from test_application_api import clients
from test_api import admin
from vic.business import transform


def human(control, task=1):
    r=control.post('/v1/runs',headers=admin(),json=dict(task_id=task,variant='A',seed=10001,runtime='browser',interaction='human'))
    assert r.status_code==201,r.text
    return r.json()


def credential(run):
    return {'Authorization':'Bearer '+run['application_url'].split('#')[1]}


def test_direct_entry_isolation_reset_and_evaluation(clients,monkeypatch):
    monkeypatch.setenv('VIC_APPLICATION_PUBLIC_BASE','http://127.0.0.1:18766')
    c,w=clients;a=human(c);b=human(c)
    assert a['application_url'].startswith('http://127.0.0.1:18766/apps/chat/')
    assert a['interaction']=='human'
    url='/api/runs/'+a['id'];p='/v1/runs/'+a['id']
    assert w.get('/api/runs/'+b['id'],headers=credential(a)).status_code==403
    state=w.get(url,headers=credential(a)).json()['state']
    value=transform(1,0,state)
    r=w.post(url+'/commands',headers=credential(a),json=dict(epoch=0,action_id='save',op='save',target='target',value=value))
    assert r.status_code==200,r.text
    assert w.get(url,headers=credential(a)).json()['state']['outputs']['target']==value
    assert c.get(p+'/observation',headers=admin()).status_code==409
    assert c.post(p+'/actions',headers=admin(),json=dict(epoch=0,frame=0,action_id='input',kind='click',x=10,y=10)).status_code==409
    result=c.post(p+'/evaluate',headers=admin());assert result.json()['success'],result.text
    assert not c.app.state.runtime.sessions
    assert w.post(url+'/commands',headers=credential(a),json=dict(epoch=0,action_id='late',op='save',target='target',value=value)).status_code==409
    reset=c.post(p+'/reset',headers=admin()).json()
    assert reset['interaction']=='human' and reset['epoch']==1
    assert w.get(url,headers=credential(a)).status_code==403
    assert w.get(url,headers=credential(reset)).json()['state']['outputs']=={}
    assert not c.post(p+'/evaluate',headers=admin()).json()['success']


def test_human_commands_do_not_inherit_agent_budget(clients):
    c,w=clients;r=human(c);path='/api/runs/'+r['id']
    for i in range(302):
        response=w.post(path+'/commands',headers=credential(r),json=dict(epoch=0,action_id=str(i),op='save',target='target',value=f'编辑稿 {i}'))
        assert response.status_code==200,response.text
    assert w.get(path,headers=credential(r)).json()['state']['outputs']['target']=='编辑稿 301'
    assert not c.app.state.runtime.sessions


def test_pilot_gate_and_human_recording_guard(clients):
    c,w=clients
    assert c.post('/v1/runs',headers=admin(),json=dict(task_id=17,variant='A',seed=10001,interaction='human')).status_code==409
    r=c.post('/v1/runs',headers=admin(),json=dict(task_id=23,variant='A',seed=0,mode='demo',interaction='human')).json()
    assert c.post('/v1/runs/'+r['id']+'/recordings/start',headers=admin()).status_code==409
    assert not c.app.state.runtime.sessions
