"""Private per-task evaluators of persisted application business records."""

import ast
import io
import tokenize
from copy import deepcopy
import json
from . import business

VALUE_FIELDS = {
    2: "nickname",
    17: "display_name",
    18: "name",
    19: "title",
    20: "tags_text",
    21: "name",
    36: "title",
    37: "prompt",
    44: "full_name",
    45: "note",
    46: "note",
    58: "code",
    59: "text",
    60: "code",
}
CHOICES = {
    9: "recipient",
    10: "conversation",
    11: "attachment",
    27: "playing_song",
    29: "reading_article",
    30: "reading_list",
    31: "playing_video",
    40: "publication",
    41: "model",
    51: "itinerary",
    52: "product",
    53: "transaction",
    63: "problem",
    64: "submission",
}


def canonical(domain):
    d = deepcopy(domain)
    for m in d["messages"]:
        m.pop("id", None)
    for key in ("messages", "artifacts", "ledger", "clipboard_history"):
        d[key] = sorted(d[key], key=lambda x: json.dumps(x, sort_keys=True))
    for key in ("collections", "memberships"):
        d[key] = {name: sorted(values) for name, values in d[key].items()}
    d.pop("checks", None)
    return d


def expected_domain(initial, variant):
    t = initial["task_id"]
    d = deepcopy(initial["domain"])
    effect = business.expected_effect(t, variant, initial)
    src = initial["source"]
    objects = d["objects"]

    def sent(body, reference=None, attachment=None):
        d["messages"].append(
            dict(
                id="ignored",
                sender="self",
                recipient="contact-a",
                body=body,
                reference=reference,
                attachment=attachment,
            )
        )

    def collection(name, obj, remove=False):
        current = set(d["collections"].get(name, []))
        current.discard(obj) if remove else current.add(obj)
        d["collections"][name] = sorted(current)

    if "outputs" in effect:
        text = effect["outputs"]["target"]
        if t in (1, 3, 4):
            sent(text)
        else:
            objects["target"][VALUE_FIELDS[t]] = text
        if t == 58:
            d["artifacts"].append(
                dict(kind="submission", target="target", body=text, syntax_valid=True)
            )
        if t == 60:
            objects["target"]["syntax_valid"] = True
    elif "labels" in effect:
        for id_, label in effect["labels"].items():
            objects[id_]["label"] = label
    elif "order" in effect:
        d["orders"]["main"] = effect["order"]
    elif "members" in effect:
        d["memberships"]["group-1"] = ["self"] + effect["members"]
        objects["group-1"] = dict(id="group-1", kind="groups", name="项目讨论组")
    elif "selection" in effect:
        ids = effect["selection"]
        d["settings"][CHOICES[t]] = ids
        if t == 11:
            for i in ids:
                sent("", attachment=i)
        if t == 29:
            for i in ids:
                objects[i]["read"] = True
        if t == 30:
            d["collections"]["reading_list"] = ids
        if t == 40:
            for i in ids:
                objects[i]["published"] = True
                d["artifacts"].append(
                    dict(kind="publication", target=i, body=objects[i]["text"])
                )
    else:
        for i, op in effect["actions"]:
            obj = objects[i]
            if op in ("转发", "回复", "发送"):
                sent(src["fixed_reply"] if op == "回复" else obj["text"], reference=i)
            elif op in ("收藏", "加入收藏"):
                collection("favorites", i)
                obj["starred"] = True
                if t == 34:
                    collection("watchlist", i, True)
            elif op == "星标":
                obj["starred"] = True
            elif op in ("归档", "置顶", "静音", "已读", "隐藏", "发布", "开启提醒"):
                obj[
                    dict(
                        归档="archived",
                        置顶="pinned",
                        静音="muted",
                        已读="read",
                        隐藏="hidden",
                        发布="published",
                        开启提醒="reminder",
                    )[op]
                ] = True
                if op == "发布":
                    d["artifacts"].append(
                        dict(kind="publication", target=i, body=obj["text"])
                    )
            elif op == "加入列表甲":
                collection("list-a", i)
            elif op in ("移入历史", "删除"):
                collection("watchlist", i, True)
                if op == "移入历史":
                    collection("history", i)
            elif op in ("加入购物车", "移出购物车"):
                collection("cart", i, op == "移出购物车")
            elif op == "确认预订":
                d["artifacts"].append(
                    dict(kind="booking", target=i, price=obj["price"], confirmed=True)
                )
            elif op == "保存":
                d["artifacts"].append(dict(kind="document", target=i, body=obj["text"]))
            elif op == "复制":
                d["clipboard_history"].append(dict(target=i, text=obj["text"]))
            elif op == "提交":
                d["artifacts"].append(
                    dict(
                        kind="submission",
                        target=i,
                        body=obj["code"],
                        syntax_valid=obj["check_pass"],
                    )
                )
            elif op == "转账":
                cents = obj["amount"] * 100
                transfer = f"transfer-{len(d['ledger']) // 2 + 1}"
                d["ledger"] += [
                    dict(
                        transfer=transfer, account="self", cents=-cents, counterparty=i
                    ),
                    dict(
                        transfer=transfer, account=i, cents=cents, counterparty="self"
                    ),
                ]
                d["balances"]["self"] -= cents
                d["balances"][i] += cents
    return d


def ast_equal(a, b):
    try:
        return ast.dump(ast.parse(a), include_attributes=False) == ast.dump(
            ast.parse(b), include_attributes=False
        )
    except (SyntaxError, ValueError):
        return False


def evaluate(initial, state, variant, events, clipboard=None):
    if initial["task_id"] >= 66:
        return business.evaluate(initial, state, variant, events)
    t = initial["task_id"]
    base = business.evaluate(initial, state, variant, events)
    actual = canonical(state["domain"])
    want = canonical(expected_domain(initial, variant))
    if t in (58, 60):
        field = "code"
        submitted = actual["objects"]["target"].get(field, "")
        expected = want["objects"]["target"][field]
        equivalent = ast_equal(submitted, expected)
        if t == 58:
            unit = {"A": "  ", "B": "    ", "C": "\t"}[variant]
            depth = 0
            try:
                for token in tokenize.generate_tokens(io.StringIO(submitted).readline):
                    if token.type == tokenize.INDENT:
                        depth += 1
                        equivalent = equivalent and token.string == unit * depth
                    elif token.type == tokenize.DEDENT:
                        depth -= 1
            except (tokenize.TokenError, IndentationError, SyntaxError):
                equivalent = False
        base["checks"] = [dict(id="code_rules_and_bindings", passed=equivalent)]
        if equivalent:
            actual["objects"]["target"]["code"] = expected
            for artifact in actual["artifacts"]:
                if artifact.get("kind") == "submission":
                    artifact["body"] = expected
    # Transfer identifiers are opaque; ledger semantics are account, amount, counterparty.
    for data in (actual, want):
        for entry in data["ledger"]:
            entry.pop("transfer", None)
        data["ledger"].sort(key=lambda x: json.dumps(x, sort_keys=True))
    checks = base["checks"] + [
        dict(id="business:" + key, passed=actual.get(key) == value)
        for key, value in want.items()
    ]
    if t == 43 and variant == "B":
        history = state["domain"]["clipboard_history"]
        checks.append(
            dict(
                id="browser_clipboard",
                passed=bool(history) and clipboard == history[-1]["text"],
            )
        )
    violations = base["violations"]
    return dict(
        success=all(x["passed"] for x in checks) and not violations,
        completion=(sum(x["passed"] for x in base["checks"]) / len(base["checks"]))
        if all(x["passed"] for x in checks[len(base["checks"]) :])
        else 0.0,
        checks=checks,
        violations=violations,
    )
