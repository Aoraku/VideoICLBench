#!/usr/bin/env bash
set -euo pipefail
# Run on Agentlab as qingle after copying/cloning this repository.
repo_dir="$(cd "$(dirname "$0")/../.." && pwd)"
service_root="${EMBODIED_SERVICE_ROOT:-/home/qingle/services/videoicl-embodied-50}"
data_dir="${EMBODIED_DATA:-$service_root/data-desktop50}"
mkdir -p "$data_dir" "$HOME/.config/systemd/user"
python_bin="${EMBODIED_PYTHON:-$service_root/.venv/bin/python}"
"$python_bin" -m ensurepip
"$python_bin" -m pip install --no-cache-dir -r "$repo_dir/simulator/benchmark/requirements.txt" -c "$repo_dir/simulator/benchmark/requirements-agentlab.lock"
cat > "$HOME/.config/systemd/user/videoicl-embodied-50.service" <<UNIT
[Unit]
Description=VideoICL Embodied 50 dual Panda benchmark
After=network.target
[Service]
Type=simple
WorkingDirectory=$repo_dir
Environment=MUJOCO_GL=osmesa
Environment=PYOPENGL_PLATFORM=osmesa
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=EMBODIED_DATA=$data_dir
ExecStart=$python_bin -m uvicorn simulator.benchmark.server:app --host 127.0.0.1 --port 18660 --workers 1
Restart=on-failure
RestartSec=5
KillMode=control-group
UMask=0077
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable videoicl-embodied-50.service
systemctl --user restart videoicl-embodied-50.service
for attempt in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:18660/health; then exit 0; fi
  sleep 1
done
exit 1
