"""Native Codex / Claude Code Stop hook: require an explicit finish, within a bounded native loop.

Reads only the public tool lifecycle log. Does not call a model or summarize history.
"""
import argparse
import json
from pathlib import Path
import sys
import time


def decision(config, now=None):
    now = time.time() if now is None else now
    root = Path(config['output_dir'])
    if (root / 'environment-error.json').exists() or config.get('deadline_unix', 0) - now < 20:
        return {}
    log = root / 'computer.jsonl'
    if log.exists() and any(json.loads(line).get('type') == 'finish' for line in log.read_text().splitlines()):
        return {}
    count_file = root / 'stop-guard-count.json'
    count = json.loads(count_file.read_text()) if count_file.exists() else 0
    if count >= 3:
        return {}
    count_file.write_text(json.dumps(count + 1))
    return {'decision': 'block', 'reason': 'The GUI task has not been explicitly finished. Continue the original task using the computer tools and current native session. If complete or unable to proceed, call the vic finish tool with an honest summary. Do not claim success without completing the actions. Do not restart the task or repeat deliveries.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    sys.stdin.read()
    print(json.dumps(decision(json.loads(args.config.read_text()))))


if __name__ == '__main__':
    main()
