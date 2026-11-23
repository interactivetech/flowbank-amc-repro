# FlowBank AMC workflow comparison

> **Screening audit notice (2026-11-18):** Historical screening rates have a confirmed Boolean grading defect and do not validate difficulty strata. Counts and figures are retained as recorded. See [the postmortem](DEEPMATH_SCREENING_POSTMORTEM.md) for evidence, limits, and the replacement screening process.

Start with the [experiment overview](EXPERIMENT_OVERVIEW.md) for the study purpose, settings, deployment, screening, completed results, and proposed fixed-budget follow-up.

Evaluate a frozen 50-item AMC subset with **Qwen3.8-27B AutoRound INT4**: one single-model rollout and the fixed Appendix D.1 workflows W1–W4. Compare final correctness and token costs, baseline-relative wins, and retrospective oracle union coverage.

For a **10-hour B300 scavenger allocation**, use [B300_SCAVENGER.md](B300_SCAVENGER.md).

Completed results and the complementarity graph: [AMC 50-item results](experiment_results/amc50_qwen38_autoround_int4/README.md).

Use [AMC_COMMANDS.md](AMC_COMMANDS.md) for the command sequence and [RUN_AMC.md](RUN_AMC.md) for review/commit, scratch-based setup, local vLLM startup within Slurm, pilot, resume, and table commands. The full specification is saved in [AMC_EXPERIMENT_PLAN.md](AMC_EXPERIMENT_PLAN.md).

The runtime uses one GPU and no Docker or Apptainer. Python environments, model weights, caches, logs, and results live under `/scratch1/mendeza/flowbank-amc/`. W2/W3 execute generated Python in a subprocess with resource limits; it runs with the user's account access.

Frozen settings: N=50, dataset seed 42, thinking on, temperature 0, top-p 1, inference seed 42, and 131,072 generated tokens per call including reasoning. Workflow total allowances exceed the single-rollout baseline. Mean tokens include input plus output over all calls. Wins vs Qwen mean workflow correct and baseline incorrect. Final tables require all 250 evaluations.

Model downloading, model serving, and inference are explicit user-run operations after review and commit. Installation never starts the experiment. See [REPRODUCTION_NOTES.md](REPRODUCTION_NOTES.md) for graph and grader fidelity and the clearly marked historical execution notes.

DeepMath completed results: [26-item report, tables, and figures](experiment_results/deepmath26_qwen38_autoround_int4/README.md). Baseline solved 18/26 (69.2%), best individual 23/26 (88.5%), and four-workflow oracle 25/26 (96.2%): a 7.7-point gain beyond the best individual. Gains did not increase monotonically with historical screening difficulty. See the [approved plan](DEEPMATH_EXPERIMENT_PLAN.md) and [run and plotting commands](RUN_DEEPMATH.md).

A separate [RedHatAI checkpoint rerun](REDHAT_DEEPMATH_RERUN.md) was authorized on November 18 to investigate the screening discrepancy; it preserves the original AutoRound results.

The [21-question screened FlowBank rerun](RUN_SCREENED21.md) uses the corrected provisional dataset with fresh baseline/W1–W4 evaluations, automatic pilot checks, and a separate results archive. Dataset audit remains pending.

The [generated-token-budget DeepMath experiment](RUN_BUDGET21.md) compares a 128K direct baseline with a 128K four-workflow portfolio (32K per complete workflow).
