#!/usr/bin/env bash
#SBATCH --account=cml-furongh
#SBATCH --partition=cml-furongh
#SBATCH --qos=cml-default
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --job-name=deepmath-report
#SBATCH --requeue
set -euo pipefail
SCREEN_RUN_ROOT="$1"
REPORT_CHECKOUT="$2"
REPORT_UNTIL="$3"
cd "$REPORT_CHECKOUT"
exec /scratch1/mendeza/flowbank-amc/screening-env/bin/python \
  monitoring/screening_reporter.py tick --run-root "$SCREEN_RUN_ROOT" \
  --checkout "$REPORT_CHECKOUT" --until "$REPORT_UNTIL" --publish
