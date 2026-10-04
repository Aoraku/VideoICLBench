"""Native application delivery commands; these never know which rule was taught."""
from copy import deepcopy

COMMANDS={'shortcut.add','shortcut.remove','favorite.add','favorite.remove','answer.submit','review.confirm'}


def apply(state,op,target,value):
    if not state.get('v2_atomic'):
        raise ValueError('此操作不适用于本环境')
    state=deepcopy(state);t=state['task_id']
    if op == 'review.confirm':
        if not state.get('rule_target') or target != state['rule_target']:
            raise ValueError('请确认本次指定的核验对象')
        state['reviewed_target'] = target
        return state
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
