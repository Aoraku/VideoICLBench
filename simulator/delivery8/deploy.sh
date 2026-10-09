#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/../.." && pwd)"
service_root="${TABLETOP8_SERVICE_ROOT:-/home/qingle/services/videoicl-tabletop8}"
python_bin="${TABLETOP8_PYTHON:-/home/qingle/services/videoicl-embodied-50/.venv/bin/python}"
mkdir -p "$service_root/service-data" "$HOME/.config/systemd/user"
cd "$repo_dir"
"$python_bin" -m simulator.delivery8.prepare --data "$service_root/service-data"
cat > "$HOME/.config/systemd/user/videoicl-tabletop8.service" <<UNIT
[Unit]
Description=VideoICL eight tabletop tasks and HTTP actors
After=network.target
[Service]
Type=simple
WorkingDirectory=$repo_dir
Environment=MUJOCO_GL=osmesa
Environment=PYOPENGL_PLATFORM=osmesa
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=TABLETOP8_DATA=$service_root/service-data
ExecStart=$python_bin -m uvicorn simulator.delivery8.server:app --host 127.0.0.1 --port 18664 --workers 1
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStopSec=120
UMask=0077
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable videoicl-tabletop8.service
systemctl --user restart videoicl-tabletop8.service
for attempt in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:18664/health; then exit 0; fi
  sleep 1
done
exit 1
