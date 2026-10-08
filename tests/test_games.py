import copy
import pytest
from vic.games import (
    apply,
    best_2048_directions,
    evaluate,
    expected,
    fixture,
    move_2048,
    reversi_moves,
    reversi_move,
    reversi_flips,
    stopping_paths,
    sudoku_candidates,
)


def test_2048_merges_once_and_scores_actual_values():
    board = [[2, 2, 2, 2], [4, 0, 4, 4], [0, 0, 0, 0], [0, 0, 0, 0]]
    left, stats = move_2048(board, "left")
    assert left[0] == [4, 4, 0, 0]
    assert left[1] == [8, 4, 0, 0]
    assert stats["merges"] == 3 and stats["score"] == 16
    assert board[0] == [2, 2, 2, 2]
    right, _ = move_2048(board, "right")
    assert right[1] == [0, 0, 4, 8]


def test_reversi_opening_and_illegal_move():
    board = [[0] * 8 for _ in range(8)]
    board[3][3] = board[4][4] = 2
    board[3][4] = board[4][3] = 1
    assert set(reversi_moves(board, 1)) == {(2, 3), (3, 2), (4, 5), (5, 4)}
    moved = reversi_move(board, 2, 3, 1)
    assert moved[3][3] == 1 and board[3][3] == 2
    with pytest.raises(ValueError):
        reversi_move(board, 0, 0, 1)


@pytest.mark.parametrize('base_seed', [0, 10, 20, 1000])
def test_reversi_relative_minima_cannot_be_replaced_by_fixed_count_or_threshold(base_seed):
    states = [fixture(74, seed) for seed in range(base_seed, base_seed + 6)]
    selected, other = [], []
    for state in states:
        board, color = state['board'], state['color']
        assert set(state['candidates']) == set(reversi_moves(board, color))
        counts = [len(reversi_flips(board, *p, color)) for p in state['candidates']]
        selected.append(min(counts))
        other.extend(n for n in counts if n != min(counts))
        assert len({expected(74, v, state) for v in 'ABC'}) == 3
        chosen = expected(74, 'C', state)
        assert len(reversi_flips(board, *chosen, color)) == min(counts)
    assert len(set(selected)) >= 3
    assert max(selected) >= min(other)


@pytest.mark.parametrize('base_seed', [0, 1, 2, 3, 10, 20, 1000, 10001])
def test_gomoku_direction_cannot_be_inferred_from_spatial_extremes(base_seed):
    states = [fixture(67, seed) for seed in range(base_seed, base_seed + 6)]
    for variant in 'AB':
        choices = [expected(67, variant, state) for state in states]
        for axis in (0, 1):
            for extreme in (min, max):
                assert any(point[axis] != extreme(p[axis] for p in state['candidates'])
                           for state, point in zip(states, choices))


def test_sudoku_row_column_and_box():
    board = [[0] * 9 for _ in range(9)]
    board[0][2] = 1
    board[2][0] = 2
    board[1][1] = 3
    assert sudoku_candidates(board, 0, 0) == [4, 5, 6, 7, 8, 9]


@pytest.mark.parametrize('seed',list(range(30))+[1000,1001,1002,10001])
def test_mines_candidates_cover_board_and_only_clicked_safe_clue_is_revealed(seed):
    from vic.games import _mines_layout
    from collections import Counter
    initial=fixture(72,seed)
    assert Counter((r//4,c//4) for r,c in initial['candidates'])=={(0,0):2,(0,1):2,(1,0):2,(1,1):2}
    # The private mine map is reconstructed only inside the server.
    _,_,clues=_mines_layout(72,seed)
    assert sum(cell==-1 for row in clues for cell in row)==10
    assert not {'clues','mines','hidden','reveals','candidate_reveals'} & initial.keys()
    for r,c in initial['candidates']:
        assert initial['board'][r][c] is None and clues[r][c]>=0
        expected_clue=sum(clues[i][j]==-1 for i in range(max(0,r-1),min(8,r+2))
                          for j in range(max(0,c-1),min(8,c+2)))
        final=apply(initial,'choose',f'{r},{c}')
        assert final['board'][r][c]==expected_clue
        assert initial['board'][r][c] is None
        assert [(i,j) for i in range(8) for j in range(8)
                if initial['board'][i][j]!=final['board'][i][j]]==[(r,c)]
        with pytest.raises(ValueError,match='Only one move'):
            apply(final,'choose',f'{r},{c}')
    # Callers cannot mutate cached layout data through a fixture.
    initial['board'][0][0]=99
    assert fixture(72,seed)['board'][0][0]!=99


def test_mines_reveal_is_checked_by_event_replay():
    initial=fixture(72,0)
    r,c=expected(72,'A',initial)
    final=apply(initial,'choose',f'{r},{c}')
    events=[dict(op='choose',target=f'{r},{c}',value='')]
    assert evaluate(initial,final,'A',events)['success']
    final['board'][r][c]+=1
    result=evaluate(initial,final,'A',events)
    assert not result['success'] and 'board_does_not_match_legal_actions' in result['violations']


@pytest.mark.parametrize("task_id", [66, 67])
def test_gomoku_demonstration_and_evaluation_boards_differ(task_id):
    examples = [fixture(task_id, seed) for seed in (0, 1, 1000, 1001, 10000, 10001)]
    assert len({repr(s["board"]) for s in examples}) == len(examples)
    assert all(expected(task_id, v, s) for s in examples for v in "ABC")


@pytest.mark.parametrize("task_id", range(66, 76))
@pytest.mark.parametrize("seed", [0, 1000, 10001])
def test_game_counterfactuals_and_reference_play(task_id, seed):
    state = fixture(task_id, seed)
    assert state == fixture(task_id, seed)
    if task_id not in (68, 69):
        assert len(set(repr(expected(task_id, v, state)) for v in "ABC")) == 3
    for v in "ABC":
        final = copy.deepcopy(state)
        events = []

        def action(op, target="", value=""):
            nonlocal final
            final = apply(final, op, target, value)
            events.append(dict(op=op, target=target, value=value))

        wanted = expected(task_id, v, state)
        if task_id in (66, 70, 73):
            for r, c in wanted:
                action("mark", f"{r},{c}")
        elif task_id in (67, 72, 74, 75):
            action("choose", f"{wanted[0]},{wanted[1]}")
        elif task_id == 68:
            action("move", value=wanted)
        elif task_id == 71:
            r, c = state["candidates"][0]
            action("fill", f"{r},{c}", str(wanted))
        else:
            for direction in stopping_paths(state)[v]:
                action("move", value=direction)
            action("stop")
        assert evaluate(state, final, v, events)["success"]
        if task_id != 69:
            for wrong in set("ABC") - {v}:
                if task_id == 68:
                    assert evaluate(state,final,wrong,events)['success'] == (wanted in best_2048_directions(state,wrong))
                elif expected(task_id, wrong, state) != wanted:
                    assert not evaluate(state, final, wrong, events)["success"]
