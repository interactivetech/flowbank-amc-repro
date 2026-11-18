"""Offline screening regressions; synthetic questions only, no live inference."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sympy as sp
from math_verify import verify
from amc_repro import screening as s, deepmath as dm
from amc_repro.grading import grade_typed
from amc_repro.storage import atomic_json


def question(index=0):
    return dict(question_id=f'deepmath-row-{index}',dataset_row=index,row_index=index,
                row={'question':'SYNTHETIC compute 2+2'},gold_answer='4',reference=dict(kind='math',gold='4'))


def sample(correct=0):
    return [dict(index=i,seed=s.seed(0,i),correct=i<correct,grading_status='correct' if i<correct else 'math_error') for i in range(32)]


def save_sample(root,q,values):
    for v in values: atomic_json(root/'rollouts'/q['question_id']/f"{v['index']:02d}.json",v)


def test_historical_boolean_regression():
    assert not verify('Yes',[sp.true])
    assert verify([sp.true],[sp.true])
    for label in ('Yes','true','No','False'):
        ref=s.reference('synthetic categorical question',label)
        assert ref['kind']=='boolean'
        s.preflight_reference(ref)
        assert grade_typed(r'\boxed{\text{'+label+'}}',ref)['correct']


@pytest.mark.parametrize('gold,prediction',[
    ('0.5',r'\frac{1}{2}'),(r'\{-1,1\}',r'\pm 1'),
    (r'\frac{\sqrt{2}}{2}',r'1/\sqrt{2}'),('-5i','-5j'),
    (r'60^\circ',r'\pi/3'),('x+1','1+x'),
])
def test_supported_references(gold,prediction):
    ref=s.reference('synthetic',gold)
    s.preflight_reference(ref)
    assert grade_typed(r'\boxed{'+prediction+'}',ref)['correct']


def test_choice():
    ref=s.reference('(A) $1$\n(B) $4$\n(C) $3$\n(D) $2$', 'B')
    assert ref['kind']=='choice'
    assert grade_typed('4',ref)['correct']
    assert not grade_typed('Option A',ref)['correct']


def test_source_mapping_order_exclusion_and_dedup():
    rows=[dict(question=f'SYNTHETIC {i}',final_answer='4',difficulty=band) for i,band in enumerate([3,9,3,9,5,5,1,1])]
    rows += [dict(rows[1]),dict(question='unparseable',final_answer='',difficulty=1)]
    excluded=[dict(dataset_row=2,row={'question':rows[2]['question']})]
    candidates,rejected=s.ordered_candidates(rows,excluded)
    assert len(candidates)==7 and len(rejected)==1
    assert [q['source_band'] for q in candidates[:4]]==[9,5,3,1]
    assert candidates==s.ordered_candidates(rows,excluded)[0]
    assert all(q['row']['question']==rows[q['dataset_row']]['question'] for q in candidates)
    assert 2 not in [q['dataset_row'] for q in candidates]


def test_seeds():
    values={s.seed(r,i) for r in range(103022) for i in range(32)}
    assert len(values)==103022*32
    assert s.seed(45570,0)==(42*1_000_003+45570*32)&0x7fffffff
    with pytest.raises(ValueError): s.seed(0,32)


@pytest.mark.parametrize('n,b',[(0,0),(1,1),(8,1),(9,2),(16,2),(17,3),(24,3),(25,4),(32,4)])
def test_boundaries(n,b):
    assert s.bucket(n)==s.BUCKETS[b]
    with pytest.raises(ValueError): s.bucket(n,31)


def test_promotion_and_incomplete():
    missing={b:0 for b in s.BUCKETS};missing['0/32']=5
    assert s.priority(sample()[:8],missing)
    assert not s.priority(sample(32)[:8],missing)
    assert not s.priority(sample()[:7],missing)
    assert not s.eligible(sample()[:31])
    values=sample();values[0]['grading_status']='grading_failure'
    assert not s.eligible(values)


def test_budget_resume_and_downtime(tmp_path):
    now=[10.0];clock=lambda:now[0]
    budget=s.Budget(tmp_path,limit=100,clock=clock)
    budget.begin();now[0]+=20
    assert budget.used()==20
    budget.save();now[0]+=5
    assert budget.used()==25
    budget.close();now[0]+=1000
    resumed=s.Budget(tmp_path,100,clock)
    assert resumed.used()==25
    resumed.begin();now[0]+=10;resumed.save()
    # Crash: persisted heartbeat is recovered; allocation downtime is excluded.
    now[0]+=1000
    again=s.Budget(tmp_path,100,clock)
    assert again.used()==95
    again.begin();now[0]+=5
    assert again.remaining()==0
    again.close()
    assert again.used()==100


def test_manual_audit_and_legacy_compatible_lock(tmp_path,monkeypatch):
    monkeypatch.setattr(dm,'require_scratch',lambda p:Path(p))
    q=question();values=sample(2);save_sample(tmp_path,q,values)
    atomic_json(tmp_path/'preparation.json',dict(source_rows=10,sources=['synthetic']))
    atomic_json(tmp_path/'run_manifest.json',dict(git_commit='synthetic'))
    atomic_json(tmp_path/'screening_complete.json',dict(reason='budget_exhausted'))
    atomic_json(tmp_path/'audit.json',{})
    with pytest.raises(ValueError,match='Manual audit'): s.finalize(tmp_path,[q])
    review=dict(decision='accept',reviewer='human',reference_checked=True,evidence_sha256=s.digest(values),incorrect_checked=list(range(2,31)))
    assert not s.accepted(q,values,review)
    review['incorrect_checked'].append(31)
    atomic_json(tmp_path/'audit.json',{q['question_id']:review})
    frozen=s.finalize(tmp_path,[q])
    assert frozen['sample_size']==1
    assert frozen['questions'][0]['screening']['responses']==32
    assert dm.load_frozen(tmp_path/'manifest.json')==frozen
    copied=tmp_path/'workflow-results'/'manifest.json'
    atomic_json(copied,frozen)
    assert dm.load_frozen(copied)==frozen
    values[0]['correct']=False
    save_sample(tmp_path,q,values)
    with pytest.raises(ValueError,match='Audit evidence'):dm.load_frozen(tmp_path/'manifest.json')


def test_selection_frozen_ties_quarantine_and_greedy_independence(tmp_path):
    qs=[question(i) for i in range(7)]
    for q in qs: save_sample(tmp_path,q,sample(32))
    selected=s.selection(tmp_path,qs)
    assert selected['25-32/32']==qs[:5]
    atomic_json(tmp_path/'greedy'/qs[0]['question_id']/'00.json',dict(correct=False))
    assert selected==s.selection(tmp_path,qs)
    atomic_json(tmp_path/'audit.json',{qs[0]['question_id']:dict(decision='quarantine')})
    assert s.selection(tmp_path,qs)['25-32/32']==qs[1:6]


def test_launch_gate(monkeypatch):
    answers={'branch':'slurm_env','status':'','rev-parse':'abc','ls-remote':'abc refs/heads/slurm_env'}
    monkeypatch.setattr(s,'git',lambda *args:answers[args[0]])
    assert s.commit_gate()=='abc'
    answers['ls-remote']='other refs/heads/slurm_env'
    with pytest.raises(ValueError,match='Remote head'):s.commit_gate()
    answers['status']=' M dirty.py'
    with pytest.raises(ValueError,match='clean'):s.commit_gate()


@pytest.mark.asyncio
async def test_run_retries_raw_resume_and_request_parameters(tmp_path,monkeypatch):
    import openai
    q=question()
    atomic_json(tmp_path/'candidates.json',[q])
    provenance=dict(runtime=dict(model=dict(served_model='synthetic')))
    monkeypatch.setattr(s,'provenance',lambda root:provenance)
    calls=[]
    failed=[False]
    class Fake:
        def __init__(self,**kwargs):
            self.models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(model_dump=lambda **kw:dict(data=[dict(id='synthetic',max_model_len=262144)]))))
            self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
        async def create(self,**request):
            calls.append(request)
            assert 'gold_answer' not in request['messages'][0]['content']
            if not failed[0]:
                failed[0]=True
                raise TimeoutError('synthetic infrastructure error')
            content='yes' if 'even integer' in request['messages'][0]['content'] else '4'
            return SimpleNamespace(model_dump=lambda **kw:dict(choices=[dict(message=dict(content=content),finish_reason='stop')],usage=dict(completion_tokens=1)))
        async def close(self):pass
    monkeypatch.setattr(openai,'AsyncOpenAI',Fake)
    monkeypatch.setenv('OPENAI_BASE_URL','http://synthetic');monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    await s.run(tmp_path)
    assert len(s.results(tmp_path,q))==32
    assert len(list((tmp_path/'attempts').glob('**/*.error.json')))==1
    assert calls[0]['seed']==calls[1]['seed']
    sampled=[c for c in calls if 'SYNTHETIC' in c['messages'][0]['content'] and c['temperature']==.6]
    assert len(sampled)==32 and len({c['seed'] for c in sampled})==32
    assert all(c['extra_body']['top_k']==20 and c['top_p']==.95 for c in sampled)
    greedy=[c for c in calls if c['temperature']==0]
    assert len(greedy)==1 and greedy[0]['seed']==42
    # Rollout result interrupted after durable raw response: regenerate grading only.
    (tmp_path/'rollouts'/q['question_id']/'05.json').unlink()
    (tmp_path/'screening_complete.json').unlink()
    before=len(calls)
    await s.run(tmp_path)
    assert len(calls)==before and len(s.results(tmp_path,q))==32

@pytest.mark.parametrize('gold',[True,sp.true,r'\text{True}',r'\mathrm{yes}'])
def test_generalized_boolean_types(gold):
    assert grade_typed(r'\boxed{\mathrm{True}}',dict(kind='boolean',gold=gold))['correct']
    assert s.reference('synthetic',gold)['kind']=='boolean'
