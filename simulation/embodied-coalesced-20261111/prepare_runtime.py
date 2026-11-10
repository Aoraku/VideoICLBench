"""Create a separate runtime tree and apply the deployed native pool overlay."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-runtime", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.base_runtime.resolve(strict=True)
    target = args.out.resolve()
    if target.exists() or target.is_relative_to(source):
        parser.error("--out must be a new directory outside --base-runtime")
    if not (source / "videoicl_isaaclab" / "realworld_scenes.py").is_file():
        parser.error("--base-runtime must be a complete VideoICL native runtime")
    root = Path(__file__).resolve().parent
    source_map = json.loads((root / "SOURCE_MAP.json").read_text())["files"]
    shutil.copytree(source, target, symlinks=True)
    for name, hashes in source_map.items():
        if not name.startswith("runtime-overlay/"):
            continue
        path = target / name.removeprefix("runtime-overlay/")
        if path.is_symlink() or not path.resolve().is_relative_to(target):
            raise ValueError("Runtime overlay must target an owned file: " + name)
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes["published_sha256"]:
            raise ValueError("Runtime overlay file hash mismatch: " + name)
        path.write_bytes(data)
    print(target)


if __name__ == "__main__":
    main()
