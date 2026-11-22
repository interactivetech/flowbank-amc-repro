# DeepMath workflow complementarity

All 105 fresh evaluations on 21 adaptively screened questions are complete. Baseline: 47.6%; best individual: 57.1%; four-workflow oracle: 76.2%; gain: 19.0 percentage points.

Screening correct/32 values are frozen selection labels, not fresh baseline results. Conclusions apply to these 21 selected questions. Oracle uses final answers and ground truth retrospectively; it is an upper bound, not a deployable selector. Cohorts overlap and are defined solely by frozen screening rates. 0/32 means no observed screening successes, not unsolvability. Best individual is recomputed within each cohort.

![Complementarity](figure1_complementarity.png)

![Harder cohorts](figure2_harder_cohorts.png)

| Maximum screening rate | N | Oracle solved | Best individual solved | Baseline solved | Gain (pp) |
|---|---|---|---|---|---|
| 100% | 21 | 16 | 12 | 10 | 19.0 |
| 75% | 16 | 11 | 7 | 5 | 25.0 |
| 50% | 12 | 7 | 6 | 1 | 8.3 |
| 25% | 8 | 3 | 3 | 1 | 0.0 |
| 0% | 5 | 0 | 0 | 0 | 0.0 |

## Independent screening buckets

Each question appears in exactly one bucket below. Oracle coverage counts a question as solved when any of W1–W4 produces a correct final answer. These groups are separate from the overlapping threshold cohorts above.

| Screening correct / 32 | Questions | Baseline solved | Oracle solved | Oracle accuracy |
|---|---:|---:|---:|---:|
| 0/32 | 5 | 0/5 | 0/5 | 0.0% |
| 1-8/32 | 3 | 1/3 | 3/3 | 100.0% |
| 9-16/32 | 4 | 0/4 | 4/4 | 100.0% |
| 17-24/32 | 4 | 4/4 | 4/4 | 100.0% |
| 25-32/32 | 5 | 5/5 | 5/5 | 100.0% |
| **Overall** | **21** | **10/21** | **16/21** | **76.2%** |

The workflows collectively solved every selected question outside the 0/32 bucket. None of the five selected 0/32 questions was solved by baseline or any workflow in this run. Small group sizes and pending manual audit limit interpretation of these results.

[Independent bucket metrics (CSV)](independent_bucket_metrics.csv). Recompute by grouping `per_item_correctness.csv` on `bucket`, summing `baseline`, and counting rows where any of W1–W4 equals 1.

**Exploratory; dataset audit pending.** Parse failures count as unsuccessful screening responses; bucket labels do not establish verified mathematical difficulty. Screening used temperature 0.6; the fresh baseline uses temperature 0. Archived AMC used a different quantized checkpoint, so cross-dataset differences do not isolate difficulty.

Reference concerns were frozen before inference; supplied labels remain unchanged. See private reference_preflight.json and manifest.json. Proof validity is not graded.

[Baseline table](../table1_baseline.md) · [Portfolio table](../table2_portfolio.md) · [Costs and failures](condition_diagnostics.csv)

Reproduce: `bash scripts/run_screened21.sh analyze`. Private questions, solutions and traces stay on scratch; publishing them requires separate authorization.
