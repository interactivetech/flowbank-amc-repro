# FlowBank on AMC and DeepMath

## The Claim

Our work was based on the [FlowBank paper](https://arxiv.org/abs/2606.11290) discussed in class. We tested whether the fixed workflows made for AMC could be transferred to DeepMath-103K while their portfolio still performed better than a direct baseline and the best individual workflow. When an AMC-optimized workflow fails on out-of-distribution mathematical reasoning, is the failure due to the underlying model never finding a correct answer, or to the workflow discarding a correct answer that appeared at an intermediate stage?

Toward this end, we reconstructed four fixed AMC workflows and evaluated **complementarity: oracle coverage minus the best individual workflow's accuracy**. Oracle coverage counts a question as solved if any W1-W4 final answer is correct; it is a retrospective upper bound, not a deployable selector. DeepMath transfer tests a boundary of the finding, rather than an explicit out-of-distribution robustness claim, which the paper does not make.

## What we Did

We began by directly reconstructing four fixed AMC workflows from Appendix D.1:

- **W1:** three differently prompted solutions, followed by LLM selection.
- **W2:** three analytical solutions, selection, and Python verification.
- **W3:** three diverse solutions, selection, and Python verification.
- **W4:** mathematical-domain classification followed by a specialist solver.

We used Qwen3.8-27B instead of GPT-4o-mini because of API-credit constraints: MIRALABS AutoRound INT4 for AMC and RedHatAI INT4 for corrected DeepMath. Evaluation used thinking enabled, temperature 0, top-p 1, seed 42, a 262,144-token context, and deterministic answer grading. We saved candidates, selections, code execution, final answers, and token usage; reference answers never entered generation.

Each experiment compared W1-W4 with a fresh single-call baseline on identical questions. We evaluated 50 frozen AMC questions, selected with seed 42 from 655 items. After detecting a historical screening defect, we screened new DeepMath questions using sampled direct solutions. We selected 21 provisional questions, each with 32 responses, across five buckets: 0, 1-8, 9-16, 17-24, and 25-32 correct, containing 5, 3, 4, 4, and 5 questions. Screening used temperature 0.6, top-p 0.95, and top-k 20; responses were not reused for evaluation.

The initial comparisons allowed **131,072 generated tokens per call**. The budget-controlled experiment instead allocated **131,072 per question to baseline and 32,768 to each complete workflow**, totaling 131,072 across the portfolio. Reasoning and code-generation retries counted; input tokens and Python execution did not. This was a **model-substituted partial reproduction**: we did not rerun workflow optimization, include W5, or reproduce the learned GNN selector.

## Results

All evaluations completed: 250 on AMC and 105 in each corrected DeepMath experiment.

| Condition | AMC: 50 questions | DeepMath: per-call caps | DeepMath: shared portfolio allowance |
|---|---:|---:|---:|
| Baseline | 46/50 (92.0%) | 10/21 (47.6%) | 11/21 (52.4%) |
| W1 | 48/50 (96.0%) | 12/21 (57.1%) | 6/21 (28.6%) |
| W2 | 49/50 (98.0%) | 10/21 (47.6%) | 6/21 (28.6%) |
| W3 | 47/50 (94.0%) | 11/21 (52.4%) | 6/21 (28.6%) |
| W4 | 49/50 (98.0%) | 12/21 (57.1%) | 11/21 (52.4%) |
| **Oracle W1-W4** | **49/50 (98.0%)** | **16/21 (76.2%)** | **11/21 (52.4%)** |
| **Complementarity gap** | **0 percentage points** | **19.0 percentage points** | **0 percentage points** |

On **AMC**, the portfolio beat baseline but added nothing beyond W2 or W4 individually. Positive portfolio complementarity was not reproduced on this subset.

On **corrected DeepMath with per-call caps**, the oracle solved four more questions than the best workflow. W1 plus W4 already achieved full portfolio coverage. Every selected question outside the 0/32 bucket was covered; none of the five 0/32 questions was solved. However, the portfolio consumed approximately **12.37 times baseline's measured input-plus-output tokens**.

Under the **shared generated-token allowance**, the oracle matched baseline and W4. Baseline solved four portfolio misses, while the portfolio solved four baseline misses. The run recorded 42 final parsing failures, 175 truncated calls, seven budget-exhausted evaluations, and zero budget violations.

For **answer preservation**, the corrected per-call-cap run recorded five W1-W3 failures despite a correct initial candidate: two aggregation losses, two verification losses, and one selection-parsing loss. Another 25 unsuccessful W1-W3 evaluations had no verified correct initial candidate. These are workflow evaluations, not distinct questions.

## Conclusions

We draw the following conclusions from the results that we obtained:

1. Complementarity depended on the questions and resource allocation: absent beyond the strongest workflow on AMC, present on corrected DeepMath with generous per-call allowances, and absent under the shared allocation.
2. Workflow selection and token allocation should be studied together. Difficulty alone was not established as the cause; fixed stage caps frequently truncated intermediate processing.
3. Correct-answer loss occurred, but was not the main recorded failure mode. A deployed selector achieving oracle coverage was not demonstrated.

## Negative and Uncertain Findings

- **Historical screening was unreliable.** A Boolean-grading defect invalidated difficulty-based interpretations of the earlier 26-question experiment. Its recorded accuracies remain historical observations, not validated difficulty evidence.
- **The corrected dataset remains provisional.** Screening selected 21 of the targeted 25 questions; manual reference and response audit is pending. A 0/32 label means no observed screening successes, not unsolvability or verified intrinsic difficulty.
- **Equal allowances were not equal compute.** Actual generated tokens averaged approximately 88,931 for the portfolio versus 25,090 for baseline. Input processing, execution, and wall time were not matched. Fresh responses and changed stage caps limit causal comparison between runs.
- **The planned trace analysis is incomplete.** Aggregate loss labels are available, but reviewed case studies, conditional solution-loss rates by difficulty, and uncertainty analysis remain unfinished. Detailed DeepMath traces are outside the repository archive.
- **Generalization is limited.** Samples are small, DeepMath selection was adaptive, AMC and corrected DeepMath used different quantized checkpoints, and grading differs from the original paper. We lack a matched repeated-direct-sampling control and population-level statistical evidence. Final-answer grading does not verify proofs.

## Reproducing the Experiments

**Source and saved outcomes.** Use the completed experiment snapshot:

```bash
git clone https://github.com/interactivetech/flowbank-amc-repro.git
cd flowbank-amc-repro
git checkout b1ac112ed334a87853b55c990c3b4b95e6e31e3e
```

Under `experiment_results/`, each run contains `correctness_matrix.csv` and `summary.json`. Average each 0/1 column for accuracy; count rows with any W1-W4 success for oracle coverage. Expected baseline/best/oracle counts are **46/49/49 of 50**, **10/12/16 of 21**, and **11/11/11 of 21**. No GPU is needed.

**New inference.** Use Linux, Python 3.12, and a one-B300 Slurm allocation. Export `AMC_ROOT` to a new writable `/scratchN/...` directory and `AMC_PYTHON312` to your interpreter. Before setup, copy the archived AMC configuration's `local_runtime.model` object into `$AMC_ROOT/model.lock.json`; this pins MIRALABS revision `a6754efcde1ea362616353759f0c97507775a5a9`.

```bash
bash scripts/setup_amc.sh
source scripts/amc_env.sh
bash scripts/start_vllm.sh
curl --fail http://127.0.0.1:8000/health
bash scripts/run_amc.sh check
```

Wait for health, then run `bash scripts/run_amc.sh` with actions `pilot`, `analyze-pilot`, `status`, `full`, and `analyze`. Inspect the pilot before continuing; repeat `full` to resume unchanged settings. Server and runner must share a node.

**DeepMath requires private inputs:** dataset `mendeza-umd/deepmath-103k-qwen-3-8-27b-screened-v1-provisional-21` at `5ad55d34498601997f551d5080301648e26e9db6`, plus screening responses, greedy controls, and selection/run metadata. Restore the Parquet to `$AMC_ROOT/hf_deepmath_screened_21_upload/data/test.parquet` and evidence to `$AMC_ROOT/screening/deepmath-v1-extension-1/`. Stop AMC's server; export `AMC_MODEL_PROFILE=redhat`; run `"$AMC_ROOT/runtime/bin/python" -m amc_repro.local_runtime prepare`, `bash scripts/screen_deepmath.sh setup`, and restart the server. RedHatAI pins revision `e45c27e8f463817db788d141a73a3c235a0a7c0c`.

After health, use `scripts/run_screened21.sh` and then `scripts/run_budget21.sh` with actions `prepare`, `pilot`, `analyze-pilot`, `status`, `full`, and `analyze`. Outputs under `$AMC_ROOT/results/` include manifests, metadata, traces, tables, summaries, and budget compliance. Use one runner per directory; unresolved budgeted usage requires review. Generated Python is resource-limited, not filesystem/network-isolated. Exact numerical replay is not guaranteed.
