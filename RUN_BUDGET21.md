# DeepMath: controlled generated-token budget

**Authorized design:** one direct baseline receives at most **131,072 generated tokens per question**. Each complete fixed workflow W1–W4 receives at most **32,768 generated tokens**, so their combined oracle portfolio receives the same maximum **131,072**. Reasoning tokens count. Input tokens and Python executor compute do not count toward the controlled allowance and are reported separately. This controls generated-token allowances, not FLOPs, wall time, total tokens, or actual equal spending.

## Dataset, model, and conditions

Reuse the exact [21-question provisional selection](RUN_SCREENED21.md) from Hugging Face repo `mendeza-umd/deepmath-103k-qwen-3-8-27b-screened-v1-provisional-21`, revision `5ad55d34498601997f551d5080301648e26e9db6`. The freeze checks uploaded parquet hashes, membership, references, and saved screening evidence. Manual audit remains pending; no new approval or relabeling is implied.

Run 105 fresh evaluations (21 questions × baseline/W1/W2/W3/W4). Do not reuse the previous experiment's responses, even for the unchanged baseline. Keep the same five pilot questions, model `RedHatAI/Qwen3.8-27B-INT4` at `e45c27e8f463817db788d141a73a3c235a0a7c0c`, prompts, workflow graphs, reference grader, and executor limits. Use one B300, thinking enabled, temperature zero, top-p one, seed 42, context 262,144, concurrency two, and no speculative decoding.

The purpose is to compare the full portfolio's oracle coverage against the single baseline at equal maximum generated-token allowance, overall and within independent screening buckets. Individual workflows receive one quarter of the baseline allowance and must be labeled accordingly. The oracle still uses ground truth retrospectively. No deployable selector or repeated direct-sampling control is implemented in this experiment.

## Fixed stage allocations and enforcement

The committed profile is `portfolio-128k-generated-v1`:

| Condition | Per-question generated-token allowance | Per-call stage limits |
|---|---:|---|
| Baseline | 131,072 | Direct solution: 131,072 |
| W1 | 32,768 | Three candidates: 8,192 each; selection: 8,192 |
| W2 | 32,768 | Three candidates: 8,192 each; selection: 4,096; each Programmer attempt: at most 4,096 from remaining wallet |
| W3 | 32,768 | Same allocations as W2 |
| W4 | 32,768 | Classification: 1,024; specialist: 31,744 |

Every request uses `min(stage limit, remaining wallet)`. W2/W3 retain at most three Programmer attempts, all sharing the same wallet. Unused early-call tokens can fund later code retries within these limits; tokens are not transferred between workflows. Early stopping can leave unused allowance. Stage allocations are a frozen design choice and are not optimized using new outcomes.

A durable reservation is written before each request. Raw successful response events, including usage and reasoning, are saved before returning a stage output. Resume replays those saved outputs and reconstructs spending without resetting the wallet. Missing/invalid usage or spending above the requested cap is an operational error.

**Transport handling differs from the prior run:** automatic transport retries are disabled in the budgeted path. A disconnected or interrupted request may have consumed unreported output. Its full requested allowance stays conservatively reserved and that evaluation cannot silently regenerate the call. The pipeline stops for operational review rather than claiming unknown spending is zero. This does not affect completed-response replay or bounded Programmer retries.

When no generated tokens remain for a required stage, the evaluation is recorded as completed and unsuccessful with `grading_status=budget_exhausted`. There is no correctness-dependent fallback to earlier candidates. Parse failures and truncations remain observed outcomes. Infrastructure failures are not scored as mathematical errors.

## Execution and monitoring

Use branch `budget128k-deepmath`. Commit and push implementation, tests, and this specification before inference; the pipeline requires matching clean local/remote HEAD. All new results use `$AMC_ROOT/results/deepmath21_budget128k_redhat_int4`; historical runs remain intact.

```bash
bash scripts/run_budget21.sh prepare
source scripts/amc_env.sh
"$AMC_ROOT/runtime/bin/python" -m pytest -q --basetemp "$AMC_ROOT/tmp/budget21-tests"
git diff --check
# After commit/push, inside the authorized GPU allocation:
bash scripts/run_budget21.sh pipeline
# Monitor:
bash scripts/run_budget21.sh status
```

Launch as a persistent Slurm step. Endpoint calibration is separate from question evaluation. Run a five-question/25-evaluation pilot, inspect it, then automatically continue to the remaining 80 evaluations when operational checks pass. Gates require all pilot evaluations, complete token usage, no context overflows, no failed evaluations, no grader exceptions, and zero budget violations. Low accuracy, parse failures, truncations, and legitimate budget exhaustion do not trigger outcome-based changes.

On interruption, preserve ledgers. Successful saved responses can be reused under the same configuration and source. Unresolved requests require review; do not delete reservations or reset a wallet to resume. The pipeline and runner reject concurrent writers.

## Analysis and artifacts

Final results require all 105 evaluations. Include:

- Fresh baseline and workflow accuracy, full oracle coverage, and independent screening-bucket results.
- Per-condition generated-token allowance, measured input/output usage, budget exhaustion, parsing failures, truncation, and latency.
- A compliance artifact confirming every workflow uses at most 32,768 generated tokens and the portfolio at most 131,072 per question.
- Existing complementarity/cohort plots and tables; comparisons to the prior run are descriptive because stage caps differ.

The pipeline archives an explicit aggregate allowlist under `experiment_results/deepmath21_budget128k_redhat_int4`, records provenance and hashes, and commits/pushes the final results on the experiment branch. Questions, references, reasoning, and raw traces stay on scratch. Reproduce final analysis with `bash scripts/run_budget21.sh analyze`.

Motivation: [experiment overview](EXPERIMENT_OVERVIEW.md) and [prior token-cost critique](experiment_results/deepmath21_screened_redhat_int4/comparison/TOKEN_COST_COMPARISON.md). The provisional, adaptively selected dataset and small bucket sizes limit generalization, and output-budget matching alone does not establish total-compute equivalence.
