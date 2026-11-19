# Hourly public screening reports

The `screening-reports` branch publishes progress under [screening_reports/deepmath-v1/](../screening_reports/deepmath-v1/). It uses a separate worktree, so reporting commits do not alter `slurm_env`, the pinned screening source, or its continuation checks. No inference is performed by reporting.

Each update commits and pushes a readable summary, `latest.json`, `questions.csv`, and UTC-hour snapshots under `history/`. Question IDs/source row indices identify the screened questions without publishing their text. Rows include candidate order, completed sampled responses, observed correctness, triage results, final bucket only after 32 responses, provisional selection, audit state, greedy-control completion, and diagnostics. Current requests are inferred from durable request/checkpoint files and may include interrupted requests. Partial solve rates are descriptive. Audit state is checked against saved evidence; reviewer names are excluded.

Reports also include dataset/model revisions, the original screening source commit, candidate totals, calibration outcomes, budget use, interruption reserve, heartbeat freshness, and completion/lock state. Question text, gold answers, response text, request bodies, raw traces, raw exception messages, credentials, and reviewer identities are never copied into the report schema. Checkpoints are atomic individually; the entire report is a near-time snapshot across files.

The publisher stages only `screening_reports/deepmath-v1/`, commits on `screening-reports`, and makes a normal fast-forward push. Unrelated edits and pushes conflicting with remote history fail safely. Failed pushes retain the local commits for the next hourly attempt. Inspect scratch `reporting/report-*.log` for failures.

User cron is disabled on this cluster. A short CPU-only Slurm job schedules the next job for 60 minutes later, then publishes a snapshot. The successor is scheduled before publication so a network/push failure does not break the chain. Scheduling checks prevent duplicate pending successors. Scratch is node-local, so reporting jobs are explicitly pinned to `cml38`, which holds these checkpoints and the reporting checkout. These jobs are independent of the GPU allocation; queueing and maintenance can delay reports. They request one CPU, 1 GB RAM, at most ten minutes, and no GPUs. The chain stops at the configured UTC deadline, an audit lock, or the scratch `reporting/STOP` marker. The last scheduled tick still publishes the final locked report.

Runtime paths:

- Reporting worktree: `/scratch1/mendeza/flowbank-amc/reporting-checkout`.
- Private screening run: `/scratch1/mendeza/flowbank-amc/screening/deepmath-v1`.
- Reporter schedule, lock, last publication, stop marker, and logs: `<run>/reporting/`.

From the reporting worktree:

```bash
PYTHON=/scratch1/mendeza/flowbank-amc/screening-env/bin/python
RUN_ROOT=/scratch1/mendeza/flowbank-amc/screening/deepmath-v1
# One immediate committed/pushed update:
"$PYTHON" monitoring/screening_reporter.py once --run-root "$RUN_ROOT" --publish
# Schedule hourly jobs; replace this example with the desired UTC deadline:
"$PYTHON" monitoring/screening_reporter.py schedule --run-root "$RUN_ROOT" \
  --until 2026-11-21T22:00:00+00:00
# Stop future reporting (the already-pending job exits when it sees the marker):
"$PYTHON" monitoring/screening_reporter.py stop --run-root "$RUN_ROOT"
```

To resume scheduling, remove the explicit STOP marker, set a fresh deadline, and run `schedule` again. A pending successor is reused. `once` without `--publish` writes reports locally for inspection. Tests use synthetic private fields and temporary local Git remotes:

```bash
"$PYTHON" -m pytest monitoring/test_screening_reporter.py -q
```
