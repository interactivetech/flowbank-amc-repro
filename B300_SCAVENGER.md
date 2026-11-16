# Run the AMC experiment on a B300 scavenger allocation

This guide runs the frozen 50-item AMC experiment with Qwen3.8-27B AutoRound INT4 on one B300, without Docker or Apptainer. Existing checkpoints, Python environments, weights, and caches live under `/scratch1/mendeza/flowbank-amc/`. The detailed runtime reference is [RUN_AMC.md](RUN_AMC.md), and the experiment definition is [AMC_EXPERIMENT_PLAN.md](AMC_EXPERIMENT_PLAN.md).

These commands are for a new allocation or recovery after an interrupted allocation. Do not launch a second runner while the current full experiment is still running against the same results directory.

## 1. Request a 10-hour B300 allocation

Run from the login node, preferably from the repository so the Slurm output lands there:

```bash
cd /nfshomes/mendeza/2026_projects/2026_848A/flowbank-amc-repro

sbatch \
  --account=scavenger \
  --partition=scavenger \
  --qos=scavenger \
  --nodelist=cml38 \
  --nodes=1 \
  --ntasks=1 \
  --gres=gpu:b300-sxm:1 \
  --cpus-per-task=16 \
  --mem=256G \
  --time=10:00:00 \
  --job-name=flowbank_amc \
  --output=slurm-%j.out \
  --wrap='sleep infinity'
```

The cluster's `scavenger` partition requires account `scavenger` and QoS `scavenger`; the original `cml-furongh` account and `cml-high_long` QoS cannot be kept with this partition. The above request was accepted by `sbatch --test-only` on 2026-11-16. That validation did not submit a job or reserve a start time.

`--time=10:00:00` is a 10-hour allocation limit. `sleep infinity` holds the allocation until its time limit, cancellation, or preemption; it does not automatically launch the model or experiment. Scavenger capacity is preemptible and is not guaranteed for the entire ten hours. Pinning `cml38` may increase queue time.

Save the job ID printed by `sbatch`, then check its status:

```bash
AMC_JOB_ID=REPLACE_WITH_SUBMITTED_JOB_ID
squeue -j "$AMC_JOB_ID" -o '%.18i %.12P %.20j %.10T %.12M %.12l %R'
```

## 2. Enter the running allocation

Once its state is `RUNNING`, attach from the login node:

```bash
srun \
  --jobid="$AMC_JOB_ID" \
  --overlap \
  --nodes=1 \
  --ntasks=1 \
  --gres=gpu:b300-sxm:1 \
  --cpus-per-task=16 \
  --pty bash -l
```

Keep the attached step open during the run, for example inside your existing terminal multiplexer session. `nohup` does not protect processes from Slurm step cleanup, allocation expiry, or preemption. Run the remaining commands inside this allocation, with both server and client on the same node:

```bash
cd /nfshomes/mendeza/2026_projects/2026_848A/flowbank-amc-repro
source scripts/amc_env.sh
hostname
printf 'Slurm job: %s\n' "$SLURM_JOB_ID"
nvidia-smi
```

## 3. Reuse scratch environments or perform first-time setup

The environments and pinned checkpoint have already been installed for the current experiment. Reuse them when resuming:

```bash
cat "$AMC_ROOT/model.lock.json"
"$AMC_ROOT/runtime/bin/python" -m pip check
```

For a first installation only, run:

```bash
bash scripts/setup_amc.sh
```

Setup creates dedicated Python 3.12 runtime/executor environments, downloads the quantized model, and records its immutable revision. All large artifacts and package/compilation caches go to scratch. Do not reinstall packages or change the checkpoint midway through a frozen experiment; resume checks their identity.

## 4. Start vLLM and verify readiness

```bash
bash scripts/start_vllm.sh
tail -n 60 "$AMC_ROOT/logs/vllm.log"
curl --fail http://127.0.0.1:8000/health
```

Repeat the health command until it succeeds. First startup can take several minutes to compile B300 kernels; later startups reuse the scratch cache. If it fails, inspect the server log. If a healthy server already exists in this allocation, reuse it rather than starting another.

The server exposes `http://127.0.0.1:8000/v1`, uses compressed-tensors INT4 weights and BF16 activations, and reserves up to 90% of GPU memory for the model and serving caches. A large allocation reported by `nvidia-smi` is expected even when requests are idle.

Run the real endpoint check:

```bash
bash scripts/run_amc.sh check
```

This verifies the pinned model ID, 262,144-token context, separated reasoning/final content, complete token usage, and acceptance of the 131,072-token generated-output allowance. Its artifacts are separate from the AMC evaluation.

## 5. Pilot or resume the full experiment

For a new experiment, run the three-item pilot first:

```bash
bash scripts/run_amc.sh pilot
bash scripts/run_amc.sh analyze-pilot
bash scripts/run_amc.sh status
```

The current experiment's pilot has already completed all 15 evaluations successfully. It does not need to be rerun. The pilot is part of the frozen 50-item manifest, so its results are reused by `full`.

Start or resume the full evaluation, followed by final analysis on success:

```bash
nohup bash -c \
  'bash scripts/run_amc.sh full && bash scripts/run_amc.sh analyze' \
  >> "$AMC_ROOT/logs/amc-full.log" 2>&1 < /dev/null &
echo "$!" > "$AMC_ROOT/runner.pid"
```

Run this command only once per active evaluation. The runner locks its result directory against concurrent writers. Do not change the code, dependencies, model, or decoding settings between checkpoints and resume.

The pilot took approximately 23.5 minutes for three questions across all five conditions. Extrapolating gives about six hours for the remaining 47 questions; a rough planning range is 4–10 hours, with substantial uncertainty from question difficulty and output length. Ten hours may not be sufficient for every run, and scavenger preemption can interrupt it sooner. Completion checkpoints make continuing in another allocation possible.

## 6. Monitor and inspect tables

```bash
bash scripts/run_amc.sh status
tail -n 30 "$AMC_ROOT/logs/amc-full.log"
tail -n 20 "$AMC_ROOT/logs/vllm.log"
squeue -j "$SLURM_JOB_ID"
```

`status` reports completed evaluations out of 250, truncations, parse failures, and saved infrastructure failures. Model-call traces and successful stage checkpoints are under `$AMC_ROOT/results/amc50/evaluations/`.

When all 250 evaluations finish, the background command generates the final tables. To regenerate them explicitly:

```bash
bash scripts/run_amc.sh analyze
cat "$AMC_ROOT/results/amc50/table1_baseline.md"
cat "$AMC_ROOT/results/amc50/table2_portfolio.md"
```

Analysis refuses incomplete data. CSV/LaTeX versions, a correctness matrix, token details, and a research summary are saved beside the Markdown tables. Pilot-only tables are in `pilot_analysis/`.

## 7. Recover from preemption or the 10-hour limit

1. Check whether Slurm requeued the allocation (`squeue -j JOB_ID`). If it did, wait for it to run again; otherwise submit another allocation using section 1.
2. Attach to the running job and return to this checkout.
3. Source `scripts/amc_env.sh`, start vLLM, and wait for `/health` to succeed.
4. Repeat the full evaluation command from section 5. Successful evaluations and stage calls are reused; the original manifest stays fixed.

A requeued `sleep infinity` job holds resources again but does not restart vLLM or the runner automatically. A response interrupted before its checkpoint was saved may need to be generated again. Do not delete the result directory to resume.

After the experiment and analysis finish, release an allocation from the login node using its exact job ID:

```bash
scancel "$AMC_JOB_ID"
```
