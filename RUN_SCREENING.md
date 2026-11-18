# Operating the corrected DeepMath screen

Run from the repository root. Private artifacts belong under `/scratch1/mendeza/flowbank-amc/screening/deepmath-v1`. [The postmortem](DEEPMATH_SCREENING_POSTMORTEM.md) explains the historical audit limitation; [the specification](SCREENING_SPEC.md) freezes selection and request settings.

```bash
bash scripts/screen_deepmath.sh setup
bash scripts/screen_deepmath.sh prepare
# Offline checks. The scratch basetemp also exercises legacy private-path guards.
source scripts/amc_env.sh
"$AMC_ROOT/screening-env/bin/python" -m pytest tests/test_screening.py -q
"$AMC_ROOT/runtime/bin/python" -m pytest --basetemp "$AMC_ROOT/tmp/screening-tests" -q
git diff --check
```

Review all staged content for secrets, private questions/references, raw outputs, and traces. Commit on `slurm_env`, push, and compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/slurm_env`. The working tree must be clean. The run command enforces the gate before calibration, pins the complete dependency lock, and writes the verified commit, source hashes, environment versions, dataset hashes, prompt, grader, deployment identity, and configuration to `run_manifest.json`. Do not edit source during a run.

After that gate, launch inside the current GPU allocation, retaining its RedHat server:

```bash
nohup bash scripts/screen_deepmath.sh run > "$AMC_ROOT/screening/deepmath-v1/run.log" 2>&1 < /dev/null &
echo $! > "$AMC_ROOT/screening/deepmath-v1/wrapper.pid"
bash scripts/screen_deepmath.sh status
```

Configure continuation only after the same commit gate. Replace the old allocation ID if needed:

```bash
export SCREEN_REPO="$PWD"
sbatch --dependency=afterany:8437053 --export=ALL,SCREEN_REPO \
  --output="$AMC_ROOT/screening/deepmath-v1/continuation-%j.log" \
  scripts/continue_screening.sbatch
```

The continuation requests one B300, starts the pinned server without inference, waits for health, and resumes the same run and remaining active-time budget. It exits without serving when screening is complete. TERM signals checkpoint and stop the runner. On interruption, rerun the same `run` command; successful raw responses are reused, including responses not yet graded. The `.screening.lock` prevents concurrent runners. Inspect `budget.json`, `status.json`, `attempts/`, `rollouts/`, and `greedy/`; use the status command for current budget accounting. Do not restart the preserved historical supervisor.

```bash
bash scripts/screen_deepmath.sh audit-export
```

Review `review_packet.json` and each selected reference. Enter a scratch `audit.json` mapping question IDs to records with `decision` (`accept` or `quarantine`), a nonempty `reviewer`, `reference_checked: true`, the packet's `evidence_sha256`, and `incorrect_checked` (the reviewed rollout indices). For the two lowest buckets include every index in `incorrect_required`. These are manual decisions: do not populate approvals automatically. A systemic grading correction requires a committed version and consistent regrading of all affected saved responses; v1 rejects changed source on resume rather than silently mixing graders.

After `screening_complete.json` exists, run `finalize`. It rejects missing or stale audits, emits `manifest.json` and its integrity lock, and supports an audited smaller set at budget exhaustion. The historical 26-item loader remains supported. Quotas are targets, not a guarantee.

Workflow evaluation is a separate explicit step after the audit. The command below is provided for the operator and is not launched by screening:

```bash
export AMC_MODEL_PROFILE=redhat
"$AMC_ROOT/runtime/bin/python" -m amc_repro.run --local-runtime \
  --dataset-format deepmath-screened \
  --dataset "$AMC_ROOT/screening/deepmath-v1/manifest.json" \
  --model-lock "$AMC_ROOT/deployments/redhat/model.lock.json" \
  --results-dir "$AMC_ROOT/results/deepmath-screen-v1-workflows"
```

Omit `--sample-size` to use the audited manifest size. A later resume of workflow evaluation requires `--resume`.
