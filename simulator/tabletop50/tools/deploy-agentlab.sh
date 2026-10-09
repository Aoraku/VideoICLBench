#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/../../.." && pwd)"
service_root="${TABLETOP50_SERVICE_ROOT:-/home/qingle/services/videoicl-tabletop50-fpv-v1}"
python_bin="${TABLETOP50_PYTHON:-/home/qingle/services/videoicl-embodied-50/.venv/bin/python}"
mkdir -p "$service_root/service-data" "$HOME/.config/systemd/user"
"$python_bin" -c 'import fastapi, uvicorn, robosuite, mujoco'
cat > "$HOME/.config/systemd/user/videoicl-tabletop50-fpv.service" <<UNIT
[Unit]
Description=VideoICL Tabletop50 first-person dual Panda
After=network.target
[Service]
Type=simple
WorkingDirectory=$repo_dir
Environment=MUJOCO_GL=osmesa
Environment=PYOPENGL_PLATFORM=osmesa
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=TABLETOP50_DATA=$service_root/service-data
ExecStart=$python_bin -m uvicorn simulator.tabletop50.server:app --host 127.0.0.1 --port 18661 --workers 1
Restart=on-failure
RestartSec=5
KillMode=control-group
UMask=0077
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable videoicl-tabletop50-fpv.service
systemctl --user restart videoicl-tabletop50-fpv.service
for attempt in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:18661/health; then exit 0; fi
  sleep 1
done
exit 1
