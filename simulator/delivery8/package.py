"""Build a self-contained simulator-only eight-task bundle, with audited MP4s."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

from .release import HERE, SIMULATOR, TASKS, verify_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = {p for p in HERE.rglob("*") if p.is_file() and not any(
        n in ("runs", "service-data", "__pycache__", ".pytest_cache") for n in p.relative_to(HERE).parts)}
    files.add(SIMULATOR/"benchmark/requirements.txt")
    for t in TASKS.values():
        archive = SIMULATOR/t["archive"]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != t["archive_sha256"]:
            raise ValueError("Source archive checksum mismatch")
        files.add(archive)
        for variant in "ABC":
            folder = verify_demo(t["id"], variant)
            files.update(p for p in folder.iterdir() if p.is_file())
            files.add(folder.parent/"manifest.private.json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    with tarfile.open(args.output, "w:gz") as tar:
        for p in sorted(files):
            name = str(Path("simulator")/p.relative_to(SIMULATOR))
            hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
            tar.add(p, arcname=name, recursive=False)
        data = json.dumps(dict(release="tabletop8-v1", tasks=8, demos=24, files=hashes), indent=2).encode()
        entry = tarfile.TarInfo("simulator/delivery8/bundle-manifest.json")
        entry.size = len(data); tar.addfile(entry, io.BytesIO(data))
    print(json.dumps(dict(path=str(args.output), files=len(files), tasks=8, demos=24,
                         bytes=args.output.stat().st_size)))


if __name__ == "__main__": main()
