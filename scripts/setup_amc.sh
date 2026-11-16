#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/amc_env.sh
mkdir -p "$AMC_ROOT" "$AMC_TMPDIR" "$AMC_ROOT/logs"
PYTHON312="${AMC_PYTHON312:-/scratch1/mendeza/CREST_mendeza_b300/env/bin/python}"
"$PYTHON312" -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
"$PYTHON312" -m venv "$AMC_ROOT/runtime"
"$PYTHON312" -m venv "$AMC_ROOT/executor"
"$AMC_ROOT/runtime/bin/python" -m pip install -r requirements.slurm.txt
"$AMC_ROOT/executor/bin/python" -m pip install -r requirements.executor.txt
"$AMC_ROOT/runtime/bin/python" -m pip freeze > "$AMC_ROOT/runtime.freeze.txt"
"$AMC_ROOT/executor/bin/python" -m pip freeze > "$AMC_ROOT/executor.freeze.txt"
"$AMC_ROOT/runtime/bin/python" -m amc_repro.local_runtime prepare
