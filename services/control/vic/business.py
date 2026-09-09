"""Deterministic task workspaces. No private rule is present in workspace state.

The imported native applications are separate deployment targets. These workspaces
are an executable development surface, not a claim of native-app certification.
"""

import ast
import copy
import hashlib
import json
import random
import re
from .catalog import task

LABELS = {
    5: ["蓝色", "红色", "绿色"],
    6: ["甲", "乙"],
    7: ["高优先级"],
    8: ["大型"],
    22: ["长"],
    23: ["数据"],
    24: ["甲"],
    25: ["短"],
    26: ["推荐"],
    38: ["长文"],
    39: ["事实"],
    47: ["快"],
    48: ["优选"],
    49: ["常规"],
    50: ["重点"],
    61: ["绿"],
    62: ["难"],
}
OPS = {
    13: ["转发", "收藏", "归档"],
    14: ["归档", "置顶", "静音"],
    16: ["已读", "星标", "回复"],
    32: ["加入列表甲"],
    33: ["已读", "收藏", "隐藏"],
    34: ["移入历史", "收藏", "删除"],
    42: ["发布"],
    43: ["检查", "保存", "复制", "发送"],
    54: ["确认预订"],
    55: ["加入购物车", "移出购物车", "收藏"],
    56: ["转账"],
    57: ["开启提醒"],
    65: ["本地检查", "提交"],
}
SINGLE = {7, 8, 9, 10, 11, 15, 26, 27, 29, 40, 41, 47, 50, 51, 52, 53, 61, 62, 63, 64}


def transform(id_, v, state):
    s = state["source"]
    text = s["text"]
    if id_ == 1:
        return [
            text[:1].lower() + text[1:].upper(),
            text[:1].upper() + text[1:].lower(),
            text.title(),
        ][v]
    if id_ == 2:
        return [text.replace(" ", ""), text.replace(" ", "_"), text.lower()][v]
    if id_ == 3:
        return text + [".", "!", "?"][v]
    if id_ == 4:
        words = [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
        ]
        return re.sub(
            r"\d", lambda m: [f"#{m[0]}", f"{m[0]}号", words[int(m[0])]][v], text
        )
    if id_ == 17:
        return [text.upper(), text.lower(), text[:-1].lower() + text[-1:].upper()][v]
    if id_ == 18:
        parts = [s["artist"], str(s["count"]), s["date"]]
        return "_".join(parts[v:] + parts[:v])
    if id_ == 19:
        return [re.sub(r"[^\w\s]", "", text), text + ".", s["publisher_short"] + text][
            v
        ]
    if id_ == 20:
        return ["/", "|", ","][v].join(s["tags"])
    if id_ == 21:
        return ["[" + text + "]", "(" + text + ")", "《" + text + "》"][v]
    if id_ == 36:
        return [
            text[:1].upper() + text[1:],
            text[:-1] + text[-1:].upper(),
            re.sub(r"\d", lambda m: "(" + m[0] + ")", text),
        ][v]
    if id_ == 37:
        return "\n".join(
            [f"-{x}", f"{i + 1}. {x}", f"{x};"][v]
            for i, x in enumerate(text.splitlines())
        )
    if id_ == 44:
        return [
            s["surname"] + " " + s["given_name"],
            s["surname"] + "-" + s["given_name"],
            (s["surname"] + s["given_name"]).upper(),
        ][v]
    if id_ == 45:
        return [
            f"{s['quantity']}{text}",
            f"{text}{s['quantity']}",
            f"{['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'][s['quantity']]}{text}",
        ][v]
    if id_ == 46:
        return [text[-4:], text[:4], text[:4] + "*" * (len(text) - 8) + text[-4:]][v]
    if id_ == 58:
        unit = ["  ", "    ", "\t"][v]
        return "\n".join(
            unit * ((len(line) - len(line.lstrip(" "))) // 3) + line.lstrip(" ")
            for line in text.split("\n")
        )
    if id_ == 59:
        return "\n".join(
            [x + ";", f"{i + 1}. {x}", x.replace(" ", "_")][v]
            for i, x in enumerate(text.splitlines())
        )
    if id_ == 60:
        for name in s["rename_targets"]:
            text = re.sub(
                r"\b" + re.escape(name) + r"\b",
                [f"x_{name}", f"{name}_v", name.upper()][v],
                text,
            )
        return text
    raise ValueError(f"No transform for {id_}")


def _top(items, key, reverse=False, count=1):
    return sorted(items, key=lambda x: x[key], reverse=reverse)[:count]


def targets(id_, v, items, source):
    t = source["threshold"]
    chosen = None
    if id_ == 5:
        chosen = [x for x in items if "?" in x["text"]]
    elif id_ == 6:
        chosen = [
            x
            for x in items
            if [
                len(x["name"]) % 2 == 0,
                len(x["name"]) % 2 == 1,
                bool(re.search("[aeiou]", x["name"], re.I)),
            ][v]
        ]
    elif id_ == 7:
        chosen = _top(
            items, ["unread", "unread", "timestamp"][v], [True, False, True][v]
        )
    elif id_ == 8:
        chosen = [
            x
            for x in items
            if [x["members"] > 5, x["members"] <= 5, bool(re.search(r"\d", x["name"]))][
                v
            ]
        ]
    elif id_ == 9:
        chosen = _top(
            items, ["surname", "contact_time", "unread"][v], [False, True, True][v]
        )
    elif id_ == 10:
        chosen = (
            [items[0]]
            if v == 0
            else [items[-1]]
            if v == 1
            else _top(items, "unread", True)
        )
    elif id_ == 11:
        chosen = _top(
            items, ["size", "size", "name_length"][v], [False, True, False][v]
        )
    elif id_ == 15:
        chosen = _top(items, ["name_length", "contact_time", "unread"][v], v != 0, 3)
    elif id_ == 22:
        chosen = [
            x
            for x in items
            if [x["duration"] > 240, x["duration"] <= 240, x["plays"] > t][v]
        ]
    elif id_ == 23:
        chosen = [
            x
            for x in items
            if [
                bool(re.search(r"\d", x["name"])),
                not bool(re.search(r"\d", x["name"])),
                x["publisher"] == source["publisher"],
            ][v]
        ]
    elif id_ == 24:
        chosen = [
            x
            for x in items
            if [
                x["publisher"][0].lower() in "aeiou",
                x["publisher"][0].lower() not in "aeiou",
                len(x["publisher"]) > 5,
            ][v]
        ]
    elif id_ == 25:
        chosen = [
            x
            for x in items
            if [
                x["duration"] < 600,
                x["duration"] >= 600,
                (x["duration"] // 60) % 2 == 0,
            ][v]
        ]
    elif id_ == 26:
        chosen = _top(
            items, ["rating", "rating", "comments"][v], [True, False, True][v], 2
        )
    elif id_ == 27:
        chosen = _top(
            items, ["rating", "plays", "name_length"][v], [True, False, False][v]
        )
    elif id_ == 29:
        chosen = _top(
            items, ["timestamp", "timestamp", "name_length"][v], [True, False, True][v]
        )
    elif id_ == 30:
        chosen = (
            _top(items, "tag_count", v == 0)
            if v < 2
            else [x for x in items if x["comments"] % 2 == 0]
        )
    elif id_ == 31:
        chosen = _top(
            items, ["duration", "like_rate", "timestamp"][v], [False, True, False][v]
        )
    elif id_ == 38:
        chosen = [
            x for x in items if [x["words"] > t, x["words"] <= t, "?" in x["name"]][v]
        ]
    elif id_ == 39:
        chosen = [
            x
            for x in items
            if [
                bool(re.search(r"\d", x["text"])),
                not bool(re.search(r"\d", x["text"])),
                "[" in x["text"],
            ][v]
        ]
    elif id_ == 40:
        chosen = _top(
            items, ["timestamp", "timestamp", "words"][v], [True, False, False][v]
        )
    elif id_ == 41:
        chosen = _top(
            items, ["context", "price", "name_length"][v], [True, False, False][v]
        )
    elif id_ == 47:
        chosen = _top(items, ["duration", "price", "transfers"][v])
    elif id_ == 48:
        chosen = [
            x
            for x in items
            if [x["rating"] >= t, x["sales"] >= t, x["comments"] % 2 == 0][v]
        ]
    elif id_ == 49:
        chosen = [
            x
            for x in items
            if [
                x["amount"] % 2 == 0,
                x["amount"] % 2 == 1,
                len(x["text"]) > source["text_threshold"],
            ][v]
        ]
    elif id_ == 50:
        chosen = _top(
            items, ["balance", "balance", "transactions"][v], [True, False, True][v]
        )
    elif id_ == 51:
        chosen = _top(
            items, ["price", "duration", "departure"][v], [False, False, True][v]
        )
    elif id_ == 52:
        chosen = _top(items, ["rating", "price", "stock"][v], [True, True, False][v])
    elif id_ == 53:
        chosen = _top(
            items, ["amount", "amount", "timestamp"][v], [True, False, False][v]
        )
    elif id_ == 61:
        chosen = (
            [x for x in items if x["verdict"] == ["AC", "RE"][v]]
            if v < 2
            else _top(items, "runtime_ms")
        )
    elif id_ == 62:
        chosen = (
            _top(items, "samples", v == 0)
            if v < 2
            else [x for x in items if x["number"] % 2 == 0]
        )
    elif id_ == 63:
        chosen = _top(
            items, ["number", "pass_rate", "name_length"][v], [False, True, True][v]
        )
    elif id_ == 64:
        chosen = _top(
            items, ["timestamp", "timestamp", "lines"][v], [True, False, True][v]
        )
    if chosen is None:
        raise ValueError(f"No selector for {id_}")
    return [x["id"] for x in chosen]


def action_targets(id_, v, items, s):
    t = s["threshold"]
    if id_ == 13:
        return [x["id"] for x in items if s["keyword"] in x["text"]], OPS[id_][v]
    if id_ == 14:
        return [
            x["id"]
            for x in items
            if [x["unread"] == 0, x["unread"] > 0, x["age_days"] > 3][v]
        ], OPS[id_][v]
    if id_ == 16:
        return [x["id"] for x in items if "收到" in x["text"]], OPS[id_][v]
    if id_ == 32:
        return [
            x["id"]
            for x in items
            if [x["rating"] > t, x["rating"] < t, x["duration"] % 2 == 0][v]
        ], OPS[id_][0]
    if id_ == 33:
        return [x["id"] for x in items if s["keyword"] in x["name"]], OPS[id_][v]
    if id_ == 34:
        return [x["id"] for x in items if x["completed"]], OPS[id_][v]
    if id_ == 42:
        return [
            x["id"]
            for x in items
            if [x["tag_count"] > 2, x["tag_count"] == 0, s["letter"] in x["name"]][v]
        ], OPS[id_][0]
    if id_ == 43:
        return [x["id"] for x in items if x["check_pass"]], OPS[id_][v + 1]
    if id_ == 54:
        return [
            x["id"]
            for x in items
            if [x["price"] < t, x["price"] > t, x["transfers"] % 2 == 0][v]
        ], OPS[id_][0]
    if id_ == 55:
        return [x["id"] for x in items if s["tag"] in x["tags"]], OPS[id_][v]
    if id_ == 56:
        return [
            x["id"]
            for x in items
            if [
                s["letter"] in x["name"],
                int(x["account"][-1]) % 2 == 0,
                x["amount"] < t,
            ][v]
        ], OPS[id_][0]
    if id_ == 57:
        return [
            x["id"]
            for x in items
            if [x["balance"] < t, x["balance"] > t, x["same_day"]][v]
        ], OPS[id_][0]
    if id_ == 65:
        return [
            x["id"]
            for x in items
            if [
                x["check_pass"],
                s["function"] in x["code"],
                len(x["code"]) < s["code_threshold"],
            ][v]
        ], OPS[id_][1]
    raise ValueError(f"No action rule for {id_}")


def ordering(id_, v, items):
    if id_ == 12:
        return [
            x["id"]
            for x in sorted(
                items,
                key=lambda x: x[["unread", "timestamp", "name"][v]],
                reverse=v != 1,
            )
        ]
    if id_ == 28:
        return [
            x["id"]
            for x in sorted(
                items,
                key=lambda x: x[["year", "duration", "artist"][v]],
                reverse=v != 0,
            )
        ]
    if id_ == 35:
        a = (
            [x for x in items if x["duration"] < 600]
            if v < 2
            else [x for x in items if x["category"] == "甲"]
        )
        b = (
            [x for x in items if x["duration"] >= 600]
            if v < 2
            else [x for x in items if x["category"] == "乙"]
        )
        if v == 1:
            a, b = b, a
        return [x["id"] for pair in zip(a, b) for x in pair]
    raise ValueError(id_)


def expected_effect(id_, variant, state):
    v = "ABC".index(variant)
    item = task(id_)
    items = state["items"]
    s = state["source"]
    if item["type"] == "T":
        return {"outputs": {"target": transform(id_, v, state)}}
    if item["type"] == "C":
        selected = targets(id_, v, items, s)
        label = LABELS[id_][v] if id_ == 5 else LABELS[id_][0]
        return {
            "labels": {x["id"]: label if x["id"] in selected else "" for x in items}
        }
    if id_ in (12, 28, 35):
        return {"order": ordering(id_, v, items)}
    if id_ == 15:
        return {"members": sorted(targets(id_, v, items, s))}
    if item["type"] == "S":
        return {"selection": sorted(targets(id_, v, items, s))}
    ids, op = action_targets(id_, v, items, s)
    return {"actions": sorted([(i, op) for i in ids])}


def generate(id_, seed):
    if 66 <= id_ <= 75:
        from .games import fixture, sudoku_candidates

        state = fixture(id_, seed)
        state.update(
            title=task(id_)["title"], type=task(id_)["type"], app=task(id_)["app"]
        )
        if state["game"] == "sudoku":
            state["candidate_values"] = {
                f"{r},{c}": sudoku_candidates(state["board"], r, c)
                for r, c in state["candidates"]
            }
        return state
    if not 1 <= id_ <= 65:
        raise ValueError("Only software workspaces are executable")
    for attempt in range(1000):
        rng = random.Random(seed * 1009 + id_ * 997 + attempt * 104729)
        names = ["Ana", "Bryn", "Cobalt7", "Delta?", "Epsilon", "Sky22"]
        # Different names across seeds, preserving the parity/letter fixtures.
        nonce = "".join(
            chr(97 + int(c, 16))
            for c in hashlib.sha256(str(seed).encode()).hexdigest()[:6]
        )
        prefix = nonce
        names = [prefix + x for x in names]
        items = []
        columns = [
            "unread",
            "contact_time",
            "size",
            "timestamp",
            "plays",
            "rating",
            "comments",
            "price",
            "words",
            "balance",
            "transactions",
            "departure",
            "stock",
            "amount",
            "pass_rate",
            "runtime_ms",
            "context",
            "like_rate",
            "sales",
        ]
        values = {c: rng.sample(range(1, 100), 6) for c in columns}
        values["unread"][0] = 0
        for i, name in enumerate(names):
            row = {c: values[c][i] for c in columns}
            row.update(
                id=f"item-{i + 1}",
                name=name,
                name_length=len(name),
                surname=["Wen", "Cao", "Lin", "Zhu", "Han", "Xu"][i],
                text=[
                    "紧急收到? 3",
                    "Plain message",
                    "收到 [ref]",
                    "Report 7",
                    "紧急 follow up",
                    "Long plain message without numbers",
                ][i],
                members=[3, 7, 4, 8, 2, 9][i],
                duration=(
                    [120, 300, 480, 660, 720, 900][i]
                    if id_ in (25, 35)
                    else rng.randrange(110, 700)
                ),
                age_days=[1, 4, 2, 5, 6, 0][i],
                transfers=[0, 3, 2, 5, 4, 1][i],
                year=2001 + rng.sample(range(20), 6)[i],
                artist=["Vela", "Arco", "Sora", "Mica", "Kite", "Nova"][i],
                publisher=["Echo", "North", "Orbit", "Sky", "AtlasNews", "Daily"][i],
                tags=["focus", "blue", "weekly"][: i % 4],
                tag_count=i % 4,
                completed=i % 2 == 0,
                category=["甲", "乙", "乙", "甲", "甲", "乙"][i],
                account=f"5826142{rng.randrange(10)}",
                same_day=i % 3 == 0,
                verdict=["AC", "WA", "RE", "AC", "TLE", "RE"][i],
                samples=i + 1,
                number=100 + i,
                lines=rng.randrange(3, 80),
                code=[
                    "print(3)",
                    "def solve():\n    return 7",
                    "print(",
                    "result = 17\nprint(result)",
                    "def other():\n    return 1",
                    'print("a longer example for checking")',
                ][i],
            )
            try:
                ast.parse(row["code"])
                row["check_pass"] = True
            except SyntaxError:
                row["check_pass"] = False
            if id_ == 33 and i % 2 == 0:
                row["name"] = "紧急 " + row["name"]
            if id_ == 38:
                row["text"] = " ".join(["word"] * row["words"])
            items.append(row)
        s = dict(
            text=f"aLpha {prefix}eTA 3",
            threshold=50,
            text_threshold=15,
            code_threshold=25,
            artist="Arco " + nonce,
            count=3 + seed % 7,
            date="2026-01-15",
            publisher="Echo",
            publisher_short="EC:",
            tags=["blue-" + nonce, "weekly", "focus"],
            surname="Lin" + nonce,
            given_name="Mei",
            quantity=3,
            keyword="紧急",
            letter="a",
            tag="focus",
            function="solve",
            fixed_reply="已确认",
            recipient="联系人甲",
            rename_targets=["value", "total"],
            reference_time="2026-01-15T12:00:00Z",
        )
        if id_ == 37:
            s["text"] = (
                f"Summarize report {nonce}\nUse short sentences\nExplain the result"
            )
        if id_ in (17, 36):
            s["text"] = f"aLpha 3 {prefix}eTa"
        if id_ == 46:
            s["text"] = str(
                100000000000
                + int(hashlib.sha256(f"account:{seed}".encode()).hexdigest()[:14], 16)
                % 900000000000
            )
        if id_ in (58, 60):
            s["text"] = (
                f"value = {seed + 7}\nif value > 0:\n   total = value + 1\n   print(total)"
            )
        if id_ == 59:
            s["text"] = f"alpha {nonce}\ngamma delta"
        public = dict(
            task_id=id_,
            title=task(id_)["title"],
            type=task(id_)["type"],
            app=task(id_)["app"],
            items=items,
            source=s,
            outputs={},
            labels={x["id"]: "" for x in items},
            order=[x["id"] for x in items],
            selection=[],
            members=[],
            actions=[],
            options=LABELS.get(id_, OPS.get(id_, [])),
            checks=[],
            clipboard="",
            ledger=[],
        )
        signatures = [
            json.dumps(expected_effect(id_, v, public), sort_keys=True) for v in "ABC"
        ]
        if len(set(signatures)) == 3 and all(
            _nonempty(expected_effect(id_, v, public)) for v in "ABC"
        ):
            return public
    raise ValueError(
        f"Could not generate distinct variants for task {id_}, seed {seed}"
    )


def _nonempty(effect):
    value = next(iter(effect.values()))
    return bool(value) and (any(value.values()) if isinstance(value, dict) else True)


def apply_mutation(state, op, target="", value="", ids=None):
    if state["task_id"] >= 66:
        from .games import apply

        return apply(state, op, target, value, ids)
    state = copy.deepcopy(state)
    id_ = state["task_id"]
    ids = ids or []
    known = {x["id"] for x in state["items"]}
    if target and target not in known and target != "target":
        raise ValueError("Unknown object")
    if any(i not in known for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid object set")
    if op == "save" and state["type"] == "T":
        state["outputs"]["target"] = value
    elif op == "label" and state["type"] == "C" and target in known:
        if value not in state["options"] + [""]:
            raise ValueError("Invalid label")
        state["labels"][target] = value
    elif op == "select" and state["type"] == "S" and id_ not in (12, 28):
        state["selection"] = sorted(ids)
    elif op == "order" and id_ in (12, 28, 35):
        if set(ids) != known:
            raise ValueError("Order must contain every object exactly once")
        state["order"] = ids
    elif op == "invite" and id_ == 15:
        if len(ids) != 3:
            raise ValueError("Choose exactly three members")
        state["members"] = sorted(ids)
    elif op == "action" and value in OPS.get(id_, []) and target in known:
        item = next(x for x in state["items"] if x["id"] == target)
        if value in ("检查", "本地检查"):
            state["checks"].append({"target": target, "passed": item["check_pass"]})
        else:
            state["actions"].append([target, value])
            if value == "复制":
                state["clipboard"] = item["text"]
            if value == "转账":
                state["ledger"].append(
                    {
                        "target": target,
                        "amount": item["amount"],
                        "account": item["account"],
                    }
                )
    else:
        raise ValueError("Action is not supported by this workspace")
    return state


def evaluate(initial, state, variant, events):
    if initial["task_id"] >= 66:
        from .games import evaluate as evaluate_game

        return evaluate_game(initial, state, variant, events)
    id_ = initial["task_id"]
    expected = expected_effect(id_, variant, initial)
    key = next(iter(expected))
    actual = state[key]
    if key == "actions":
        actual = sorted(tuple(x) for x in actual)
    want = expected[key]
    if isinstance(want, dict):
        checks = [
            dict(id=f"{key}:{k}", passed=actual.get(k) == v) for k, v in want.items()
        ]
        extra = set(actual) - set(want)
    else:
        checks = [dict(id=key, passed=actual == want)]
        extra = set()
    violations = []
    if extra:
        violations.append("unexpected_objects")
    if not events:
        violations.append("no_action")
    if id_ == 43 or (id_ == 65 and variant == "A"):
        checked = set()
        for e in events:
            if e["op"] == "action" and e["value"] in ("检查", "本地检查"):
                row = next(x for x in initial["items"] if x["id"] == e["target"])
                if row["check_pass"]:
                    checked.add(e["target"])
            elif e["op"] == "action" and e["target"] not in checked:
                violations.append("action_before_successful_check")
    if id_ == 56:
        checks.append(
            dict(
                id="ledger",
                passed=len(state["ledger"]) == len(want)
                and sum(x["amount"] for x in state["ledger"])
                == sum(
                    next(x for x in initial["items"] if x["id"] == i)["amount"]
                    for i, op in want
                ),
            )
        )
    return dict(
        success=all(x["passed"] for x in checks) and not violations,
        completion=sum(x["passed"] for x in checks) / len(checks),
        checks=checks,
        violations=sorted(set(violations)),
    )
