"""Fingerprint the actual control/evaluator and application surface at startup."""

import hashlib
from importlib.metadata import version
import platform
from .config import ROOT


def provenance():
    digest = hashlib.sha256()
    files = list((ROOT / "services/control/vic").glob("*.py"))
    files += list((ROOT / "apps/portal/dist").rglob("*"))
    for path in sorted(p for p in files if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return dict(
        implementation_digest=digest.hexdigest(),
        python=platform.python_version(),
        packages={
            name: version(name)
            for name in ("fastapi", "sqlalchemy", "playwright", "pillow")
        },
    )
