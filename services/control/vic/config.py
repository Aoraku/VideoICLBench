from pathlib import Path
import os

ROOT = Path(os.environ.get("VIC_ROOT", Path(__file__).resolve().parents[3])).resolve()
DATA = Path(os.environ.get("VIC_DATA", ROOT / ".local"))
DATABASE_URL = os.environ.get(
    "VIC_DATABASE_URL", f"sqlite:///{DATA / 'control.sqlite3'}"
)
TASK_FILE = ROOT / "tasks" / "catalog.json"
PUBLIC_BASE = os.environ.get("VIC_PUBLIC_BASE", "http://127.0.0.1:8765").rstrip("/")


def admin_token():
    token = os.environ.get("VIC_ADMIN_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError(
            "VIC_ADMIN_TOKEN must contain at least 32 characters; run scripts/dev.py"
        )
    return token
