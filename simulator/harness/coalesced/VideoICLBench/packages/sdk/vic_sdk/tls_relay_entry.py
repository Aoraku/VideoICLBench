"""Absolute stdlib bootstrap for the campaign-pinned relay, never an ambient SDK."""
from pathlib import Path
import sys

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    for name in list(sys.modules):
        if name == 'vic_sdk' or name.startswith('vic_sdk.'):
            del sys.modules[name]
    sys.path.insert(0, str(root))
    from vic_sdk import tls_relay
    if Path(tls_relay.__file__).resolve() != root/'vic_sdk/tls_relay.py':
        raise RuntimeError('Provider relay must load the campaign-pinned SDK')
    tls_relay.main()
