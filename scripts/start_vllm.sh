#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
: "${SLURM_JOB_ID:?Start inside a GPU Slurm allocation}"
mkdir -p "$AMC_ROOT/logs" "$AMC_TMPDIR"
DEPLOYMENT="$AMC_ROOT"
[[ "${AMC_MODEL_PROFILE:-autoround}" != redhat ]] || DEPLOYMENT="$AMC_ROOT/deployments/redhat"
mkdir -p "$DEPLOYMENT"
PIDFILE="$DEPLOYMENT/vllm.pid"
SERVER_LOG="$AMC_ROOT/logs/vllm.log"
[[ "${AMC_MODEL_PROFILE:-autoround}" != redhat ]] || SERVER_LOG="$DEPLOYMENT/vllm.log"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Launcher already running: $(cat "$PIDFILE")" >&2
    exit 1
fi
nohup "$AMC_ROOT/runtime/bin/python" -u -m amc_repro.local_runtime serve \
    >> "$SERVER_LOG" 2>&1 < /dev/null &
SERVER_PID=$!
echo "$SERVER_PID" > "$PIDFILE"
# Keep the launching shell alive until Python has detached its process group.
# Otherwise command-session cleanup can terminate it before os.setsid().
DETACHED=false
for attempt in {1..150}; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Server exited during startup; inspect $SERVER_LOG" >&2
        exit 1
    fi
    SERVER_GROUP=$(ps -o pgid= -p "$SERVER_PID" | tr -d ' ')
    if [[ "$SERVER_GROUP" == "$SERVER_PID" ]]; then
        DETACHED=true
        break
    fi
    sleep 0.2
done
if [[ "$DETACHED" != true ]]; then
    echo "Server has not detached after 30 seconds; inspect $SERVER_LOG" >&2
    exit 1
fi
echo "Started launcher PID $SERVER_PID in Slurm job $SLURM_JOB_ID"
echo "Log: $SERVER_LOG"
echo 'Readiness: curl --fail http://127.0.0.1:8000/health'
