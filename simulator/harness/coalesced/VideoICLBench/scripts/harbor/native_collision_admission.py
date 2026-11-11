"""Private native startup log gate; no policy inputs or task rewards."""
import json
from pathlib import Path


def assert_native_collision_admission(log_path):
    """Reject source shape construction errors before GUI/model admission."""
    path=Path(log_path)
    if not path.is_file():
        raise RuntimeError('Native collision admission log is missing: '+str(path))
    failures=[line for line in path.read_text(errors='replace').splitlines()
              if '[omni.physx' in line and 'Unable to create convex mesh' in line]
    if failures:
        evidence=path.with_name('native-collision-admission.private.json')
        evidence.write_text(json.dumps(dict(schema='videoicl-native-collision-admission-v1',
            admitted=False,log=str(path),errors=failures),indent=2)+'\n')
        raise RuntimeError('Native collision creation failed; model admission rejected: '+str(evidence))
