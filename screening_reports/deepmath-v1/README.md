# DeepMath screening progress

Updated: 2026-11-20T17:13:33.866416+00:00

Screening source: `61969f4a8c01410c6a72e68d56cad764d08bbd72`.

**15 fully screened; 52 triaged; 777 sampled responses completed.**

Checkpointed active time: 24.00 hours / 24 hours; interruption reserve: 0 seconds.

Screening complete: True. Audit lock present: False. Recent heartbeat: False.

| Bucket | Fully screened | Provisional | Audit accepted | Target |
|---|---:|---:|---:|---:|
| 0/32 | 5 | 5 | 0 | 5 |
| 1-8/32 | 2 | 2 | 0 | 5 |
| 9-16/32 | 1 | 1 | 0 | 5 |
| 17-24/32 | 2 | 2 | 0 | 5 |
| 25-32/32 | 5 | 5 | 0 | 5 |

## Current question requests

No outstanding sampled requests observed.

See [questions.csv](questions.csv) for every question with activity, [latest.json](latest.json) for diagnostics, and [history/](history/) for hourly snapshots.

Only row IDs and derived statistics are published. Question text, references, responses, request bodies, reviewer identities, and traces stay on scratch.

Buckets require 32 sampled responses; partial solve rates are descriptive. Selections remain provisional until manual audit. Pending request files may include interrupted calls. Checkpoints are read atomically per file; a report is a near-time snapshot, not a transaction across all files. Hourly Slurm jobs can be delayed by queueing or maintenance.
