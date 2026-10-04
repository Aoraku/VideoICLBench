"""Native application delivery commands; these never know which rule was taught."""
from copy import deepcopy

COMMANDS={'shortcut.add','shortcut.remove','favorite.add','favorite.remove','answer.submit','batch.open'}


def apply(state,op,target,value):
    if not state.get('v2_atomic'):
        raise ValueError('此操作不适用于本环境')
    state=deepcopy(state);t=state['task_id']
    if op == 'batch.open':
        batch=state.get('work_batch')
        if not batch or value or target not in {u['id'] for u in batch['units']}:
            raise ValueError('请选择工作清单中的项目')
        active=next(u for u in batch['units'] if u['id']==batch['active'])
        active['state']={k:deepcopy(v) for k,v in state.items() if k!='work_batch'}
        selected=next(u for u in batch['units'] if u['id']==target)
        following=deepcopy(selected['state'])
        batch['active']=target
        following['work_batch']=batch
        return following
    d=state['domain']
    if op in ('shortcut.add','shortcut.remove','favorite.add','favorite.remove'):
        is_shortcut=op.startswith('shortcut.')
        if t != (10 if is_shortcut else 27) or target not in {x['id'] for x in state['items']}:
            raise ValueError('请选择有效对象')
        collection=d['collections']['shortcuts' if is_shortcut else 'favorites']
        if op.endswith('.add'):
            if target not in collection:collection.append(target)
            state['selection']=[target]
            d['settings']['conversation' if is_shortcut else 'playing_song']=[target]
        elif target in collection:
            collection.remove(target)
    elif op=='answer.submit' and t==59 and target=='target':
        text=d['objects']['target'].get('text','')
        if not text or state['outputs'].get('target')!=text:
            raise ValueError('请先保存答案，再提交')
        records=[a for a in d['artifacts'] if a.get('kind')!='answer_submission']
        records.append(dict(kind='answer_submission',problem=state['source']['answer_problem']['number'],
                            target='target',body=text,id='answer-1'))
        d['artifacts']=records
    else:
        raise ValueError('此操作不适用于本任务')
    return state
