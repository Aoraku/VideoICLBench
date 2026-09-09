"""Create local credentials without printing values or replacing existing files."""

import os
import hmac
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
local = root / ".local"
local.mkdir(exist_ok=True)


def write_once(path, content):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w") as file:
        file.write(content)


write_once(local / "admin-token", secrets.token_urlsafe(32) + "\n")
values = {
    "VIC_ADMIN_TOKEN": (local / "admin-token").read_text().strip(),
    "VIC_DB_PASSWORD": secrets.token_hex(24),
    "VIC_APP_SECRET": secrets.token_hex(32),
    "VIC_OJ_ADMIN_PASSWORD": secrets.token_hex(24),
}
write_once(
    local / "docker.env", "".join(f"{key}={value}\n" for key, value in values.items())
)
print("Credential files are ready under .local/. Existing credentials are preserved.")

# Upgrade credential files without rotating any existing value.
path = local / "docker.env"
existing = dict(
    line.split("=", 1)
    for line in path.read_text().splitlines()
    if line and not line.startswith("#")
)
if "VIC_APP_RUNTIME_TOKEN" not in existing:
    value = hmac.new(
        existing["VIC_ADMIN_TOKEN"].encode(), b"application-worker", "sha256"
    ).hexdigest()
    with path.open("a") as stream:
        stream.write("VIC_APP_RUNTIME_TOKEN=" + value + "\n")
    path.chmod(0o600)
