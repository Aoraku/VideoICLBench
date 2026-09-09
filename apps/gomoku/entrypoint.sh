#!/bin/bash
set -euo pipefail
export DISPLAY=:1
export SDL_VIDEO_X11_REQUIRE_WM=0
export SDL_RENDER_DRIVER=software
Xvfb :1 -screen 0 1280x960x24 &
xvfb_pid=$!
trap 'kill "$xvfb_pid" ${vnc_pid:-} ${web_pid:-} 2>/dev/null || true' EXIT
for attempt in $(seq 1 50); do
  if xdpyinfo -display :1 >/dev/null 2>&1; then break; fi
  sleep 0.1
done
xdpyinfo -display :1 >/dev/null
x11vnc -forever -shared -rfbport 5900 -display :1 -nopw -quiet &
vnc_pid=$!
websockify --web=/usr/share/novnc 6080 localhost:5900 &
web_pid=$!
cd /app
/app/build/gomoku_benchmark
