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
