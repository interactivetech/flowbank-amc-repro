# FlowBank experiments: workflow complementarity, difficulty, and compute

This document is the central record of the experiments so far and the next experiment to run. It links to the original specifications, deployment notes, and result archives so each section can be expanded as the study develops.

**Current status:** AMC reproduction and the 21-question corrected-screening DeepMath evaluation are complete. The generated-token-budget DeepMath experiment is implemented and prepared for launch; its separate results are pending. The corrected DeepMath selection remains provisional pending manual audit.

## Purpose

Investigate when a portfolio of optimized workflows helps a language model solve mathematical questions, and when that complementarity breaks down as questions become more difficult.

The study separates three questions:

1. Can we reproduce the fixed FlowBank optimized workflow graphs and measure their accuracy under retrospective oracle selection?
2. How does their complementary coverage change across questions with different observed screening solve rates?
3. Does complementarity remain useful when baseline and workflows receive the same total compute allowance?

We evaluate existing fixed workflows, rather than rerunning workflow optimization. An oracle selector counts a question as solved when at least one workflow's final answer is correct. It uses ground truth retrospectively and is an upper bound, not a selector that can be deployed without knowing the answer.

## Experiment settings

All completed workflow comparisons use a fresh single-call baseline and the same fixed W1–W4:

| Condition | Behavior |
|---|---|
| Baseline | One direct solution |
| W1 | Three diverse candidate solutions followed by ensemble selection |
| W2 | Three analytical candidates, ensemble selection, and Python verification |
| W3 | Diverse candidates, ensemble selection, and Python verification |
| W4 | Question classification followed by a specialist solver |

Shared evaluation settings are thinking enabled, temperature 0, top-p 1, inference seed 42, a 262,144-token context, and a **131,072 generated-token cap per call**, including reasoning. Two concurrent requests run on one B300. W2/W3 execute generated Python with resource limits. Only question text enters generation; reference answers and screening outcomes are used retrospectively.

The cap is per call, not per question or portfolio. Workflows therefore have different total allowances. Report accuracy alongside input/output token usage, latency, parse failures, truncations, and operational failures. Keep oracle coverage separate from an individual workflow's selected-answer accuracy.

Details: [AMC specification](AMC_EXPERIMENT_PLAN.md), [implementation fidelity and limitations](REPRODUCTION_NOTES.md), and [corrected DeepMath run settings](RUN_SCREENED21.md).

## Model deployment

The runs use pinned Qwen3.8-27B quantized checkpoints served locally with vLLM on one NVIDIA B300 SXM6, tensor parallelism one, and no speculative decoding.

| Experiments | Model repository | Pinned revision |
|---|---|---|
| AMC and historical 26-question DeepMath | `MIRALABS/Qwen3.8-27B-W4A16-AutoRound` | `a6754efcde1ea362616353759f0c97507775a5a9` |
| Corrected screening and 21-question DeepMath | `RedHatAI/Qwen3.8-27B-INT4` | `e45c27e8f463817db788d141a73a3c235a0a7c0c` |

The RedHatAI checkpoint declares INT4 weights and an FP8 KV-cache quantization scheme. Deployment identities, environment versions, and request settings are recorded with each experiment. Changing quantized checkpoints is a confound in cross-experiment comparisons; AMC versus corrected DeepMath does not isolate difficulty alone.

Details: [deployment and runtime guide](RUN_AMC.md), [Slurm recovery guide](B300_SCAVENGER.md), and [RedHatAI deployment/rerun record](REDHAT_DEEPMATH_RERUN.md). The latter also documents a separate historical-dataset diagnostic rerun; its launch record is not a substitute for an archived final result.

## Screening experiment: finding DeepMath questions

**Purpose:** select questions across observed direct-solution success rates, independently of workflow evaluation outcomes.

The corrected screen uses `zwhe99/DeepMath-103K` revision `5cf055d1fe3d7a2eb19719ac020211469736ae44` with the RedHatAI checkpoint above. It excludes the previous 26 questions, deduplicates question text, and freezes a seed-42 candidate order interleaving source-difficulty bands.

Candidates receive eight sampled responses for triage; promoted candidates receive 32 sampled responses. Sampling uses temperature 0.6, top-p 0.95, top-k 20, and deterministic per-slot seeds. A separate greedy control is saved for fully screened questions and does not determine selection. The target is five questions in each final success-count bucket: 0, 1–8, 9–16, 17–24, and 25–32 correct out of 32.

The original 24-hour active-time budget plus one 24-hour extension produced 1,599 sampled responses. Twenty-five questions completed all 32 samples, yielding **21 provisional selections** after applying the five-per-bucket quota; four additional completed questions fell in the already-full highest bucket.

| Screening correct / 32 | Selected questions | Target |
|---|---:|---:|
| 0 | 5 | 5 |
| 1–8 | 3 | 5 |
| 9–16 | 4 | 5 |
| 17–24 | 4 | 5 |
| 25–32 | 5 | 5 |
| **Total** | **21** | **25** |

The published private snapshot is [the 21-question provisional dataset](https://huggingface.co/datasets/mendeza-umd/deepmath-103k-qwen-3-8-27b-screened-v1-provisional-21), pinned to revision `5ad55d34498601997f551d5080301648e26e9db6`.

**Interpretation:** solve rates are observations under this screening model, decoding setup, and grader, not verified intrinsic difficulty. Parse failures count as unsuccessful responses. Human reference and low-success response audit is still pending. The earlier historical screen had a confirmed Boolean-grading defect and cannot validate difficulty strata.

Details: [screening specification](SCREENING_SPEC.md), [screening procedure and audit requirements](RUN_SCREENING.md), and [historical screening postmortem](DEEPMATH_SCREENING_POSTMORTEM.md).

## AMC FlowBank reproduction

**Purpose:** establish the fixed workflow reproduction and oracle-portfolio measurement before moving to more difficult questions.

All **250 evaluations** completed on 50 frozen AMC questions: baseline and W1–W4 on each question. This reproduces the Appendix D.1 workflow graphs under our local model and evaluation configuration; it does not rerun FlowBank's optimizer or establish an exact reproduction of its published headline results.

| Condition | Solved | Accuracy |
|---|---:|---:|
| Baseline | 46/50 | 92.0% |
| W1 | 48/50 | 96.0% |
| W2 | 49/50 | 98.0% |
| W3 | 47/50 | 94.0% |
| W4 | 49/50 | 98.0% |
| Oracle union of W1–W4 | 49/50 | 98.0% |

**Finding:** the oracle exceeds baseline by 6 percentage points but adds no coverage beyond the best individual workflow. Every workflow pair reaches 49/50. On this selected AMC subset, the best individual workflow already captures the full four-workflow oracle coverage.

Details: [AMC experiment plan](AMC_EXPERIMENT_PLAN.md), [run instructions](RUN_AMC.md), and [completed AMC report and complementarity figure](experiment_results/amc50_qwen38_autoround_int4/README.md).

## DeepMath results: when does complementarity break down?

**Purpose:** investigate how workflow coverage and oracle gains change as observed baseline screening success decreases.

The historical 26-question experiment completed 130 evaluations: baseline 18/26 (69.2%), best individual 23/26 (88.5%), and oracle 25/26 (96.2%). Its screening labels are affected by the historical audit limitation and must not be treated as valid difficulty strata. These results motivated corrected screening and a new evaluation with the screening checkpoint.

The corrected 21-question run completed **105 fresh evaluations**, with no failed evaluations. It used the RedHatAI checkpoint, unchanged fixed workflows, and no reused screening responses as evaluation checkpoints.

| Condition | Solved | Accuracy |
|---|---:|---:|
| Baseline | 10/21 | 47.6% |
| W1 | 12/21 | 57.1% |
| W2 | 10/21 | 47.6% |
| W3 | 11/21 | 52.4% |
| W4 | 12/21 | 57.1% |
| Oracle union of W1–W4 | 16/21 | 76.2% |

Oracle coverage exceeds baseline by **28.6 percentage points** and the best individual workflow by **19.0 points**. W1 plus W4 already attains the full oracle coverage; W2/W3 add no further solved questions beyond that pair.

Independent, non-overlapping screening buckets show where the failures occur:

| Screening correct / 32 | Questions | Baseline solved | Oracle solved | Oracle accuracy |
|---|---:|---:|---:|---:|
| 0 | 5 | 0/5 | 0/5 | 0% |
| 1–8 | 3 | 1/3 | 3/3 | 100% |
| 9–16 | 4 | 0/4 | 4/4 | 100% |
| 17–24 | 4 | 4/4 | 4/4 | 100% |
| 25–32 | 5 | 5/5 | 5/5 | 100% |

**Finding:** the portfolio recovers questions in the low/intermediate screening buckets, but all workflows fail on the selected 0/32 group. This is evidence of a coverage boundary in this sample, not proof of a general difficulty threshold. Small adaptive groups, unreviewed references, and answer parsing remain important limitations; the fresh baseline has six parse failures.

Details: [historical DeepMath plan](DEEPMATH_EXPERIMENT_PLAN.md), [historical 26-question results](experiment_results/deepmath26_qwen38_autoround_int4/README.md), [corrected 21-question run instructions](RUN_SCREENED21.md), [corrected results and independent bucket table](experiment_results/deepmath21_screened_redhat_int4/comparison/RESULTS_REPORT.md), and [independent bucket CSV](experiment_results/deepmath21_screened_redhat_int4/comparison/independent_bucket_metrics.csv).

## Budget-constrained DeepMath experiment

**Status: implemented; prepared for launch.** The authorized design gives the baseline 131,072 generated tokens and each complete workflow 32,768, controlling the full portfolio at the same maximum. Reasoning counts; input tokens do not. See the [committed specification and launch procedure](RUN_BUDGET21.md).

**Purpose:** determine whether complementary workflows remain effective under a fixed total compute allowance, and where their coverage breaks down as questions become more difficult.

The completed experiment does not answer this question because its limits apply per call. Measured mean input plus output usage was:

| Condition | Mean tokens/question | Relative to baseline | Accuracy |
|---|---:|---:|---:|
| Baseline | 30,052 | 1.00× | 47.6% |
| W1 | 83,141 | 2.77× | 57.1% |
| W2 | 135,851 | 4.52× | 47.6% |
| W3 | 125,472 | 4.18× | 52.4% |
| W4 | 27,205 | 0.91× | 57.1% |

Running the whole portfolio used about **12.37×** the baseline's tokens. Token usage is a proxy for compute, not hardware FLOPs or monetary cost. W4's lower observed usage and higher accuracy is encouraging but is not yet a general efficiency result.

The next experiment should freeze an audited selection and compare direct sampling, individual workflows, and portfolios at explicitly matched total budgets. Include candidate generation, classification, selection, verification, and retries in each method's budget. Compare oracle against oracle and actual selected answers against actual selected answers. Report cost and latency alongside accuracy by independent difficulty bucket.

The budget unit, budget levels, stage allocations, repeated-sampling baseline, answer selector, and repeated-run protocol must be specified before inference. Equal per-call caps are insufficient. For example, 32K per call across four calls fits a 128K generation allowance, but does not equalize prompt-processing or executor costs.

**Authorized run record:**

- Dataset: the same 21-question snapshot at revision `5ad55d34498601997f551d5080301648e26e9db6`; audit pending.
- Budget: generated tokens including reasoning; 131,072 baseline versus 32,768 per workflow, enforced by durable per-evaluation wallets.
- Conditions: fresh direct baseline and fixed W1–W4; retrospective oracle. Repeated direct sampling and a deployable answer selector remain future controls.
- Protocol: one fresh evaluation per question/condition, seed 42; five-question pilot with operational and budget-compliance gates, then automatic continuation.
- Implementation commit and launch identity: recorded by the pipeline before inference. Results will be archived separately after all 105 evaluations.

Prior evidence and motivation: [measured token-cost comparison and critiques](experiment_results/deepmath21_screened_redhat_int4/comparison/TOKEN_COST_COMPARISON.md). The [dedicated specification](RUN_BUDGET21.md) freezes the implementation; a results report will be linked after completion.

## Insights: difficulty-aware workflow optimization

**Research direction:** workflow optimization methods should focus on difficulty awareness. Workflow structure and compute allocation should be allowed to change as questions become more difficult, rather than assuming one fixed portfolio is equally useful across the entire range.

The completed experiments motivate this direction:

- On AMC, the full oracle adds nothing beyond the best individual workflow, suggesting limited value from additional portfolio members on this sample.
- On corrected DeepMath, complementarity recovers questions missed by individual workflows in low/intermediate screening buckets, while the selected 0/32 group defeats the entire fixed portfolio.
- More workflow calls do not guarantee useful diversity. W1 plus W4 matches the full portfolio's coverage here, and W4 uses fewer mean tokens than baseline.
- The current results cannot separate benefits of workflow structure from unequal compute. The fixed-budget experiment is needed to test that distinction.

A difficulty-aware optimizer could learn when a direct or specialist solver is sufficient, when diverse attempts or verification justify their cost, and when a different strategy or abstention is warranted. Any deployed difficulty estimate must be available before the answer is known; screening labels and oracle correctness cannot serve as a deployable router.

These are hypotheses for the next optimization study. The present experiments evaluate fixed graphs and do not demonstrate that an adaptive optimizer outperforms them. Future claims should require audited labels, compute-matched controls, and evaluation on held-out questions with uncertainty estimates.
