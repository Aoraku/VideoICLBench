"""Own and release only this run's subprocess tree, including new sessions."""
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import time


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_ticks: int


def linux_process(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        fields = text[text.rindex(')') + 2:].split()
        return dict(pid=pid, ppid=int(fields[1]), start_ticks=int(fields[19]), state=fields[0])
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        return None


def identity(pid):
    row = linux_process(pid)
    return ProcessIdentity(pid, row['start_ticks']) if row else None


def descendants(owner):
    """A fresh /proc snapshot; PID reuse never grants ownership."""
    root = linux_process(owner.pid)
    if not root or root['start_ticks'] != owner.start_ticks:
        return []
    rows = {}
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            value = linux_process(int(path.name))
            if value:
                rows[value['pid']] = value
    owned = {owner.pid}
    while True:
        new = {p for p, row in rows.items() if row['ppid'] in owned} - owned
        if not new:
            break
        owned.update(new)
    return [ProcessIdentity(p, rows[p]['start_ticks']) for p in owned if p in rows]


def signal_owned(process, sig):
    row = linux_process(process.pid)
    if not row or row['start_ticks'] != process.start_ticks or row['state'] == 'Z':
        return False
    try:
        os.kill(process.pid, sig)
        return True
    except ProcessLookupError:
        return False


def alive(process):
    row = linux_process(process.pid)
    return bool(row and row['start_ticks'] == process.start_ticks and row['state'] != 'Z')


def terminate_tree(owner, *, grace_seconds=8., include_owner=True):
    """Release this process and children even when a CLI created a new PGID.

    The run's owner must still exist when ownership is captured. Normal and
    forced exits both validate PID start times before every signal. Other
    processes sharing this GPU are never selected by GPU number or name.
    """
    snapshot = [p for p in descendants(owner) if include_owner or p != owner]
    for p in snapshot:
        signal_owned(p, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and any(alive(p) for p in snapshot):
        # Include children spawned during a graceful shutdown, before the
        # original parent disappears. Preserve the initial children as well.
        if alive(owner):
            fresh = [p for p in descendants(owner) if include_owner or p != owner]
            snapshot = list(set(snapshot + fresh))
        time.sleep(.05)
    for p in snapshot:
        signal_owned(p, signal.SIGKILL)
    return [dict(pid=p.pid, start_ticks=p.start_ticks) for p in snapshot]
