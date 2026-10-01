"""Procurement source messages and discussion share the isolated order workspace."""
import json
import pytest
from vic import v2
from vic_apps import procurement
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def test_purchase_conversation_persists_and_reset_restores_sources(clients):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=45,variant='A',seed=10001,mode='eval',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id'];headers=credential(run)
    initial=worker.get(path,headers=headers).json()['state']
    assert initial['linked_apps']==['shop','im']
    assert len({d['im'] for d in initial['world']['departments']})==3
    for d in initial['world']['departments']:
        sources=[r for r in initial['world']['requests'] if r['department']==d['id']]
        assert len(sources)==3 and {r['revision'] for r in sources}=={1,2}
        text=d['name']+'的采购资料已收到，请以申请编号核对。'
        body=dict(epoch=0,action_id='message-'+d['id'],op='message.send',target=str(d['im']),value=json.dumps(dict(text=text)))
        response=worker.post(path+'/commands',headers=headers,json=body)
        assert response.status_code==200,response.text
        duplicate=worker.post(path+'/commands',headers=headers,json=body)
        assert duplicate.json()['state']==response.json()['state']
    final=worker.get(path,headers=headers).json()['state']
    assert len(final['world']['discussion'])==3
    assert final['world']['requests']==initial['world']['requests']
    assert final['world']['orders']=={}
    assert not v2.evaluate(initial,final,'A',[])['success']
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin())
    assert reset.status_code==200,reset.text
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial


@pytest.mark.parametrize('target,data',[('999',{'text':'test'}),('10',{'text':''}),('10',{'text':12}),('10',{'text':'x','extra':'y'})])
def test_purchase_messages_require_valid_department_and_text(target,data):
    initial=procurement.fixture(10001)
    with pytest.raises(ValueError):procurement.apply(initial,'message.send',target,json.dumps(data))
    assert initial['world']['discussion']==[]
