# Current experiment status

## Local deployment verified — 2026-11-16

Qwen3.8-27B AutoRound INT4 is deployed on the allocated B300 on `cml38`, within Slurm job `8437053`. This records verification at deployment time; use the health command to check whether that allocation and process are still running.

- Checkpoint: `MIRALABS/Qwen3.8-27B-W4A16-AutoRound`, revision `a6754efcde1ea362616353759f0c97507775a5a9`.
- Endpoint: `http://127.0.0.1:8000/v1`; model ID `qwen3.8-27b-autoround-int4-a6754efcde1e`.
- `/health` returned HTTP 200. A thinking-enabled endpoint request accepted a 131,072-token output cap and returned the correct sum of 1–100, 5050, with separated reasoning/final content.
- Check usage: 76 prompt tokens and 109 completion tokens, including 53 reasoning tokens; finish reason `stop`.
- Runtime: Python 3.12.15, vLLM 0.32.0, PyTorch 2.13.0+cu130. All 34 local tests passed in the dedicated environment; the executor passed a real SymPy/NumPy/SciPy check.
- Runtime environments, checkpoint, compilation caches, logs, and endpoint-check artifacts are under `/scratch1/mendeza/flowbank-amc/`. Primary logs are `setup.log` and `logs/vllm.log`; endpoint artifacts are in `results/endpoint/`.
- Startup now waits for process-group detachment and exposes runtime tools and the installed CUDA 13.0.2 compiler. First-use compilation caches persist on scratch.

**No AMC pilot or full experiment has run.** Next: `bash scripts/run_amc.sh pilot`, inspect its results, then explicitly run `full`. Commands and acceptance checks are in [RUN_AMC.md](RUN_AMC.md); the frozen plan is [AMC_EXPERIMENT_PLAN.md](AMC_EXPERIMENT_PLAN.md).

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
