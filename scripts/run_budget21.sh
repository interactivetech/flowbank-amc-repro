#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
export AMC_MODEL_PROFILE=redhat
FROZEN="$AMC_ROOT/deepmath/screened21/frozen"
RESULTS="$AMC_ROOT/results/deepmath21_budget128k_redhat_int4"
PYTHON="$AMC_ROOT/runtime/bin/python"
case "${1:-}" in
  prepare)
    "$AMC_ROOT/screening-env/bin/python" -m amc_repro.screened_experiment \
      --source "$AMC_ROOT/hf_deepmath_screened_21_upload/data/test.parquet" \
      --screening-root "$AMC_ROOT/screening/deepmath-v1-extension-1" --output-dir "$FROZEN"
    ;;
  pilot|full)
    EXTRA=()
    [[ ! -f "$RESULTS/config.json" ]] || EXTRA+=(--resume)
    if [[ "$1" == pilot ]]; then
      EXTRA+=(--limit-items 5)
    else
      "$PYTHON" - "$RESULTS" <<'PY'
import json,sys
from pathlib import Path
from amc_repro.screened_pipeline import pilot_flags
p=Path(sys.argv[1])/'pilot_inspection.json'
if not p.exists(): raise SystemExit('Run and inspect the pilot first.')
flags=pilot_flags(json.loads(p.read_text()))
if flags: raise SystemExit('Pilot operational checks failed: '+str(flags))
PY
    fi
    exec "$PYTHON" -m amc_repro.run --local-runtime --dataset-format deepmath-screened \
      --dataset "$FROZEN/manifest.json" --allow-provisional-screening \
      --generated-budget-profile portfolio-128k-generated-v1 \
      --model-lock "$AMC_ROOT/deployments/redhat/model.lock.json" \
      --results-dir "$RESULTS" "${EXTRA[@]}"
    ;;
  analyze-pilot|analyze)
    ACTION=pilot
    [[ "$1" != analyze ]] || ACTION=final
    exec "$PYTHON" -m amc_repro.deepmath_analysis "$ACTION" --results-dir "$RESULTS" \
      --allow-provisional-screening
    ;;
  status)
    "$PYTHON" - "$RESULTS" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for name in ('pipeline_status.json','run_status.json','pilot_inspection.json'):
    if (root/name).exists(): print(name, (root/name).read_text())
print('Completed evaluations:',len(list(root.glob('evaluations/*/*/result.json'))),'/ 105')
PY
    ;;
  pipeline) exec "$PYTHON" -m amc_repro.screened_pipeline --budget-controlled ;;
  *) echo 'Usage: run_budget21.sh {prepare|pilot|full|analyze-pilot|analyze|status|pipeline}' >&2; exit 2 ;;
esac
