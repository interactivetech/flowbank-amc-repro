#!/usr/bin/env bash
#SBATCH --account=cml-furongh
#SBATCH --partition=cml-furongh
#SBATCH --qos=cml-high_long
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:b300-sxm:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=256G
#SBATCH --time=1-00:00:00
#SBATCH --signal=B:TERM@180
#SBATCH --job-name=deepmath-screen-v1
set -euo pipefail
: "${SCREEN_REPO:?Pass SCREEN_REPO in sbatch --export}"
cd "$SCREEN_REPO"
source scripts/amc_env.sh
export AMC_MODEL_PROFILE=redhat
SCREEN_ROOT="${SCREEN_ROOT:-$AMC_ROOT/screening/deepmath-v1}"
export SCREEN_ROOT
# Verify the source gate before serving or resuming. Serving performs no inference.
"$AMC_ROOT/screening-env/bin/python" -c 'from amc_repro.screening import commit_gate; print(commit_gate())'
if [[ -f "$SCREEN_ROOT/screening_complete.json" ]]; then exit 0; fi
# PID files are node-local process identities; never trust a stale PID after allocation expiry.
rm -f "$AMC_ROOT/deployments/redhat/vllm.pid"
bash scripts/start_vllm.sh
for attempt in {1..900}; do
    if curl --fail --silent http://127.0.0.1:8000/health >/dev/null; then break; fi
    sleep 2
done
curl --fail --silent http://127.0.0.1:8000/health >/dev/null
bash scripts/screen_deepmath.sh run &
SCREEN_WRAPPER=$!
trap 'kill -TERM "$SCREEN_WRAPPER" 2>/dev/null || true; wait "$SCREEN_WRAPPER" || true; exit 0' TERM INT
wait "$SCREEN_WRAPPER"
