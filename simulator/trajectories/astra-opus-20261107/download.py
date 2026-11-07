#!/usr/bin/env python3
"""Download published trajectory assets and verify their size and SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('manifest.json'))
    parser.add_argument('--out', type=Path, default=Path('trajectory-downloads'))
    parser.add_argument('--model', choices=['all', 'astra', 'opus'], default='all')
    parser.add_argument('--package', action='append', choices=['astra-main', 'astra-logs', 'opus-main', 'opus-logs', 'opus-supplement'], help='Download one package; repeat to select several')
    args = parser.parse_args()
    if args.package and args.model != 'all' and any(not package.startswith(args.model + '-') for package in args.package):
        parser.error('--package must belong to the selected --model')
    manifest = json.loads(args.manifest.read_text())
    if args.package:
        present = {asset.get('package') for asset in manifest['assets']}
        if set(args.package) - present:
            raise ValueError('Requested package is absent from the verified release manifest')
    args.out.mkdir(parents=True, exist_ok=True)
    for asset in manifest['assets']:
        if args.model != 'all' and asset.get('model') not in (args.model, 'shared'):
            continue
        if args.package and asset.get('package') not in args.package:
            continue
        name = asset['name']
        if Path(name).name != name or name in ('', '.', '..'):
            raise ValueError('Unsafe asset name')
        target = args.out / name
        if target.is_file() and target.stat().st_size == asset['size'] and digest(target) == asset['sha256']:
            print('Verified existing:', name)
            continue
        url = asset['url']
        if not url.startswith('https://github.com/Aoraku/VideoICLBench/releases/download/'):
            raise ValueError('Unexpected asset origin')
        partial = target.with_name(target.name + '.partial')
        h = hashlib.sha256()
        total = 0
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as stream:
            while block := response.read(4 * 1024 * 1024):
                stream.write(block)
                h.update(block)
                total += len(block)
        if total != asset['size'] or h.hexdigest() != asset['sha256']:
            raise RuntimeError('Download integrity failure: ' + name)
        partial.replace(target)
        print('Downloaded and verified:', name)


if __name__ == '__main__':
    main()
