import csv
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from amc_repro import deepmath as dm, run, local_runtime
from amc_repro.grading import grade_typed
from amc_repro.storage import atomic_json
from amc_repro.deepmath_analysis import cohort_metrics, inspect_pilot, final_analysis


@pytest.fixture
def frozen_fixture(monkeypatch, tmp_path):
    # Synthetic input supports tests on machines without the production scratch mount.
    monkeypatch.setattr(dm,'require_scratch',lambda path:Path(path).absolute())
    with tempfile.TemporaryDirectory(prefix='deepmath-test-', dir=tmp_path) as directory:
        root = Path(directory)
        ids = [45570,3226,791,1659,96,503,391,3431,5699,13995,14286] + list(range(1000,1015))
        counts = [0]*5 + [4]*3 + [12]*3 + [20]*3 + [31]*12
        rows = []
        for number,count in zip(ids,counts):
            row = {'dataset_row':str(number),'question':f'SYNTHETIC_QUESTION_{number}',
                   'gold_answer':'42','correct':str(count),'responses':'32','solve_rate':str(count/32),
                   'difficulty':'5','difficulty_band':'synthetic','topic':'synthetic','source_checkpoints':'synthetic'}
            if number == 96: row['gold_answer']='0.8'
            if number == 45570: row['gold_answer']='Yes'
            if number == 3226: row['gold_answer']=r'\pm 1'
            if number == 503: row['gold_answer']='-5i'
            if number in (791,391,3431,5699,13995,14286):
                row.update(question=row['question']+'\n(A) $1$\n(B) $42$\n(C) $3$\n(D) $4$',gold_answer='B')
            rows.append(row)
        source = root/dm.FILENAME
        with source.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        monkeypatch.setattr(dm,'SHA256',hashlib.sha256(source.read_bytes()).hexdigest())
        frozen=dm.manifest(source)
        atomic_json(root/'manifest.json',frozen)
        yield root,frozen


def test_frozen_mapping_and_preflight(frozen_fixture):
    root,frozen=frozen_fixture
    assert [q['dataset_row'] for q in frozen['questions'][:5]] == list(dm.PILOT)
    assert [len(frozen['cohorts'][str(t)]) for t in dm.THRESHOLDS] == [26,14,11,8,5]
    assert len(frozen['cohorts']['0']) == 5
    assert all(q['gold_answer']==q['row']['gold_answer'] for q in frozen['questions'])
    with (root/dm.FILENAME).open(newline='') as stream:
        original = {int(r['dataset_row']):r for r in csv.DictReader(stream)}
    assert all(q['row']==original[q['dataset_row']] for q in frozen['questions'])
    assert '\n(A)' in next(q['row']['question'] for q in frozen['questions'] if q['dataset_row']==791)
    assert dm.preflight(frozen)['status']=='passed'
    assert dm.load_frozen(root/'manifest.json')==frozen
    frozen['questions'][0]['screening']['solve_rate']=1
    atomic_json(root/'manifest.json',frozen)
    with pytest.raises(ValueError,match='manifest mismatch'): dm.load_frozen(root/'manifest.json')


def test_source_and_rate_validation(frozen_fixture,monkeypatch):
    root,frozen=frozen_fixture
    source=root/dm.FILENAME
    source.write_bytes(source.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='source hash'): dm.manifest(source)
    source.write_text(source.read_text().replace(',32,',',31,',1))
    monkeypatch.setattr(dm,'SHA256',hashlib.sha256(source.read_bytes()).hexdigest())
    with pytest.raises(ValueError,match='screening counts'): dm.manifest(source)


def test_option_formats():
    assert dm.options(r'Choose:\nA. $17$\nB. $18$\nC. $19$\nD. $20$')['A']=='17'
    assert dm.options(r'(a) \((a-b)(a+b)\)'+'\n'+r'(b) \(2\)'+'\n'+r'(c) \(3\)'+'\n'+r'(d) None')['A']=='(a-b)(a+b)'
    assert dm.options(r'\(\text{(A) } \sin^4x \), \(\text{(B) } \sin^2x \), \(\text{(C) } \cos^2x \), \(\text{(D) does not exist} \).')['B']==r'\sin^2x'


@pytest.mark.parametrize('response,reference,correct',[
    ('Final answer: Yes.',{'kind':'boolean','gold':'Yes'},True),
    (r'\boxed{\text{Yes, } the identity holds.}',{'kind':'boolean','gold':'Yes'},True),
    (r'\boxed{\text{No, } a counterexample exists.}',{'kind':'boolean','gold':'Yes'},False),
    ('Yesterday it worked',{'kind':'boolean','gold':'Yes'},False),
    ('Code:\ndef solve(): return False\nOutput: False',{'kind':'boolean','gold':'Yes'},False),
    ('I said yes earlier\nI am unsure',{'kind':'boolean','gold':'Yes'},False),
    (r'\boxed{\frac{1}{2}}',{'kind':'choice','gold':'B','options':{'A':'1','B':'0.5','C':'3','D':'4'}},True),
    ('Option A',{'kind':'choice','gold':'B','options':{'A':'1','B':'0.5','C':'3','D':'4'}},False),
    ('1',{'kind':'math','gold':r'\pm 1'},False),
    (r'\{-1,1\}',{'kind':'math','gold':r'\pm 1'},True),
    ('-5j',{'kind':'complex','gold':'-5i'},True),
    ('5i',{'kind':'complex','gold':'-5i'},False),
    (r'-\frac{10}{2}i',{'kind':'complex','gold':'-5i'},True),
    (r'-\sqrt{25}i',{'kind':'complex','gold':'-5i'},True),
    ('60 degrees',{'kind':'math','gold':r'60^\circ'},True),
    (r'\frac{\pi}{3}',{'kind':'math','gold':r'60^\circ'},True),
    (r'\frac{\pi}{6}',{'kind':'math','gold':r'60^\circ'},False),
])
def test_typed_grading(response,reference,correct):
    assert grade_typed(response,reference)['correct'] is correct


def test_cohort_membership_outcome_independent(frozen_fixture):
    _,frozen=frozen_fixture
    before=json.dumps(frozen['cohorts'],sort_keys=True)
    ids=[q['question_id'] for q in frozen['questions']]
    def records(correct):
        return {(q,w):{'status':'completed','correct':correct,'grading_status':'correct'} for q in ids for w in ('baseline','W1','W2','W3','W4')}
    a=cohort_metrics(frozen,records(False));b=cohort_metrics(frozen,records(True))
    assert [r['N'] for r in a]==[r['N'] for r in b]==[26,14,11,8,5]
    assert a[-1]['oracle_solved']==0 and b[-1]['oracle_solved']==5
    assert json.dumps(frozen['cohorts'],sort_keys=True)==before


@pytest.mark.asyncio
async def test_deepmath_pilot_resume_no_label_leakage(frozen_fixture,monkeypatch):
    root,frozen=frozen_fixture
    results=root/'results'; calls=[]
    original_questions={q['row']['question'] for q in frozen['questions']}
    class FakeClient:
        def __init__(self,settings):
            self.model='synthetic';self.api=SimpleNamespace(close=AsyncMock())
        async def discover(self): pass
        def parameters(self): return {'temperature':0,'top_p':1,'seed':42,'max_tokens':131072}
        def metadata(self): return {'model':self.model,'request_parameters':self.parameters()}
        async def call(self,prompt,stage,operator,trace):
            calls.append(stage)
            assert 'source_checkpoints' not in prompt and 'solve_rate' not in prompt and 'gold_answer' not in prompt
            text = '<solution_letter>A</solution_letter>' if operator=='ScEnsemble' else ('def solve():\n    return 42' if operator=='Programmer' else ('ALGEBRA' if stage=='classify' else '42'))
            trace.emit(event='llm_call',stage_id=stage,status='success',latency=1,usage={'prompt_tokens':10,'completion_tokens':20})
            return text
    async def execute(code): return {'status':'Success','output':'42'}
    original=run.Workflow
    class CheckedWorkflow(original):
        async def run(self,workflow,problem):
            assert problem in original_questions
            return await super().run(workflow,problem)
    monkeypatch.setattr(run,'Client',FakeClient)
    monkeypatch.setattr(run,'Workflow',lambda c,t:CheckedWorkflow(c,t,execute))
    monkeypatch.setattr(run,'preflight',lambda:{'backend':'fixture'})
    archived=json.loads(Path('experiment_results/amc50_qwen38_autoround_int4/config.json').read_text())['local_runtime']
    monkeypatch.setattr(local_runtime,'configure_client',lambda:archived)
    monkeypatch.setattr(local_runtime,'identity',lambda:archived)
    base=['--dataset-format','deepmath-screened','--dataset',str(root/'manifest.json'),'--results-dir',str(results),'--local-runtime']
    await run.main(run.parser().parse_args(base+['--limit-items','5']))
    saved=(results/'manifest.json').read_bytes()
    assert len(calls)==85
    assert inspect_pilot(results)['estimated_remaining_hours']==pytest.approx(85/2*105/25/3600)
    with pytest.raises(ValueError,match='Incomplete matrix'): final_analysis(results,Path('experiment_results/amc50_qwen38_autoround_int4'))
    assert not (results/'comparison').exists()
    # Interrupt after a successful LLM call in an unfinished evaluation.
    (results/'evaluations/deepmath-row-45570/baseline/result.json').unlink()
    await run.main(run.parser().parse_args(base+['--resume']))
    assert len(calls)==442  # Reuses the unfinished workflow's direct-call checkpoint.
    assert len(list(results.glob('evaluations/*/*/result.json')))==130
    assert (results/'manifest.json').read_bytes()==saved
    assert json.loads((results/'run_status.json').read_text())['status']=='complete'
    await run.main(run.parser().parse_args(base+['--resume']))
    assert len(calls)==442
    # Exercise final rendering/export on synthetic results, never real inference.
    pytest.importorskip('matplotlib')
    archive=Path('experiment_results/amc50_qwen38_autoround_int4')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir() if p.is_file()}
    final_analysis(results,archive)
    assert hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir() if p.is_file()}
    output=results/'comparison'
    for name in ('figure1_complementarity','figure2_harder_cohorts'):
        for ext in ('png','pdf','svg'): assert (output/f'{name}.{ext}').stat().st_size>1000
    with (output/'all_subset_coverage.csv').open() as f: assert len(list(csv.DictReader(f)))==30
    assert (output/'RESULTS_REPORT.md').exists()
    from amc_repro.deepmath_analysis import plot_archive
    replotted = results/'aggregate_replot'
    plot_archive(output,replotted)
    assert len(list(replotted.glob('figure*'))) == 6


def test_private_paths_require_scratch():
    assert dm.require_scratch('/scratch1/example/results') == Path('/scratch1/example/results')
    with pytest.raises(ValueError,match='must be stored on scratch'):
        dm.require_scratch('/nfshomes/example/scratch/results')
