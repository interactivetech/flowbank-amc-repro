# FlowBank rerun on the 21 screened questions

This is an **exploratory experiment; dataset audit pending**. It evaluates a fresh single-model baseline and the existing fixed FlowBank W1–W4 on all 21 selected questions (105 evaluations). Lower baseline accuracy is a hypothesis, never a launch or success criterion. No workflow optimization, new selection, label correction, or audit approval is performed.

## Frozen input and settings

Dataset: `mendeza-umd/deepmath-103k-qwen-3-8-27b-screened-v1-provisional-21`, revision `5ad55d34498601997f551d5080301648e26e9db6`. The verified local upload is authoritative; preparation checks its parquet SHA-256 against the committed constant and matches all selected IDs, question text, references, and screening results against private evidence. The frozen manifest is protected by a separate integrity digest, not an audited lock. The runner and analysis require `--allow-provisional-screening`; audited v2 validation remains mandatory for audited inputs.

Model: `RedHatAI/Qwen3.8-27B-INT4`, revision `e45c27e8f463817db788d141a73a3c235a0a7c0c`. One B300, tensor parallelism one, no speculative decoding, thinking enabled, context 262,144, output cap 131,072, temperature zero, top-p one, seed 42, concurrency two, 30 requests/minute, request timeout 14,400 seconds, three transport retries. Existing workflows, prompts, grading, routing, and executor limits are retained. Only question text enters generation. All model calls are fresh; screening and historical experiment responses are never evaluation checkpoints.

Pilot rows are 68549, 77420, 11841, 14981, and 28981 (one per bucket), followed by the remaining selected rows in ascending source-row order. Frozen nested cohorts at thresholds 100%, 75%, 50%, 25%, and 0% contain 21, 16, 12, 8, and 5 questions.

## Commit before inference

Branch: `screened21-flowbank-rerun`. Snapshot commit `09d6fbd` records the clean original code at parent `61969f4` before implementation. Commit and push all implementation, tests and documentation before launch. The pipeline requires a clean branch whose HEAD matches the remote, and records this implementation commit before serving or inference. Do not edit the checkout during the experiment. The final automatic aggregate-results commit is created only after all 105 evaluations and final analysis finish.

## Offline checks and launch

Run from the repository root:

```bash
bash scripts/run_screened21.sh prepare
source scripts/amc_env.sh
"$AMC_ROOT/runtime/bin/python" -m pytest -q --basetemp "$AMC_ROOT/tmp/screened21-tests"
git diff --check
```

Preparation uses the existing screening environment for parquet support and never calls a model. In the authorized running GPU allocation, launch the committed pipeline as a persistent Slurm step:

```bash
srun --jobid=8476106 --overlap --nodes=1 --ntasks=1 \
  --gres=gpu:b300-sxm:1 --cpus-per-task=16 --mem=256G \
  --time=7-00:00:00 bash scripts/run_screened21.sh pipeline
```

The pipeline starts or reuses a healthy pinned endpoint, verifies it with the endpoint check, runs the 25-evaluation pilot, inspects it, and automatically resumes the remaining 80 evaluations. Pilot gates require complete evaluations and token accounting, zero failed evaluations, zero grader exceptions, and zero context overflows. Parsing failures, truncations, and handled Programmer retries are reported without gating on accuracy. Operational failures pause or stop the pipeline and record the reason. It never fills failed evaluations with mathematical-error labels.

Successful evaluations and successful model calls within unfinished workflows are checkpointed. The pipeline forwards allocation signals to the active runner. After interruption, rerun the same pipeline command in a valid GPU allocation with the same checkout/environment. Existing configuration, source, model, executor, and manifest must match. Locks reject duplicate pipelines and runners.

## Monitoring and final output

```bash
bash scripts/run_screened21.sh status
```

Scratch results: `$AMC_ROOT/results/deepmath21_screened_redhat_int4`. `pipeline_status.json` records phases/errors; `pilot_inspection.json` reports diagnostic gates and estimated remaining time. The estimate is based on pilot request latencies and may underestimate difficult questions.

Final analysis requires all 105 evaluations. Outputs include baseline and portfolio tables, per-item correctness, all 15 workflow-subset unions, nested cohort metrics, token costs, parse/truncation diagnostics, a descriptive screening/greedy/fresh-baseline comparison, and two figures in PNG/PDF/SVG. Cross-dataset AMC comparisons explicitly identify the different quantized checkpoint. Screening temperature 0.6 differs from the fresh greedy baseline. Bucket labels are not verified mathematical difficulty and the oracle is retrospective, not a deployable selector.

The pipeline copies an explicit allowlist of aggregates and figures to `experiment_results/deepmath21_screened_redhat_int4`, adds hashes and provenance, and commits/pushes that archive on the experiment branch. It does not copy questions, references, raw outputs, traces, credentials, or local dataset manifests. To repeat final analysis offline:

```bash
bash scripts/run_screened21.sh analyze
```
