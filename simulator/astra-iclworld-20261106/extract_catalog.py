"""Reconstruct the frozen Codex catalog from an operator-provided local copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path

PIN = Path(__file__).resolve().parent / "config/model-catalog-pin.json"


def reconstruct(source, pin):
    models = json.loads(source.read_bytes()).get("models")
    if not isinstance(models, list):
        raise ValueError("Expected a local CLI cache containing a models array.")
    astra = [row for row in models if row.get("slug") == pin["model"]]
    if len(astra) != 1 or astra[0].get("max_context_window", 0) < pin["context_window"]:
        raise ValueError("Expected one Astra row supporting the experiment window.")
    astra[0]["context_window"] = pin["context_window"]
    astra[0]["auto_compact_token_limit"] = pin["auto_compact_token_limit"]
    public_schema = {"models": models}
    raw = (json.dumps(public_schema, ensure_ascii=False, indent=2) + "\n").encode()
    if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Catalog snapshot mismatch. Use the original operator cache snapshot "
                         "or frozen private model-catalog.json for this run. A newer CLI cache "
                         "can have different rows. No file was created.")
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = reconstruct(args.source, json.loads(PIN.read_bytes()))
        fd = os.open(args.out, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    print("Verified catalog written. Keep this file outside the repository.")


if __name__ == "__main__":
    main()
