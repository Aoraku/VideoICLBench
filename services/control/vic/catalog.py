import hashlib
import json
from .config import TASK_FILE


def catalog():
    return json.loads(TASK_FILE.read_text())


def task(task_id: int):
    for item in catalog()["tasks"]:
        if item["id"] == task_id:
            return item
    raise KeyError(task_id)


def task_digest(task_id: int):
    return hashlib.sha256(
        json.dumps(task(task_id), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def public_task(task_id: int):
    item = task(task_id)
    return {k: item[k] for k in ("id", "title", "type", "app", "runtime", "status")}
