"""Prepare one standalone QA config. This performs no inference."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "config/qa51.json")
    parser.add_argument("--qa-id", required=True)
    parser.add_argument("--media-root", type=Path, required=True, help="Root for manifest-relative video_path")
    for name in ("sdk-root", "binary", "credentials", "ca-bundle", "api-gate-config",
                 "model-catalog", "output-dir", "config-out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.manifest.read_bytes())["entries"]
    matches = [r for r in rows if r["qa_id"] == args.qa_id]
    if len(matches) != 1:
        parser.error("QA identity must appear exactly once")
    row = matches[0]
    media = (args.media_root / row["video_path"]).resolve(strict=True)
    if not media.is_relative_to(args.media_root.resolve()) or sha(media) != row["video_sha256"]:
        parser.error("Assigned video path or digest differs from manifest")
    cfg = {
        "schema": "standalone-native-video-qa-run-v1",
        "identity": {key: row[key] for key in ("qa_id", "task", "variant", "seed")},
        "question": row["public_question"], "video_path": str(media), "video_sha256": row["video_sha256"],
        "model": "gpt-6-astra", "effort": "high", "expected_cli_version": "codex-cli 0.163.0",
        "output_dir": str(args.output_dir.resolve()),
    }
    for name in ("sdk_root", "binary", "credentials", "api_gate_config", "model_catalog", "ca_bundle"):
        cfg[name] = str(getattr(args, name).resolve(strict=True))
    for path_key, hash_key in (("credentials", "credentials_sha256"), ("api_gate_config", "api_gate_sha256"),
                               ("model_catalog", "model_catalog_sha256")):
        cfg[hash_key] = sha(Path(cfg[path_key]))
    pin = Path(__file__).resolve().parents[1] / "config/model-catalog-pin.json"
    if cfg["model_catalog_sha256"] != json.loads(pin.read_bytes())["sha256"]:
        parser.error("Model catalog differs from the pinned experiment version")
    with args.config_out.open("x", encoding="utf-8") as stream:
        json.dump(cfg, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
