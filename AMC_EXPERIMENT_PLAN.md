# AMC experiment: Qwen3.8-27B AutoRound INT4

## Deliverable and stopping point

Implement the experiment setup, save this plan in the repository, and provide runnable setup, serving, evaluation, resume, and analysis commands. Stop after implementation and local tests. The user reviews and commits before downloading weights, starting the server, or running inference. Do not automatically commit or execute the experiment.

## Frozen experiment

- Select 50 AMC items with seed 42. Freeze a complete manifest before inference and use the same items for baseline and W1–W4.
- Use `MIRALABS/Qwen3.8-27B-W4A16-AutoRound` for every condition. Resolve its immutable revision during user-run setup and retain the revision, config hash, quantization configuration, and served model ID. Source: https://huggingface.co/MIRALABS/Qwen3.8-27B-W4A16-AutoRound
- The publisher describes INT4 AutoRound weights, BF16 activations, and compressed-tensors packing. Require declared compressed-tensors 4-bit configuration and fail on incompatibility; never substitute precision or checkpoint automatically.
- Thinking on, temperature 0, top-p 1, seed 42, maximum 131,072 generated tokens per call including reasoning. The baseline uses exactly one rollout. Workflow totals can exceed this allowance because each call receives it.
- Preserve published prompts and graph order, including three repeated W2 calls despite possible identical greedy results. Preserve deterministic grading and at most three Programmer generations, retrying execution errors rather than wrong answers.

## Runtime and storage

- Use dedicated Python 3.12 runtime and executor environments under `/scratch1/mendeza/flowbank-amc/`. Put weights, package/download caches, compilation caches, temporary files, logs, and results there.
- Pin core serving packages against the existing working environment as the compatibility reference; leave that environment untouched. Record complete package versions for resume.
- Launch a background vLLM Python process within a GPU Slurm allocation. Bind to `127.0.0.1:8000`, use one GPU, BF16 activations, declared compressed-tensors quantization, automatic KV-cache dtype, 262,144-token context, 90% memory utilization, prefix caching, and at most two active sequences. Disable speculative decoding and model generation-config overrides.
- Use the Qwen reasoning parser. Save reasoning and full response metadata; pass final content to workflow stages.
- Replace Docker with a Python subprocess executor using pinned SymPy, NumPy, and SciPy, the `solve()` contract, 20-second wall timeout, 15-second CPU limit, 2 GiB address-space limit, bounded output, and process-group cleanup. Use temporary working directories and a minimal environment without API credentials. This is resource limiting, not filesystem or network isolation.

## Harness and tables

- Bind the immutable model and server settings, full runtime package versions, executor identity, decoding settings, and source hashes to resume configuration.
- Freeze all 50 items before a pilot. Schedule the first three using an execution limit outside experiment identity; full resume reuses pilot results and successful calls.
- Allow four hours per request. Save usage, reasoning, finish reasons, truncation counts, and infrastructure failures. Reject prompt overflow instead of truncating candidates or reducing the 128K allowance.
- Count completed but invalid model selections as parse failures, without repeating them on resume. Keep infrastructure failures incomplete until resolved.
- Table 1: model, N, decoding/budget, accuracy, mean tokens. Label the model Qwen3.8-27B AutoRound INT4.
- Table 2: workflow labels, N, final accuracy, wins versus Qwen, mean tokens. Wins mean workflow correct and baseline incorrect, independently of other workflows. Oracle accuracy is the union of W1–W4 final correctness; its wins and tokens cells are em dashes.
- Mean tokens include input plus generated tokens, including reasoning, across all calls for each item. Keep separate input/output totals, call counts, truncation counts, and portfolio token costs in supporting JSON. Incomplete usage makes the corresponding token mean unavailable.
- Export Markdown, CSV, LaTeX, correctness matrix, full traces, metadata, and a concise summary. Pilot artifacts go into a separate pilot analysis directory. Final tables require all 250 evaluations.

## Validation and user-run sequence

Implementation validation uses local executor fixtures and mocked model responses only. Cover success/errors, timeout, memory/output limits, descendant cleanup, reasoning separation, full output allowance and context overflow, baseline-relative wins, oracle union, token accounting, incomplete usage, and pilot/full resume identity.

Provide exact user commands to review and commit; install environments and download the pinned checkpoint; launch vLLM and inspect readiness/PID/logs; check reasoning, identity, context, usage, and output-cap acceptance; run and inspect the three-item pilot; resume all 50; continue in a later allocation; and generate final artifacts.

The full experiment requires at least 850 LLM calls, plus Programmer retries. Background processes remain subject to Slurm allocation lifetime. Preserve scratch checkpoints across restarts. No model performance or kernel compatibility claim is made before user-run preflight and pilot.
