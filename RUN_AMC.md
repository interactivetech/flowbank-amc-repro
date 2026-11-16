# Run the AMC comparison

For allocation submission and preemption recovery, see [B300_SCAVENGER.md](B300_SCAVENGER.md).

The saved specification is [AMC_EXPERIMENT_PLAN.md](AMC_EXPERIMENT_PLAN.md). All commands below start from this repository. No model inference is performed by installation. **Setup downloads weights; `check` performs a real inference request.**

## 1. Review and commit before running

```bash
git diff --check
git diff
git status --short
git add .gitignore README.md REPRODUCTION_NOTES.md EXPERIMENT_STATUS.md \
  AMC_EXPERIMENT_PLAN.md RUN_AMC.md requirements.slurm.txt requirements.executor.txt \
  amc_repro scripts tests
git commit -m "Prepare Slurm AMC evaluation with Qwen AutoRound INT4"
```

## 2. Install and download to scratch

```bash
bash scripts/setup_amc.sh
source scripts/amc_env.sh
cat "$AMC_ROOT/model.lock.json"
```

Default storage root: `/scratch1/mendeza/flowbank-amc`. Override `AMC_ROOT` **before sourcing** the environment script if needed, and retain it for all subsequent commands. The script uses `/scratch1/mendeza/CREST_mendeza_b300/env/bin/python` solely to create new Python 3.12 virtual environments; it does not install into that existing environment. To use another Python 3.12, export `AMC_PYTHON312=/absolute/path/to/python` before setup.

Setup installs pinned core dependencies, records full package freezes, downloads the checkpoint, and saves an immutable revision lock. Rerunning setup reuses the locked revision. Do not rerun setup or change dependencies midway through an experiment. The older `requirements.lock.txt` is a historical client-only environment and is not used here.

## 3. Launch inside the allocated GPU node

Use the existing GPU Slurm allocation. In a later allocation, return to this checkout and repeat this section with the same scratch root. The server and runner must be on the same node because the endpoint is loopback-only.

```bash
source scripts/amc_env.sh
bash scripts/start_vllm.sh
tail -n 60 "$AMC_ROOT/logs/vllm.log"
curl --fail http://127.0.0.1:8000/health
```

Repeat the health command after model loading finishes. First startup may take several minutes while CUDA kernels compile; later startups reuse the scratch cache. The environment script adds the runtime tools to PATH and uses `/opt/common/cuda/cuda-13.0.2` when CUDA_HOME is unset and that toolkit exists. To choose another installed toolkit, export CUDA_HOME before sourcing the script. A successful launcher message does not mean the model is ready; inspect its log if health fails. Startup uses the checkpoint's compressed-tensors INT4 format; kernel/model incompatibility is an error, with no precision fallback. Speculative decoding is disabled.

Inspect or stop the server:

```bash
ps -p "$(cat "$AMC_ROOT/vllm.pid")" -o pid,etime,args
nvidia-smi
# Run only when you intend to stop the server and its process group:
kill -TERM -- "-$(cat "$AMC_ROOT/vllm.pid")"
```

A background process cannot outlive its Slurm allocation. `nohup` keeps logs and detaches terminal input; it does not reserve GPU time.

## 4. Check the endpoint, then run the pilot

```bash
bash scripts/run_amc.sh check
bash scripts/run_amc.sh pilot
bash scripts/run_amc.sh status
bash scripts/run_amc.sh analyze-pilot
```

`check` verifies the revision-bearing served ID, advertised context length, acceptance of the full output allowance, separated reasoning/final content, and complete usage. It makes a real model call and saves it separately from evaluation data.

The pilot schedules the first three members of the full 50-item manifest across all five conditions, without modifying that manifest. Successful pilot execution exits zero while `run_status.json` still says `incomplete` with 235 remaining evaluations. Verify `scheduled_missing` is zero. Pilot tables and supporting files are under `$AMC_ROOT/results/amc50/pilot_analysis/`.

Inspect failures, truncations, reasoning, and Programmer traces before continuing. An invalid selector is a completed parse failure; infrastructure failures remain incomplete. Generated code runs as your account with resource limits, without filesystem/network isolation.

## 5. Run or resume the remaining items

```bash
bash scripts/run_amc.sh full
```

The same command resumes after interruption and skips completed evaluations and successful stage calls. Do not run two runners against this result directory. To keep the runner in the background within the allocation:

```bash
nohup bash scripts/run_amc.sh full > "$AMC_ROOT/logs/amc-full.log" 2>&1 < /dev/null &
echo "$!" > "$AMC_ROOT/runner.pid"
tail -n 30 "$AMC_ROOT/logs/amc-full.log"
bash scripts/run_amc.sh status
squeue -j "$SLURM_JOB_ID"
```

Use either the foreground or background command. All 50 items use the same model, thinking-on greedy settings, and 131,072 generated tokens **per call**, including reasoning. Baseline has one rollout; workflows can consume more overall. Expect at least 850 calls. Request timeout is four hours; actual runtime depends on generated lengths. Context overflow is recorded as an infrastructure failure with prompt size; it is never silently truncated. Resolve such a failure with an explicitly revised experiment rather than mixing settings into this result directory.

For a new Slurm allocation, source the environment, launch the same server, wait for health, and repeat `bash scripts/run_amc.sh full`. Resume rejects changed model, packages, executor, decoding, or source. A crash immediately after a response but before durable checkpointing can repeat that request; this cannot provide exactly-once inference.

## 6. Generate final tables

```bash
bash scripts/run_amc.sh status
bash scripts/run_amc.sh analyze
cat "$AMC_ROOT/results/amc50/table1_baseline.md"
cat "$AMC_ROOT/results/amc50/table2_portfolio.md"
```

Final analysis refuses an incomplete 250-evaluation matrix. Table files are Markdown/CSV/LaTeX under `$AMC_ROOT/results/amc50/`. Mean tokens sum input and output, including reasoning, across all calls per item. Wins vs Qwen count items solved by a workflow but missed by the baseline. Oracle is union coverage, with em dashes for wins and tokens. JSON retains separate token counts, truncations, workflow-exclusive wins, and portfolio costs. No results are written into this checkout by these commands.

To rerun local tests after setup (no model calls):

```bash
"$AMC_ROOT/runtime/bin/python" -m pytest -q
```
