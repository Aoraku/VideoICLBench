"""Compile the original inventory and reviewed task definitions reproducibly."""

from pathlib import Path
import json
import re
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
groups = {
    "chat": list(range(1, 15)),
    "im": [15, 16],
    "music": [17, 18, 22, 27, 28, 32],
    "news": [19, 20, 23, 24, 29, 30, 33],
    "code": list(range(58, 66)),
    "gomoku": [66, 67],
    "media": [21, 25, 26, 31, 34, 35],
    "blog": [36, 38, 40, 42],
    "studio": [37, 39, 41, 43],
    "travel": [44, 47, 51, 54],
    "shop": [45, 48, 52, 55],
    "bank": [46, 49, 50, 53, 56, 57],
    "games": list(range(68, 76)),
    "windows": list(range(76, 91)),
    "linux": list(range(92, 99)),
    "android": [91, 99, 100],
}
overrides = json.loads((ROOT / "tasks/catalog-overrides.json").read_text())
allowed_fields = {"title", "variants", "version", "parameters", "max_actions", "max_seconds"}
assert all(set(fields) <= allowed_fields for fields in overrides.values())
tasks = []
for line in (ROOT / "VideoICL_100_tasks.md").read_text().splitlines():
    match = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([TCSA])\s*\|\s*(.*)\|$", line)
    if not match:
        continue
    id_, title, type_, rules = match.groups()
    id_ = int(id_)
    app = next(k for k, v in groups.items() if id_ in v)
    pieces = re.split(r"(?:^|；)([ABC])：", rules.strip())
    variants = {pieces[i]: pieces[i + 1].strip() for i in range(1, len(pieces), 2)}
    tasks.append(
        dict(
            id=id_,
            title=title.strip(),
            type=type_,
            app=app,
            runtime=app
            if app in ("windows", "linux", "android")
            else ("linux" if app == "gomoku" else "windows"),
            status="application-ready" if id_ <= 75 else "deferred-system",
            variants=variants,
            original_rules=rules.strip(),
            version="1.1.0",
            parameters=dict(
                reference_time="2026-01-15T12:00:00Z",
                threshold=50,
                fixed_reply="已确认",
                keyword="紧急",
                letter="a",
            ),
            seed_splits=dict(
                demo=[0, 999], development=[1000, 9999], evaluation=[10000, 2147483647]
            ),
            max_actions=120,
            max_seconds=300,
            qa={
                v: {"question": "请说明教程中的选择、变换或操作规则。", "answer": r}
                for v, r in variants.items()
            },
        )
    )
    task = tasks[-1]
    for field, value in overrides.get(str(id_), {}).items():
        if field in ("variants", "parameters"):
            task[field].update(value)
        else:
            task[field] = value
    task["qa"] = {
        v: {"question": "请说明教程中的选择、变换或操作规则。", "answer": rule}
        for v, rule in task["variants"].items()
    }
assert [t["id"] for t in tasks] == list(range(1, 101))
assert set(overrides) <= {str(t["id"]) for t in tasks}
assert Counter(t["type"] for t in tasks) == dict(T=25, C=25, S=25, A=25)
assert all(set(t["variants"]) == set("ABC") for t in tasks)
(ROOT / "tasks/catalog.json").write_text(
    json.dumps(dict(schema_version=1, tasks=tasks), ensure_ascii=False, indent=2) + "\n"
)
print(f"Compiled {len(tasks)} tasks, 300 variants.")
