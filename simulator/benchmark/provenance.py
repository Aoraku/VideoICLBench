import hashlib
from pathlib import Path

def harness_sha256():
    root=Path(__file__).resolve().parent
    digest=hashlib.sha256()
    for path in sorted([*root.glob('*.py'),root/'operator.html',root/'tasks.json']):
        digest.update(path.name.encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()
