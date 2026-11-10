"""Aggregate DiverseFlow per-round evaluation CSVs into CuraFlow score sources.

DiverseFlow writes, for each workflow round, one or more per-query evaluation
CSVs (columns: ``question, prediction, expected_output, score, cost``). CuraFlow
(``CuraFlow/k_coverage_selection.py``) and the selector-data builder both consume
a JSON mapping ``{workflow_label: [score_per_query]}`` aligned across workflows.

This script reads one round directory (or explicit CSVs) per workflow, averages
the per-query ``score`` (and ``cost``) across repeated evaluation runs, aligns all
workflows on their common set of questions, and writes:

    <out>/sources.json   {label: [effect_per_query]}   (feed to CuraFlow --sources)
    <out>/costs.json     {label: [cost_per_query]}
    <out>/queries.json   [question_text, ...]           (feed to build_selector_data)

Usage
-----
    python data_processing/aggregate_round_scores.py \
        --workflow W1_AF_R4 workspace_qwen3/AMC/workflows/round_4 \
        --workflow W2_SF_R1 workspace_qwen3/AMC/workflows_scoreflow/round_1 \
        --out runs/math_from_diverseflow

Each ``--workflow LABEL PATH`` pair gives a label and either a round directory
or a single eval file. A directory is scanned NON-recursively for ``*.jsonl`` and
``*.csv`` eval files, averaging their per-query ``score``. Point it at ``round_N``
for the generation-time TRAIN/validation scores (DiverseFlow writes these jsonl
directly in the round dir), or at ``round_N/test_results`` for the held-out TEST
scores written by ``run_test.py`` — same command, just the right subdirectory.
"""
import argparse
import glob
import json
import os
from collections import defaultdict

import pandas as pd


def _iter_rows(fpath):
    """Yield {question, score, cost} dicts from a .jsonl (generation rounds and
    run_test.py test_results) or .csv eval file."""
    if fpath.endswith(".jsonl"):
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    else:
        for _, row in pd.read_csv(fpath).iterrows():
            yield row.to_dict()


def load_workflow_scores(path):
    """Return {question: (mean_score, mean_cost)} for a round dir or eval file.

    A directory is scanned (non-recursively) for both ``*.jsonl`` (DiverseFlow
    generation rounds and run_test.py test_results) and ``*.csv``; repeated eval
    runs of the same workflow are averaged per query. The query key is the
    ``question`` field (or ``inputs`` for ScoreFlow-style files).
    """
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.csv")) +
                       glob.glob(os.path.join(path, "*.jsonl")))
    else:
        files = [path]
    if not files:
        raise FileNotFoundError(f"no .csv/.jsonl eval files found at {path}")
    score_acc, cost_acc, cnt = defaultdict(float), defaultdict(float), defaultdict(int)
    for fpath in files:
        for row in _iter_rows(fpath):
            q = str(row.get("question", row.get("inputs", "")))
            if q == "" or "score" not in row:
                continue
            score_acc[q] += float(row["score"])
            cost_acc[q] += float(row.get("cost", 0.0) or 0.0)
            cnt[q] += 1
    return {q: (score_acc[q] / cnt[q], cost_acc[q] / cnt[q]) for q in cnt}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workflow", nargs=2, action="append", required=True,
                    metavar=("LABEL", "PATH"),
                    help="workflow label and its round dir or eval file .csv/.jsonl (repeatable)")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args()

    per_wf = {label: load_workflow_scores(path) for label, path in args.workflow}

    # Align on the questions common to all workflows, in a stable order.
    common = None
    for d in per_wf.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    if not common:
        raise ValueError("no questions are shared across all workflows")
    questions = sorted(common)
    dropped = {l: len(d) - len(questions) for l, d in per_wf.items()}
    if any(v for v in dropped.values()):
        print(f"NOTE: aligned to {len(questions)} shared questions; dropped per WF: {dropped}")

    sources = {l: [per_wf[l][q][0] for q in questions] for l in per_wf}
    costs = {l: [per_wf[l][q][1] for q in questions] for l in per_wf}

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "sources.json"), "w") as f:
        json.dump(sources, f, indent=2)
    with open(os.path.join(args.out, "costs.json"), "w") as f:
        json.dump(costs, f, indent=2)
    with open(os.path.join(args.out, "queries.json"), "w") as f:
        json.dump(questions, f, indent=2)
    print(f"Wrote {len(per_wf)} workflows x {len(questions)} queries -> {args.out}/")
    print("  next: CuraFlow/k_coverage_selection.py --sources "
          f"{os.path.join(args.out, 'sources.json')} ...")


if __name__ == "__main__":
    main()
