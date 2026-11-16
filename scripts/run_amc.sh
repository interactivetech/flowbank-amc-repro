#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
PYTHON="$AMC_ROOT/runtime/bin/python"
RESULTS="$AMC_ROOT/results/amc50"
case "${1:-}" in
  check)
    "$PYTHON" -m amc_repro.check_endpoint --local-runtime --results-dir "$AMC_ROOT/results/endpoint"
    ;;
  pilot|full)
    EXTRA=()
    [[ ! -f "$RESULTS/config.json" ]] || EXTRA+=(--resume)
    [[ "$1" != pilot ]] || EXTRA+=(--limit-items 3)
    "$PYTHON" -m amc_repro.run --local-runtime --sample-size 50 --seed 42 \
      --workflows baseline,W1,W2,W3,W4 --results-dir "$RESULTS" \
      --temperature 0 --top-p 1 --inference-seed 42 --max-tokens 131072 \
      --thinking on --concurrency 2 --requests-per-minute 30 --timeout 14400 \
      "${EXTRA[@]}"
    ;;
  analyze-pilot)
    "$PYTHON" -m amc_repro.analyze --results-dir "$RESULTS" --limit-items 3
    ;;
  analyze)
    "$PYTHON" -m amc_repro.analyze --results-dir "$RESULTS"
    ;;
  status)
    "$PYTHON" - "$RESULTS" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
records = [json.loads(p.read_text()) for p in root.glob('evaluations/*/*/result.json')]
print(json.dumps({'completed':len(records),'expected':250,
                 'truncated_calls':sum(r.get('truncated_calls',0) for r in records),
                 'parse_failures':sum(r['grading_status']=='parse_failure' for r in records)},indent=2))
if (root/'run_status.json').exists(): print((root/'run_status.json').read_text())
for p in root.glob('evaluations/*/*/failure.json'):
    print(p, json.loads(p.read_text())['error'])
PY
    ;;
  *) echo 'Usage: bash scripts/run_amc.sh {check|pilot|analyze-pilot|full|status|analyze}' >&2; exit 2 ;;
esac
