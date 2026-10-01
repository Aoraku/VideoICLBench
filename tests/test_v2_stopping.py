from copy import deepcopy
import pytest
from vic import v2,games
from vic_apps import stopping_training as training
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


@pytest.mark.parametrize('variant',list('ABC'))
def test_stopping_native_api_persists_first_condition_and_resets(clients,variant):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=69,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();url='/api/runs/'+run['id'];headers=credential(run)
    initial=worker.get(url,headers=headers).json()['state']
    path=training.reference_paths(initial['seed'])[variant]
    assert 14<=len(path)<=initial['move_budget']
    for i,direction in enumerate(path+['stop']):
        response=worker.post(url+'/commands',headers=headers,json=dict(epoch=0,action_id=str(i),op='stop' if direction=='stop' else 'move',value='' if direction=='stop' else direction))
        assert response.status_code==200,response.text
    state=worker.get(url,headers=headers).json()['state']
    assert state['stopped'] and len(state['moves'])==len(path)
    response=control.post('/v2/tasks/69/eval',headers=admin(),json={'run_id':run['id']})
    assert response.status_code==200 and response.json()['success'],response.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin())
    assert reset.status_code==200
    assert worker.get(url,headers=credential(reset.json())).json()['state']==initial


@pytest.mark.parametrize('seed',[1000,10001,27183,1007,1009])
def test_reachable_opening_and_distinct_first_stop_conditions(seed):
    initial=v2.generate(69,seed,'eval')
    assert initial==v2.generate(69,seed,'eval')
    assert sorted(n for row in initial['board'] for n in row if n)==[2,2]
    assert initial['score']==0 and initial['moves']==[]
    for variant,path in training.reference_paths(seed).items():
        state=initial;events=[]
        for i,direction in enumerate(path):
            assert not training.conditions(state)[variant]
            events.append(dict(op='move',value=direction))
            state=training.apply(state,'move',value=direction)
        assert training.conditions(state)[variant]
        before_stop=state
        state=training.apply(state,'stop');events.append(dict(op='stop'))
        assert v2.evaluate(initial,state,variant,events)['success']
        for wrong in set('ABC')-{variant}:
            assert not v2.evaluate(initial,state,wrong,events)['success']
        changed=deepcopy(state);changed['score']+=1
        assert not v2.evaluate(initial,changed,variant,events)['success']
        assert not v2.evaluate(initial,before_stop,variant,events[:-1])['success']
        moves=[d for d in games.DIRECTIONS if games.move_2048(before_stop['board'],d)[1]['changed']]
        if moves and len(path)<initial['move_budget']:
            late=training.apply(before_stop,'move',value=moves[0]);late=training.apply(late,'stop')
            assert not v2.evaluate(initial,late,variant,events[:-1]+[dict(op='move',value=moves[0]),dict(op='stop')])['success']
    early=training.apply(initial,'stop')
    assert not v2.evaluate(initial,early,'A',[dict(op='stop')])['success']
    with pytest.raises(ValueError):training.apply(early,'move',value='up')
    exhausted=dict(initial,moves=['left']*initial['move_budget'])
    with pytest.raises(ValueError):training.apply(exhausted,'move',value='right')
