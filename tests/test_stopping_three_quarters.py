from copy import deepcopy
import pytest
from vic import games
from vic_apps import stopping_training


def test_069c_counts_occupied_cells_not_tile_values():
    state=stopping_training.opening(10001)
    for count in (11,12,13,16):
        state['board']=[[1024 if r*4+c<count else 0 for c in range(4)] for r in range(4)]
        assert stopping_training.conditions(state)['C'] == (count>=12)


@pytest.mark.parametrize('seed',[0,1,2,3,4,5,17])
def test_demo_stops_at_first_twelve_cells(seed):
    initial=games.fixture(69,seed)
    assert sum(bool(n) for row in initial['board'] for n in row)<12
    for variant,path in games.stopping_paths(initial).items():
        state=deepcopy(initial);events=[]
        for direction in path:
            event=dict(op='move',target='',value=direction)
            state=games.apply(state,**event);events.append(event)
        event=dict(op='stop',target='',value='')
        state=games.apply(state,**event);events.append(event)
        assert games.evaluate(initial,state,variant,events)['success']
        if variant=='C':
            assert sum(bool(n) for row in state['board'] for n in row)==12
            assert len(path)<=8


@pytest.mark.parametrize('seed',[10001,10002])
def test_inference_first_stop_is_reachable(seed):
    initial=stopping_training.opening(seed)
    for variant,path in stopping_training.reference_paths(seed).items():
        state=deepcopy(initial);events=[]
        for direction in path:
            e=dict(op='move',target='',value=direction);state=stopping_training.apply(state,**e);events.append(e)
        e=dict(op='stop',target='',value='');state=stopping_training.apply(state,**e);events.append(e)
        assert stopping_training.evaluate(initial,state,variant,events)['success']
