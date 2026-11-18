# DeepMath: workflow complementarity as baseline solve rate decreases

> **Screening audit notice (2026-11-18):** Historical screening rates have a confirmed Boolean grading defect and do not validate difficulty strata. Counts and figures are retained as recorded. See [the postmortem](DEEPMATH_SCREENING_POSTMORTEM.md) for evidence, limits, and the replacement screening process.

## 1. Frozen experiment

Evaluate **all 26 screened questions** from `mendeza-umd/deepmath-103k-qwen-3-8-27b-results`, pinned to revision `e723e4604d862e25fa2c57313a7c37494a674c03`.

Run a **fresh single-model baseline plus W1–W4** on every question: **130 evaluations**. Use the existing AMC configuration:

- Qwen3.8-27B AutoRound INT4, same pinned checkpoint.
- Thinking enabled; temperature 0; top-p 1; seed 42.
- Maximum 131,072 generated tokens per call, including reasoning.
- Same workflow prompts, routing categories, execution limits, and retry rules.
- Two concurrent requests on one B300; environments, caches, and results on scratch.

Treat the historical `correct / 32` values as **screening difficulty labels**, not replacement baseline results. Their original decoding, quantization, and grading settings are not documented in the CSV. The sample was selected adaptively, so conclusions apply to these 26 questions.

Save this specification as `DEEPMATH_EXPERIMENT_PLAN.md` during implementation.

## 2. Dataset and grading support

Add `--dataset-format deepmath-screened` while preserving the existing AMC behavior.

- Map `question` to the workflow’s problem input and use `gold_answer` directly. Identify items as `deepmath-row-{dataset_row}`.
- Freeze the source revision, file hash, original rows, typed references, screening counts, and metadata before inference.
- Validate unique IDs, 32 screening responses per item, and agreement between `correct / responses` and `solve_rate`.
- Pass only the original question to workflows. Screening outcomes, difficulty labels, references, and other workflows’ correctness must never enter generation or selection.

Extend grading before running: the current AMC grader cannot fairly handle all references.

- For the six multiple-choice questions, freeze mappings between option letters and option expressions. Accept an explicit correct letter or a mathematically equivalent final expression.
- For the `Yes` reference, support explicit final yes/no answers and Boolean code returns.
- Retain mathematical equivalence grading for expressions, sets, infinities, and angles; normalize imaginary-unit notation for the complex-number question.
- Test all 26 references and representative equivalent/incorrect answers before inference. Record suspected reference problems before freezing; do not silently change labels after observing workflow results.

The historical screening rates remain unchanged. Without the original responses, we cannot determine whether some low rates reflect grading differences.

## 3. Two figures and supporting tables

**Figure 1 — Complementarity versus workflow count**

Produce an AMC/DeepMath comparison with two panels and a shared 0–100% accuracy axis.

- X-axis: number of workflows, **k = 1, 2, 3, 4**.
- Enumerate all 15 subsets of W1–W4.
- For each subset, accuracy is the fraction of questions solved by at least one member’s final answer.
- Show best-subset coverage, mean coverage, and the min–max range, matching the existing AMC analysis.
- Include each dataset’s single-model baseline and annotate the gain from the best individual workflow to the four-workflow oracle.
- Recompute the AMC panel from its archived correctness matrix; preserve the original AMC artifacts.

**Figure 2 — Oracle performance on progressively harder questions**

Use nested cohorts defined solely by the frozen historical screening rates:

| Maximum recorded solve rate | Questions |
|---|---:|
| 100% | 26 |
| 75% | 14 |
| 50% | 11 |
| 25% | 8 |
| 0% | 5 |

Order the x-axis from 100% to 0%, so difficulty increases toward the right.

- Upper panel: four-workflow oracle coverage, best individual workflow accuracy within that cohort, and fresh baseline accuracy.
- Lower panel: oracle coverage minus best individual workflow accuracy, in percentage points.
- Label every cohort’s N and retain solved counts. These are overlapping cohorts, not independent samples.
- Describe 0/32 as “no observed screening successes,” not proof that the question is unsolvable.

Also generate the two AMC-style result tables, per-item correctness, all-subset coverage, cohort metrics, token costs, parsing failures, and truncation counts. Export figures as PNG/PDF/SVG and numerical data as CSV.

## 4. Pilot, execution, and recovery

Freeze all 26 items, placing these five pilot IDs first to cover the screening range and exercise categorical grading: **45570, 3226, 791, 1659, 96**. Order the remaining items by dataset row.

1. Run local tests and reference preflight without model calls.
2. Run the five-item pilot across all five conditions: **25 evaluations**.
3. Inspect grading, code execution, context overflow, truncation, and token usage.
4. Estimate remaining runtime from measured pilot generation and latency.
5. Explicitly resume the remaining **105 evaluations**, reusing pilot checkpoints.
6. Generate final tables and figures only after all 130 evaluations complete.

Expect at least **442 model calls** overall, plus Programmer retries. Hard questions may consume the full output allowance, so do not assume one ten-hour allocation will suffice. Preserve checkpoints and resume after scavenger preemption or allocation expiry.

Implementation should provide user-run commands; it must not automatically launch inference.

## 5. Validation and deliverables

Test dataset mapping, typed grading, unchanged AMC behavior, pilot-to-full resume, baseline-relative wins, exhaustive subset unions, and threshold membership—including the five 0/32 items. Verify that cohort membership cannot change based on new outcomes.

Keep private question text, solutions, and raw traces on scratch. Prepare a Markdown results report, aggregate tables, both figures, and reproducible plotting commands. Publishing private dataset contents requires separate authorization.
