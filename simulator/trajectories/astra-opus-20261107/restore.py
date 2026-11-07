#!/usr/bin/env python3
"""Restore exported media paths and optionally inline image data in redacted logs."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

MARKER = '[EXTERNALIZED_DATA_URI:'


def safe_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or '\x00' in relative:
        raise ValueError('Invalid archive-relative path')
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in ('', '.', '..') for p in path.parts):
        raise ValueError('Unsafe archive-relative path: ' + relative)
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes root: ' + relative)
    return target


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class Restorer:
    def __init__(self, archive, output):
        self.archive, self.output = archive.resolve(), output.resolve()
        self.checked_blobs = set()

    def blob(self, ref):
        digest = ref['sha256']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid blob SHA-256')
        expected = 'blobs/sha256/' + digest[:2] + '/' + digest
        if ref['$artifact'] != expected:
            raise ValueError('Blob path does not match SHA-256')
        source = safe_path(self.archive, expected)
        key = (expected, ref['bytes'])
        if key not in self.checked_blobs:
            if not source.is_file() or source.stat().st_size != ref['bytes'] or sha(source) != digest:
                raise ValueError('Blob size/SHA-256 verification failed: ' + expected)
            self.checked_blobs.add(key)
        return source

    def inline(self, ref, encoding):
        data = base64.b64encode(self.blob(ref).read_bytes()).decode('ascii')
        if encoding == 'base64':
            return data
        if encoding == 'data_uri':
            mime = ref.get('mime_type')
            if not isinstance(mime, str) or not re.fullmatch(r'[\w.+/-]+', mime):
                raise ValueError('Invalid data URI MIME type')
            return 'data:' + mime + ';base64,' + data
        raise ValueError('Unknown artifact encoding')

    def restore_string(self, value):
        if value.lstrip().startswith(('{', '[')):
            try:
                parsed = json.loads(value)
            except ValueError:
                pass
            else:
                if isinstance(parsed, (dict, list)):
                    return json.dumps(self.restore_object(parsed), ensure_ascii=False, separators=(',', ':'))
        pieces, offset = [], 0
        while True:
            start = value.find(MARKER, offset)
            if start < 0:
                pieces.append(value[offset:])
                return ''.join(pieces)
            pieces.append(value[offset:start])
            body_start = start + len(MARKER)
            ref, used = json.JSONDecoder().raw_decode(value[body_start:])
            end = body_start + used
            if value[end:end + 1] != ']':
                raise ValueError('Malformed externalized data URI marker')
            pieces.append(self.inline(ref, 'data_uri'))
            offset = end + 1

    def restore_object(self, value):
        if isinstance(value, dict):
            if '$artifact' in value and value.get('encoding') in ('base64', 'data_uri'):
                return self.inline(value, value['encoding'])
            return {key: self.restore_object(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.restore_object(item) for item in value]
        if isinstance(value, str):
            return self.restore_string(value)
        return value

    def write(self, target, source=None, content=None):
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.parent.resolve().is_relative_to(self.output):
            raise ValueError('Output parent escapes root')
        expected_sha = sha(source) if source else hashlib.sha256(content).hexdigest()
        if target.exists():
            if target.is_file() and sha(target) == expected_sha:
                return
            raise FileExistsError('Refusing to overwrite differing file: ' + str(target))
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.restore-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                if source:
                    with source.open('rb') as input_stream:
                        shutil.copyfileobj(input_stream, stream, 4 * 1024 * 1024)
                else:
                    stream.write(content)
                stream.close()
                if sha(temporary) != expected_sha:
                    raise ValueError('Restored file integrity failure')
                # Hard-link creates the destination exclusively (no overwrite).
                os.link(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def run(self, media_only=False):
        manifest = json.loads((self.archive / 'manifest.json').read_text())
        if manifest.get('schema') != 'videoicl-public-trajectories-v1':
            raise ValueError('Unsupported export manifest schema')
        counts = {'media_files': 0, 'text_files': 0}
        self.output.mkdir(parents=True, exist_ok=True)
        for row in manifest['files']:
            episode = row['episode_id']
            if not isinstance(episode, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', episode) or episode in ('.', '..'):
                raise ValueError('Unsafe episode identity')
            relative = 'episodes/' + episode + '/' + row['source_relative_path']
            target = safe_path(self.output, relative)
            if 'artifact' in row:
                self.write(target, source=self.blob(row['artifact']))
                counts['media_files'] += 1
                continue
            if media_only:
                continue
            if row['export_path'] != relative:
                raise ValueError('Text export path does not match identity')
            source = safe_path(self.archive, row['export_path'])
            if source.stat().st_size != row['export_bytes'] or sha(source) != row['export_sha256']:
                raise ValueError('Exported text size/SHA-256 verification failed')
            text = source.read_text()
            suffix = target.suffix.lower()
            if suffix in ('.jsonl', '.ndjson'):
                lines = []
                for line in text.splitlines():
                    value = json.loads(line)
                    if isinstance(value, dict) and set(value) == {'$unparsed_source_line'}:
                        lines.append(self.restore_string(value['$unparsed_source_line']))
                    else:
                        lines.append(json.dumps(self.restore_object(value), ensure_ascii=False, separators=(',', ':')))
                text = '\n'.join(lines) + '\n'
            elif suffix == '.json' and not row.get('invalid_source_json'):
                text = json.dumps(self.restore_object(json.loads(text)), ensure_ascii=False, separators=(',', ':')) + '\n'
            else:
                text = self.restore_string(text)
            self.write(target, content=text.encode())
            counts['text_files'] += 1
        return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Extracted model archive directory containing manifest.json')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--media-only', action='store_true', help='Restore only media paths; do not expand images into JSON logs')
    args = parser.parse_args()
    print(json.dumps(Restorer(args.archive, args.out).run(args.media_only)))


if __name__ == '__main__':
    main()
