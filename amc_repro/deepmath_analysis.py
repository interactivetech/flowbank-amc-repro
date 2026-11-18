"""Offline DeepMath pilot inspection and complete-study figures/tables."""
import argparse
import csv
import json
from pathlib import Path
from .analyze import analyze, statistics, CONDITIONS, WF
from .deepmath import load_frozen, require_scratch, THRESHOLDS, COUNTS
from .storage import atomic_json
from scripts.plot_workflow_complementarity import subset_coverage, write_csv


def cohort_metrics(frozen, results):
    rows = []
    # Membership comes only from the immutable screening manifest.
    for threshold, expected in zip(THRESHOLDS, COUNTS):
        ids = frozen['cohorts'][str(threshold)]
        if len(ids) != expected: raise ValueError('Frozen cohort size mismatch')
        stats = statistics(results, ids)
        n = len(ids)
        best = max(WF, key=lambda w:stats['accuracy'][w])
        oracle = sum(any(results[q,w]['correct'] for w in WF) for q in ids)
        counts = {w:sum(results[q,w]['correct'] for q in ids) for w in CONDITIONS}
        rows.append({'max_screening_rate':threshold, 'N':n,'oracle_solved':oracle,
            'best_workflow':best,'best_individual_solved':counts[best],'baseline_solved':counts['baseline'],
            'oracle_pct':100*oracle/n,'best_individual_pct':100*counts[best]/n,
            'baseline_pct':100*counts['baseline']/n, 'gain_pp':100*(oracle-counts[best])/n,
            **{w+'_solved':counts[w] for w in WF}})
    return rows


def inspect_pilot(root):
    root = require_scratch(root)
    frozen = load_frozen(root/'manifest.json')
    ids = {q['question_id'] for q in frozen['questions'][:5]}
    records = [json.loads(p.read_text()) for p in root.glob('evaluations/*/*/result.json') if p.parent.parent.name in ids]
    records += [json.loads(p.read_text()) for p in root.glob('evaluations/*/*/failure.json') if p.parent.parent.name in ids and not (p.parent/'result.json').exists()]
    events = [json.loads(line) for p in root.glob('evaluations/*/*/trace.jsonl')
              if p.parent.parent.name in ids for line in p.read_text().splitlines()]
    calls = [e for e in events if e['event']=='llm_call']
    completed = sum(r['status']=='completed' for r in records)
    latency = sum(e.get('latency',0) for e in calls)
    tokens = sum(e.get('usage',{}).get('completion_tokens',0) or 0 for e in calls if e.get('usage'))
    complete = completed == 25
    report = {'completed':completed,'expected':25,'model_call_attempts':len(calls),
        'summed_request_latency_seconds':latency,'completion_tokens':tokens,
        'usage_complete':bool(calls) and all(e.get('usage') and isinstance(e['usage'].get('completion_tokens'),int) for e in calls),
        'completion_tokens_per_summed_request_second':tokens/latency if latency else None,
        'truncated_calls':sum(e.get('finish_reason')=='length' for e in calls),
        'parsing_failures':sum(r['grading_status']=='parse_failure' for r in records),
        'code_execution_errors':sum(e['event']=='code_execution' and e.get('status')!='Success' for e in events),
        'context_overflows':sum(e['event']=='context_overflow' for e in events),
        'failed_evaluations':sum(r['status']!='completed' for r in records),
        'remaining_evaluations_after_pilot':105,
        'estimated_remaining_hours':latency/2*(105/25)/3600 if complete and latency else None,
        'estimate_method':'Summed pilot request latency / concurrency 2, scaled by 105/25; approximate, not an allocation guarantee. Harder questions and retries may take longer.',
        'failures':[{'question_id':r['question_id'],'workflow_id':r['workflow_id'],'error':r.get('error')} for r in records if r.get('error')]}
    atomic_json(root/'pilot_inspection.json',report)
    if complete: analyze(root,5)
    print(json.dumps(report,indent=2))
    return report


def render_figures(output, datasets, cohorts):
    coverage = []
    for name, rows in datasets:
        _, summary, baseline = subset_coverage(rows)
        coverage.append({'dataset':name,'N':len(rows),'summary':summary,'baseline_pct':baseline})
    render_coverage(output, coverage, cohorts)


def render_coverage(output, coverage, cohorts):
    """Render from aggregate data so public figures need no private item contents."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig, axes = plt.subplots(1,2,figsize=(11,5),sharey=True,layout='constrained')
    for ax, data in zip(axes,coverage):
        name, summary, baseline = data['dataset'], data['summary'], data['baseline_pct']
        k = [r['k'] for r in summary]
        best = [r['best_accuracy_pct'] for r in summary]
        ax.fill_between(k,[r['min_accuracy_pct'] for r in summary],best,alpha=.15,color='#0072B2',label='Min–max range')
        ax.plot(k,best,'o-',color='#0072B2',label='Best subset')
        ax.plot(k,[r['mean_accuracy_pct'] for r in summary],'s--',color='#D55E00',label='Mean subset')
        ax.axhline(baseline,ls=':',color='#555555',label=f'Single-model baseline ({baseline:.1f}%)')
        ax.text(.04,.04,f'Best individual → four-workflow oracle\n{best[0]:.1f}% → {best[-1]:.1f}% (+{best[-1]-best[0]:.1f} pp)',transform=ax.transAxes,fontsize=9)
        ax.set(title=f'{name} (N={data["N"]})',xlabel='Number of workflows, k',xticks=k,ylim=(0,100))
        ax.grid(axis='y',alpha=.2)
        ax.legend(loc='center right',fontsize=8)
    axes[0].set_ylabel('Final-answer union accuracy (%)')
    fig.suptitle('Workflow complementarity: all 15 subsets of W1–W4')
    for suffix in ('png','pdf','svg'): fig.savefig(output/f'figure1_complementarity.{suffix}',dpi=220)
    plt.close(fig)
    fig,(upper,lower) = plt.subplots(2,1,figsize=(8,7),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[2,1]})
    x = list(range(len(cohorts)))
    for key,label,color in [('oracle_pct','Four-workflow oracle','#0072B2'),('best_individual_pct','Best individual within cohort','#D55E00'),('baseline_pct','Fresh single-model baseline','#555555')]:
        upper.plot(x,[r[key] for r in cohorts],'o-',label=label,color=color)
    upper.set(ylim=(0,100),ylabel='Final-answer accuracy (%)',title='Oracle performance on progressively harder questions')
    upper.legend(fontsize=9)
    lower.plot(x,[r['gain_pp'] for r in cohorts],'o-',color='#0072B2')
    lower.set(ylabel='Oracle − best (pp)',xlabel='Maximum historical screening solve rate (difficulty increases →)',
              ylim=(0,min(100,max(5,max(r['gain_pp'] for r in cohorts)*1.25))))
    lower.set_xticks(x,[f'{100*r["max_screening_rate"]:g}%\nN={r["N"]}' for r in cohorts])
    for ax in (upper,lower): ax.grid(axis='y',alpha=.2)
    fig.get_layout_engine().set(rect=(0,.08,1,.92))
    fig.text(.5,.01,'Overlapping nested cohorts; screening labels are frozen.\n0/32 means no observed screening successes. Oracle is retrospective coverage.',ha='center',fontsize=8)
    for suffix in ('png','pdf','svg'): fig.savefig(output/f'figure2_harder_cohorts.{suffix}',dpi=220)
    plt.close(fig)
    atomic_json(output/'plot_environment.json',{'matplotlib':matplotlib.__version__})


def final_analysis(root, amc_root):
    root = require_scratch(root)
    frozen = load_frozen(root/'manifest.json')
    records = [json.loads(p.read_text()) for p in root.glob('evaluations/*/*/result.json')]
    results = {(r['question_id'],r['workflow_id']):r for r in records}
    ids = [q['question_id'] for q in frozen['questions']]
    stats = statistics(results,ids)  # Refuse all final output until all 130 are complete.
    if len(results) != 130: raise ValueError('Expected exactly 130 evaluations')
    stats = analyze(root)
    output = root/'comparison'
    output.mkdir(exist_ok=True)
    with (Path(amc_root)/'correctness_matrix.csv').open() as f: amc = list(csv.DictReader(f))
    with (root/'correctness_matrix.csv').open() as f: deep = list(csv.DictReader(f))
    subsets, summaries = [], []
    for name, rows in [('AMC',amc),('DeepMath',deep)]:
        sub, summary, baseline = subset_coverage(rows)
        subsets.extend({'dataset':name,**r} for r in sub)
        summaries.extend({'dataset':name,'baseline_pct':baseline,**r} for r in summary)
    cohorts = cohort_metrics(frozen,results)
    write_csv(output/'all_subset_coverage.csv',subsets)
    write_csv(output/'complementarity_by_k.csv',summaries)
    write_csv(output/'cohort_metrics.csv',cohorts)
    write_csv(output/'cohort_membership.csv',[{'question_id':q,'max_screening_rate':t} for t in THRESHOLDS for q in frozen['cohorts'][str(t)]])
    write_csv(output/'per_item_correctness.csv',[{'question_id':q['question_id'],**q['screening'],
        **{w:int(results[q['question_id'],w]['correct']) for w in CONDITIONS}} for q in frozen['questions']])
    write_csv(output/'evaluation_costs.csv',[{'question_id':q,'workflow_id':w,
        **{k:results[q,w].get(k) for k in ('prompt_tokens','completion_tokens','usage_complete','llm_calls','truncated_calls','grading_status','latency_this_attempt')}} for q in ids for w in CONDITIONS])
    write_csv(output/'condition_diagnostics.csv',[{'workflow_id':w,**stats['token_usage'][w],
        'parsing_failures':stats['parsing_failures'][w]} for w in CONDITIONS])
    render_figures(output,[('AMC',amc),('DeepMath',deep)],cohorts)
    report = (f'# DeepMath workflow complementarity\n\nAll 130 fresh evaluations on 26 adaptively screened questions are complete. '
        f'Baseline: {100*stats["accuracy"]["baseline"]:.1f}%; best individual: {100*stats["best_individual_accuracy"]:.1f}%; '
        f'four-workflow oracle: {100*stats["oracle_coverage"]:.1f}%; gain: {100*stats["complementarity_gain"]:.1f} percentage points.\n\n'
        'Historical correct/32 values are screening difficulty labels, not baseline results. Original decoding, quantization and grading settings are undocumented. '
        'Without the original responses, low screening rates cannot be separated from grading differences. Conclusions apply to these 26 questions. '
        'Oracle uses final answers and ground truth retrospectively; it is an upper bound, not a deployable selector. '
        'Cohorts overlap and are defined solely by frozen historical rates. 0/32 means no observed screening successes, not unsolvability. '
        'Best individual is recomputed within each cohort.\n\n'
        '![Complementarity](figure1_complementarity.png)\n\n![Harder cohorts](figure2_harder_cohorts.png)\n\n'
        '| Maximum screening rate | N | Oracle solved | Best individual solved | Baseline solved | Gain (pp) |\n|---|---|---|---|---|---|\n')
    report += ''.join(f'| {100*r["max_screening_rate"]:g}% | {r["N"]} | {r["oracle_solved"]} | {r["best_individual_solved"]} | {r["baseline_solved"]} | {r["gain_pp"]:.1f} |\n' for r in cohorts)
    report += '\nReference concerns were frozen before inference; supplied labels remain unchanged. See private reference_preflight.json and manifest.json. Proof validity is not graded.\n\n'
    report += '[Baseline table](../table1_baseline.md) · [Portfolio table](../table2_portfolio.md) · [Costs and failures](condition_diagnostics.csv)\n\n'
    report += 'Reproduce: `bash scripts/run_deepmath.sh analyze`. Private questions, solutions and traces stay on scratch; publishing them requires separate authorization.\n'
    (output/'RESULTS_REPORT.md').write_text(report)
    return stats


def plot_archive(root, output):
    """Replot published aggregate CSVs; no references, private data, or model calls."""
    def read_numbers(path):
        with path.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            for key, value in row.items():
                if key in ('dataset','best_workflow'): continue
                row[key] = float(value)
                if row[key].is_integer(): row[key] = int(row[key])
        return rows
    summaries = read_numbers(Path(root)/'complementarity_by_k.csv')
    cohorts = read_numbers(Path(root)/'cohort_metrics.csv')
    coverage = []
    for name in ('AMC','DeepMath'):
        rows = sorted((r for r in summaries if r['dataset']==name), key=lambda r:r['k'])
        if [r['k'] for r in rows] != [1,2,3,4]: raise ValueError('Expected k=1..4 per dataset')
        coverage.append({'dataset':name,'N':rows[0]['N'],'baseline_pct':rows[0]['baseline_pct'],'summary':rows})
    if [r['N'] for r in cohorts] != list(COUNTS): raise ValueError('Unexpected cohort sizes')
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    render_coverage(output, coverage, cohorts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['pilot','final','plot'])
    p.add_argument('--results-dir',type=Path,required=True)
    p.add_argument('--amc-results-dir',type=Path,default=Path('experiment_results/amc50_qwen38_autoround_int4'))
    p.add_argument('--output-dir',type=Path,help='Required for plotting public aggregate CSVs')
    args = p.parse_args()
    if args.action == 'plot':
        if args.output_dir is None: p.error('plot requires --output-dir')
        plot_archive(args.results_dir,args.output_dir)
    elif args.action == 'pilot': inspect_pilot(args.results_dir)
    else: final_analysis(args.results_dir,args.amc_results_dir)

if __name__ == '__main__': main()
