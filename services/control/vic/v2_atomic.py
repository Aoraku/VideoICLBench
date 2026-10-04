"""Small, purposeful v2 tasks in the original application surfaces."""
from copy import deepcopy
from itertools import combinations
import json
from . import business, application_eval, games
from vic_apps.domain import initialize

TASKS = {1,3,4,5,10,17,19,20,21,24,25,27,36,37,39,59,62,66,67,68,70,71,72,73,75}
FOUR_OBJECTS = {5,24,25,39,62}
SINGLE_REVIEW = FOUR_OBJECTS | {66,70,73}


def generate(task_id, seed, spec):
    state=business.generate(task_id,seed)
    if task_id in FOUR_OBJECTS:
        # Keep a small inference batch without collapsing the A/B/C distinction.
        for subset in combinations(state['items'],4):
            candidate=deepcopy(state)
            candidate['items']=list(subset)
            candidate['labels']={x['id']:'' for x in subset}
            candidate['order']=[x['id'] for x in subset]
            outcomes={json.dumps(business.expected_effect(task_id,v,candidate),sort_keys=True) for v in 'ABC'}
            if len(outcomes)==3:
                state=candidate
                break
        else:
            raise ValueError('Cannot construct four informative inference objects')
    if task_id == 1:
        state['source']['text']=f'Please confirm the Riverside launch on day {seed%28+1}'
    elif task_id == 3:
        state['source']['text']=f'Please join the project briefing on October {seed%28+1}'
    elif task_id == 4:
        state['source']['text']=f'Dispatch {seed%5+2} units to dock {seed%3+1}'
    elif task_id == 37:
        state['source']['text']='\n'.join([f'Summarize the October {seed%28+1} research report','Use short sentences','Explain the result','Keep the original section order'])
    elif task_id == 27:
        for item in state['items']:
            item['name']='精选 · '+item['name']
        state['source']['search_keyword']='精选'
        state['source']['collection_name']='活动备选歌曲'
    if task_id == 59:
        state['source']['answer_problem']={key:state['items'][0][key] for key in ('number','name')}
    state=initialize(state)
    state['v2_atomic']=True
    state['execution']=dict(assignment=spec['assignment'],delivery=spec['delivery'],instructions=spec['inference']['instructions'])
    if task_id in SINGLE_REVIEW:
        # One application of the learned predicate. Context objects remain
        # available for comparison, but are not additional classification work.
        if task_id < 66:
            candidates = state['items']
            if task_id == 5:
                candidates = [x for x in candidates if '?' in x['text'] or '？' in x['text']]
            target = candidates[seed % len(candidates)]
            state['rule_target'] = target['id']
            identity = (f"题号 {target['number']} · " if task_id == 62 else '') + target['name']
        else:
            row, col = state['candidates'][seed % len(state['candidates'])]
            state['rule_target'] = f'{row},{col}'
            identity = f'第 {row + 1} 行、第 {col + 1} 列'
        state['reviewed_target'] = None
        state['review_target_label'] = identity
        state['review_instructions'] = f'本次只核验「{identity}」。符合视频条件时标注，不符合时保持未标注；其他对象仅供比较，请勿修改。完成判断后确认本条核验。'
    if task_id == 10:
        state['domain']['collections']['shortcuts']=[]
    if task_id == 37:
        state['domain']['objects']['target'].update(kind='templates',name='研究报告摘要',project='research')
    return state


def evaluate(initial,state,variant,events,clipboard=None):
    t=initial['task_id']
    result=application_eval.evaluate(initial,state,variant,events,clipboard)
    if initial.get('rule_target'):
        confirmed = state.get('reviewed_target') == initial['rule_target']
        result['checks'].append(dict(id='single_target_review_confirmed',passed=confirmed))
        result['success'] = result['success'] and confirmed
        result['completion'] = sum(c['passed'] for c in result['checks']) / len(result['checks'])
        if not confirmed:
            result['violations'].append('请确认本条核验结果')
    if t == 75:
        # Several legal moves can satisfy the stated local condition.
        points=[tuple(p) for p in initial['candidates']]
        board,color=initial['board'],initial['color']
        if variant=='A':
            valid=[p for p in points if sum(x==color for row in games.reversi_move(board,*p,color) for x in row) > sum(x==3-color for row in games.reversi_move(board,*p,color) for x in row)]
        elif variant=='B':
            counts={p:len(games.reversi_moves(games.reversi_move(board,*p,color),3-color)) for p in points}
            valid=[p for p in points if counts[p]==min(counts.values())]
        else:
            valid=[p for p in points if p[0] in (0,len(board)-1) or p[1] in (0,len(board)-1)]
        passed=state['selection'] is not None and tuple(state['selection']) in valid
        result.update(checks=[dict(id='game_rule',passed=passed)],success=passed and not result['violations'],completion=float(passed))
    if t not in (10,27,59):
        return result
    # Evaluate the original rule and the actual additional delivery independently.
    normal=deepcopy(state)
    d=normal['domain']
    checks=[]
    if t in (10,27):
        wanted=business.expected_effect(t,variant,initial)['selection']
        collection='shortcuts' if t==10 else 'favorites'
        checks.append(dict(id='delivery:'+collection,passed=sorted(d['collections'][collection])==sorted(wanted)))
        d['collections'][collection]=initial['domain']['collections'][collection]
    else:
        wanted=business.transform(t,'ABC'.index(variant),initial)
        submitted=[a for a in d['artifacts'] if a.get('kind')=='answer_submission']
        problem=initial['source']['answer_problem']['number']
        checks.append(dict(id='delivery:answer_submission',passed=len(submitted)==1 and
            submitted[0].get('problem')==problem and submitted[0].get('body')==wanted))
        d['artifacts']=[a for a in d['artifacts'] if a.get('kind')!='answer_submission']
    base=application_eval.evaluate(initial,normal,variant,events,clipboard)
    all_checks=base['checks']+checks
    return dict(success=all(c['passed'] for c in all_checks) and not base['violations'],
                completion=sum(c['passed'] for c in all_checks)/len(all_checks),checks=all_checks,
                violations=base['violations']+[c['id'] for c in checks if not c['passed']])
