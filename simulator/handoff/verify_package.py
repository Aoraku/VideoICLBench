"""Check packaged file integrity without importing a simulator."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'handoff/sha256.json').read_text())
for name,expected in manifest.items():
    actual=hashlib.sha256((root/name).read_bytes()).hexdigest()
    if actual!=expected:raise SystemExit('Hash mismatch: '+name)
print(f'OK: {len(manifest)} packaged files verified')
