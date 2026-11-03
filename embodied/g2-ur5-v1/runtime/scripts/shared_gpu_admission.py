"""Reserve measured VRAM during startup and hold one shared native worker lock."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

PREFIX = Path(os.environ.get('VIC_GPU_LOCK_PREFIX','/tmp/videoicl-realworld50-gpu'))


def parse_gpu_process_memory(xml):
    """Read the single physical card, including graphics and C+G processes.

    A PID reported in both process classes owns one allocation, so use its
    largest reported value rather than summing duplicate rows. Unknown process
    memory earns no credit against a startup reservation.
    """
    gpus = ET.fromstring(xml).findall('gpu')
    if len(gpus) != 1:
        raise ValueError('Admission requires exactly one physical GPU; no aggregate-card admission')
    gpu = gpus[0]
    def mib(value):
        parts = (value or '').strip().split()
        if len(parts) != 2 or parts[1] != 'MiB':
            raise ValueError('A measured integer MiB value is required')
        number = int(parts[0])
        if number < 0:
            raise ValueError('GPU memory must be nonnegative')
        return number
    free = mib(gpu.findtext('fb_memory_usage/free'))
    processes = {}
    for row in gpu.findall('processes/process_info'):
        try:
            pid = int(row.findtext('pid'))
            used = mib(row.findtext('used_memory'))
            if pid <= 0:
                raise ValueError('A positive PID is required')
        except (TypeError, ValueError):
            continue
        processes[pid] = max(used, processes.get(pid, 0))
    return free, processes


def group_process_memory(processes, getpgid=os.getpgid, proc=Path('/proc')):
    groups = {};ready = {}
    for pid, used in processes.items():
        try:
            group = getpgid(pid)
            groups[group] = groups.get(group, 0) + used
            arguments=(proc/str(pid)/'cmdline').read_bytes().decode().split('\0')
            if '--out' in arguments:
                directory=Path(arguments[arguments.index('--out')+1])
                witness=directory/'initial-state.private.json'
                if witness.is_file():ready[group]=dict(file=str(witness),mtime=witness.stat().st_mtime)
        except (ProcessLookupError, ValueError):
            continue
        except (FileNotFoundError,PermissionError,IndexError):
            continue
    return groups, ready


def measurements():
    # One XML snapshot provides both real free VRAM and all process classes.
    # The previous single-card policy is retained; multiple physical cards fail
    # closed rather than adding their free memory together.
    xml = subprocess.check_output(['nvidia-smi', '-q', '-x'], text=True)
    free, processes = parse_gpu_process_memory(xml)
    groups, ready = group_process_memory(processes)
    return free, groups, ready


def startup_reserved(rows, groups, ready):
    """Retire only fresh native initialization evidence, then count shortfall."""
    for row in rows:
        witness=ready.get(row['group'])
        if witness and witness['mtime']>=row['started_unix_s'] and row['budget_mib']:
            row.update(initial_budget_mib=row['budget_mib'],budget_mib=0,
                startup_complete_witness=witness['file'])
    return sum(max(0, row['budget_mib']-groups.get(row['group'], 0)) for row in rows)


def alive(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget-mib', type=int, default=6800)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or not 1000 <= args.budget_mib <= 24000:
        parser.error('A native command and measured VRAM budget are required')
    names = [str(PREFIX)+suffix for suffix in ('.lock', '-secondary.lock', '-tertiary.lock')]
    names += [str(PREFIX)+f'-extra-{i}.lock' for i in range(3, 8)]
    startup = open(str(PREFIX)+'-startup.lock', 'a+')
    ledger_path = Path(str(PREFIX)+'-reservations.json')
    child = None
    slot_file = None
    state = {}

    def read_ledger():
        rows = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        return [row for row in rows if alive(row['group'])]

    def save_ledger(rows):
        tmp = ledger_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(rows, indent=2)+'\n')
        tmp.replace(ledger_path)

    def stop(signum, frame):
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        last_notice = 0
        while child is None:
            fcntl.flock(startup, fcntl.LOCK_EX)
            try:
                rows = read_ledger()
                free, groups,ready = measurements()
                reserved = startup_reserved(rows, groups, ready)
                if free-reserved >= args.budget_mib:
                    for index, name in enumerate(names):
                        candidate = open(name, 'a+')
                        try:
                            fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            candidate.close()
                            continue
                        slot_file = candidate
                        env = os.environ.copy()
                        env['VIC_REALWORLD_WORKER_SLOT'] = str(index)
                        child = subprocess.Popen(command, env=env, start_new_session=True)
                        state = dict(group=child.pid, broker=os.getpid(), slot=index,
                                     budget_mib=args.budget_mib, started_unix_s=time.time())
                        rows.append(state)
                        print('GPU_ADMITTED '+json.dumps(dict(state, measured_free_mib=free,
                            startup_reserved_mib=reserved)), flush=True)
                        break
                save_ledger(rows)
                if child is None and time.time()-last_notice >= 60:
                    print('GPU_WAIT '+json.dumps(dict(free_mib=free,
                        startup_reserved_mib=reserved, required_mib=args.budget_mib)), flush=True)
                    last_notice = time.time()
            finally:
                fcntl.flock(startup, fcntl.LOCK_UN)
            if child is None:
                time.sleep(2)
        return child.wait()
    finally:
        if child is not None:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            fcntl.flock(startup, fcntl.LOCK_EX)
            try:
                save_ledger([row for row in read_ledger() if row['group'] != child.pid])
            finally:
                fcntl.flock(startup, fcntl.LOCK_UN)
        if slot_file is not None:
            slot_file.close()
        startup.close()


if __name__ == '__main__':
    raise SystemExit(main())
