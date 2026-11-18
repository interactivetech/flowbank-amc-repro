# DeepMath rerun with the RedHatAI checkpoint

> **Screening audit notice (2026-11-18):** Historical screening rates have a confirmed Boolean grading defect and do not validate difficulty strata. Counts and figures are retained as recorded. See [the postmortem](DEEPMATH_SCREENING_POSTMORTEM.md) for evidence, limits, and the replacement screening process.

The user authorized redeploying vLLM and rerunning all 26 frozen questions on November 18, 2026, after identifying that the original screening deployment used a different checkpoint repository. This is a separate 130-evaluation experiment; the completed AutoRound experiment remains intact.

## Frozen change

- Model: `RedHatAI/Qwen3.8-27B-INT4`.
- Pinned revision: `e45c27e8f463817db788d141a73a3c235a0a7c0c`.
- Served ID: `qwen3.8-27b-redhat-int4-e45c27e8f463`.
- One B300, tensor parallelism 1; DFlash/speculative decoding disabled.
- Preserve the original experiment's 262,144-token context, 131,072 generated-token cap, thinking enabled, temperature 0, top-p 1, inference seed 42, concurrency 2, prompts, grading, routing, execution limits, retries, 26-question manifest, and five pilot IDs.
- Fresh single-call baseline and W1–W4 for all questions. No AutoRound model-call or evaluation checkpoints are reused.

This isolates switching the quantized checkpoint under the experiment configuration. It is **not a full reproduction of the historical screening deployment**, which used tensor parallelism 4, context 204,800, and DFlash. Historical request settings and grading remain unknown until the screening script/raw responses are audited. The currently available allocation has one B300. Checkpoint identity alone cannot establish why the historical screening rates differ.

The RedHat checkpoint declares compressed-tensors INT4 weights and an FP8 KV-cache quantization scheme. The server retains `--kv-cache-dtype auto`; vLLM confirmed `torch.float8_e4m3fn` KV cache in its startup log. The exact serving command, quantization configuration and vLLM version are recorded in the separate deployment metadata, with resolved cache observations in `observed_runtime.json`. No precision fallback is permitted.

## Separate artifacts

Scratch root: `/scratch1/mendeza/flowbank-amc`.

- `deployments/redhat/model.lock.json`: immutable RedHat model identity.
- `deployments/redhat/serving.json`, `vllm.log`, `vllm.pid`: serving metadata/log/PID.
- `deployments/redhat/pipeline_status.json`, `pipeline.log`: rerun phase, diagnostics, errors and runtime estimate.
- `results/deepmath26_redhat_int4`: new pilot/full results and final analysis.
- Original `model.lock.json`, `serving.json`, logs, `results/deepmath26`, and repository archives remain unchanged.

The pilot runs 25 evaluations first. A complete pilot with clean diagnostics explicitly resumes the remaining 105 evaluations; flagged diagnostics pause the pipeline for review. Successful calls and evaluations are checkpointed within this new run. Final tables and figures require all 130 completed evaluations. The archived AMC comparison panel uses the AutoRound checkpoint, so an AMC/RedHat comparison also changes checkpoint and cannot isolate dataset difficulty.

## Commands

Run from the repository root, within the GPU allocation:

```bash
source scripts/amc_env.sh
export AMC_MODEL_PROFILE=redhat
"$AMC_ROOT/runtime/bin/python" -m amc_repro.local_runtime prepare
# Stop the old server only after checking that it is idle and its runs are complete.
bash scripts/start_vllm.sh
curl --fail http://127.0.0.1:8000/health
"$AMC_ROOT/runtime/bin/python" -m amc_repro.check_endpoint --local-runtime \
  --results-dir "$AMC_ROOT/results/endpoint_redhat"
bash scripts/run_deepmath.sh pilot
bash scripts/run_deepmath.sh analyze-pilot
# Inspect the pilot before explicitly continuing:
bash scripts/run_deepmath.sh full
bash scripts/run_deepmath.sh analyze
```

Retain `AMC_MODEL_PROFILE=redhat` when resuming. The runner requires the explicit RedHat lock supplied by the wrapper and rejects a checkpoint mismatch. The default profile remains AutoRound and its original lock check is retained.

Initial planning estimate: several hours, using the original run's approximately four-hour elapsed time as a comparison. The new pilot will provide a measured estimate; long generations and allocation expiry may require recovery. No new accuracy is claimed before the rerun completes. Private questions, references and traces stay on scratch.
