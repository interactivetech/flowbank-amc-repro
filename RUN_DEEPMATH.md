# DeepMath experiment commands

Specification: [approved experiment plan](DEEPMATH_EXPERIMENT_PLAN.md). This implementation never starts inference automatically. The offline freeze has been validated on the pinned source. See `EXPERIMENT_STATUS.md` for the current launch state; avoid starting a duplicate pipeline.

Use the same B300 allocation, pinned server, runtime, executor, and scratch cache as [RUN_AMC.md](RUN_AMC.md) and [B300_SCAVENGER.md](B300_SCAVENGER.md). The model revision must match the archived AMC checkpoint (`a6754efcde1ea362616353759f0c97507775a5a9`). Preserve `AMC_ROOT`; do not rerun model preparation against a new revision. The server command remains `bash scripts/start_vllm.sh` in the GPU allocation. Keep two requests concurrent on one B300.

From the repository root, run offline preparation and tests (no model calls):

```bash
source scripts/amc_env.sh
"$AMC_ROOT/runtime/bin/python" -m pip install -r requirements.analysis.txt
"$AMC_ROOT/runtime/bin/python" -m pytest -q --basetemp "$AMC_ROOT/tmp/deepmath-tests"
bash scripts/run_deepmath.sh freeze
```

`freeze` downloads only the exact approved dataset revision if absent. It verifies the pinned CSV SHA-256, all 26 unique IDs, screening counts/rates, option mappings, references, and cohort sizes. It writes the original CSV, original rows, typed references, screening metadata, cohort memberships, pre-inference reference concerns, and representative grading checks to `$AMC_ROOT/deepmath/frozen`. Repeating it cannot change a frozen manifest. The questions, solutions, references, and raw traces remain on scratch. Source code and aggregate results may be reviewed without copying private text into the repository.

Start only the pilot after the server is ready:

```bash
bash scripts/run_deepmath.sh pilot
bash scripts/run_deepmath.sh analyze-pilot
```

The full 26-item manifest is frozen at the start. The pilot schedules rows 45570, 3226, 791, 1659, 96 across baseline and W1–W4 (25 evaluations). Results go to `$AMC_ROOT/results/deepmath26`. Inspect `pilot_inspection.json`, `pilot_analysis/`, and the per-evaluation traces, including code execution errors, context overflow, parsing failures, truncation, tokens, and grading. The inspection estimates remaining runtime using measured request latencies at concurrency two, scaled to 105 remaining evaluations. This is a rough projection; screening difficulty, long generations, retries, and server contention can change runtime substantially.

After inspecting the pilot, explicitly resume:

```bash
bash scripts/run_deepmath.sh full
```

Repeat the same command after allocation expiry or scavenger preemption. Completed evaluations and successful calls within unfinished workflows are reused. Configuration, source code, manifest, model identity and executor must match; changing code after the pilot intentionally prevents an unrecorded mixed experiment. There are 130 evaluations in total, at least 442 model calls plus Programmer retries. Do not assume a ten-hour allocation is enough. The full command never runs automatically after the pilot.

Generate final results only after all 130 evaluations are complete:

```bash
bash scripts/run_deepmath.sh analyze
```

This generates the two AMC-style tables (`table1_baseline.*`, `table2_portfolio.*`) and correctness matrix under the results directory. `comparison/` contains:

- `RESULTS_REPORT.md` and both figures in PNG/PDF/SVG.
- `all_subset_coverage.csv` (15 subsets per dataset) and `complementarity_by_k.csv`.
- `cohort_metrics.csv` with N and solved counts, and `cohort_membership.csv`.
- `per_item_correctness.csv`, `evaluation_costs.csv`, and `condition_diagnostics.csv` with token usage, parsing failures, and truncation counts.

The AMC comparison is recomputed read-only from `experiment_results/amc50_qwen38_autoround_int4/correctness_matrix.csv`; archived artifacts are never overwritten. For a different archive location, use:

```bash
"$AMC_ROOT/runtime/bin/python" -m amc_repro.deepmath_analysis final \
  --results-dir "$AMC_ROOT/results/deepmath26" \
  --amc-results-dir experiment_results/amc50_qwen38_autoround_int4
```

Historical correct/32 values are screening labels with undocumented original settings. Cohorts (26, 14, 11, 8, 5 items at thresholds 100%, 75%, 50%, 25%, 0%) overlap and cannot change with new results. 0/32 means no observed screening successes. The oracle is retrospective union coverage, not a deployable selector. Reference concerns are recorded without relabeling; final-answer grading does not verify requested proofs. Publishing private dataset contents requires separate authorization.
