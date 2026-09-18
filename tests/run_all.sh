#!/usr/bin/env bash
# Runs both halves of the suite. They must be separate processes: server/ and client/
# each define a top-level `models` package that would otherwise collide (see conftest.py
# at the repo root). Extra arguments are forwarded to both pytest invocations.
set -u
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
status=0
echo "=== server tests ==="
"$PY" -m pytest tests/server "$@" || status=1
echo
echo "=== client tests ==="
QT_QPA_PLATFORM=offscreen "$PY" -m pytest tests/client "$@" || status=1
exit $status
