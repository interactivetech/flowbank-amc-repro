# Current experiment status

> **Screening audit notice (2026-11-18):** Historical screening rates have a confirmed Boolean grading defect and do not validate difficulty strata. Counts and figures are retained as recorded. See [the postmortem](DEEPMATH_SCREENING_POSTMORTEM.md) for evidence, limits, and the replacement screening process.

## Local deployment verified — 2026-11-16

Qwen3.8-27B AutoRound INT4 is deployed on the allocated B300 on `cml38`, within Slurm job `8437053`. This records verification at deployment time; use the health command to check whether that allocation and process are still running.

- Checkpoint: `MIRALABS/Qwen3.8-27B-W4A16-AutoRound`, revision `a6754efcde1ea362616353759f0c97507775a5a9`.
- Endpoint: `http://127.0.0.1:8000/v1`; model ID `qwen3.8-27b-autoround-int4-a6754efcde1e`.
- `/health` returned HTTP 200. A thinking-enabled endpoint request accepted a 131,072-token output cap and returned the correct sum of 1–100, 5050, with separated reasoning/final content.
- Check usage: 76 prompt tokens and 109 completion tokens, including 53 reasoning tokens; finish reason `stop`.
- Runtime: Python 3.12.15, vLLM 0.32.0, PyTorch 2.13.0+cu130. All 34 local tests passed in the dedicated environment; the executor passed a real SymPy/NumPy/SciPy check.
- Runtime environments, checkpoint, compilation caches, logs, and endpoint-check artifacts are under `/scratch1/mendeza/flowbank-amc/`. Primary logs are `setup.log` and `logs/vllm.log`; endpoint artifacts are in `results/endpoint/`.
- Startup now waits for process-group detachment and exposes runtime tools and the installed CUDA 13.0.2 compiler. First-use compilation caches persist on scratch.

**The pilot and full experiment completed on 2026-11-16.** All 250 evaluations finished; final tables and a workflow-complementarity graph are archived in [the results folder](experiment_results/amc50_qwen38_autoround_int4/README.md). Baseline accuracy was 92%; W1–W4 were 96%, 98%, 94%, and 98%; oracle coverage was 98%. There were no infrastructure failures, 26 capped calls, and five final parsing failures. Commands and acceptance checks are in [RUN_AMC.md](RUN_AMC.md); the frozen plan is [AMC_EXPERIMENT_PLAN.md](AMC_EXPERIMENT_PLAN.md).

The prior Mac experiment status below is historical and is not evidence of a running process or completed result on this Slurm node.

---

# Experiment status

## Material Passport

- Objective: fixed AMC workflow complementarity reproduction.
- Sources: official FlowBank commit dde948d9f65cede15e6a3418dde3bf7feffdd087 and Appendix D.1.
- Verification: 28 tests pass, including real Docker isolation tests; numerical execution in progress.
- Integrity: no accuracy results claimed before all conditions complete.

The user authorized changing the executor from the busy Qwen endpoint on port 8001 to `deepseek-v4-flash` on port 8000. Model discovery and minimal completion succeeded on the new endpoint. The server advertises display name DeepSeek V4.1 Flash and owner ds4.c; these are server claims, not independent weight verification.

The real smoke test runs in results/smoke with concurrency 2, temperature 0, top-p 1, seed 42, max_tokens 4096, DeepSeek thinking.type=disabled, timeout 180s. The preselected 50-question manifest remains unchanged. The interrupted Qwen attempts are preserved in results/smoke_8001_interrupted and are excluded from all DeepSeek results.

scripts/finish_experiment.py monitors the smoke test. Only after it completes successfully will the script analyze the smoke results, run the 50-question experiment in results/amc (same decoding settings, concurrency 2, timeout 600s), and generate tables and a research summary. Consult results/pipeline_status.json and results/pipeline.log for current status. A failed smoke test prevents the full run.

Final accuracy and complementarity conclusions are pending. README.md contains setup, resume, and offline-analysis commands; REPRODUCTION_NOTES.md documents the model change and all fidelity choices.

## DeepMath extension — complete (2026-11-17)

All 130 evaluations and final analysis completed on November 17 at 4:48 PM Eastern, approximately 4 hours 5 minutes after launch. Baseline solved 18/26 (69.2%); W1 19/26 (73.1%); W2 and W3 each 23/26 (88.5%); W4 22/26 (84.6%); the four-workflow oracle solved 25/26 (96.2%). Oracle gain beyond the best individual is 2 questions (7.7 percentage points). There were no infrastructure failures, 6 final-answer parsing failures, and 7 truncated model calls. These diagnostics are retained without post-run relabeling.

The published aggregate report is [archived in the repository](experiment_results/deepmath26_qwen38_autoround_int4/README.md); the original report remains at `/scratch1/mendeza/flowbank-amc/results/deepmath26/comparison/RESULTS_REPORT.md`. Both figures exist in PNG/PDF/SVG alongside aggregate CSVs; the two AMC-style tables are in the parent results directory. The nested historical cohorts do not show monotonically increasing complementarity: gains are 7.7, 14.3, 9.1, 0, and 0 percentage points as screening thresholds decrease from 100% to 0%. All five questions with no observed screening successes were solved by W2, W3, and W4 individually; their fresh baseline solved four. Historical screening labels are not directly comparable with the fresh baseline.

The following paragraphs record launch and recovery history.

The approved specification is saved as `DEEPMATH_EXPERIMENT_PLAN.md`; commands are in `RUN_DEEPMATH.md`. The pinned 26-row CSV and typed references are frozen on scratch at `/scratch1/mendeza/flowbank-amc/deepmath/frozen`. All 214 reference preflight cases and 60 local tests pass. Supplied labels and historical screening rates remain unchanged.

The user explicitly authorized launch on November 17. The staged pipeline ran inside B300 allocation 8437053 on cml38. The 25-evaluation pilot passed all diagnostic gates, so the pipeline continued to the remaining 105 evaluations and generated final analysis after all 130 completed.

The initial pilot exposed an extraction-format bug: a boxed yes/no label followed by a justification was rejected. The Boolean parser now accepts a categorical label at the start of the extracted final answer. Regression tests cover this format. Original pilot artifacts are retained intact under `/scratch1/mendeza/flowbank-amc/results/deepmath26_initial_boolean_parser`; `deepmath26/grading_correction.json` records the correction. Generation prompts, settings, gold labels, and model were unchanged. Fourteen successful call checkpoints and their traces were reused, with results recomputed under the corrected grader and a fresh source/configuration record.

Active results: `/scratch1/mendeza/flowbank-amc/results/deepmath26`. Pipeline state: `/scratch1/mendeza/flowbank-amc/deepmath/pipeline_status.json`. Log: `/scratch1/mendeza/flowbank-amc/logs/deepmath-pipeline.log`. The launcher is `/scratch1/mendeza/flowbank-amc/deepmath/run_experiment.py`; its PID is recorded in `pipeline.pid` beside it. It survives terminal detachment but requires recovery if the Slurm allocation ends.

A 26-item extrapolation from archived AMC evaluation latencies at concurrency two is approximately 4.0 hours. This is a comparison, not a reliable DeepMath prediction; hard questions may exceed ten hours in total. The completed pilot initially projected 1.17 hours for the remainder, which underestimated the later long generations. Observed total elapsed time was approximately 4 hours 5 minutes.

## RedHatAI DeepMath rerun — pilot running (2026-11-18)

The user authorized a new full DeepMath experiment using the checkpoint from the screening deployment, `RedHatAI/Qwen3.8-27B-INT4`. Revision `e45c27e8f463817db788d141a73a3c235a0a7c0c` is pinned; separate model locks, logs and results preserve the completed AutoRound run. All 64 local tests pass, including alternate-model lock rejection, profile isolation, indexed-weight completeness, and pilot-to-full resume.

The idle AutoRound server was stopped and the RedHat server launched in Slurm allocation 8437053. This allocation has one B300; the rerun keeps the prior experiment's settings and disables speculative decoding, rather than reproducing the screening deployment's four-GPU DFlash configuration. See [rerun specification and commands](REDHAT_DEEPMATH_RERUN.md). No new accuracy is reported while the rerun is incomplete.

The RedHat weights loaded successfully after fetching the additional MTP weight file referenced by the model index (required by the loader even with speculative decoding disabled). Preparation now validates every indexed weight file before serving. The RedHat endpoint passed a real reasoning-enabled check accepting the 131,072-token cap. Pipeline PID 1460775 started the fresh pilot at 3:11 PM Eastern with two active requests, then will run diagnostics and continue to the full run if the pilot is clean. The new and old manifest hashes and decoding/limit settings match. vLLM resolved the RedHat checkpoint to FP8 KV cache, recorded in the deployment log and `observed_runtime.json`. State and logs are under `/scratch1/mendeza/flowbank-amc/deployments/redhat/`.

## Replacement screening implementation — 2026-11-18

The RedHat workflow batch was preserved with 173 successful calls and 51 completed evaluations, then stopped. The existing allocation and model server were retained. The replacement screen is governed by [the frozen specification](SCREENING_SPEC.md) and [operator commands](RUN_SCREENING.md). Launch requires committed, pushed, verified code and offline tests. Screening outputs remain provisional until manual audit; no workflow rerun is launched automatically.
