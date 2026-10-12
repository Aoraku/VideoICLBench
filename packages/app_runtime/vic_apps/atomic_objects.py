"""Ordinary edits to multiple objects in a single persistent application."""
from copy import deepcopy
from .domain import SAVE_FIELD


def apply(state, op, target, value, ids):
    state = deepcopy(state); d = state['domain']; t = state['task_id']
    entries = {x['id']:x for x in state['atomic_inputs']}
    objects = d['objects']
    if op == 'save' and target in entries and t in (1,3,4,17,19,20,21,36,37,59):
        if t in (1,3,4):
            d['messages'].append(dict(id=f'message-{len(d["messages"])+1}',sender='self',recipient=target,body=value,reference=None,attachment=None))
        else:
            objects[target][SAVE_FIELD[t]]=value
        state['outputs'][target]=value
    elif op == 'label' and t==39 and target in objects and value in ['', *state['options']]:
        objects[target]['label']=value;state['labels'][target]=value
    elif op in ('shortcut.add','shortcut.remove','favorite.add','favorite.remove') and t in (10,27) and target in objects:
        expected='shortcut.' if t==10 else 'favorite.'
        if not op.startswith(expected): raise ValueError('操作与应用不匹配')
        collection=d['collections']['shortcuts' if t==10 else 'favorites']
        if op.endswith('.add') and target not in collection: collection.append(target)
        if op.endswith('.remove') and target in collection: collection.remove(target)
    elif op == 'select' and t in (10,27) and len(ids)==1 and ids[0] in objects:
        state['selection']=ids
        d['settings']['conversation' if t==10 else 'playing_song']=ids
    elif op=='answer.submit' and t==59 and target in entries:
        text=state['outputs'].get(target)
        if text is None or text != objects[target]['text']: raise ValueError('请先保存答案')
        d['artifacts']=[a for a in d['artifacts'] if a.get('target')!=target]
        d['artifacts'].append(dict(kind='answer_submission',problem=entries[target]['source']['answer_problem']['number'],target=target,body=text,id='answer-'+target))
    else:
        raise ValueError('请选择有效对象和操作')
    return state
