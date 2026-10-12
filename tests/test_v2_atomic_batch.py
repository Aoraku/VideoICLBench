"""One persistent native environment; independent objects and partial outcomes."""
from copy import deepcopy
import pytest
from vic import business, v2
from vic.schemas import Mutation
from vic.v2_atomic import TASKS, MULTI_OBJECT_TASKS, TEXT_OBJECT_TASKS
from vic_apps.store import ApplicationStore
from test_applications import reference


def item_reference(state, variant, delivery=True):
    actions=reference(state,variant)
    t=state['task_id']
    if delivery and t in (10,27,59):
        if t==59: actions.append(('answer.submit','target','',[]))
        else: actions.append(('shortcut.add' if t==10 else 'favorite.add',business.expected_effect(t,variant,state)['selection'][0],'',[]))
    return actions


def batch_reference(state,variant,delivery=True):
    """Shared test helper; each action addresses a real object in one database."""
    if state.get('board_documents'):
        from vic_apps.board_collection import project
        return [('board.'+op,key,value,[target] if target else []) for key in state['board_documents'] for op,target,value,ids in item_reference(project(state,key),variant,delivery)]
    if not state.get('atomic_inputs'): return item_reference(state,variant,delivery)
    actions=[];t=state['task_id']
    for entry in state['atomic_inputs']:
        sample={**state,'source':entry['source'],'items':[x for x in state['items'] if x['id'] in entry['item_ids']]}
        if t in TEXT_OBJECT_TASKS:
            actions.append(('save',entry['id'],business.transform(t,'ABC'.index(variant),sample),[]))
            if t==59 and delivery: actions.append(('answer.submit',entry['id'],'',[]))
        elif t==39:
            actions.extend(('label',k,v,[]) for k,v in business.expected_effect(t,variant,sample)['labels'].items() if v)
        elif delivery:
            actions.append(('shortcut.add' if t==10 else 'favorite.add',business.expected_effect(t,variant,sample)['selection'][0],'',[]))
    return actions


def act(store,run,actions,prefix='step'):
    for index,(op,key,value,ids) in enumerate(actions):
        store.mutate(run,Mutation(epoch=0,action_id=f'{prefix}-{index}',op=op,target=key,value=value,ids=ids))


@pytest.mark.parametrize('task_id', sorted(MULTI_OBJECT_TASKS))
@pytest.mark.parametrize('variant', list('ABC'))
def test_shared_environment_persists_every_object(task_id,variant,tmp_path):
    initial=v2.generate(task_id,10001,'eval')
    assert 'work_batch' not in initial
    assert len(initial['atomic_inputs'])==3
    assert all('state' not in e for e in initial['atomic_inputs'])
    store=ApplicationStore(tmp_path);store.initialize('shared',initial)
    actions=batch_reference(initial,variant)
    # Finish the last object first, then the rest. No open/switch mutation.
    act(store,'shared',actions[-2:] if task_id==59 else actions[-1:],'last')
    partial=v2.evaluate(initial,store.snapshot('shared'),variant,store.events('shared'))
    assert not partial['success'] and partial['completion']<1
    # For answer.submit the last file must already be saved.
    store.initialize('shared',initial)
    act(store,'shared',actions)
    final=ApplicationStore(tmp_path).snapshot('shared')
    result=v2.evaluate(initial,final,variant,store.events('shared'))
    assert result['success'],(task_id,variant,result)
    assert not any(e['op']=='batch.open' for e in store.events('shared'))
    assert final['atomic_inputs']==initial['atomic_inputs']
    tampered=deepcopy(final);tampered['domain']['objects'][initial['items'][0]['id']]['name']='unexpected edit'
    assert not v2.evaluate(initial,tampered,variant,store.events('shared'))['success']
    with pytest.raises(ValueError):act(store,'shared',[('batch.open','work-2','',[])],'switch')
    store.initialize('shared',initial)
    assert store.snapshot('shared')==initial and store.events('shared')==[]


@pytest.mark.parametrize('task_id',sorted(TASKS))
def test_correct_relation_and_unchanged_demo(task_id,tmp_path):
    initial=v2.generate(task_id,10001,'eval')
    demo=v2.generate(task_id,0,'demo')
    assert not initial.get('work_batch') and not demo.get('atomic_inputs')
    store=ApplicationStore(tmp_path);store.initialize('rules',initial)
    act(store,'rules',batch_reference(initial,'A'))
    assert v2.evaluate(initial,store.snapshot('rules'),'A',store.events('rules'))['success']
    assert not v2.evaluate(initial,store.snapshot('rules'),'B',store.events('rules'))['success']


@pytest.mark.parametrize('task_id',[66,67,68,70,71,72,73,75])
@pytest.mark.parametrize('variant',list('ABC'))
def test_three_board_documents_are_one_persistent_workspace(task_id,variant,tmp_path):
    initial=v2.generate(task_id,10001,'eval')
    assert len(initial['board_documents'])==3 and 'work_batch' not in initial
    assert len({str(x['board']) for x in initial['board_documents'].values()})==3
    store=ApplicationStore(tmp_path);store.initialize('boards',initial)
    actions=batch_reference(initial,variant)
    act(store,'boards',[a for a in actions if a[1]=='board-3'],'last')
    partial=v2.evaluate(initial,store.snapshot('boards'),variant,store.events('boards'))
    assert partial['completion']==pytest.approx(1/3) and not partial['success']
    before=store.snapshot('boards')['board_documents']
    act(store,'boards',[('board.view','board-2','',[])],'view')
    assert store.snapshot('boards')['board_documents']==before
    act(store,'boards',[a for a in actions if a[1]!='board-3'],'others')
    assert v2.evaluate(initial,store.snapshot('boards'),variant,store.events('boards'))['success']
    assert ApplicationStore(tmp_path).snapshot('boards')==store.snapshot('boards')
