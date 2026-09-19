"""Domain state transitions. No variant or answer is accessible to applications."""

from copy import deepcopy
import ast
import hashlib
import base64

ENTITY = {
    1: "messages",
    2: "contacts",
    3: "messages",
    4: "messages",
    5: "messages",
    6: "contacts",
    7: "conversations",
    8: "groups",
    9: "contacts",
    10: "conversations",
    11: "attachments",
    12: "conversations",
    13: "messages",
    14: "conversations",
    15: "contacts",
    16: "messages",
    17: "songs",
    18: "playlists",
    19: "articles",
    20: "articles",
    21: "folders",
    22: "songs",
    23: "articles",
    24: "articles",
    25: "videos",
    26: "videos",
    27: "songs",
    28: "songs",
    29: "articles",
    30: "articles",
    31: "videos",
    32: "songs",
    33: "articles",
    34: "videos",
    35: "videos",
    36: "posts",
    37: "documents",
    38: "posts",
    39: "documents",
    40: "posts",
    41: "models",
    42: "posts",
    43: "documents",
    44: "passengers",
    45: "products",
    46: "transfer_drafts",
    47: "itineraries",
    48: "products",
    49: "transactions",
    50: "accounts",
    51: "itineraries",
    52: "products",
    53: "transactions",
    54: "itineraries",
    55: "products",
    56: "accounts",
    57: "accounts",
    58: "submissions",
    59: "answers",
    60: "source_files",
    61: "submissions",
    62: "problems",
    63: "problems",
    64: "submissions",
    65: "source_files",
}
SAVE_FIELD = {
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
SELECT_FIELD = {
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


def initialize(state):
    state = deepcopy(state)
    if state["task_id"] >= 66:
        return state
    t = state["task_id"]
    # Instance-scoped identifiers prevent demonstration object IDs from being reused.
    seed = state.get("seed", state.get("source", {}).get("instance_seed", 0))
    for item in state["items"]:
        item["id"] = (
            "object-"
            + hashlib.sha256(f"{seed}:{t}:{item['id']}".encode()).hexdigest()[:10]
        )
    state["labels"] = {x["id"]: "" for x in state["items"]}
    state["order"] = [x["id"] for x in state["items"]]
    kind = ENTITY[t]
    objects = {
        x["id"]: {
            **deepcopy(x),
            "kind": kind,
            "label": "",
            "read": False,
            "starred": False,
            "archived": False,
            "pinned": False,
            "muted": False,
            "hidden": False,
            "published": False,
            "reminder": False,
        }
        for x in state["items"]
    }
    objects["target"] = {
        "id": "target",
        "kind": kind,
        "name": state["source"]["text"],
        "text": state["source"]["text"],
    }
    objects["contact-a"] = {
        "id": "contact-a",
        "kind": "contacts",
        "name": state["source"]["recipient"],
    }
    d = dict(
        objects=objects,
        messages=[],
        memberships={},
        collections=(
            {"list-a": [], "favorites": []}
            if state["app"] == "music"
            else {
                "watchlist": [x["id"] for x in state["items"]],
                "history": [],
                "favorites": [],
            }
            if state["app"] == "media"
            else {"cart": [x["id"] for x in state["items"]][::2], "favorites": []}
            if state["app"] == "shop"
            else {"reading_list": [], "favorites": []}
            if state["app"] == "news"
            else {"favorites": []}
            if state["app"] == "chat"
            else {}
        ),
        orders={"main": [x["id"] for x in state["items"]]},
        settings={},
        artifacts=[],
        checks=[],
        ledger=[],
        balances={
            "self": 1000000,
            **{x["id"]: int(x["balance"]) * 100 for x in state["items"]},
        },
        clipboard_history=[],
        files={},
    )
    if t == 11:
        for item in state["items"]:
            content = item["file_text"].encode("utf-8")
            d["files"][item["id"]] = dict(
                name=item["name"],
                content=base64.b64encode(content).decode(),
                sha256=hashlib.sha256(content).hexdigest(),
                size=len(content),
            )
    if t in (1, 3, 4):
        d["messages"] = [
            dict(
                id="received-1",
                sender="contact-a",
                recipient="self",
                body="请整理并发送消息。",
                reference=None,
                attachment=None,
            )
        ]
    if t == 43:
        # This task's generated results are code fragments; "check" means Python syntax.
        for obj in objects.values():
            if obj["id"] not in ("target", "contact-a"):
                obj["text"] = obj["code"]
    state["domain"] = d
    return state


def syntax_check(text):
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError, TypeError):
        return False


def apply(state, op, target="", value="", ids=None):
    """Execute an ordinary application command, without consulting an evaluator."""
    state = deepcopy(state)
    d = state["domain"]
    t = state["task_id"]
    ids = ids or []
    obj = d["objects"].get(target)

    def message(body, recipient="contact-a", reference=None, attachment=None):
        d["messages"].append(
            dict(
                id=f"sent-{len(d['messages']) + 1}",
                sender="self",
                recipient=recipient,
                body=body,
                reference=reference,
                attachment=attachment,
            )
        )

    def collect(name, item, remove=False):
        values = d["collections"].setdefault(name, [])
        if remove:
            if item in values:
                values.remove(item)
        elif item not in values:
            values.append(item)

    if op == "save":
        if t in (1, 3, 4):
            message(value)
        else:
            d["objects"]["target"][SAVE_FIELD[t]] = value
        if t == 58:
            d["artifacts"].append(
                dict(
                    kind="submission",
                    target="target",
                    body=value,
                    syntax_valid=syntax_check(value),
                )
            )
        if t == 60:
            d["objects"]["target"]["syntax_valid"] = syntax_check(value)
    elif op == "label":
        obj["label"] = value
    elif op == "order":
        d["orders"]["main"] = list(ids)
    elif op == "invite":
        d["memberships"]["group-1"] = ["self"] + list(ids)
        d["objects"]["group-1"] = dict(id="group-1", kind="groups", name="项目讨论组")
    elif op == "select":
        d["settings"][SELECT_FIELD[t]] = list(ids)
        if t == 11:
            for i in ids:
                message("", attachment=i)
        if t == 29:
            for i in ids:
                d["objects"][i]["read"] = True
        if t == 30:
            d["collections"]["reading_list"] = list(ids)
        if t == 40:
            for i in ids:
                d["objects"][i]["published"] = True
                d["artifacts"].append(
                    dict(kind="publication", target=i, body=d["objects"][i]["text"])
                )
    elif op == "action":
        if value in ("检查", "本地检查"):
            passed = syntax_check(obj["code"])
            d["checks"].append(dict(target=target, passed=passed, kind="python-syntax"))
        elif value == "转发":
            message(obj["text"], reference=target)
        elif value == "回复":
            message(state["source"]["fixed_reply"], reference=target)
        elif value in ("收藏", "加入收藏"):
            collect("favorites", target)
            obj["starred"] = True
            if t == 34:
                collect("watchlist", target, True)
        elif value == "星标":
            obj["starred"] = True
        elif value in ("归档", "置顶", "静音", "已读", "隐藏", "发布", "开启提醒"):
            field = {
                "归档": "archived",
                "置顶": "pinned",
                "静音": "muted",
                "已读": "read",
                "隐藏": "hidden",
                "发布": "published",
                "开启提醒": "reminder",
            }[value]
            obj[field] = True
            if value == "发布":
                d["artifacts"].append(
                    dict(kind="publication", target=target, body=obj["text"])
                )
        elif value == "加入列表甲":
            collect("list-a", target)
        elif value in ("移入历史", "删除"):
            collect("watchlist", target, True)
            if value == "移入历史":
                collect("history", target)
        elif value == "加入购物车":
            collect("cart", target)
        elif value == "移出购物车":
            collect("cart", target, True)
        elif value == "确认预订":
            d["artifacts"].append(
                dict(kind="booking", target=target, price=obj["price"], confirmed=True)
            )
        elif value == "保存":
            d["artifacts"].append(
                dict(kind="document", target=target, body=obj["text"])
            )
        elif value == "复制":
            d["clipboard_history"].append(dict(target=target, text=obj["text"]))
        elif value == "发送":
            message(obj["text"], reference=target)
        elif value == "提交":
            d["artifacts"].append(
                dict(
                    kind="submission",
                    target=target,
                    body=obj["code"],
                    syntax_valid=syntax_check(obj["code"]),
                )
            )
        elif value == "转账":
            cents = int(obj["amount"]) * 100
            if d["balances"]["self"] < cents:
                raise ValueError("余额不足")
            transfer = f"transfer-{len(d['ledger']) // 2 + 1}"
            d["ledger"] += [
                dict(
                    transfer=transfer, account="self", cents=-cents, counterparty=target
                ),
                dict(
                    transfer=transfer, account=target, cents=cents, counterparty="self"
                ),
            ]
            d["balances"]["self"] -= cents
            d["balances"][target] += cents
        else:
            raise ValueError("Unsupported domain command")
    else:
        raise ValueError("Unsupported domain command")
    return state
