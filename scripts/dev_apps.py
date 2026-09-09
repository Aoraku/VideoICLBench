"""Start independent business application worker on localhost."""

import os, hmac, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
secret = (root / ".local/admin-token").read_text().strip()
os.environ.setdefault("VIC_ROOT", str(root))
os.environ.setdefault(
    "VIC_APP_RUNTIME_TOKEN",
    hmac.new(secret.encode(), b"application-worker", "sha256").hexdigest(),
)
os.execv(
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "vic_apps.server:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8771",
    ],
)
