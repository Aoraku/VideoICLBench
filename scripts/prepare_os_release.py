"""Fetch and verify a pinned OS-ICL release, then apply the visual-contract patch."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

REPO = 'peilin717/OS-ICL'
COMMIT = 'e6c805094eade3ee391d89ad19dbbefc5bc76e11'
ROOT = Path(__file__).resolve().parents[1]


def prepare(destination: Path):
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use an empty destination; deployed source and runtime data are never overwritten')
    tree = json.load(urlopen(f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1',timeout=30))
    if tree.get('sha') != COMMIT or tree.get('truncated'):
        raise ValueError('Unexpected or incomplete source tree')
    entries = [entry for entry in tree['tree'] if entry['type']=='blob']
    destination.mkdir(parents=True, exist_ok=True)
    def fetch(entry):
        path = destination / entry['path']
        if not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Source path escapes release directory')
        for attempt in range(3):
            try:
                content=urlopen(f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{entry["path"]}',timeout=60).read()
                actual=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
                if actual!=entry['sha']:raise ValueError('Source blob checksum mismatch')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
                if entry['mode']=='100755':path.chmod(0o755)
                return
            except Exception:
                if attempt==2:raise
                time.sleep(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fetch,entries))
    manifest=json.loads((destination/'data/manifests/os-icl-1.0.0.json').read_text())
    assert len(manifest['entries'])==108
    for entry in manifest['entries']:
        content=(destination/entry['video']).read_bytes()
        if len(content)!=entry['bytes'] or hashlib.sha256(content).hexdigest()!=entry['sha256']:
            raise ValueError('Demonstration checksum mismatch')
    patch=ROOT/'patches/os-icl-visible-recovery-order.patch'
    subprocess.run(['patch','-p1','-i',str(patch)],cwd=destination,check=True)
    provenance={'repository':REPO,'commit':COMMIT,'files_verified':len(entries),'videos_verified':108,
                'patch':patch.name,'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest()}
    (destination/'videoicl-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps(provenance))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    prepare(parser.parse_args().destination.resolve())
