#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
: "${SLURM_JOB_ID:?Start inside a GPU Slurm allocation}"
mkdir -p "$AMC_ROOT/logs" "$AMC_TMPDIR"
PIDFILE="$AMC_ROOT/vllm.pid"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Launcher already running: $(cat "$PIDFILE")" >&2
    exit 1
fi
nohup "$AMC_ROOT/runtime/bin/python" -u -m amc_repro.local_runtime serve \
    >> "$AMC_ROOT/logs/vllm.log" 2>&1 < /dev/null &
echo "$!" > "$PIDFILE"
echo "Started launcher PID $! in Slurm job $SLURM_JOB_ID"
echo "Log: $AMC_ROOT/logs/vllm.log"
echo 'Readiness: curl --fail http://127.0.0.1:8000/health'
