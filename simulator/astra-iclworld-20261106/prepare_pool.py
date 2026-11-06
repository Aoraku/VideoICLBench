"""Materialize an Astra pool for a fresh reproduction. Never starts a process."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil

CONFIG = Path(__file__).resolve().parent / "config"


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prepare(args):
    catalog = args.model_catalog.resolve(strict=True)
    if digest(catalog) != load(CONFIG / "model-catalog-pin.json")["sha256"]:
        raise ValueError("Model catalog mismatch. Prepare the pinned catalog using extract_catalog.py.")
    manifest = load(CONFIG / "experiment.json")
    pools = {p["pool_id"]: p for p in manifest["pools"]}
    pool = pools[args.pool]
    by_id = {r["episode_id"]: r for r in manifest["episodes"]}
    rows = [by_id[ep].copy() for ep in pool["episode_ids"]]
    tasks = load(CONFIG / "tasks.json")
    # Locate required model-facing videos by exact bytes. Source filenames can differ.
    required = {}
    for row in rows:
        field = {"real": "demo", "sim": "demo_sim"}.get(row["input_condition"])
        if field:
            required[tasks[row["task_package"]]["native"][field]["sha256"]] = None
    if required:
        if not args.media_root:
            raise ValueError("Video pools require --media-root containing the exact videos.")
        for path in args.media_root.rglob("*"):
            if path.suffix.lower() not in {".mp4", ".mov", ".webm"} or not path.is_file():
                continue
            sha = digest(path)
            if sha in required:
                required[sha] = path.resolve()
                if all(required.values()):
                    break
        missing = [sha for sha, path in required.items() if path is None]
        if missing:
            raise ValueError("Missing exact demonstration bytes: " + ", ".join(missing))

    root = args.out.resolve()
    if root.exists():
        raise FileExistsError(f"Choose a fresh output directory: {root}")
    paths = load(args.paths)
    runner = args.bench.resolve() / "scripts/harbor/run_embodied_pool.py"
    root.mkdir(parents=True, exist_ok=False)
    binding_dir = root / "config"
    binding_dir.mkdir()
    # Native E pairing opens these exact sibling filenames, including the canonical I.
    for binding in (CONFIG / "bindings").glob("*.json"):
        shutil.copyfile(binding, binding_dir / (binding.stem + ".private.json"))
    for row in rows:
        rel = row["task_package"]
        package = root / rel
        spec = tasks[rel]
        for filename, sha in spec["files"].items():
            source = CONFIG / "task-content" / sha
            if digest(source) != sha:
                raise ValueError(f"Task text checksum mismatch: {source}")
            target = package / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        native = spec["native"].copy()
        for field in ("demo", "demo_sim"):
            if field in native:
                demo = dict(native[field])
                original = required.get(demo["sha256"])
                demo["path"] = str(original or (package / demo["path"]))
                native[field] = demo
        write_json(package / "environment/native.json", native)
        row["bindings"] = str(binding_dir / (Path(row["bindings"]).stem + ".private.json"))
        row["robot"] = str(CONFIG / row["robot"])
        row["task_package"] = str(package)
        row["task_root"] = str(package.parent)
    cases = root / "cases.json"
    write_json(cases, {"cases": rows})
    command = [
        paths["gui_python"], str(runner), "--native-python", paths["native_python"],
        "--gui-python", paths["gui_python"], "--runtime-root", str(args.runtime.resolve()),
        "--cases", str(cases), "--task-root", str(root / pool["task_root"]),
        "--credentials", str(args.credentials.resolve()), "--browser-path", paths["browser_path"],
        "--provider-ca-bundle", paths["ca_bundle"], "--api-concurrency-config", str(args.gate.resolve()),
        "--engine", "codex", "--binary", paths["codex_binary"], "--model", "gpt-6-astra",
        "--condition", pool["default_input_condition"], "--effort", "high",
        "--native-structured-tools", "--provider-request-metadata", "--codex-context-window", "262144",
        "--codex-compact-tokens", "120000", "--codex-model-catalog", str(catalog),
        "--codex-model-catalog-sha256", digest(catalog), "--embodied-harness", "program_gui",
        "--embodied-auto-recover", "--unknown-api-policy", "preserve_world", "--max-actions", "500",
        "--timeout", "0", "--experience", paths["experience"], "--epoch", root.name + "-" + args.pool,
        "--out", str(root / "result"), "--allow-unvalidated-environment",
        "--native-kit-args=" + paths["native_kit_args"],
    ]
    environment = paths["native_environment"]
    allowed = set(load(CONFIG / "paths.example.json")["native_environment"])
    if set(environment) != allowed:
        raise ValueError("Unexpected or missing native environment variable")
    exports = [f"export {key}={shlex.quote(value)}" for key, value in environment.items()]
    shell = ["#!/bin/sh", "set -eu", *exports,
             ': "${CUDA_VISIBLE_DEVICES:?select an allocated GPU}"',
             f'test ! -e {shlex.quote(str(root / "result"))}', "exec " + shlex.join(command)]
    (root / "run.sh").write_text("\n".join(shell) + "\n")
    print(f"Prepared {len(rows)} episodes in {root}; inspect run.sh before running.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("out", "runtime", "bench", "paths", "credentials", "gate", "model-catalog"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--pool", required=True, choices=[p["pool_id"] for p in load(CONFIG / "experiment.json")["pools"]])
    parser.add_argument("--media-root", type=Path)
    prepare(parser.parse_args())
