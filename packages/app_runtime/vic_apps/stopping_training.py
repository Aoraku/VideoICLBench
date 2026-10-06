"""Reachable 2048 practice with public goals and a private stopping evaluator."""
from copy import deepcopy
from functools import lru_cache
import random
from vic import games


def conditions(state):
    return dict(A=any(n==state['target_number'] for row in state['board'] for n in row),
                B=state['score']>=state['target_score'],
                C=sum(bool(n) for row in state['board'] for n in row)>=12)


def opening(seed):
    board=[[0]*4 for _ in range(4)]
    for r,c in random.Random(seed).sample([(r,c) for r in range(4) for c in range(4)],2):board[r][c]=2
    return dict(task_id=69,seed=seed,app='games',game='2048',type='A',v2_2048=True,
        board=board,color=1,candidates=[],selection=None,marks=[],moves=[],score=0,stopped=False,
        target_number=64,target_score=128,move_budget=80)


def apply(state,op,target='',value=''):
    if op.startswith('assignment.'):
        from .workset_delivery import apply as delivery_apply
        return delivery_apply(state,op,target,value)
    if op not in ('move','stop'):raise ValueError('请选择移动方向或停止操作')
    if op=='move' and len(state['moves'])>=state['move_budget']:
        raise ValueError('已达到本次练习的移动上限，请停止并保存结果，或重置练习')
    return games.apply(state,op,target,value)


@lru_cache(maxsize=512)
def reference_paths(seed):
    """Solvability certificates from ordinary legal play; never public state."""
    rng=random.Random(seed+69000);found={}
    for _ in range(2000):
        state=opening(seed);seen=set()
        for step in range(state['move_budget']):
            moves=[d for d in games.DIRECTIONS if games.move_2048(state['board'],d)[1]['changed']]
            if not moves:break
            state=apply(state,'move',value=rng.choice(moves))
            met={v for v,yes in conditions(state).items() if yes}
            new=met-seen
            if len(new)==1:
                v=next(iter(new))
                if v not in found:found[v]=list(state['moves'])
            seen|=met
            if len(found)==3:return found
    raise ValueError('无法在公开步数上限内生成三个停止条件的可完成练习')


def fixture(seed,spec):
    reference_paths(seed)
    from .workset_delivery import attach
    return attach(dict(opening(seed),title=spec['title'],
        execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery'])), spec)


def evaluate(initial,final,variant,events):
    replay=deepcopy(initial);first_met=None;violations=[]
    for index,event in enumerate(events):
        op=event.get('op')
        if first_met is not None and op not in ('stop',) and not op.startswith('assignment.'):violations.append('continued_after_stop_condition')
        try:replay=apply(replay,op,event.get('target',''),event.get('value',''))
        except (ValueError,TypeError,KeyError):
            violations.append('illegal_action_sequence');break
        if first_met is None and conditions(replay)[variant]:first_met=index
    checks=[dict(id='stopped_at_first_matching_state',passed=first_met is not None and replay['stopped'] and not violations),
            dict(id='legal_moves_within_public_budget',passed=0<len(replay['moves'])<=initial['move_budget']),
            dict(id='persisted_board_score_and_moves',passed=replay==final)]
    if initial.get('workset_delivery'):
        from .workset_delivery import checks as delivery_checks
        checks.extend(delivery_checks(initial,final,['practice-result']))
    return dict(success=all(c['passed'] for c in checks) and not violations,
        completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,
        violations=violations+[c['id'] for c in checks if not c['passed']])
