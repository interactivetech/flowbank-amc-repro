# DeepMath screening grading postmortem

The historical screening counts cannot support difficulty-based interpretations. The approved audit identified a string-versus-SymPy Boolean grading defect: passing a raw categorical reference string to a mathematical equivalence checker can reject a correct Boolean prediction. The checkpoint mismatch was real, but was not established as the cause of the audited 0/32 result.

## Evidence and its limits

The approved implementation plan reports a historical audit of the zero-success categorical item and confirms this grading defect. The original audit script and historical raw responses were not present in this workspace; the operator could not locate them during implementation. This document records that provenance limitation rather than claiming a fresh inspection of those files. Historical request settings and the complete incidence of affected labels remain unverified here.

A new offline regression reproduces the type mismatch with synthetic data in the pinned screening environment: `verify('Yes', [sympy.true])` is false, while `verify([sympy.true], [sympy.true])` is true. The corrected typed path interprets yes/no/true/false as categorical labels before mathematical parsing. Regression tests also cover boxed labels, negative labels, choices, numerical values, symbolic expressions, sets, angles, and complex values. A mathematical error, an unextractable model answer, a grader exception, and a transport failure have separate statuses. Grader exceptions quarantine the candidate; infrastructure failures leave the sampled slot incomplete.

A separate preserved RedHat probe returned **32/32 correct**, with no parse failures or truncated responses, on the historical zero-success categorical item. It took approximately 141 seconds and used 36,310 generated tokens. All requests used temperature 0, top-p 1, seed 42, and the fresh GENERAL baseline prompt. There were 17 distinct final response texts. This was a repeated greedy control, not 32 independent stochastic samples or a matched reconstruction of the historical screen. Its private evidence is at `/scratch1/mendeza/flowbank-amc/results/deepmath_redhat_row45570_repeat32/`.

The original workflow experiment used `MIRALABS/Qwen3.8-27B-W4A16-AutoRound`; the historical screening deployment used `RedHatAI/Qwen3.8-27B-INT4`. Changing checkpoint does not repair historical grading. The historical deployment also differed in tensor parallelism, context limit, and speculative decoding. The probe and original workflow measurements cannot isolate those factors.

## What remains descriptive

The completed workflow matrix, historical counts, manifests, tables, and figures are retained as recorded. Workflow accuracies, oracle coverage, parsing/truncation diagnostics, and complementarity describe those particular evaluated questions under their recorded configuration and grading. They do not establish complementarity as a function of independently measured difficulty. Historical nested cohorts and zero-success labels are not validated difficulty strata; any difficulty-gradient interpretation based on them is unsupported. Existing notes about ambiguous references remain relevant.

## Preservation and replacement

Before changing the running experiment, its source, uncommitted patch, scripts, deployment metadata, environment versions, allocation identity, frozen inputs, and successful result/call checkpoints were copied to `/scratch1/mendeza/flowbank-amc/preserved/redhat-before-rescreen-20261118/`. The snapshot contains 173 successful call checkpoints and 51 completed evaluations. The RedHat supervisor and batch runner were stopped; Slurm allocation 8437053 and the RedHat server were retained. The interrupted batch is not a completed 130-evaluation result and must not resume concurrently with screening.

The replacement screen uses a separate pinned environment and the frozen specification in [SCREENING_SPEC.md](SCREENING_SPEC.md). Code and documentation must be committed, pushed, verified against GitHub, and clean before even calibration inference. Full private request/response evidence, seed identities, source hashes, and the active-time ledger remain on scratch. The target is five audit-accepted questions in each of five disjoint sampled-success buckets; 24 active hours cannot guarantee those quotas. Only a manual audit can unlock a workflow-ready manifest. Screening does not launch W1–W4 evaluation.
