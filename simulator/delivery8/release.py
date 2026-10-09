"""Verify media and reconstruct the exact historical per-task runtime."""
import hashlib
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
SIMULATOR = HERE.parent
MANIFEST = json.loads((HERE/"release.private.json").read_text())
TASKS = {t["id"]: t for t in MANIFEST["tasks"]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hash(root):
    # Reproduce the recorder's original hashing contract, including old paths.
    old = (root/"scripts/tabletop50/record.py").is_file()
    tools = "scripts/tabletop50/*.py" if old else "simulator/tabletop50/tools/*.py"
    files = sorted([*root.glob("simulator/tabletop50/*.py"), *root.glob(tools),
                    root/"simulator/benchmark/environment.py",
                    root/"simulator/benchmark/pilot.py", root/"simulator/benchmark/protocol.py"])
    digest = hashlib.sha256()
    for p in files:
        digest.update(str(p.relative_to(root)).encode()+b"\0"+p.read_bytes()+b"\0")
    return digest.hexdigest()


def verify_demo(task, variant):
    row = TASKS[task]["demos"][variant]
    folder = SIMULATOR/row["folder"]
    proof = json.loads((folder/"result.private.json").read_text())
    audit = json.loads((folder/"media-audit.private.json").read_text())
    batch = json.loads((folder.parent/"manifest.private.json").read_text())
    case = next(c for c in batch["cases"] if c["folder"] == folder.name)
    checks = [
        (proof["task"], proof["variant"], proof["seed"]) == (task, variant, 0),
        proof["score"]["success"], not proof["error"], proof["source_unchanged"],
        proof["source_sha256"] == row["source_sha256"],
        proof["world_sha256"] == row["world_sha256"],
        proof["cross_rule_predicates"][variant], sum(proof["cross_rule_predicates"].values()) == 1,
        proof["video"]["recorded"], proof["video"]["full_episode"], proof["video"]["final_success"],
        sha(folder/"video.mp4") == row["video_sha256"] == audit["video_sha256"],
        audit["decoded_frames"] == row["frames"], audit["ending_image_mae"] < 20,
        case.get("usable_for_agent_demo", False),
        case.get("visual_environment", {}).get("fixtures_visible", True),
    ]
    if not all(checks):
        raise ValueError(f"Demo failed verification: {task}-{variant}")
    return folder


def prepare(root):
    """Unpack only regular archive files; never modify the frozen sources."""
    root = Path(root).resolve()
    for task in TASKS.values():
        archive = SIMULATOR/task["archive"]
        if sha(archive) != task["archive_sha256"]:
            raise ValueError("Frozen archive checksum mismatch")
        digest = task["demos"]["A"]["source_sha256"]
        target = root/digest
        if not target.exists():
            target.mkdir(parents=True)
            with tarfile.open(archive) as tar:
                for entry in tar:
                    p = (target/entry.name).resolve()
                    if not p.is_relative_to(target) or not (entry.isfile() or entry.isdir()):
                        raise ValueError("Unsafe archive entry")
                    if entry.isfile():
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(tar.extractfile(entry).read())
        if source_hash(target) != digest:
            raise ValueError("Frozen runtime source does not match recording")
        for variant in "ABC": verify_demo(task["id"], variant)
    return root
