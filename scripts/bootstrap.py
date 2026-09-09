"""Create local credentials without printing values or replacing existing files."""

import os
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
