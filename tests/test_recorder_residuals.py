from copy import deepcopy
import json,re
import pytest
from vic import v2,business,games,lessons
from vic_apps.domain import apply as apply_domain
from test_api import client,admin


def test_parameter_guidance_preserves_recorded_contracts(client):
    ids=[22,38,49,57,59,68,72]
    before={i:v2.digest(i) for i in ids}
    tasks={t['id']:t for t in client.get('/v2/tasks',headers=admin()).json()['tasks']}
    for i,key,expected in [(22,'threshold',50),(38,'threshold',50),(49,'text_threshold',15),(57,'threshold',50)]:
        assert tasks[i]['recording_parameters'][key]==expected
    assert '仅保存草稿不算完成' in tasks[59]['inference']['goal']
    assert '只需编辑规则示例并保存草稿' in tasks[59]['demo']['completion_checks'][-1]
    assert '并列' in tasks[68]['demo']['rule_explanations']['A']
    assert '行号' in tasks[72]['inference']['instructions']
    assert before=={i:v2.digest(i) for i in ids}
    assert '15 个字符' in v2.generate(49,10001,'eval')['public_parameters']


@pytest.mark.parametrize('seed',[1000,10001,10002])
def test_39_has_twelve_different_names_and_bodies_with_rule_contrasts(seed):
    initial=v2.generate(39,seed,'eval')
    batch=initial['atomic_inputs']
    items=initial['items']
    assert len(items)==12
    assert len({x['name'] for x in items})==12
    assert len({x['text'] for x in items})==12
    for u in batch:
        state={**initial,'source':u['source'],'items':[x for x in items if x['id'] in u['item_ids']]};effects=[business.expected_effect(39,v,state) for v in 'ABC']
        assert len({json.dumps(e,sort_keys=True) for e in effects})==3
        for x in state['items']:
            assert state['domain']['objects'][x['id']]['text']==x['text']


@pytest.mark.parametrize('seed',[0,4,92,10001])
@pytest.mark.parametrize('variant',list('AB'))
def test_68_accepts_every_tied_maximum_and_rejects_lower_values(seed,variant):
    initial=games.fixture(68,seed)
    metric='merges' if variant=='A' else 'score'
    stats={d:games.move_2048(initial['board'],d)[1] for d in games.DIRECTIONS}
    peak=max(s[metric] for s in stats.values() if s['changed'])
    for direction,s in stats.items():
        if not s['changed']:continue
        event=dict(op='move',target='',value=direction)
        final=games.apply(initial,**event)
        assert games.evaluate(initial,final,variant,[event])['success']==(s[metric]==peak)


@pytest.mark.parametrize('seed',[1000,10001,12345,98765])
def test_68_execution_avoids_vacuous_boards_and_separates_rules(seed):
    from vic_apps.board_collection import project
    shared=v2.generate(68,seed,'eval')
    batch=[dict(state=project(shared,key)) for key in shared['board_documents']]
    distinct=False
    for u in batch:
        s=u['state'];legal=[d for d in games.DIRECTIONS if games.move_2048(s['board'],d)[1]['changed']]
        a,b=[set(games.best_2048_directions(s,v)) for v in 'AB']
        assert len(a)<len(legal) and len(b)<len(legal)
        distinct |= a!=b
    assert distinct


def test_72_fifth_example_uses_documented_row_column_tiebreak():
    initial=games.fixture(72,lessons.seeds_for(72,0)[4]);board=initial['board'];n=len(board)
    def score(p):
        r,c=p
        return sum(board[i][j] or 0 for i in range(max(0,r-1),min(n,r+2)) for j in range(max(0,c-1),min(n,c+2)) if (i,j)!=(r,c))
    best=min(score(p) for p in initial['candidates'])
    tied=sorted(tuple(p) for p in initial['candidates'] if score(p)==best)
    assert games.expected(72,'A',initial)==tied[0]
    for p in tied:
        e=dict(op='choose',target=f'{p[0]},{p[1]}',value='')
        assert games.evaluate(initial,games.apply(initial,**e),'A',[e])['success']==(p==tied[0])

@pytest.mark.parametrize('variant',list('ABC'))
def test_59_demo_save_is_enough_but_inference_also_requires_submission(variant):
    from vic import application_eval,v2_atomic
    from vic_apps import atomic_delivery
    demo=v2.generate(59,0,'demo')
    text=business.transform(59,'ABC'.index(variant),demo)
    e=dict(op='save',target='target',value=text)
    saved=apply_domain(business.apply_mutation(demo,**e),**e)
    assert application_eval.evaluate(demo,saved,variant,[e])['success']
    from test_v2_atomic_batch import batch_reference
    from vic_apps.atomic_objects import apply
    initial=v2.generate(59,10001,'eval');saved=deepcopy(initial);events=[]
    for op,target,value,ids in batch_reference(initial,variant,delivery=False):
        saved=apply(saved,op,target,value,ids);events.append(dict(op=op,target=target,value=value,ids=ids))
    assert not v2.evaluate(initial,saved,variant,events)['success']
    for entry in initial['atomic_inputs']:
        saved=apply(saved,'answer.submit',entry['id'],'',[])
    assert v2.evaluate(initial,saved,variant,events)['success']
