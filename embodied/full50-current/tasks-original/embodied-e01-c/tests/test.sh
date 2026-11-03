#!/bin/sh
set -eu
exec "${VIDEOICL_PYTHON:-python3}" "$(dirname "$0")/verify.py"
