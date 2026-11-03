#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
: "${VIC_ISAACLAB_ROOT:?Set VIC_ISAACLAB_ROOT to IsaacLab checkout}"
: "${VIC_ISAAC_PYTHON:?Set VIC_ISAAC_PYTHON to an existing Isaac Sim Python environment}"
export PYTHONPATH="$project_dir:$VIC_ISAACLAB_ROOT/source/isaaclab:$VIC_ISAACLAB_ROOT/source/isaaclab_assets:$project_dir/vendor/python:${PYTHONPATH:-}"
if [ -n "${VIC_ISAACSIM_ROOT:-}" ]; then export ISAACSIM_PATH="$VIC_ISAACSIM_ROOT"; fi
export ACCEPT_EULA=Y
export OMNI_KIT_ACCEPT_EULA=YES
exec "$VIC_ISAAC_PYTHON" "$@"
