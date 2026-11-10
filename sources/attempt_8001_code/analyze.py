"""Recompute every statistic from saved results; never calls a model."""
import argparse
import csv
import itertools
import json
from pathlib import Path
from .storage import atomic_json

CONDITIONS = ['baseline','W1','W2','W3','W4']
WF = CONDITIONS[1:]


def statistics(results, ids):
    for q in ids:
        if any((q,w) not in results for w in CONDITIONS):
            raise ValueError('Incomplete matrix: refusing to report partial portfolio accuracy')
        if any(results[q,w]['status'] != 'completed' for w in CONDITIONS):
            raise ValueError('Failed evaluations cannot be treated as mathematical errors')
    n = len(ids)
    solved = {w:{q for q in ids if results[q,w]['correct']} for w in CONDITIONS}
    oracle = set.union(*(solved[w] for w in WF))
    accuracy = {w:len(solved[w])/n for w in CONDITIONS}
    unique = {w:len(solved[w] - set.union(*(solved[v] for v in WF if v != w))) for w in WF}
    pairs = {}
    for a,b in itertools.combinations(WF,2):
        inter,union = solved[a]&solved[b],solved[a]|solved[b]
        pairs[a+'_'+b] = {'intersection_count':len(inter),'union_count':len(union),
                         'jaccard':len(inter)/len(union) if union else None,
                         'both_wrong':n-len(union),'a_only':len(solved[a]-solved[b]),'b_only':len(solved[b]-solved[a])}
    return {'sample_size':n,'accuracy':accuracy,'oracle_coverage':len(oracle)/n,
            'best_individual_accuracy':max(accuracy[w] for w in WF),
            'complementarity_gain':len(oracle)/n-max(accuracy[w] for w in WF),
            'oracle_minus_baseline':len(oracle)/n-accuracy['baseline'],
            'unique_wins':unique,'unsolved_count':n-len(oracle), 'pairwise_overlap':pairs,
            'solution_loss':{w:{stage:sum(results[q,w].get('loss_stage')==stage for q in ids)
                                for stage in ['aggregation','verification','selection_parse_failure']} for w in WF},
            'parsing_failures':{w:sum(results[q,w]['grading_status']=='parse_failure' for q in ids) for w in CONDITIONS}}


def table(path, headers, rows):
    with path.with_suffix('.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    content = '| ' + ' | '.join(headers) + ' |\n|' + '|'.join(['---']*len(headers)) + '|\n'
    content += ''.join('| ' + ' | '.join(map(str,row)) + ' |\n' for row in rows)
    path.with_suffix('.md').write_text(content)
    # Standalone LaTeX table ready for inclusion in a manuscript.
    def esc(x): return str(x).replace('_',r'\_').replace('%',r'\%')
    latex = '\\begin{tabular}{'+'l'*len(headers)+'}\n\\hline\n'
    latex += ' & '.join(map(esc,headers)) + ' \\\\\n\\hline\n'
    latex += ''.join(' & '.join(map(esc,row)) + ' \\\\\n' for row in rows)
    path.with_suffix('.tex').write_text(latex+'\\hline\n\\end{tabular}\n')


def analyze(root):
    root = Path(root)
    manifest = json.loads((root/'manifest.json').read_text())
    ids = [q['question_id'] for q in manifest['questions']]
    records = [json.loads(p.read_text()) for p in root.glob('evaluations/*/*/result.json')]
    results = {(r['question_id'],r['workflow_id']):r for r in records}
    stats = statistics(results,ids)
    metadata = json.loads((root/'metadata.json').read_text())
    stats['model_metadata'] = metadata
    def mean(w,key):
        if key in ('prompt_tokens','completion_tokens') and not all(results[q,w]['usage_complete'] for q in ids): return 'unavailable'
        return round(sum(results[q,w][key] for q in ids)/len(ids),2)
    pct = lambda x:f'{100*x:.1f}%'
    n = len(ids)
    rows = [[metadata['model'],n,json.dumps(metadata['request_parameters'],sort_keys=True),pct(stats['accuracy']['baseline']),
             mean('baseline','prompt_tokens'),mean('baseline','completion_tokens')]]
    table(root/'table1_baseline',['model','sample size','decoding settings','accuracy','mean input tokens','mean output tokens'],rows)
    portfolio = []
    for w in WF:
        token = (round(sum(results[q,w]['prompt_tokens']+results[q,w]['completion_tokens'] for q in ids)/n,2)
                 if all(results[q,w]['usage_complete'] for q in ids) else 'unavailable')
        portfolio.append([w,n,pct(stats['accuracy'][w]),stats['unique_wins'][w],token,mean(w,'llm_calls')])
    total = round(sum(results[q,w]['prompt_tokens']+results[q,w]['completion_tokens'] for q in ids for w in WF)/n,2)
    if not all(results[q,w]['usage_complete'] for q in ids for w in WF): total='unavailable'
    portfolio.append(['Oracle portfolio coverage',n,pct(stats['oracle_coverage']),'N/A',total,
                      round(sum(results[q,w]['llm_calls'] for q in ids for w in WF)/n,2)])
    table(root/'table2_portfolio',['workflow','sample size','accuracy','unique wins','mean total tokens','mean LLM calls'],portfolio)
    table(root/'correctness_matrix',['question ID']+CONDITIONS,
          [[q]+[int(results[q,w]['correct']) for w in CONDITIONS] for q in ids])
    atomic_json(root/'summary.json',stats)
    with (root/'raw_traces.jsonl').open('w') as out:
        for q in ids:
            for w in CONDITIONS:
                out.write((root/'evaluations'/q/w/'trace.jsonl').read_text())
    summary = (f"Evaluated {n} fixed AMC questions with {metadata['model']}. Baseline accuracy: {pct(stats['accuracy']['baseline'])}. "
               f"Best individual workflow: {pct(stats['best_individual_accuracy'])}; oracle coverage: {pct(stats['oracle_coverage'])}. "
               f"Complementarity gain: {100*stats['complementarity_gain']:.1f} percentage points "
               f"({round(n*stats['complementarity_gain'])} additional questions). Oracle exceeds baseline by "
               f"{100*stats['oracle_minus_baseline']:.1f} points. No workflow solved {stats['unsolved_count']} questions.\n\n"
               "Oracle uses ground truth retrospectively and is an upper bound, not a deployable selector or GNN accuracy. "
               "Portfolio token/call costs sum all four workflows. Unique wins exclude the baseline. "
               "These are descriptive results on this subset; they do not establish population significance.\n")
    (root/'RESEARCH_SUMMARY.md').write_text(summary)
    print(summary)
    return stats

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--results-dir',default='results/amc')
    analyze(p.parse_args().results_dir)
