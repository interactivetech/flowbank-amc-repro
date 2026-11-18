#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
export AMC_MODEL_PROFILE=redhat
SCREEN_ROOT="${SCREEN_ROOT:-$AMC_ROOT/screening/deepmath-v1}"
SCREEN_PYTHON="$AMC_ROOT/screening-env/bin/python"
case "${1:-}" in
  setup)
    "$AMC_ROOT/runtime/bin/python" -m venv "$AMC_ROOT/screening-env"
    "$SCREEN_PYTHON" -m pip install -r requirements.screening.lock.txt
    ;;
  prepare)
    "$SCREEN_PYTHON" -m amc_repro.screening prepare --root "$SCREEN_ROOT" \
       --exclude "$AMC_ROOT/deepmath/frozen/manifest.json"
    ;;
  preflight|status|audit-export|finalize)
    "$SCREEN_PYTHON" -m amc_repro.screening "$1" --root "$SCREEN_ROOT"
    ;;
  run)
    "$SCREEN_PYTHON" -m amc_repro.screening run --root "$SCREEN_ROOT" &
    SCREEN_PID=$!
    trap 'kill -TERM "$SCREEN_PID" 2>/dev/null || true; wait "$SCREEN_PID" || true; exit 0' TERM INT
    wait "$SCREEN_PID"
    ;;
  *) echo 'Usage: screen_deepmath.sh {setup|prepare|preflight|run|status|audit-export|finalize}' >&2; exit 2 ;;
esac
