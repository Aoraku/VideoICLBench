#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "$ROOT_DIR"

"$PYTHON_BIN" backend/manage.py test \
  chat.tests.MessageViewTest \
  chat.tests.GroupViewTest \
  chat.tests.CoverageBoostEdgeCaseTest \
  chat.tests.UploadViewTest \
  chat.tests.SyncMessagesViewTest \
  chat.tests.AIViewTest
