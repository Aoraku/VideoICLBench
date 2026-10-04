"""Six-turn Reversi practice against a public, deterministic opponent."""
from copy import deepcopy
import random
from vic.games import reversi_moves, reversi_move, expected


def apply(state, op, target='', value=''):
    if op.startswith('assignment.'):
        from .workset_delivery import apply as delivery_apply
        return delivery_apply(state,op,target,value)
    if op!='choose' or state['stopped']:
        raise ValueError('请选择本回合的合法落点')
    try:
        point=tuple(map(int,target.split(',')))
    except (ValueError,AttributeError):
        raise ValueError('需要行、列坐标')
    if point not in [tuple(p) for p in reversi_moves(state['board'],state['color'])]:
        raise ValueError('此处不是合法落点')
    out=deepcopy(state);color=state['color']
    out['board']=reversi_move(out['board'],*point,color)
    turn=dict(turn=len(out['turns'])+1,player=list(point),opponent=[])
    # Public opponent policy: first legal square in row/column order. If the
    # player must pass, the opponent continues until the player can move again.
    while True:
        legal=reversi_moves(out['board'],3-color)
        if legal:
            move=min(legal)
            out['board']=reversi_move(out['board'],*move,3-color)
            turn['opponent'].append(list(move))
        player_moves=reversi_moves(out['board'],color)
        if player_moves or not legal:break
    out['turns'].append(turn)
    out['selection']=list(point)
    out['candidates']=[list(p) for p in player_moves]
    out['stopped']=len(out['turns'])>=out['required_turns'] or not player_moves
    return out


def fixture(seed,spec):
    rng=random.Random(seed)
    for attempt in range(400):
        board=[[0]*8 for _ in range(8)]
        board[3][3]=board[4][4]=2;board[3][4]=board[4][3]=1
        color=1
        # Reach a varied position by legal play from the standard opening.
        for _ in range(rng.randrange(10,19)):
            moves=reversi_moves(board,color)
            if moves:board=reversi_move(board,*rng.choice(moves),color)
            color=3-color
        state=dict(task_id=74,seed=seed,app='games',game='reversi',type='S',
            title=spec['title'],v2_reversi=True,board=board,color=color,
            candidates=[list(p) for p in reversi_moves(board,color)],selection=None,
            marks=[],moves=[],score=0,stopped=False,turns=[],required_turns=6,
            execution=dict(assignment=spec['assignment'],delivery=spec['delivery'],
                instructions=spec['inference']['instructions']),
            opponent_policy='对手每次选择按行号、列号排列最靠前的合法位置。无合法落点时自动跳过该方；完成六个己方回合即结束。')
        if len({expected(74,v,state) for v in 'ABC'})!=3:continue
        valid=True
        for variant in 'ABC':
            probe=deepcopy(state)
            for _ in range(6):
                chosen=expected(74,variant,probe)
                if probe['stopped'] or chosen is None:
                    valid=False;break
                probe=apply(probe,'choose',','.join(map(str,chosen)))
            if not valid:break
        if valid:
            from .workset_delivery import attach
            return attach(state)
    raise ValueError('无法生成三个规则都可完成六回合的棋局')


def evaluate(initial,final,variant,events):
    replay=deepcopy(initial);checks=[];violations=[]
    for index,event in enumerate(events):
        try:
            if event.get('op','').startswith('assignment.'):
                replay=apply(replay,event['op'],event.get('target',''),event.get('value',''))
                continue
            wanted=expected(74,variant,replay)
            actual=tuple(map(int,event.get('target','').split(',')))
            checks.append(dict(id=f'turn:{index+1}:rule',passed=actual==wanted))
            replay=apply(replay,event['op'],event.get('target',''),event.get('value',''))
        except (ValueError,TypeError,KeyError):
            violations.append('illegal_action_sequence');break
    checks.extend([dict(id='six_player_turns',passed=len(final['turns'])==6 and final['stopped']),
                   dict(id='persisted_game_matches_moves',passed=replay==final)])
    if initial.get('workset_delivery'):
        from .workset_delivery import checks as delivery_checks
        checks.extend(delivery_checks(initial,final,['practice-result']))
    return dict(success=all(c['passed'] for c in checks) and not violations,
                completion=sum(c['passed'] for c in checks)/len(checks),
                checks=checks,violations=violations+[c['id'] for c in checks if not c['passed']])
