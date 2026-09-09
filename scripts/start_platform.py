"""Start the control plane and business worker; stop both on exit."""

import sys, subprocess, time, signal
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / "scripts/bootstrap.py")], check=True)
processes = []


def stop(*_):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


signal.signal(signal.SIGINT, lambda *_: (stop(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda *_: (stop(), sys.exit(0)))
try:
    for script, port in [("dev_apps.py", 8771), ("dev.py", 8765)]:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1)
            if response.is_success:
                raise RuntimeError(
                    f"Port {port} already has a service; stop it before using this launcher"
                )
        except httpx.TransportError:
            pass
        process = subprocess.Popen(
            [sys.executable, str(root / "scripts" / script)], cwd=root
        )
        processes.append(process)
        for attempt in range(60):
            if process.poll() is not None:
                raise RuntimeError(f"{script} exited")
            try:
                if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).is_success:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError(f"{script} startup timeout")
    print("Portal ready: http://127.0.0.1:8765", flush=True)
    while all(p.poll() is None for p in processes):
        time.sleep(1)
    raise RuntimeError("A platform service exited unexpectedly")
finally:
    stop()
