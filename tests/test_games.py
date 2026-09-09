import copy
import pytest
from vic.games import (
    apply,
    evaluate,
    expected,
    fixture,
    move_2048,
    reversi_moves,
    reversi_move,
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


def test_sudoku_row_column_and_box():
    board = [[0] * 9 for _ in range(9)]
    board[0][2] = 1
    board[2][0] = 2
    board[1][1] = 3
    assert sudoku_candidates(board, 0, 0) == [4, 5, 6, 7, 8, 9]


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
    if task_id != 69:
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
                assert not evaluate(state, final, wrong, events)["success"]
