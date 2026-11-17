"""Plot exhaustive workflow-subset union coverage; no model calls required."""
import argparse
import csv
import itertools
import json
from pathlib import Path
import statistics

WORKFLOWS = ('W1', 'W2', 'W3', 'W4')


def subset_coverage(rows):
    if not rows or len({r['question ID'] for r in rows}) != len(rows):
        raise ValueError('Expected a nonempty correctness matrix with unique item IDs')
    for row in rows:
        if any(row[w] not in ('0', '1') for w in ('baseline',) + WORKFLOWS):
            raise ValueError('Correctness entries must be 0 or 1')
    n = len(rows)
    solved = {w: {r['question ID'] for r in rows if r[w] == '1'} for w in WORKFLOWS}
    subsets = []
    summaries = []
    for k in range(1, 5):
        accuracies = []
        for members in itertools.combinations(WORKFLOWS, k):
            count = len(set.union(*(solved[w] for w in members)))
            accuracy = 100 * count / n
            subsets.append({'k': k, 'workflows': '+'.join(members), 'solved': count, 'N': n,
                            'accuracy_pct': accuracy,
                            'gain_over_best_member_pp': 100 * (count-max(len(solved[w]) for w in members))/n})
            accuracies.append(accuracy)
        summaries.append({'k': k, 'number_of_subsets': len(accuracies), 'N': n,
                          'min_accuracy_pct': min(accuracies),
                          'mean_accuracy_pct': statistics.mean(accuracies),
                          'best_accuracy_pct': max(accuracies)})
    baseline = 100 * sum(r['baseline'] == '1' for r in rows) / n
    return subsets, summaries, baseline


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render(root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with (root/'correctness_matrix.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    subsets, summaries, baseline = subset_coverage(rows)
    write_csv(root/'workflow_subsets.csv', subsets)
    write_csv(root/'complementarity_by_k.csv', summaries)
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42, 'ps.fonttype': 42})
    fig, ax = plt.subplots(figsize=(8, 5.3), layout='constrained')
    k = [r['k'] for r in summaries]
    best = [r['best_accuracy_pct'] for r in summaries]
    mean = [r['mean_accuracy_pct'] for r in summaries]
    low = [r['min_accuracy_pct'] for r in summaries]
    ax.fill_between(k, low, best, color='#0072B2', alpha=.13, label='Range across subsets')
    ax.scatter([r['k'] for r in subsets], [r['accuracy_pct'] for r in subsets],
               color='#6B7280', s=23, alpha=.6, zorder=3)
    ax.plot(k, best, color='#0072B2', linewidth=2.4, marker='o', markersize=7,
            label='Best subset (oracle upper bound)', zorder=4)
    ax.plot(k, mean, color='#D55E00', linewidth=2, linestyle='--', marker='s',
            markersize=5, label='Mean across subsets', zorder=5)
    ax.axhline(baseline, color='#555555', linewidth=1.5, linestyle=':',
               label=f'Qwen single baseline ({baseline:g}%)')
    gain = best[-1] - best[0]
    ax.text(.98, .44, f'Best single workflow: {best[0]:g}%\nAll four workflows: {best[-1]:g}%\n'
            f'Gain beyond best single: {gain:g} percentage points',
            transform=ax.transAxes, ha='right', va='center', fontsize=10,
            bbox={'facecolor':'white', 'edgecolor':'#DDDDDD', 'boxstyle':'round,pad=0.6'})
    ax.set_xticks(k, [f'k = {i}' for i in k])
    ax.set_xlim(.85, 4.15)
    # A focused percentage axis makes the small observed differences visible.
    ax.set_ylim(max(0, min(baseline, min(low))-2), min(100.8, max(best)+2.5))
    ax.set_xlabel('Number of workflows, k')
    ax.set_ylabel('Oracle union accuracy (%)')
    ax.set_title(f'Workflow complementarity on {len(rows)} frozen AMC items', loc='left', pad=12)
    ax.grid(axis='y', alpha=.22)
    ax.legend(loc='lower right', fontsize=9, frameon=True, facecolor='white', edgecolor='none', framealpha=.95)
    fig.get_layout_engine().set(rect=(0, .08, 1, .90))
    fig.text(.5, .015, 'Every subset of W1–W4 is evaluated; an item is covered if any member solves it.\n'
             'Retrospective coverage, not a deployable selector. Shading is the min–max range, not uncertainty.',
             ha='center', va='bottom', fontsize=8, color='#555555')
    for extension in ('png', 'pdf', 'svg'):
        fig.savefig(root/f'workflow_complementarity.{extension}', dpi=220, bbox_inches='tight', pad_inches=.15)
    plt.close(fig)
    (root/'plot_environment.json').write_text(json.dumps({'matplotlib':matplotlib.__version__,
        'definition':'Accuracy of the union of final solved sets for every subset of size k',
        'subset_counts':[r['number_of_subsets'] for r in summaries],
        'best_single_to_all_gain_pp':gain}, indent=2)+'\n')
    print(json.dumps({'baseline_accuracy_pct':baseline, 'coverage_by_k':summaries}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path,
        default=Path('experiment_results/amc50_qwen38_autoround_int4'))
    render(parser.parse_args().results_dir)
