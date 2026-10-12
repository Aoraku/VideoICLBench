"""Several saved board documents in one application database, addressed by id."""
from copy import deepcopy
from vic import games

FIELDS = ('seed','selection','marks','moves','stopped','score','target_number','target_score','game','board','candidates','color','candidate_values')


def project(state, key):
    record=state['board_documents'].get(key)
    if record is None:raise ValueError('Unknown board document')
    return {**{k:deepcopy(v) for k,v in state.items() if k not in ('board_documents','board_view')},**deepcopy(record)}


def apply(state,op,target,value,ids):
    out=deepcopy(state)
    if op=='board.view':
        if target not in out['board_documents']:raise ValueError('Unknown board document')
        out['board_view']=target
        return out
    if not op.startswith('board.'):raise ValueError('Choose a board document')
    result=games.apply(project(state,target),op.removeprefix('board.'),ids[0] if ids else '',value)
    out['board_documents'][target]={k:result[k] for k in FIELDS if k in result}
    return out
