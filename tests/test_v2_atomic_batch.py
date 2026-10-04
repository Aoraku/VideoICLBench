"""Low difficulty repeats a learned rule over real saved work, without grading gates."""
from copy import deepcopy

import pytest

from vic import business, games, v2
from vic.schemas import Mutation
from vic.v2_atomic import TASKS, BATCH_TASKS, FOUR_OBJECTS
from vic_apps.store import ApplicationStore
from test_applications import reference


def item_reference(state, variant, delivery=True):
    actions=reference(state,variant)
    t=state['task_id']
    if delivery and t in (10,27,59):
        if t==59:actions.append(('answer.submit','target','',[]))
        else:actions.append(('shortcut.add' if t==10 else 'favorite.add',business.expected_effect(t,variant,state)['selection'][0],'',[]))
    return actions


def batch_reference(state,variant,delivery=True):
    if not state.get('work_batch'):
        return item_reference(state,variant,delivery)
    actions=[]
    for unit in state['work_batch']['units']:
        actions.append(('batch.open',unit['id'],'',[]))
        actions.extend(item_reference(unit['state'],variant,delivery))
    return actions


def act(store,run,actions,prefix='step'):
    for index,(op,key,value,ids) in enumerate(actions):
        store.mutate(run,Mutation(epoch=0,action_id=f'{prefix}-{index}',op=op,target=key,value=value,ids=ids))


@pytest.mark.parametrize('task_id', sorted(BATCH_TASKS))
@pytest.mark.parametrize('variant', list('ABC'))
def test_all_three_saved_work_items_required_and_revisitable(task_id,variant,tmp_path):
    initial=v2.generate(task_id,10001,'eval')
    units=initial['work_batch']['units']
    assert len(units)==3 and len({u['state']['seed'] for u in units})==3
    assert not any(u['state'].get('rule_target') for u in units)
    if task_id>=66:
        assert len({str(u['state']['board']) for u in units})==3
    else:
        assert len({str(u['state']['source']) for u in units})==3
    store=ApplicationStore(tmp_path);store.initialize('batch',initial)
    # Switching has no correctness gate: an unfinished first item can be left.
    last=units[-1]
    act(store,'batch',[('batch.open',last['id'],'',[])]+item_reference(last['state'],variant),'last')
    assert not v2.evaluate(initial,store.snapshot('batch'),variant,store.events('batch'))['success']
    saved_last=deepcopy(store.snapshot('batch'))
    # Visit and finish the other two in arbitrary order, preserving the last.
    for unit in units[:2]:
        act(store,'batch',[('batch.open',unit['id'],'',[])]+item_reference(unit['state'],variant),unit['id'])
    final=ApplicationStore(tmp_path).snapshot('batch')
    result=v2.evaluate(initial,final,variant,store.events('batch'))
    assert result['success'],(task_id,variant,result)
    act(store,'batch',[('batch.open',last['id'],'',[])],'reopen')
    reopened=store.snapshot('batch')
    assert {k:v for k,v in reopened.items() if k!='work_batch'}=={k:v for k,v in saved_last.items() if k!='work_batch'}
    assert v2.evaluate(initial,reopened,variant,store.events('batch'))['success']
    # Deleting a prior saved result cannot be hidden by a correct current item.
    tampered=deepcopy(reopened)
    tampered['work_batch']['units'][0]['state']=deepcopy(units[0]['state'])
    assert not v2.evaluate(initial,tampered,variant,store.events('batch'))['success']
    store.initialize('batch',initial)
    assert store.snapshot('batch')==initial and store.events('batch')==[]


@pytest.mark.parametrize('task_id',sorted(TASKS))
def test_repeated_inference_requires_correct_rule_and_demo_is_unchanged(task_id,tmp_path):
    initial=v2.generate(task_id,10001,'eval')
    assert not initial.get('rule_target')
    demo=v2.generate(task_id,0,'demo')
    assert not demo.get('work_batch') and not demo.get('rule_target')
    if task_id in FOUR_OBJECTS:
        assert len(initial['items'])==4
        assert len({str(business.expected_effect(task_id,v,initial)) for v in 'ABC'})==3
    store=ApplicationStore(tmp_path);store.initialize('rules',initial)
    act(store,'rules',batch_reference(initial,'A'))
    assert v2.evaluate(initial,store.snapshot('rules'),'A',store.events('rules'))['success']
    assert not v2.evaluate(initial,store.snapshot('rules'),'B',store.events('rules'))['success']
    with pytest.raises(ValueError):
        store.mutate('rules',Mutation(epoch=0,action_id='unknown',op='batch.open',target='forged'))
