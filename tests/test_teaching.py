"""Review regressions: observable facts, boundary coverage, and real state changes."""
from copy import deepcopy
from datetime import datetime
import pytest
from vic import business, application_eval, games
from vic.teaching import BATCH_TASKS
from vic_apps.domain import initialize
from vic_apps.store import ApplicationStore
from vic.schemas import Mutation
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


@pytest.mark.parametrize('seed', [0, 1, 2, 3, 4, 5, 1000, 10001])
def test_playlist_duration_parity_is_not_whole_minutes(seed):
    state = business.generate(32, seed)
    values = [x['duration'] for x in state['items']]
    assert len(set(values)) == len(values)
    assert {238,239,240,241,242,243} <= set(values)
    assert sum(x % 2 == 0 for x in values) == len(values) // 2
    assert any(x % 2 == 0 and x % 60 != 0 for x in values)
    assert any(x % 2 == 1 and (x // 60) % 2 == 0 for x in values)
    selected = business.action_targets(32, 2, state['items'], state['source'])[0]
    assert set(selected) == {x['id'] for x in state['items'] if x['duration'] % 2 == 0}


@pytest.mark.parametrize('task_id', [12, 28, 35])
@pytest.mark.parametrize('base_seed', [0, 10, 37, 1000, 10000])
def test_sorting_lessons_require_an_observable_rearrangement(task_id, base_seed):
    for seed in range(base_seed, base_seed + 6):
        initial = business.generate(task_id, seed)
        for variant in 'ABC':
            desired = business.expected_effect(task_id, variant, initial)['order']
            assert desired != initial['order']
            state = business.apply_mutation(initial, 'order', ids=desired)
            assert business.evaluate(initial, state, variant, [{'op':'order'}])['success']


@pytest.mark.parametrize('task_id', [31, 47, 51])
@pytest.mark.parametrize('base_seed', [0, 10, 20, 37, 1000])
def test_shortest_duration_lessons_rule_out_constant_values_and_thresholds(task_id, base_seed):
    choices, others = [], []
    for seed in range(base_seed, base_seed + 6):
        values = [item['duration'] for item in business.generate(task_id, seed)['items']]
        assert len(values) == len(set(values)) == 6
        assert all(0 < value < 1200 for value in values)
        choices.append(min(values))
        others.extend(value for value in values if value != min(values))
    assert len(set(choices)) == 6
    assert max(choices) > min(others)


@pytest.mark.parametrize('task_id', sorted(BATCH_TASKS))
def test_demonstrations_are_larger_than_queries(task_id):
    for seed in (0, 1, 2):
        demo = business.generate(task_id, seed)
        query = business.generate(task_id, 1000 + seed)
        assert len(demo['items']) == 24
        assert len(query['items']) == 6
        assert len({x['id'] for x in demo['items']}) == 24
        assert all('variant' not in x for x in demo['items'])


@pytest.mark.parametrize('task_id,field,boundaries', [
    (8, 'members', {4,5,6}), (22, 'duration', {239,240,241}),
    (25, 'duration', {599,600,601}), (32, 'rating', {49,50,51}),
    (38, 'words', {49,50,51}), (48, 'rating', {49,50,51}),
    (48, 'sales', {49,50,51}), (54, 'price', {49,50,51}),
    (56, 'amount', {49,50,51}), (57, 'balance', {49,50,51}),
])
def test_demo_boundaries_are_observable(task_id, field, boundaries):
    for seed in (0,1,2):
        assert boundaries <= {x[field] for x in business.generate(task_id, seed)['items']}


def test_text_and_code_length_boundaries():
    assert {14,15,16} <= {len(x['text']) for x in business.generate(49,0)['items']}
    assert {24,25,26} <= {len(x['code']) for x in business.generate(65,0)['items']}


def test_numeric_formatting_and_full_name_examples():
    s = business.generate(4,0)
    assert s['source']['text'] == '评审改到会议室3，请在下午14点前确认'
    assert business.transform(4,0,s) == '评审改到会议室#3，请在下午#1#4点前确认'
    assert business.transform(4,1,s) == '评审改到会议室3号，请在下午1号4号点前确认'
    assert business.transform(4,2,s) == '评审改到会议室three，请在下午onefour点前确认'
    s = business.generate(44,0)
    assert business.transform(44,2,s) == 'LIN MEI'
    assert {len(business.generate(46,s)['source']['text']) for s in range(6)} == {10,12,14,16,18,19}


def test_quotes_are_quotes_not_square_brackets():
    s = business.generate(39,0)
    rows = [dict(s['items'][0], id=str(i), text=text) for i,text in enumerate(
        ['see [design]', 'she said “yes”', 'he said "ready"', 'plain sentence'])]
    assert business.targets(39,2,rows,s['source']) == ['1','2']


@pytest.mark.parametrize('variant', ['A','B'])
def test_cart_requires_only_possible_membership_changes(tmp_path, variant):
    raw = business.generate(55,1000)
    for i,item in enumerate(raw['items']):
        item['tags'] = ['focus'] if i < 4 else []
        item['initial_in_cart'] = i in (0,2,4)
    initial = initialize(raw)
    ids = [x['id'] for x in initial['items']]
    store = ApplicationStore(tmp_path)
    store.initialize('run', initial)
    targets = [1,3] if variant == 'A' else [0,2]
    op = '加入购物车' if variant == 'A' else '移出购物车'
    for index in targets:
        store.mutate('run',Mutation(epoch=0,action_id=str(index),op='action',target=ids[index],value=op))
    final = store.snapshot('run')
    assert set(final['domain']['collections']['cart']) == ({ids[i] for i in (0,1,2,3,4)} if variant == 'A' else {ids[4]})
    assert application_eval.evaluate(initial,final,variant,store.events('run'))['success']
    # An unrelated product operation is still an error.
    store.mutate('run',Mutation(epoch=0,action_id='extra',op='action',target=ids[5],value=op))
    assert not application_eval.evaluate(initial,store.snapshot('run'),variant,store.events('run'))['success']


def test_visible_dates_agree_with_order_and_reminder_predicates():
    for seed in (0,1,1000):
        s = business.generate(53,seed)
        chronological = sorted(s['items'],key=lambda x:datetime.fromisoformat(x['created_at']))
        assert business.targets(53,2,s['items'],s['source']) == [chronological[0]['id']]
        s = business.generate(57,seed)
        dates = {x['id']:[tx['occurred_at'][:10] for tx in x['recent_transactions']] for x in s['items']}
        wanted = {key for key,(latest,prior) in dates.items() if latest == prior}
        assert set(business.action_targets(57,2,s['items'],s['source'])[0]) == wanted
        assert 0 < len(wanted) < len(dates)
        # The evaluator reads the actual records, not an invisible boolean.
        for x in s['items']: x['same_day'] = not x['same_day']
        assert set(business.action_targets(57,2,s['items'],s['source'])[0]) == wanted


def test_task_63_seed_one_and_positions_vary():
    for task_id,variant in ((41,'C'),(47,'C'),(63,'A')):
        positions=set()
        for seed in range(12):
            s=business.generate(task_id,seed)
            selected=business.targets(task_id,'ABC'.index(variant),s['items'],s['source'])
            positions.add(next(i for i,x in enumerate(s['items']) if x['id'] in selected))
        assert len(positions) >= 3


def winning_moves(board, color):
    """Independent five-in-a-row scan, without calling the task oracle."""
    result=set()
    for r in range(15):
        for c in range(15):
            if board[r][c]: continue
            for dr,dc in ((1,0),(0,1),(1,1),(1,-1)):
                count=1
                for sign in (-1,1):
                    a,b=r+sign*dr,c+sign*dc
                    while 0<=a<15 and 0<=b<15 and board[a][b]==color:
                        count+=1;a+=sign*dr;b+=sign*dc
                if count>=5: result.add((r,c))
    return result


def test_gomoku_block_prevents_immediate_white_win():
    for seed in range(30):
        state=games.fixture(66,seed)
        threats=winning_moves(state['board'],2)
        assert len(threats)==1
        blocks=games.expected(66,'C',state)
        assert set(blocks)==threats
        board=deepcopy(state['board'])
        for r,c in blocks: board[r][c]=1
        assert not winning_moves(board,2)


@pytest.mark.parametrize('task_id', [66, 67])
def test_gomoku_practice_does_not_start_with_a_winner(task_id):
    for seed in [*range(128), 1000, 10001]:
        board = games.fixture(task_id, seed)['board']
        for r in range(15):
            for c in range(15):
                if not board[r][c]:
                    continue
                for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
                    line = [(r + k * dr, c + k * dc) for k in range(5)]
                    assert not all(
                        0 <= a < 15 and 0 <= b < 15 and board[a][b] == board[r][c]
                        for a, b in line
                    ), (task_id, seed, line)


def test_sudoku_middle_candidate_has_no_row_parity_requirement():
    for seed in range(10):
        state=games.fixture(71,seed)
        r,c=state['candidates'][0]
        choices=games.sudoku_candidates(state['board'],r,c)
        assert len(choices)>=3 and len(choices)%2==1
        assert games.expected(71,'C',state)==choices[len(choices)//2]


def test_old_run_cannot_be_graded_until_reset_migrates_it(clients, tmp_path):
    from vic.models import Run
    c,w=clients
    run=c.post('/v1/runs',headers=admin(),json=dict(task_id=22,variant='A',seed=0,mode='demo',interaction='human')).json()
    with c.app.state.sessions() as db:
        stored=db.get(Run,run['id'])
        stored.manifest={**stored.manifest,'task_digest':'old-contract'}
        db.commit()
    path='/v1/runs/'+run['id']
    assert c.post(path+'/evaluate',headers=admin()).status_code==409
    reset=c.post(path+'/reset',headers=admin())
    assert reset.status_code==200,reset.text
    current=reset.json()
    assert current['epoch']==1 and current['manifest']['task_digest']!='old-contract'
    assert w.get('/api/runs/'+run['id'],headers=credential(run)).status_code==403
    state=w.get('/api/runs/'+run['id'],headers=credential(current)).json()['state']
    assert len(state['items'])==24
    archive=tmp_path/'control'/'runs'/run['id']/'epoch-0'
    assert (archive/'manifest.json').is_file() and (archive/'initial.json').is_file()
