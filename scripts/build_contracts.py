"""Versioned evaluation contracts for every task, including deferred system tasks."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tasks = json.loads((ROOT / "tasks/catalog.json").read_text())["tasks"]
fields = {
    1: ["messages.recipient", "messages.body"],
    2: ["objects.nickname"],
    3: ["messages.body"],
    4: ["messages.body"],
    11: ["messages.attachment"],
    15: ["memberships"],
    17: ["objects.display_name"],
    18: ["objects.name"],
    19: ["objects.title"],
    20: ["objects.tags_text"],
    21: ["objects.name"],
    30: ["collections.reading_list"],
    32: ["collections.list-a"],
    34: ["collections.watchlist", "collections.history", "collections.favorites"],
    35: ["orders.main"],
    36: ["objects.title"],
    37: ["objects.prompt"],
    40: ["objects.published", "artifacts"],
    41: ["settings.model"],
    43: ["checks", "artifacts", "messages", "browser.clipboard"],
    44: ["objects.full_name"],
    45: ["objects.note"],
    46: ["objects.note"],
    54: ["artifacts.booking"],
    55: ["collections.cart", "collections.favorites"],
    56: ["ledger", "balances"],
    57: ["objects.reminder"],
    58: ["objects.code", "artifacts.submission"],
    59: ["objects.text"],
    60: ["objects.code", "AST.bindings"],
    65: ["checks", "artifacts.submission"],
}
system = {
    76: ["files.name"],
    77: ["files.text"],
    78: ["files.parent"],
    79: ["selection.file"],
    80: ["artifacts.path_text"],
    81: ["files.backup_name"],
    82: ["documents.title"],
    83: ["annotations.process"],
    84: ["processes.started"],
    85: ["windows.state"],
    86: ["settings.short_date"],
    87: ["annotations.network"],
    88: ["annotations.notification"],
    89: ["selection.device"],
    90: ["settings.night_light"],
    91: ["devices.connected"],
    92: ["artifacts.output_text"],
    93: ["artifacts.path_text"],
    94: ["annotations.command"],
    95: ["annotations.process"],
    96: ["selection.process"],
    97: ["selection.file"],
    98: ["command_events", "execution.paused"],
    99: ["settings.battery_saver"],
    100: ["packages.stopped"],
}
contracts = []
for t in tasks:
    id_ = t["id"]
    readset = fields.get(
        id_,
        ["objects.label"]
        if t["type"] == "C"
        else ["orders.main"]
        if id_ in (12, 28)
        else ["settings"]
        if t["type"] == "S"
        else ["objects", "messages", "collections", "artifacts"],
    )
    if id_ >= 66:
        readset = (
            ["board", "moves", "marks", "selection", "stopped", "events"]
            if id_ <= 75
            else system[id_]
        )
    c = dict(
        schema_version=1,
        task_id=id_,
        task_version=t["version"],
        title=t["title"],
        app=t["app"],
        type=t["type"],
        status="implemented" if id_ <= 75 else "deferred-system",
        execution_surface="application-benchmark" if id_ <= 75 else t["runtime"],
        variants={
            v: dict(
                rule=r,
                evaluator=f"task_{id_:03d}_{v}",
                predicate="Exact rule result, lawful event replay, required business effect, and unchanged non-target state",
            )
            for v, r in t["variants"].items()
        },
        api=dict(
            create="POST /v1/runs",
            evaluate=f"POST /v1/tasks/{id_}/eval",
            contract=f"GET /v1/tasks/{id_}/contract",
            reset="POST /v1/runs/{run_id}/reset",
            evidence="GET /v1/runs/{run_id}/evidence",
        ),
        request_schema=dict(
            type="object",
            required=["run_id"],
            additionalProperties=False,
            properties={"run_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"}},
        ),
        response_fields=[
            "task_id",
            "variant",
            "success",
            "completion",
            "checks",
            "violations",
            "epoch",
            "evidence_ref",
            "official",
        ],
        read_set=readset,
        process_constraints=[
            "nonempty_action_trace",
            "no_rule_or_answer_in_actor_surface",
            "sealed_input_before_evaluation",
            "idempotent_evaluation",
            "no_extra_side_effects",
        ],
        initialization=dict(
            generator=f"task_{id_:03d}",
            seed_partitions=t["seed_splits"],
            public_parameters=t["parameters"],
        ),
        ties="单对象数值相同时按初始对象顺序；棋盘候选点按行、列升序；2048 方向顺序：左、上、右、下。",
        system_snapshot_schema=dict(
            required=system.get(id_, []),
            collector="guest-side read-only adapter",
            availability="deferred",
        )
        if id_ > 75
        else None,
    )
    if id_ == 35:
        c["ties"] = (
            "队列类别交替，同类对象保持初始相对顺序；A 从短视频开始，B 从长视频开始，C 从甲类开始。"
        )
    if id_ == 18:
        c["format"] = "Three fields cyclically reordered and joined with underscore."
    if id_ == 60:
        c["format"] = (
            "Identifiers must follow the demonstrated rename; AST bindings and semantics must be preserved. Comments and harmless whitespace are permitted."
        )
    if id_ in (43, 65):
        c["process_constraints"].append("successful_check_precedes_required_delivery")
    contracts.append(c)
    d = ROOT / "tasks/contracts"
    d.mkdir(exist_ok=True)
    (d / f"{id_:03d}.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2) + "\n"
    )
(ROOT / "tasks/contracts/index.json").write_text(
    json.dumps(
        dict(schema_version=1, contracts=contracts), ensure_ascii=False, indent=2
    )
    + "\n"
)
lines = [
    "# 逐题应用与评测索引",
    "",
    "任务 1–75 使用应用 benchmark 模式，共 225 个规则版本。任务 76–100 的系统执行与采集适配暂缓。",
    "",
    "每题通过 `POST /v1/tasks/{task_id}/eval` 接收 `run_id`。管理服务封存该运行，按固定版本检查完整业务结果与过程约束；非目标状态必须保持一致。模型凭证只允许截图与键鼠输入。",
    "",
    "契约链接提供初始化参数、种子划分、读取字段、过程约束、请求结构与返回字段。规则中的指定词、阈值、联系人等参数以该运行的任务资料为准。",
    "",
]
for label, entries in [
    ("软件与游戏", contracts[:75]),
    ("系统任务：执行适配暂缓", contracts[75:]),
]:
    lines += [
        f"## {label}",
        "",
        "| 题号／契约 | 应用 | 任务 | A | B | C | 判分读取字段 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in entries:
        cells = [
            f"[{c['task_id']:03d}](../tasks/contracts/{c['task_id']:03d}.json)",
            c["app"],
            c["title"],
            *(c["variants"][v]["rule"] for v in "ABC"),
            "、".join(f"`{field}`" for field in c["read_set"]),
        ]
        lines.append("| " + " | ".join(x.replace("|", "\\|") for x in cells) + " |")
    lines.append("")
(ROOT / "docs/task-evaluation-map.md").write_text("\n".join(lines))
print(
    "100 eval contracts, 225 implemented rule versions, 75 deferred system rule versions"
)
