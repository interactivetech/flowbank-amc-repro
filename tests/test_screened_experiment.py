"""Synthetic provisional data, resume, operational gates, and aggregate exports."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from amc_repro import deepmath as dm, screened_experiment as se, run, local_runtime
from amc_repro.deepmath_analysis import inspect_pilot, final_analysis
from amc_repro.screening import digest, seed, bucket
from amc_repro.screened_pipeline import pilot_flags
from amc_repro.storage import atomic_json


@pytest.fixture
def provisional(tmp_path,monkeypatch):
    monkeypatch.setattr(dm,'require_scratch',lambda p:Path(p))
    monkeypatch.setattr(se,'require_scratch',lambda p:Path(p))
    source=tmp_path/'frozen';source.mkdir()
    (source/'source.parquet').write_bytes(b'synthetic source')
    monkeypatch.setattr(se,'SHA256',hashlib.sha256(b'synthetic source').hexdigest())
    evidence=tmp_path/'screening'
    counts=[0]*5+[1]*3+[9]*4+[17]*4+[25]*5
    ids=list(range(100,121))
    for i,row in zip((0,5,8,12,16),se.PILOT): ids[i]=row
    selected={b:[] for b in se.BUCKETS};questions=[]
    for row,correct in zip(ids,counts):
        q=dict(question_id=f'deepmath-row-{row}',dataset_row=row,row_index=row,
            row={'question':f'SYNTHETIC compute 42 ({row})'},gold_answer='42',reference={'kind':'math','gold':'42'})
        sample=[dict(index=i,seed=seed(row,i),correct=i<correct,grading_status='correct' if i<correct else 'math_error') for i in range(32)]
        for r in sample: atomic_json(evidence/'rollouts'/q['question_id']/f"{r['index']:02d}.json",r)
        atomic_json(evidence/'greedy'/q['question_id']/'00.json',dict(correct=False))
        selected[bucket(correct)].append(q)
        questions.append({**q,'screening':dict(correct=correct,responses=32,solve_rate=correct/32,bucket=bucket(correct),greedy_correct=False,evidence_sha256=digest(sample))})
    questions.sort(key=lambda q:(0,se.PILOT.index(q['dataset_row'])) if q['dataset_row'] in se.PILOT else (1,q['dataset_row']))
    atomic_json(evidence/'provisional.json',selected)
    manifest=dict(dataset_format=se.FORMAT,repository=se.REPOSITORY,revision=se.REVISION,dataset_sha256=se.SHA256,
        frozen_root=str(source),screening_run=str(evidence),sample_size=21,audit_status='pending',questions=questions,
        cohorts={str(t):[q['question_id'] for q in questions if q['screening']['solve_rate']<=t] for t in dm.THRESHOLDS})
    atomic_json(source/'manifest.json',manifest)
    atomic_json(source/'freeze_integrity.json',dict(manifest_sha256=digest(manifest)))
    return source,manifest


def test_provisional_requires_optin_and_binds_evidence(provisional):
    source,manifest=provisional
    with pytest.raises(ValueError,match='requires --allow-provisional'):dm.load_frozen(source/'manifest.json')
    assert dm.load_frozen(source/'manifest.json',allow_provisional=True)==manifest
    q=manifest['questions'][0]
    evidence=Path(manifest['screening_run'])/'rollouts'/q['question_id']/'00.json'
    saved=json.loads(evidence.read_text());saved['correct']=not saved['correct'];atomic_json(evidence,saved)
    with pytest.raises(ValueError,match='counts mismatch'):dm.load_frozen(source/'manifest.json',allow_provisional=True)


def test_provisional_integrity_and_cohorts(provisional):
    source,manifest=provisional
    manifest['cohorts']['0']=[]
    atomic_json(source/'manifest.json',manifest)
    with pytest.raises(ValueError,match='integrity mismatch'):dm.load_frozen(source/'manifest.json',allow_provisional=True)
    atomic_json(source/'freeze_integrity.json',dict(manifest_sha256=digest(manifest)))
    with pytest.raises(ValueError,match='cohort mismatch'):dm.load_frozen(source/'manifest.json',allow_provisional=True)


def test_operational_gates_ignore_accuracy_and_observed_parse_failures():
    report=dict(completed=25,expected=25,usage_complete=True,context_overflows=0,failed_evaluations=0,grading_failures=0,parsing_failures=10,truncated_calls=4,code_execution_errors=3)
    assert pilot_flags(report)=={}
    for key in ('context_overflows','failed_evaluations','grading_failures'):
        assert key in pilot_flags({**report,key:1})
    assert 'pilot_completeness_or_usage' in pilot_flags({**report,'usage_complete':False})


@pytest.mark.asyncio
@pytest.mark.parametrize("budgeted",[False,True])
async def test_provisional_pilot_resume_full_and_final(provisional,monkeypatch,budgeted):
    source,manifest=provisional;root=source.parent/'results';calls=[]
    class FakeClient:
        def __init__(self,settings):self.model='synthetic';self.api=SimpleNamespace(close=AsyncMock())
        async def discover(self):pass
        def parameters(self):return {'temperature':0,'top_p':1,'seed':42,'max_tokens':131072}
        def metadata(self):return {'model':self.model,'request_parameters':self.parameters()}
        async def call(self,prompt,stage,operator,trace,**limits):
            assert 'screening_solve_rate' not in prompt and 'gold_answer' not in prompt
            calls.append(stage)
            output = '<solution_letter>A</solution_letter>' if operator=='ScEnsemble' else 'def solve():\n    return 42' if operator=='Programmer' else 'ALGEBRA' if stage=='classify' else '42'
            trace.emit(event='llm_call',stage_id=stage,status='success',output=output,latency=1,usage={'prompt_tokens':10,'completion_tokens':20})
            return output
    async def execute(code):return {'status':'Success','output':'42'}
    original=run.Workflow
    monkeypatch.setattr(run,'Workflow',lambda c,t:original(c,t,execute))
    monkeypatch.setattr(run,'Client',FakeClient)
    monkeypatch.setattr(run,'preflight',lambda:{'backend':'synthetic'})
    runtime=json.loads(Path('experiment_results/amc50_qwen38_autoround_int4/config.json').read_text())['local_runtime']
    monkeypatch.setattr(local_runtime,'configure_client',lambda:runtime)
    monkeypatch.setattr(local_runtime,'identity',lambda:runtime)
    base=['--dataset-format','deepmath-screened','--dataset',str(source/'manifest.json'),'--results-dir',str(root),'--local-runtime']
    with pytest.raises(ValueError,match='requires --allow-provisional'):await run.main(run.parser().parse_args(base))
    base+=['--allow-provisional-screening']
    if budgeted:base+=['--generated-budget-profile','portfolio-128k-generated-v1']
    await run.main(run.parser().parse_args(base+['--limit-items','5']))
    assert len(calls)==85
    inspection=inspect_pilot(root,True)
    assert inspection['expected']==25 and inspection['remaining_evaluations_after_pilot']==80
    assert inspection['estimated_remaining_hours']==pytest.approx(85/2*80/25/3600)
    assert not pilot_flags(inspection)
    archive=Path('experiment_results/amc50_qwen38_autoround_int4')
    with pytest.raises(ValueError,match='Incomplete matrix'):final_analysis(root,archive,True)
    assert not (root/'comparison').exists()
    (root/'evaluations'/manifest['questions'][0]['question_id']/'baseline/result.json').unlink()
    await run.main(run.parser().parse_args(base+['--resume']))
    assert len(calls)==357 and len(list(root.glob('evaluations/*/*/result.json')))==105
    await run.main(run.parser().parse_args(base+['--resume']))
    assert len(calls)==357
    config=json.loads((root/'config.json').read_text());assert config['audit_status']=='pending'
    config['source_hashes']['changed']='yes';atomic_json(root/'config.json',config)
    with pytest.raises(ValueError,match='Resume config/source mismatch'):await run.main(run.parser().parse_args(base+['--resume']))
    pytest.importorskip('matplotlib')
    stats=final_analysis(root,archive,True)
    assert stats['sample_size']==21
    text=(root/'comparison/RESULTS_REPORT.md').read_text()
    assert '105 fresh evaluations on 21' in text and 'dataset audit pending' in text
    import csv
    with (root/'comparison/cohort_metrics.csv').open() as f:assert [int(r['N']) for r in csv.DictReader(f)]==[21,16,12,8,5]
    assert (root/'comparison/baseline_screening_comparison.csv').exists()
    if budgeted:
        assert json.loads((root/'budget_compliance.json').read_text())['violations']==0
        assert (root/'comparison/generated_budget_costs.csv').exists()
        assert (root/'comparison/independent_bucket_metrics.csv').exists()
    # Exercise the archive allowlist without changing Git or contacting a remote.
    from amc_repro import screened_pipeline as pipeline
    monkeypatch.setattr(pipeline,'RESULTS',root)
    monkeypatch.setattr(pipeline,'BUDGET_CONTROLLED',budgeted)
    monkeypatch.setattr(pipeline,'REPO',source.parent)
    monkeypatch.setattr(pipeline,'gate',lambda:'source-sha')
    def fake_git(*args):
        if args[0]=='rev-parse':return 'source-sha'
        if args[:3]==('diff','--cached','--name-only'):
            return '\n'.join(str(p.relative_to(source.parent)) for p in (source.parent/pipeline.ARCHIVE).rglob('*') if p.is_file())
        return ''
    monkeypatch.setattr(pipeline,'git',fake_git)
    assert pipeline.archive('source-sha')=='source-sha'
    files=list((source.parent/pipeline.ARCHIVE).rglob('*'))
    assert not any(p.name in ('manifest.json','trace.jsonl','result.json','source.parquet') for p in files)
