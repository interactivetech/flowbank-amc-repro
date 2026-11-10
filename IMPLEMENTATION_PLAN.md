# Plan and source inventory

1. Pin official repository; recover Appendix D.1 graphs from PDF (HTML omits code).
2. Implement environment-configured async client, math-verify grading, fixed manifest, and durable traces.
3. Reconstruct W1–W4 using recovered prompts and original operator contracts; mock-test graph order, selection, routing, and verification.
4. Add baseline, call checkpoints, immutable resume configuration, and offline analysis.
5. Verify endpoint and isolated Python execution; run 3 questions through all five conditions.
6. Only after the smoke test passes, run the preselected 50-question subset and generate tables.

No missing workflow prompts: all D.1 prompts and final return values recovered from PDF. Generic round_1 graph is not used. Missing runtime prerequisite initially: Docker daemon (started locally). Initial API key rejected; user supplied a replacement and connectivity succeeded.
