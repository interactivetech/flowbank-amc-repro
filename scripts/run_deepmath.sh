#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
PYTHON="$AMC_ROOT/runtime/bin/python"
FROZEN="$AMC_ROOT/deepmath/frozen"
RESULTS="$AMC_ROOT/results/deepmath26"
case "${1:-}" in
  freeze)
    # Network access only when the exact revision is absent; no inference.
    SOURCE=$("$PYTHON" - <<'PY'
from huggingface_hub import hf_hub_download
from amc_repro.deepmath import REPOSITORY, REVISION, FILENAME
print(hf_hub_download(REPOSITORY, FILENAME, repo_type='dataset', revision=REVISION))
PY
)
    "$PYTHON" -m amc_repro.deepmath --source "$SOURCE" --output-dir "$FROZEN"
    ;;
  pilot|full)
    EXTRA=()
    [[ ! -f "$RESULTS/config.json" ]] || EXTRA+=(--resume)
    if [[ "$1" == pilot ]]; then
      EXTRA+=(--limit-items 5)
    else
      # Full is an explicit second action after the user inspects the pilot.
      "$PYTHON" - "$RESULTS" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])/'pilot_inspection.json'
if not p.exists() or json.loads(p.read_text())['completed'] != 25:
    raise SystemExit('Run pilot and analyze-pilot before explicitly resuming full.')
PY
    fi
    "$PYTHON" -m amc_repro.run --local-runtime --dataset-format deepmath-screened \
      --dataset "$FROZEN/manifest.json" --sample-size 26 --seed 42 \
      --workflows baseline,W1,W2,W3,W4 --results-dir "$RESULTS" \
      --temperature 0 --top-p 1 --inference-seed 42 --max-tokens 131072 \
      --thinking on --concurrency 2 --requests-per-minute 30 --timeout 14400 \
      "${EXTRA[@]}"
    ;;
  analyze-pilot|status)
    "$PYTHON" -m amc_repro.deepmath_analysis pilot --results-dir "$RESULTS"
    ;;
  analyze)
    "$PYTHON" -m amc_repro.deepmath_analysis final --results-dir "$RESULTS"
    ;;
  *) echo 'Usage: bash scripts/run_deepmath.sh {freeze|pilot|analyze-pilot|full|status|analyze}' >&2; exit 2 ;;
esac
