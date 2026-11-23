# Token cost and accuracy comparison

**Exploratory; dataset audit pending.** All conditions evaluated the same 21 screened DeepMath questions. This experiment does not enforce equal total token budgets across conditions.

| Condition | Mean input + output tokens/question | Relative to baseline | Accuracy |
|---|---:|---:|---:|
| Baseline | 30,052 | 1.00× | 47.6% |
| W1 | 83,141 | 2.77× | 57.1% |
| W2 | 135,851 | 4.52× | 47.6% |
| W3 | 125,472 | 4.18× | 52.4% |
| W4 | 27,205 | 0.91× | 57.1% |

The table uses measured mean prompt plus completion tokens from [condition diagnostics](condition_diagnostics.csv), including reasoning tokens in completion usage. Accuracy comes from [the experiment summary](../summary.json). Displayed token counts are rounded; cost ratios use the saved mean values. These ratios measure token usage, not hardware compute or monetary cost: input processing, generation, and Python execution have different costs.

## Budget interpretation

The maximum is **131,072 generated tokens per model call**, not per complete workflow. The baseline makes one call. W1 makes three candidate calls plus selection; W2/W3 normally make five calls, with additional calls possible for Programmer retries; W4 makes two calls. Therefore, equal per-call caps do not establish equal total budgets.

For example, W1 can receive up to four times the baseline's generated-token allowance. A fixed 131,072-token total budget could instead allocate 32,768 tokens to each of its four calls, including selection. That is a possible future control, not the configuration used here, and it would still require accounting for prompt-processing cost.

W4 achieved higher observed accuracy with fewer mean tokens than baseline. This is an observation on 21 selected questions, not evidence of a reliable general efficiency advantage.

## Oracle interpretation and limitations

Running all four workflows used approximately **371,670 total tokens per question**, or **12.37×** the baseline's token usage. Their retrospective oracle solved **16/21 (76.2%)**, compared with **10/21 (47.6%)** for the baseline. Oracle coverage uses ground truth to identify whether any workflow succeeded; a deployable selector achieving that coverage has not been demonstrated.

A repeated direct-sampling baseline is missing. A stronger comparison would match total generation budgets, report actual token usage and latency, compare selected-answer accuracy separately from oracle coverage, and use fresh direct samples with a predefined voting or selection rule. W1 plus W4 already attains the full four-workflow oracle coverage on this sample; W2/W3 add no solved questions beyond that pair.

Grading and sampling also limit interpretation: the baseline has six final-answer parse failures; manual dataset audit is pending; and the 21 questions were adaptively selected using the same model checkpoint. The observed accuracy is not an estimate of performance across DeepMath-103K.

The supported conclusion is that the fixed workflows produced complementary correct answers on this provisional selection under unequal compute budgets. The experiment does not isolate a workflow advantage at equal compute.
