import pytest
from scripts.plot_workflow_complementarity import subset_coverage


def test_union_coverage_exhaustive_and_baseline_excluded():
    rows = [dict(zip(('question ID','baseline','W1','W2','W3','W4'), row)) for row in [
        ('a','1','1','0','0','0'), ('b','1','0','1','0','0'),
        ('c','1','0','0','0','0'), ('d','1','0','0','0','0')]]
    subsets, summaries, baseline = subset_coverage(rows)
    assert baseline == 100
    assert len(subsets) == 15
    assert [r['number_of_subsets'] for r in summaries] == [4,6,4,1]
    assert summaries[0]['best_accuracy_pct'] == 25
    assert summaries[-1]['best_accuracy_pct'] == 50
    pair = next(r for r in subsets if r['workflows'] == 'W1+W2')
    assert pair['solved'] == 2 and pair['gain_over_best_member_pp'] == 25


@pytest.mark.parametrize('rows', [[], [{'question ID':'a','baseline':'1','W1':'2','W2':'0','W3':'0','W4':'0'}]])
def test_invalid_matrix(rows):
    with pytest.raises(ValueError): subset_coverage(rows)
