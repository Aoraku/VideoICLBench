"""Absolute-path, stdlib-only bootstrap; reject preloaded/ambient older SDKs."""
from pathlib import Path
import sys

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    for name in list(sys.modules):
        if name == 'vic_sdk' or name.startswith('vic_sdk.'):
            del sys.modules[name]
    sys.path.insert(0, str(root))
    from vic_sdk import embodied_codex_mcp
    if Path(embodied_codex_mcp.__file__).resolve() != root/'vic_sdk/embodied_codex_mcp.py':
        raise RuntimeError('Native structured tools must load their pinned SDK')
    embodied_codex_mcp.main()
