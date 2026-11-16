# AMC experiment commands

Run from the repository root. The implementation and these instructions are committed before any model download or experiment run. Full explanations, monitoring, stop commands, and recovery instructions are in [RUN_AMC.md](RUN_AMC.md); the specification is [AMC_EXPERIMENT_PLAN.md](AMC_EXPERIMENT_PLAN.md).

## Install and download to scratch

```bash
bash scripts/setup_amc.sh
source scripts/amc_env.sh
```

This creates dedicated environments and downloads the pinned Qwen3.8-27B AutoRound INT4 checkpoint under `/scratch1/mendeza/flowbank-amc/`.

## Start vLLM inside the GPU Slurm allocation

```bash
bash scripts/start_vllm.sh
tail -n 60 "$AMC_ROOT/logs/vllm.log"
curl --fail http://127.0.0.1:8000/health
```

Wait for model loading to finish and repeat the health command until it succeeds. Inspect the log if startup fails. The server and runner must use the same allocated node; background processes remain subject to the allocation lifetime.

## Check the endpoint and run the pilot

```bash
bash scripts/run_amc.sh check
bash scripts/run_amc.sh pilot
bash scripts/run_amc.sh analyze-pilot
bash scripts/run_amc.sh status
```

Inspect the pilot results before continuing. They are saved under `$AMC_ROOT/results/amc50/pilot_analysis/`. The pilot uses the first three items of the frozen 50-item manifest; full evaluation reuses its completed calls and evaluations.

## Run or resume the full experiment

```bash
bash scripts/run_amc.sh full
bash scripts/run_amc.sh status
```

Repeat `full` after an interruption to resume. Run only one evaluation process against this results directory. In a new allocation, source `scripts/amc_env.sh`, restart the server, wait for health, then resume.

## Generate and inspect final tables

```bash
bash scripts/run_amc.sh analyze
cat "$AMC_ROOT/results/amc50/table1_baseline.md"
cat "$AMC_ROOT/results/amc50/table2_portfolio.md"
```

Final analysis requires all 250 item-condition evaluations. Model downloads, startup, endpoint checks, and inference are user-run operations; publishing this commit does not execute them.
