#!/usr/bin/env python3
"""Download HF data files concurrently using HF_TOKEN or the local HF login."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import subprocess
import tempfile

from huggingface_hub import hf_hub_download


ROOT = Path(__file__).resolve().parent
CODE_SUFFIXES = {'.py', '.md', '.sh', '.toml', '.html', '.js', '.css'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def github_files():
    """Keep the checked-out code, task configs, and documentation versions."""
    try:
        result = subprocess.run(
            ['git', 'ls-files', '-z', '--', 'embodied/'], cwd=ROOT,
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        return {ROOT / os.fsdecode(name) for name in result.stdout.split(b'\0') if name}
    except (OSError, subprocess.CalledProcessError):
        return set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--g2-only', action='store_true', help='Download only the original ten UR5 tasks')
    parser.add_argument('--workers', type=int, default=16)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')

    config = json.loads((ROOT / 'embodied/ARTIFACTS.json').read_text())
    repo = config['repo_id']
    revision = config.get('revision', 'main')
    manifest_file = config.get('file_manifest', 'FILE_MANIFEST.json')
    manifest_path = hf_hub_download(
        repo, filename=manifest_file, repo_type='dataset', revision=revision,
    )
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get('schema') != 1 or not isinstance(manifest.get('files'), list):
        raise ValueError('Unsupported FILE_MANIFEST.json schema')

    destination = (ROOT / 'embodied').resolve()
    rows = []
    seen = set()
    for row in manifest['files']:
        path = PurePosixPath(row['path'])
        if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in row['path']:
            raise ValueError('Unsafe manifest path')
        if str(path) in seen:
            raise ValueError('Duplicate manifest path')
        seen.add(str(path))
        if args.g2_only and path.parts[0] != 'g2-ur5-v1':
            continue
        checksum = row['sha256']
        if not isinstance(row['bytes'], int) or row['bytes'] < 0:
            raise ValueError('Invalid manifest byte count')
        if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
            raise ValueError('Invalid manifest SHA256')
        target = destination / str(path)
        # Reject existing symlinks that would redirect writes outside embodied/.
        target.resolve().relative_to(destination)
        rows.append((row, target))

    preserved = github_files()

    def download(item):
        row, target = item
        if target.exists():
            if target in preserved or target.suffix in CODE_SUFFIXES:
                return 'kept_code'
            if target.is_file() and target.stat().st_size == row['bytes'] and digest(target) == row['sha256']:
                return 'already_present'
        cached = Path(hf_hub_download(
            repo, filename=row['path'], repo_type='dataset', revision=revision,
        ))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.resolve().relative_to(destination)
        temporary = None
        try:
            with cached.open('rb') as source, tempfile.NamedTemporaryFile(
                mode='wb', prefix=target.name + '.', suffix='.download-partial',
                dir=target.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                checksum = hashlib.sha256()
                size = 0
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    output.write(block)
                    checksum.update(block)
                    size += len(block)
            if size != row['bytes'] or checksum.hexdigest() != row['sha256']:
                raise ValueError('Downloaded file does not match manifest')
            os.replace(temporary, target)
            return 'downloaded'
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    counts = {'downloaded': 0, 'already_present': 0, 'kept_code': 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download, row): row[0]['path'] for row in rows}
        for finished, future in enumerate(as_completed(futures), 1):
            try:
                counts[future.result()] += 1
            except Exception as error:
                # Avoid echoing provider exceptions containing signed download URLs.
                raise RuntimeError(f"Download failed for {futures[future]} ({type(error).__name__})") from None
            if finished % 25 == 0 or finished == len(rows):
                print(f'{finished}/{len(rows)} files: {counts}', flush=True)
    print(f'Data available in {destination}; GitHub code/configuration versions preserved.')


if __name__ == '__main__':
    main()
