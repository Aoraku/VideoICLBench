"""Pure board transitions shared by game clients and private evaluators."""

from copy import deepcopy
from functools import lru_cache
import random
import json

DIRECTIONS = ("left", "up", "right", "down")


def move_2048(board, direction):
    if direction not in DIRECTIONS:
        raise ValueError("Unknown direction")
    n = len(board)
    out = deepcopy(board)
    merges = score = 0
    for k in range(n):
        coords = (
            [(k, i) for i in range(n)]
            if direction == "left"
            else [(k, i) for i in reversed(range(n))]
            if direction == "right"
            else [(i, k) for i in range(n)]
            if direction == "up"
            else [(i, k) for i in reversed(range(n))]
        )
        values = [board[r][c] for r, c in coords if board[r][c]]
        merged = []
        i = 0
        while i < len(values):
            if i + 1 < len(values) and values[i] == values[i + 1]:
                merged.append(values[i] * 2)
                score += values[i] * 2
                merges += 1
                i += 2
            else:
                merged.append(values[i])
                i += 1
        merged.extend([0] * (n - len(merged)))
        for (r, c), v in zip(coords, merged):
            out[r][c] = v
    return out, {
        "changed": out != board,
        "merges": merges,
        "score": score,
        "empty": sum(x == 0 for row in out for x in row),
    }


def spawn_2048(board, seed, step):
    board = deepcopy(board)
    empty = [
        (r, c) for r in range(len(board)) for c in range(len(board)) if board[r][c] == 0
    ]
    if empty:
        rng = random.Random(seed * 65537 + step)
        r, c = rng.choice(empty)
        board[r][c] = 4 if rng.random() < 0.1 else 2
    return board


def sudoku_candidates(board, r, c):
    if board[r][c]:
        return []
    used = (
        set(board[r])
        | {row[c] for row in board}
        | {
            board[i][j]
            for i in range(r // 3 * 3, r // 3 * 3 + 3)
            for j in range(c // 3 * 3, c // 3 * 3 + 3)
        }
    )
    return sorted(set(range(1, 10)) - used)


def gomoku_run(board, r, c, color, dr, dc):
    count = 0
    n = len(board)
    for sign in (-1, 1):
        i, j = r + dr * sign, c + dc * sign
        while 0 <= i < n and 0 <= j < n and board[i][j] == color:
            count += 1
            i += dr * sign
            j += dc * sign
    return count


def reversi_flips(board, r, c, color):
    n = len(board)
    if not (0 <= r < n and 0 <= c < n) or board[r][c]:
        return []
    result = []
    for dr, dc in [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]:
        pending = []
        i, j = r + dr, c + dc
        while 0 <= i < n and 0 <= j < n and board[i][j] == 3 - color:
            pending.append((i, j))
            i += dr
            j += dc
        if pending and 0 <= i < n and 0 <= j < n and board[i][j] == color:
            result.extend(pending)
    return result


def reversi_moves(board, color):
    return [
        (r, c)
        for r in range(len(board))
        for c in range(len(board))
        if reversi_flips(board, r, c, color)
    ]


def reversi_move(board, r, c, color):
    flips = reversi_flips(board, r, c, color)
    if not flips:
        raise ValueError("Illegal move")
    board = deepcopy(board)
    board[r][c] = color
    for i, j in flips:
        board[i][j] = color
    return board


def mine_clues(mines):
    n = len(mines)
    return [
        [
            -1
            if mines[r][c]
            else sum(
                mines[i][j]
                for i in range(max(0, r - 1), min(n, r + 2))
                for j in range(max(0, c - 1), min(n, c + 2))
            )
            for c in range(n)
        ]
        for r in range(n)
    ]


@lru_cache(maxsize=512)
def _mines_layout(task_id, seed):
    """Server-only layout; unrevealed clues never enter the public fixture."""
    rng = random.Random(seed)
    for attempt in range(200):
        mines = [[False] * 8 for _ in range(8)]
        for r, c in rng.sample([(r, c) for r in range(8) for c in range(8)], 10):
            mines[r][c] = True
        clues = mine_clues(mines)
        safe = [(r, c) for r in range(8) for c in range(8) if not mines[r][c]]
        hidden = set(rng.sample(safe, 18))
        board = [[None if (r,c) in hidden or mines[r][c] else clues[r][c]
                  for c in range(8)] for r in range(8)]
        if task_id == 72:
            quadrants = [[p for p in sorted(hidden) if p[0]//4 == r and p[1]//4 == c]
                         for r in range(2) for c in range(2)]
            if any(len(points) < 2 for points in quadrants):
                continue
            candidates = [p for points in quadrants for p in rng.sample(points, 2)]
            rng.shuffle(candidates)
        else:
            candidates = rng.sample([(r,c) for r in range(8) for c in range(8)
                                     if board[r][c] is not None], 6)
        state = dict(board=board, candidates=candidates, color=1)
        signatures = [expected(task_id, v, state) for v in 'ABC']
        if all(s is not None and s != [] for s in signatures) and len(set(map(repr,signatures))) == 3:
            return board, candidates, clues
    raise ValueError('No discriminative mines fixture')


def fixture(task_id, seed):
    rng = random.Random(seed)
    base = dict(
        task_id=task_id,
        seed=seed,
        selection=None,
        marks=[],
        moves=[],
        stopped=False,
        score=0,
        target_number=32,
        target_score=64,
    )
    if task_id in (66, 67):
        board = [[0] * 15 for _ in range(15)]
        if task_id == 66:
            for c in (1, 2, 3):
                board[1][c] = 1
            for c in (1, 2):
                board[5][c] = 1
            for c in (1, 2, 3, 4):
                board[10][c] = 2
            board[10][0] = 1  # Close the far end; the candidate blocks the only winning end.
            candidates = [(1, 4), (5, 3), (10, 5)]
        else:
            for c in (1, 2, 3):
                board[1][c] = 1
            for r in (8, 9, 10):
                board[r][12] = 1
            candidates = [(1, 4), (11, 12), (rng.randrange(5, 10), rng.randrange(5, 10))]
        # Vary spatial positions and distractors across demonstration/evaluation seeds.
        # Reflect/rotate the full board so row/column rules remain visually grounded.
        # Six consecutive teaching seeds must cover both sides of the board;
        # random orientation alone can make every vertical answer rightmost.
        rotations = seed % 4 if task_id == 67 else rng.randrange(4)
        for _ in range(rotations):
            board = [list(row) for row in zip(*board[::-1])]
            candidates = [(c, 14 - r) for r, c in candidates]
        reflect = (seed // 4) % 2 == 1 if task_id == 67 else rng.choice([True, False])
        if reflect:
            board = [row[::-1] for row in board]
            candidates = [(r, 14 - c) for r, c in candidates]
        available = [
            (r, c)
            for r in range(15)
            for c in range(15)
            if not board[r][c]
            and all(max(abs(r - a), abs(c - b)) > 1 for a, b in candidates)
        ]
        for r, c in rng.sample(available, 12):
            stone = rng.choice([1, 2])
            # A practice position must still be in play. Background stones can
            # otherwise extend a three-stone example into an existing five.
            if any(gomoku_run(board, r, c, stone, dr, dc) >= 4
                   for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1))):
                continue
            board[r][c] = stone
        state = dict(**base, game="gomoku", board=board, candidates=candidates, color=1)
        outcomes = [expected(task_id, v, state) for v in "ABC"]
        if not all(outcomes) or len(set(map(repr, outcomes))) != 3:
            return fixture(task_id, seed + 104729) | {"seed": seed}
        return state
    if task_id in (68, 69):
        for attempt in range(1000):
            board = [
                [rng.choice([0, 0, 2, 2, 4, 8, 16]) for _ in range(4)] for _ in range(4)
            ]
            state = dict(**base, game="2048", board=board, candidates=[], color=1)
            if task_id == 69:
                if sum(bool(x) for row in board for x in row) < 12 and stopping_paths(state):
                    return state
            elif all(expected(68, v, state) for v in "ABC"):
                return state
        raise ValueError("No discriminative 2048 fixture")
    if task_id in (70, 71):
        solved = [[(r * 3 + r // 3 + c) % 9 + 1 for c in range(9)] for r in range(9)]
        for attempt in range(3000):
            board = deepcopy(solved)
            for r, c in rng.sample([(r, c) for r in range(9) for c in range(1, 9)], 48):
                board[r][c] = 0
            candidates = [(r, c) for r in range(9) for c in range(9) if not board[r][c]]
            if task_id == 71:
                candidates = [
                    (r, c)
                    for r, c in candidates
                    if len(sudoku_candidates(board, r, c)) >= 3
                    and len(sudoku_candidates(board, r, c)) % 2 == 1
                ]
                if not candidates:
                    continue
                candidates = [rng.choice(candidates)]
            else:
                candidates = rng.sample(candidates, 6)
            state = dict(
                **base, game="sudoku", board=board, candidates=candidates, color=1
            )
            signatures = [expected(task_id, v, state) for v in "ABC"]
            if all(signatures) and len(set(repr(s) for s in signatures)) == 3:
                return state
        raise ValueError("No discriminative Sudoku fixture")
    if task_id in (72, 73):
        board, candidates, _ = _mines_layout(task_id, seed)
        return dict(**base, game='mines', board=deepcopy(board),
                    candidates=deepcopy(candidates), color=1)
    if task_id in (74, 75):
        minimum_flips = (1, 2, 3, 1, 3, 2)[seed % 6]
        for attempt in range(3000 if task_id == 74 else 200):
            board = [[0] * 8 for _ in range(8)]
            board[3][3] = board[4][4] = 2
            board[3][4] = board[4][3] = 1
            color = 1
            for _ in range(rng.randrange(36, 59) if task_id == 74 else rng.randrange(18, 48)):
                moves = reversi_moves(board, color)
                if moves:
                    board = reversi_move(board, *rng.choice(moves), color)
                color = 3 - color
            state = dict(
                **{**base, "color": color},
                game="reversi",
                board=board,
                candidates=reversi_moves(board, color),
            )
            # Use reachable positions with different relative minima. Otherwise
            # "fewest flips" is indistinguishable from "flip exactly one".
            if task_id == 74 and (
                len(state["candidates"]) < 3
                or min(len(reversi_flips(board, *p, color))
                       for p in state["candidates"]) != minimum_flips
            ):
                continue
            signatures = [expected(task_id, v, state) for v in "ABC"]
            if (
                all(s is not None for s in signatures)
                and len(set(repr(s) for s in signatures)) == 3
            ):
                return state
        raise ValueError("No discriminative Reversi fixture")
    raise ValueError(task_id)


def stopping_paths(state):
    """Bounded reference solutions, never included in the public fixture."""
    found = {}
    queue = [(state["board"], 0, [])]
    visited = set()
    for depth in range(8):
        next_queue = []
        for board, score, path in queue:
            for direction in DIRECTIONS:
                changed, stats = move_2048(board, direction)
                if not stats["changed"]:
                    continue
                after = spawn_2048(changed, state["seed"], len(path))
                score2 = score + stats["score"]
                path2 = path + [direction]
                conditions = [
                    any(x == state["target_number"] for row in after for x in row),
                    score2 >= state["target_score"],
                    sum(bool(x) for row in after for x in row) >= 12,
                ]
                for v, met in zip("ABC", conditions):
                    if met and v not in found:
                        found[v] = path2
                if len(found) == 3:
                    return found
                signature = (tuple(tuple(r) for r in after), score2, len(path2))
                if signature not in visited:
                    visited.add(signature)
                    next_queue.append((after, score2, path2))
        queue = next_queue[:4000]
    return {}


def best_2048_directions(state, variant):
    """All legal maximizers; opposite directions can legitimately tie."""
    options = []
    for direction in DIRECTIONS:
        board, stats = move_2048(state['board'], direction)
        if not stats['changed']:
            continue
        if variant == 'C':
            maximum = max(map(max, board))
            last = len(board) - 1
            value = int(any(board[r][c] == maximum for r,c in ((0,0),(0,last),(last,0),(last,last))))
        else:
            value = stats[{'A':'merges','B':'score'}[variant]]
        options.append((direction, value))
    if not options:
        return []
    maximum = max(value for _, value in options)
    return [direction for direction, value in options if value == maximum]


def expected(task_id, variant, state):
    return _expected(task_id, variant, state)


def _expected(task_id, variant, state):
    v = "ABC".index(variant)
    board = state["board"]
    points = [tuple(p) for p in state["candidates"]]
    n = len(board)
    color = state["color"]
    if task_id == 66:
        return sorted(
            (r, c)
            for r, c in points
            if max(
                gomoku_run(board, r, c, 1 if v < 2 else 2, dr, dc)
                for dr, dc in [(1, 0), (0, 1), (1, 1), (1, -1)]
            )
            == [3, 2, 4][v]
        )
    if task_id == 67:
        return (
            min(points, key=lambda p: (-gomoku_run(board, *p, color, 0, 1), p))
            if v == 0
            else min(points, key=lambda p: (-gomoku_run(board, *p, color, 1, 0), p))
            if v == 1
            else min(
                points, key=lambda p: ((p[0] - n // 2) ** 2 + (p[1] - n // 2) ** 2, p)
            )
        )
    if task_id == 68:
        choices = best_2048_directions(state, variant)
        return choices[0] if choices else None
    if task_id == 70:
        if v < 2:
            return sorted(
                p
                for p in points
                if all(x % 2 == v for x in sudoku_candidates(board, *p))
            )
        smallest = min(len(sudoku_candidates(board, *p)) for p in points)
        return sorted(
            p for p in points if len(sudoku_candidates(board, *p)) == smallest
        )
    if task_id == 71:
        r, c = points[0]
        candidates = sudoku_candidates(board, r, c)
        return [
            candidates[0],
            candidates[-1],
            candidates[len(candidates) // 2],
        ][v]
    if task_id == 72:

        def key(p):
            r, c = p
            around = [
                board[i][j]
                for i in range(max(0, r - 1), min(n, r + 2))
                for j in range(max(0, c - 1), min(n, c + 2))
                if (i, j) != p
            ]
            return (
                [
                    sum(x for x in around if x is not None),
                    -sum(x is None for x in around),
                    r * r + c * c,
                ][v],
                p,
            )

        return min(points, key=key)
    if task_id == 73:
        return sorted(
            p
            for p in points
            if [
                board[p[0]][p[1]] == 1,
                board[p[0]][p[1]] == 2,
                p[0] in (0, n - 1) or p[1] in (0, n - 1),
            ][v]
        )
    if task_id == 74:

        def key(p):
            return (
                [
                    -len(reversi_flips(board, *p, color)),
                    min(
                        (p[0] - r) ** 2 + (p[1] - c) ** 2
                        for r, c in [(0, 0), (0, 7), (7, 0), (7, 7)]
                    ),
                    len(reversi_flips(board, *p, color)),
                ][v],
                p,
            )

        return min(points, key=key) if points else None
    if task_id == 75:
        if v == 0:
            valid = [
                p
                for p in points
                if sum(
                    x == color for row in reversi_move(board, *p, color) for x in row
                )
                > sum(
                    x == 3 - color
                    for row in reversi_move(board, *p, color)
                    for x in row
                )
            ]
            return min(valid) if valid else None
        if v == 1:
            return (
                min(
                    points,
                    key=lambda p: (
                        len(reversi_moves(reversi_move(board, *p, color), 3 - color)),
                        p,
                    ),
                )
                if points
                else None
            )
        edge = [p for p in points if p[0] in (0, 7) or p[1] in (0, 7)]
        return min(edge) if edge else None
    return None


def apply(state, op, target="", value="", ids=None):
    out = deepcopy(state)
    task_id = state["task_id"]
    if out["stopped"]:
        raise ValueError("The game task is stopped")
    if op == "stop":
        out["stopped"] = True
        return out
    if task_id in (68, 69) and op == "move":
        board, stats = move_2048(out["board"], value)
        if not stats["changed"]:
            raise ValueError("Move does not change the board")
        out["score"] += stats["score"]
        out["selection"] = value
        out["board"] = (
            spawn_2048(board, out["seed"], len(out["moves"]))
            if task_id == 69
            else board
        )
        out["moves"].append(value)
        return out
    try:
        r, c = map(int, target.split(","))
    except (ValueError, AttributeError):
        raise ValueError("A row,column target is required")
    if [r, c] not in [list(p) for p in out["candidates"]]:
        raise ValueError("Choose a highlighted candidate")
    if op == "mark" and task_id in (66, 70, 73):
        p = [r, c]
        if p in out["marks"]:
            out["marks"].remove(p)
        else:
            out["marks"].append(p)
    elif op == "choose" and task_id in (67, 72, 74, 75):
        if out["selection"] is not None:
            raise ValueError("Only one move is allowed")
        out["selection"] = [r, c]
        if task_id == 67:
            out["board"][r][c] = out["color"]
        elif task_id == 72:
            _, _, clues = _mines_layout(task_id, out['seed'])
            out['board'][r][c] = clues[r][c]
        elif task_id in (74, 75):
            out["board"] = reversi_move(out["board"], r, c, out["color"])
    elif op == "fill" and task_id == 71:
        number = int(value)
        if number not in sudoku_candidates(out["board"], r, c):
            raise ValueError("Choose a displayed candidate number")
        out["board"][r][c] = number
        out["selection"] = number
    else:
        raise ValueError("Unsupported game action")
    return out


def evaluate(initial, final, variant, events):
    id_ = initial["task_id"]
    violations = []
    replayed = deepcopy(initial)
    try:
        for event in events:
            replayed = apply(
                replayed,
                event["op"],
                event.get("target", ""),
                event.get("value", ""),
                event.get("ids"),
            )
        if json.dumps(replayed, sort_keys=True) != json.dumps(final, sort_keys=True):
            violations.append("board_does_not_match_legal_actions")
    except (ValueError, TypeError, KeyError):
        violations.append("illegal_action_sequence")
    if id_ == 69:
        replay = deepcopy(initial)
        met_at = None
        for i, e in enumerate(events):
            replay = apply(replay, e["op"], e["target"], e["value"])
            condition = [
                any(
                    x == replay["target_number"] for row in replay["board"] for x in row
                ),
                replay["score"] >= replay["target_score"],
                sum(bool(x) for row in replay["board"] for x in row) >= 12,
            ]["ABC".index(variant)]
            if condition and met_at is None:
                met_at = i
            elif met_at is not None and e["op"] != "stop":
                violations.append("continued_after_stop_condition")
        passed = met_at is not None and final["stopped"]
    else:
        wanted = expected(id_, variant, initial)
        actual = (
            sorted(tuple(p) for p in final["marks"])
            if id_ in (66, 70, 73)
            else tuple(final["selection"])
            if isinstance(final["selection"], list)
            else final["selection"]
        )
        passed = actual == wanted
        if id_ == 68:
            passed = actual in best_2048_directions(initial, variant)
            if len(final['moves']) != 1:
                passed = False
    if not events:
        violations.append("no_action")
    return dict(
        success=passed and not violations,
        completion=float(passed),
        checks=[{"id": "game_rule", "passed": passed}],
        violations=sorted(set(violations)),
    )
