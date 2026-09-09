"""Launch the local-only workbench without printing credentials."""

import os
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parents[1]
local = root / ".local"
local.mkdir(mode=0o700, exist_ok=True)
token_path = local / "admin-token"
if not token_path.exists():
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_urlsafe(40))
os.environ["VIC_ADMIN_TOKEN"] = token_path.read_text().strip()
os.environ.setdefault("VIC_ROOT", str(root))
os.environ.setdefault("VIC_PUBLIC_BASE", "http://127.0.0.1:8765")
print("VideoICL local portal: http://127.0.0.1:8765", flush=True)
print(f"Login credential: {token_path} (not included in Git)", flush=True)
os.execv(
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "vic.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ],
)
