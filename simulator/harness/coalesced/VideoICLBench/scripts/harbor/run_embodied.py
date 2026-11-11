#!/usr/bin/env python3
"""Run one embodied package with a native CLI or the bounded GUI driver."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/sdk"))
if '--native-structured-tools' in sys.argv:
    for name in list(sys.modules):
        if name == 'vic_sdk' or name.startswith('vic_sdk.'):
            del sys.modules[name]

from vic_sdk.embodied_agent import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["codex", "claude", "robodawn"])
    parser.add_argument("--embodied-task-dir", type=Path, required=True)
    parser.add_argument("--embodied-connection", type=Path, required=True)
    parser.add_argument("--embodied-harness", choices=["gui", "program_gui"], default="gui", help="Opt-in episode-local GUI programs; default: gui")
    parser.add_argument('--native-structured-tools', action='store_true', help='Real Codex conversation with structured public GUI tools and native compaction')
    parser.add_argument("--condition", choices=["real", "sim", "text_rule"], required=True)
    parser.add_argument("--max-actions", type=int, required=True)
    parser.add_argument("--max-gui-inputs", type=int, help="Separate GUI editing budget; physical Commits use --max-actions")
    parser.add_argument("--browser-path", type=Path, help="Pinned Chromium/Chrome executable for GUI interaction")
    parser.add_argument("--timeout", type=int, required=True)
    parser.add_argument("--model")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--output-root", type=Path, default=Path("outputs/embodied"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh"], default="low")
    parser.add_argument("--codex-compact-tokens", type=int, default=32768, help="Native Codex auto-compaction threshold; no custom history summarizer")
    parser.add_argument('--codex-context-window', type=int, help='Explicit native Codex context window; requires compatible pinned catalog')
    parser.add_argument('--lean-text-projection', action=argparse.BooleanOptionalAction, default=True, help='Compact JSON output for new program_gui episodes; images and fields unchanged')
    parser.add_argument("--codex-model-catalog", type=Path, help="Pinned native model catalog for blocking GUI tool calls")
    parser.add_argument("--codex-model-catalog-sha256", help="Exact SHA256 of the pinned native model catalog")
    parser.add_argument("--embodied-auto-recover", action="store_true", help="Recover the same Codex session and environment after transient provider failures")
    parser.add_argument('--robodawn-window-tokens', type=int, default=128000)
    parser.add_argument('--robodawn-compact-trigger-tokens', type=int, default=96000)
    parser.add_argument('--robodawn-max-receipts', type=int, default=12)
    parser.add_argument('--robodawn-notes-max-chars', type=int, default=2500)
    parser.add_argument('--robodawn-max-old-gui', type=int, default=0)
    parser.add_argument("--code-mode", action="store_true")
    parser.add_argument("--max-budget-usd", type=float, default=1.)
    parser.add_argument("--claude-compact-percent", type=int)
    parser.add_argument("--serial-tools", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--allow-unvalidated-environment", action="store_true")
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
