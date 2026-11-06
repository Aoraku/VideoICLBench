"""Assemble the pinned runtime without touching existing sources or environments."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, action='append', default=[],
                        help='external runtime root, repeatable')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('output must be a fresh directory')
    here = Path(__file__).resolve().parent
    roots = [here.parent / 'runtime', *args.source]
    records = json.loads((here / 'runtime-sha256.json').read_text())
    sources, missing = {}, []
    for rel, expected in records.items():
        for root in roots:
            path = root / rel
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                sources[rel] = path
                break
        else:
            missing.append(rel)
    if missing:
        parser.exit(1, 'Missing or mismatched files:\n' + '\n'.join(missing) + '\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / 'runtime'
        for rel, source in sources.items():
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        stage.rename(output)
    print(f'Materialized {len(sources)} pinned files at {output}')


if __name__ == '__main__':
    main()
