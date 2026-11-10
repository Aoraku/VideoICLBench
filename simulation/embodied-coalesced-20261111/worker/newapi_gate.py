"""User-authorized unlimited campaign admission for NEW immutable relays only.

This does not modify the legacy gate, slots, FIFO tickets, or accepted requests.
Per-room singleflight, delivery guards and native API lifecycle remain elsewhere.
"""
from contextlib import contextmanager
from pathlib import Path
import time

CAMPAIGN = 'four-model-remaining559-newapi-20261108'
LIMIT = None


@contextmanager
def upstream_admission(out, receipt):
    if not any(parent.name == CAMPAIGN for parent in Path(out).resolve().parents):
        yield
        return
    admitted = time.time()
    receipt['api_gate'] = {
        'scope': CAMPAIGN,
        'enabled': False,
        'limit': None,
        'mode': 'unlimited_authorized_20261108',
        'phase': 'unlimited_admitted',
        'queued_at': admitted,
        'admitted_at': admitted,
        'queue_wait_seconds': 0.0,
        'legacy_lease_acquired': False,
    }
    try:
        yield
    finally:
        # Request completion metadata only: no legacy permit was acquired or released.
        receipt['api_gate'].update(phase='unlimited_completed', completed_at=time.time())
