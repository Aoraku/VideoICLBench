"""Fingerprint the actual control/evaluator and application surface at startup."""

import hashlib
from importlib.metadata import version
import platform
from .config import ROOT


def provenance():
    digest = hashlib.sha256()
    files = list((ROOT / "services/control/vic").glob("*.py"))
    files += list((ROOT / "apps/portal/dist").rglob("*"))
    files += list((ROOT / "packages/app_runtime/vic_apps").glob("*.py"))
    files += list((ROOT / "packages/app_runtime/vic_apps").glob("*.json"))
    for directory in (
        "apps/chat/frontend/frontend/dist", "apps/im/Frontend/out",
        "apps/news/src/main/resources/web", "apps/music/blog/templates",
        "apps/music/blog/static/benchmark", "apps/media/assets",
    ):
        files += list((ROOT / directory).rglob("*"))
    files += [ROOT / name for name in (
        "apps/code/app/frontend.py", "apps/code/app/benchmark_bridge.py",
        "apps/gomoku/main.cpp", "apps/gomoku/simhei.ttf", "apps/gomoku/build/gomoku_benchmark",
    )]
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
