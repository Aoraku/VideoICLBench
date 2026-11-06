"""Generate private transport configuration for fresh Astra pools. No network calls."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


def publish_new(path, payload):
    """Publish a complete mode-0600 file without replacing an existing file."""
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.link(stream.name, path)


def configure(credentials, gate, shared_directory, scope, verified, base_url, key):
    url = urlsplit(base_url)
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.password is not None or url.query or url.fragment or url.path.rstrip("/") != "/v1"):
        raise ValueError("Specify the verified HTTPS Responses base URL ending in /v1")
    if not key or any(ch.isspace() for ch in key):
        raise ValueError("Provide a nonempty private API key")
    if not verified or not shared_directory.is_absolute() or ".." in shared_directory.parts:
        raise ValueError("Supply the absolute shared gate directory after verifying cross-host atomic mkdir")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", scope):
        raise ValueError("Use a stable credential scope consisting of letters, digits, underscores or hyphens")
    gate_config = dict(schema="videoicl-api-concurrency-v1", scope=scope, limit=50, legacy_reserved=0,
                       lock_directory=str(shared_directory), filesystem_atomic_mkdir_verified=True)
    if credentials.resolve() == gate.resolve():
        raise ValueError("Credentials and gate config require distinct paths")
    if not gate.exists():
        try:
            publish_new(gate, gate_config)
        except FileExistsError:
            pass
    if json.loads(gate.read_bytes()) != gate_config:
        raise ValueError("Existing shared gate differs; preserve it and check the configured gate")
    provider = {"codex": {"base_url": base_url.rstrip("/"), "api_key": key,
                          "model": "gpt-6-astra", "native_auth": False}}
    publish_new(credentials, provider)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--gate", required=True, type=Path)
    parser.add_argument("--shared-lock-directory", required=True, type=Path)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--atomic-mkdir-verified", action="store_true")
    args = parser.parse_args()
    configure(args.credentials, args.gate, args.shared_lock_directory, args.scope,
              args.atomic_mkdir_verified, os.environ.get("VIDEOICL_API_BASE_URL", ""),
              os.environ.get("VIDEOICL_API_KEY", ""))


if __name__ == "__main__":
    main()
