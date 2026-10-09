"""Package tracked simulator files, including the complete indexed media."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "simulator/tabletop50"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "simulator/"], cwd=ROOT
    ).decode().split("\0")
    names = sorted(set(n for n in names if n) | {str(Path(__file__).resolve().relative_to(ROOT))})
    if output == ROOT or any(output == ROOT / n for n in names):
        raise SystemExit("Output would overwrite an input file")
    tracked = set(names)
    indexed = re.findall(r"\[视频\]\(([^)]+)\)", (BASE / "VIDEOS.md").read_text())
    if not indexed:
        raise SystemExit("Video index is empty")
    evidence = {}
    for manifest in (BASE / "artifacts").glob("*/manifest.private.json"):
        for row in json.loads(manifest.read_text()).get("cases", []):
            if row.get("usable_for_agent_demo"):
                name = str((manifest.parent / row["folder"] / "video.mp4").relative_to(ROOT))
                evidence[name] = row["video_sha256"]
    for relative in indexed:
        path = (BASE / relative).resolve()
        if not path.is_relative_to(BASE / "artifacts"):
            raise SystemExit(f"Video escapes artifacts: {relative}")
        name = str(path.relative_to(ROOT))
        if name not in tracked or not path.is_file():
            raise SystemExit(f"Indexed video is missing or untracked: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != evidence.get(name):
            raise SystemExit(f"Indexed video does not match audited checksum: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    temporary = output.with_name(output.name + ".partial")
    try:
        with tarfile.open(temporary, "w:gz") as bundle:
            for name in names:
                path = ROOT / name
                if not path.is_file() or path.is_symlink():
                    raise SystemExit(f"Expected regular tracked file: {name}")
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                bundle.add(path, arcname=name, recursive=False)
            data = json.dumps(dict(indexed_videos=len(indexed), files=hashes,
                                   media_role="historical maintainer previews"), indent=2).encode()
            info = tarfile.TarInfo("simulator/tabletop50/bundle-manifest.json")
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps(dict(output=str(output), files=len(names), indexed_videos=len(indexed),
                          bytes=output.stat().st_size)))


if __name__ == "__main__":
    main()
