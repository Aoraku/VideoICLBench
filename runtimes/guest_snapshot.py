"""Read-only Linux workspace evidence; keep this collector outside writable tasks."""

import argparse
import hashlib
import json
from pathlib import Path


def snapshot(root):
    root = Path(root).resolve(strict=True)
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_file():
            stat = path.stat()
            if stat.st_size > 16 * 1024 * 1024:
                raise ValueError("Task evidence exceeds the per-file limit")
            data = path.read_bytes()
            files.append(
                dict(
                    path=str(path.relative_to(root)),
                    size=len(data),
                    modified_ns=stat.st_mtime_ns,
                    sha256=hashlib.sha256(data).hexdigest(),
                    text=data.decode("utf-8", errors="replace"),
                )
            )
    return {"files": files}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    print(json.dumps(snapshot(args.root), ensure_ascii=False))
