from copy import deepcopy
import pytest
from vic import games, v2, v2_atomic
from test_api import client, admin

BOARDS = [
    ([[0,4,16,16],[16,0,2,0],[2,16,2,2],[8,2,16,0]], {'up','right'}),
    ([[0,4,4,0],[2,4,2,8],[4,0,4,0],[16,2,2,4]], {'left','down'}),
]

@pytest.mark.parametrize('board,accepted',BOARDS)
def test_reported_boards_accept_all_and_only_corner_moves(board,accepted):
    state=games.fixture(68,0);state['board']=deepcopy(board)
    assert set(games.best_2048_directions(state,'C'))==accepted
    for direction in games.DIRECTIONS:
        event=dict(op='move',target='',value=direction)
        final=games.apply(state,**event)
        assert games.evaluate(state,final,'C',[event])['success']==(direction in accepted)
    # The merged 32 and the unmerged 16 are equally valid if each is in a corner.
    if 'right' in accepted:
        assert max(map(max,games.move_2048(board,'right')[0]))==32
        assert max(map(max,games.move_2048(board,'up')[0]))==16

@pytest.mark.parametrize('seed',[0,1,5,92,10001,99991])
def test_corner_metric_is_post_merge_and_ignores_noops(seed):
    state=games.fixture(68,seed);candidates={}
    for direction in games.DIRECTIONS:
        board,stats=games.move_2048(state['board'],direction)
        if stats['changed']:
            top=max(map(max,board))
            candidates[direction]=top in (board[0][0],board[0][-1],board[-1][0],board[-1][-1])
    expected={d for d,satisfies in candidates.items() if satisfies} or set(candidates)
    assert set(games.best_2048_directions(state,'C'))==expected


def test_noop_does_not_count_as_retaining_corner():
    state=games.fixture(68,0);state['board']=[[16,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]]
    assert set(games.best_2048_directions(state,'C'))=={'right','down'}


def test_inference_uses_same_corner_check():
    for unit in v2.generate(68,10001,'eval')['work_batch']['units']:
        state=unit['state']
        for direction in games.best_2048_directions(state,'C'):
            event=dict(op='move',target='',value=direction)
            assert v2_atomic._evaluate_item(state,games.apply(state,**event),'C',[event])['success']


def test_059_goal_and_068_corner_guidance_are_visible(client):
    before={i:v2.digest(i) for i in (59,68)}
    tasks={t['id']:t for t in client.get('/v2/tasks',headers=admin()).json()['tasks']}
    assert '分别正式提交' in tasks[59]['inference']['goal']
    assert '只保存文件（草稿）不算完成' in tasks[59]['inference']['goal']
    assert tasks[59]['inference']['completion_checks']
    explanation=tasks[68]['demo']['rule_explanations']['C']
    assert '合并结束后' in explanation and '任选一个' in explanation
    assert before=={i:v2.digest(i) for i in (59,68)}


def test_when_no_direction_can_corner_the_maximum_any_effective_move_is_valid():
    state=games.fixture(68,0)
    state['board']=[[2,2,4,8],[4,64,8,16],[8,16,32,4],[16,8,4,2]]
    assert set(games.best_2048_directions(state,'C'))=={'left','right'}
    for direction in ('left','right'):
        event=dict(op='move',target='',value=direction)
        assert games.evaluate(state,games.apply(state,**event),'C',[event])['success']
