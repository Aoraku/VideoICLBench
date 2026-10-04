"""Repeated rule practice through native work batches and multi-object lists."""
from copy import deepcopy
from itertools import combinations
import json
from . import business, application_eval, games
from vic_apps.domain import initialize

TASKS = {1,3,4,5,10,17,19,20,21,24,25,27,36,37,39,59,62,66,67,68,70,71,72,73,75}
FOUR_OBJECTS = {5,24,25,39,62}
BATCH_TASKS = TASKS - FOUR_OBJECTS
BATCH_SIZE = 3


def _generate_item(task_id, seed, spec):
    state=business.generate(task_id,seed)
    if task_id in FOUR_OBJECTS:
        # Keep a small inference batch without collapsing the A/B/C distinction.
        for subset in combinations(state['items'],4):
            candidate=deepcopy(state)
            candidate['items']=list(subset)
            candidate['labels']={x['id']:'' for x in subset}
            candidate['order']=[x['id'] for x in subset]
            effects=[business.expected_effect(task_id,v,candidate) for v in 'ABC']
            outcomes={json.dumps(effect,sort_keys=True) for effect in effects}
            if len(outcomes)==3 and all(any(effect['labels'].values()) for effect in effects):
                state=candidate
                break
        else:
            raise ValueError('Cannot construct four informative inference objects')
    if task_id == 1:
        state['source']['text']=[f'Please confirm your workshop booking for October {seed%28+1}', 'Please review the revised delivery schedule', 'Please share feedback on the onboarding guide'][seed%3]
    elif task_id == 3:
        state['source']['text']=['Please join the product briefing at two', 'Remember to bring your badge to the library tour', 'The volunteer training starts in room five'][seed%3]
    elif task_id == 4:
        state['source']['text']=[f'Dispatch {seed%5+2} monitors to dock 3', f'Move {seed%4+3} chairs from floor 2 to floor 5', f'Prepare {seed%6+1} boxes and deliver them before 4'][seed%3]
    elif task_id == 37:
        state['source']['text']='\n'.join([['Summarize the customer interviews','Separate requests from observations','Include the next action'],['Draft the volunteer briefing','List arrival times and meeting points','Keep emergency contacts visible'],['Explain the survey findings','Preserve sample sizes','Mention the limitations']][seed%3])
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
    if task_id == 10:
        state['domain']['collections']['shortcuts']=[]
    if task_id == 37:
        state['domain']['objects']['target'].update(kind='templates',name=['客户访谈摘要','志愿者简报','调查结果说明'][seed%3],project='writing')
    return state


def _evaluate_item(initial,state,variant,events,clipboard=None):
    t=initial['task_id']
    result=application_eval.evaluate(initial,state,variant,events,clipboard)
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


# Native work items retain the full application state: messages, saved documents,
# collections and board moves can be reopened. No variant or answer lives here.
BATCH_LABELS = {
    1: ('客户通知', '分别整理并发送三位客户的通知草稿'),
    3: ('活动提醒', '分别按格式发送三场活动的提醒'),
    4: ('调货通知', '分别转换并发送三份调货通知'),
    10: ('客户沟通', '为三项客户沟通分别选择会话并加入快捷入口'),
    17: ('歌曲资料', '分别规范三首新入库歌曲的显示标题'),
    19: ('文章标题', '分别整理三篇文章标题并保留各自正文'),
    20: ('标签文字', '分别整理三篇文章的标签展示文字'),
    21: ('视频收藏夹', '分别规范三个收藏夹名称并保留成员'),
    27: ('活动选曲', '分别为三场活动选择并收藏一首歌曲'),
    36: ('博客草稿', '分别整理三篇草稿标题并保持未发布'),
    37: ('写作模板', '分别整理三份写作模板的要求格式'),
    59: ('课程答案', '分别整理三份答案并提交到各自题目'),
    66: ('五子棋棋形', '在三个不同棋形中逐一标注符合条件的候选点'),
    67: ('五子棋落点', '在三个不同棋形中分别按规则选择落点'),
    68: ('2048 方向练习', '在三个独立棋盘上分别应用一次方向规则'),
    70: ('数独候选练习', '在三个不同数独盘中标注符合条件的候选格'),
    71: ('数独填写练习', '在三个不同数独盘中分别填写指定候选格'),
    72: ('扫雷安全选点', '在三个独立训练盘中分别选择一个安全候选格'),
    73: ('扫雷线索练习', '在三个独立训练盘中标注符合条件的位置'),
    75: ('黑白棋局部练习', '在三个不同局面中分别执行一次规定的局部操作'),
}


def generate(task_id, seed, spec):
    if task_id not in BATCH_TASKS:
        return _generate_item(task_id, seed, spec)
    from .identity_context import contextualize
    label, purpose = BATCH_LABELS[task_id]
    units=[];seen_boards=set()
    for index in range(BATCH_SIZE):
        item_seed=seed + index * 104729
        for attempt in range(100):
            item=contextualize(_generate_item(task_id,item_seed+attempt,spec),'eval')
            board_key=json.dumps(item.get('board'))
            if task_id<66 or board_key not in seen_boards:
                seen_boards.add(board_key)
                break
        else:
            raise ValueError('Cannot construct three distinct training boards')
        # Each item starts at its own ordinary application home; the navigator
        # is a work queue and never grades an answer or gates movement.
        item['execution'] = dict(assignment=purpose+'。',
            instructions=f'本批共有 {BATCH_SIZE} 项。当前为第 {index+1} 项：按视频规则处理当前资料，在应用中保存或提交后，可从工作清单切换并随时返回修改。',
            delivery=purpose+'；三项结果分别保存且互不覆盖。')
        title=f'{label} {index+1}'
        if item.get('source',{}).get('text') and task_id<66:
            excerpt=item['source']['text'].splitlines()[0]
            title+=' · '+excerpt[:48]
        units.append(dict(id=f'work-{index+1}',title=title,state=item))
    current=deepcopy(units[0]['state'])
    current['work_batch']=dict(title=purpose,active='work-1',units=units)
    # The application database and HTTP boundary use JSON arrays for coordinates.
    return json.loads(json.dumps(current,ensure_ascii=False))


def _batch_states(state):
    batch=state['work_batch']
    active={k:deepcopy(v) for k,v in state.items() if k!='work_batch'}
    return {unit['id']:active if unit['id']==batch['active'] else unit['state'] for unit in batch['units']}


def evaluate(initial,state,variant,events,clipboard=None):
    if not initial.get('work_batch'):
        return _evaluate_item(initial,state,variant,events,clipboard)
    before=initial['work_batch'];after=state.get('work_batch',{})
    ids=[unit['id'] for unit in before['units']]
    if ([u.get('id') for u in after.get('units',[])]!=ids or after.get('active') not in ids):
        return dict(success=False,completion=0,checks=[dict(id='work_batch_integrity',passed=False)],violations=['work_batch_integrity'])
    active=before['active'];by_item={key:[] for key in ids}
    for event in events:
        if event['op']=='batch.open':
            if event.get('target') in by_item:active=event['target']
        else:by_item[active].append(event)
    actual=_batch_states(state);checks=[];violations=[]
    for unit in before['units']:
        result=_evaluate_item(unit['state'],actual[unit['id']],variant,by_item[unit['id']],clipboard)
        checks.extend(dict(id=unit['id']+':'+c['id'],passed=c['passed']) for c in result['checks'])
        # Some legacy evaluators attach no_action only to violations. Keep it
        # visible so skipping an entire work item cannot produce full credit.
        checks.append(dict(id=unit['id']+':recorded_result',passed=result['success']))
        violations.extend(unit['id']+':'+v for v in result['violations'])
    return dict(success=all(c['passed'] for c in checks) and not violations,
                completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=violations)
