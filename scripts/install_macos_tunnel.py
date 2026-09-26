#!/usr/bin/env python3
"""Install the user's persistent VideoICL SSH tunnel with macOS launchd."""

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="qingle@agentlab", help="SSH account and host alias")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This installer requires macOS.")
    if args.host.startswith("-"):
        parser.error("Invalid SSH host.")

    # Verify unattended authentication without relying on a terminal's agent.
    env = dict(os.environ)
    env.pop("SSH_AUTH_SOCK", None)
    subprocess.run([
        "/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        args.host, "true",
    ], env=env, check=True)

    label = "com.videoicl.agentlab-tunnel"
    domain = f"gui/{os.getuid()}"
    plist_path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    log_dir = Path.home() / "Library/Logs/VideoICL"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = {
        "Label": label,
        "ProgramArguments": [
            "/usr/bin/ssh", "-NT", "-S", "none",
            "-o", "BatchMode=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "TCPKeepAlive=yes",
            "-L", "127.0.0.1:18765:127.0.0.1:8765",
            "-L", "127.0.0.1:18766:127.0.0.1:8771",
            args.host,
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 15,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "tunnel.stdout.log"),
        "StandardErrorPath": str(log_dir / "tunnel.stderr.log"),
    }
    subprocess.run(["/bin/launchctl", "bootout", f"{domain}/{label}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with plist_path.open("wb") as handle:
        plistlib.dump(config, handle)
    plist_path.chmod(0o600)
    subprocess.run(["/bin/launchctl", "enable", f"{domain}/{label}"], check=True)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(plist_path)], check=True)
    print(f"Installed: {plist_path}")
    print("Open http://127.0.0.1:18765/ after the tunnel connects.")
    print(f"Logs: {log_dir}")


if __name__ == "__main__":
    main()
