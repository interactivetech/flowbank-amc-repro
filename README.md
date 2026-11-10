# FlowBank AMC workflow complementarity reproduction

This project reconstructs Appendix D.1 W1–W4 and compares them with a direct single-agent baseline on a fixed official AMC test subset. It excludes W5, workflow training, GNN selection, and DeepMath. The oracle is a retrospective upper bound, not a selector.

## Setup

Run commands from this directory. The FlowBank source files are included in `vendor/FlowBank`; their upstream commit is recorded in `sources/provenance.json`:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
source .venv/bin/activate
cp .env.example .env  # fill in the API key; never commit .env
# Start Docker Desktop, then build the isolated verification environment:
docker build -f Dockerfile.sandbox -t amc-repro-sandbox:1 .
python -m amc_repro.check_endpoint
python -m pytest -q
```

The local `.env` is ignored and permission-restricted. Model IDs are discovered via `/models`; set optional `OPENAI_MODEL` only when multiple models are listed. The original port-8001 endpoint resolved `qwen3.8-27b`, but remained busy. The user authorized port 8000 and `deepseek-v4-flash` (advertised display name `DeepSeek V4.1 Flash`) for the executed experiment. Configure `OPENAI_MODEL=deepseek-v4-flash` because that endpoint advertises two IDs. A minimal chat completion returned `OK`. Defaults: temperature 0, top-p 1, seed 42, max output tokens 4096, thinking off (DeepSeek `thinking.type=disabled`, Qwen `enable_thinking=false`), concurrency 1, 30 requests/minute, timeout 180s, three infrastructure retries. See saved metadata for actual run settings. Context capacity is not a generated-token allowance.

## Execute and resume

```bash
python -m amc_repro.run --sample-size 3 --seed 42 --results-dir results/smoke --concurrency 2
python -m amc_repro.analyze --results-dir results/smoke
python -m amc_repro.run --dataset datasets/amc_test.jsonl --sample-size 50 --seed 42 --workflows baseline,W1,W2,W3,W4 --results-dir results/amc --concurrency 2 --timeout 600
# Same command and parameters; completed evaluations and successful stage calls are reused:
python -m amc_repro.run --sample-size 50 --seed 42 --results-dir results/amc --concurrency 2 --timeout 600 --resume
python -m amc_repro.analyze --results-dir results/amc
```

Use `--sample-size 100` with a fresh directory for a larger preselected sample. `--concurrency 2` permits two workflows in flight while bounding LLM requests. Other options: `--temperature`, `--top-p`, `--inference-seed`, `--max-tokens`, `--thinking on|off|default`, `--requests-per-minute`, `--timeout`, `--retries`. Every option and source hash is bound in config.json; resume rejects changes. Use a fresh directory for a new experiment. Do not run concurrent runner processes against one directory.

The manifest is saved before any LLM calls and includes row IDs, complete original examples, extracted gold, and dataset hash. Failed workflows save failure.json; completed but wrong/parse-failed answers save result.json and are never retried. Resume may retry failed infrastructure stages. ScEnsemble parsing failures receive no automatic retries. Programmer retries only syntax/execution errors, at most three generations, regardless of whether a successfully executed answer is wrong. Full return values preserve the released code-plus-output semantics.

## Outputs

Each result directory contains config.json, manifest.json, metadata.json, sandbox.json, evaluations/<question>/<condition>/result.json, per-stage call checkpoints and trace.jsonl. The timestamped run.log records question/workflow progress, model-call status, and short previews from the beginning and end of each response. Full responses remain in the per-evaluation trace.jsonl files. After offline analysis it also contains:

- table1_baseline and table2_portfolio, each as Markdown, CSV, and LaTeX;
- correctness_matrix in the same formats;
- summary.json: oracle, best workflow, complementarity gain, baseline comparison, pairwise solved-set overlap/Jaccard, unique wins, unsolved count, parsing failures and solution-loss stage counts;
- raw_traces.jsonl and RESEARCH_SUMMARY.md.

Analysis refuses an incomplete matrix. No model is called during analysis. Token counts come from server usage; oracle resource costs sum W1–W4, and unique wins exclude the baseline. Traces include exact request and response, model/settings, prompt/completion usage, finish reason, attempts/latency, selection, generated code and bounded execution stdout/stderr. Candidate correctness is added retrospectively, after generation, so answers cannot leak into selection. An interrupted call's consumed server tokens may be unknown.

See [REPRODUCTION_NOTES.md](REPRODUCTION_NOTES.md) for graph correspondence, prompt transcription, upstream grader differences, sandbox restrictions, retry policy, and limitations. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for source inventory. Do not interpret a gain on 50 questions as population significance or exact numerical replication of the published GPT-4o-mini study.

For the actual supervised experiment, both smoke and full run use `--concurrency 2`. The full run uses `--timeout 600` to tolerate temporary server queues. Reuse those exact flags with `--resume`. `scripts/finish_experiment.py --wait-for-pid <smoke-pid>` optionally gates full execution on an active smoke process completing successfully. See EXPERIMENT_STATUS.md and saved run-status files.

Resume the current smoke test, if interrupted, with `python -m amc_repro.run --sample-size 3 --seed 42 --results-dir results/smoke --concurrency 2 --resume`. Do not run this command while the active smoke runner is still running.
