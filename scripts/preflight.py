"""Inspect capabilities without starting services or accepting simulated fallbacks."""

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def command(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


checks = {
    "linux_host": platform.system() == "Linux",
    "kvm": Path("/dev/kvm").exists() and os.access("/dev/kvm", os.R_OK | os.W_OK),
    "docker_running": command(["docker", "info"]),
    "libvirt": command(["virsh", "-c", "qemu:///system", "list"]),
    "android_emulator": shutil.which("emulator") is not None,
    "adb": shutil.which("adb") is not None,
    "windows_image_configured": bool(os.environ.get("VIC_WINDOWS_IMAGE")),
}
print(json.dumps(checks, indent=2))
