import asyncio
import json
from types import SimpleNamespace

import pytest

from amc_repro import token_budget as b
from amc_repro.storage import Trace, atomic_json


class FakeClient:
    def __init__(self,usage=3,fail=False):self.calls=[];self.usage=usage;self.fail=fail
    async def call(self,prompt,stage,operator,trace,*,max_tokens,retries):
        self.calls.append((stage,max_tokens,retries))
        if self.fail:raise TimeoutError('Response unknown')
        trace.emit(event='llm_call',stage_id=stage,status='success',output='42',usage=dict(prompt_tokens=5,completion_tokens=self.usage),finish_reason='stop')
        return '42'


@pytest.mark.asyncio
async def test_shared_wallet_exact_boundary_and_resume(tmp_path,monkeypatch):
    monkeypatch.setitem(b.BUDGETS,'W2',10)
    client=FakeClient(usage=5);trace=Trace(tmp_path/'trace',{})
    wallet=b.BudgetedCachedClient(client,tmp_path/'calls','W2')
    assert await wallet.call('a','candidate_0','Custom',trace)=='42'
    assert await wallet.call('b','candidate_1','Custom',trace)=='42'
    assert [c[1] for c in client.calls]==[10,5]
    with pytest.raises(b.BudgetExhausted):await wallet.call('c','candidate_2','Custom',trace)
    assert wallet.accounting()['completion_tokens']==10
    resumed=b.BudgetedCachedClient(client,tmp_path/'calls','W2')
    assert await resumed.call('a','candidate_0','Custom',trace)=='42'
    assert len(client.calls)==2
    with pytest.raises(b.BudgetIntegrityError,match='identity mismatch'):await resumed.call('changed','candidate_0','Custom',trace)


@pytest.mark.asyncio
async def test_stage_reservation_and_retry_pool(tmp_path):
    client=FakeClient(usage=4096);trace=Trace(tmp_path/'trace',{})
    wallet=b.BudgetedCachedClient(client,tmp_path/'calls','W2')
    for stage in ('candidate_0','candidate_1','candidate_2','ensemble','programmer_0','programmer_1','programmer_2'):
        await wallet.call(stage,stage,'Custom',trace)
    assert [c[1] for c in client.calls]==[8192,8192,8192,4096,4096,4096,4096]
    assert wallet.accounting()['completion_tokens']==28672
    assert all(c[2]==0 for c in client.calls)


@pytest.mark.asyncio
async def test_interrupted_request_cannot_be_reissued(tmp_path):
    client=FakeClient(fail=True);trace=Trace(tmp_path/'trace',{})
    wallet=b.BudgetedCachedClient(client,tmp_path/'calls','W1')
    with pytest.raises(TimeoutError):await wallet.call('a','candidate_0','Custom',trace)
    assert json.loads((tmp_path/'calls/candidate_0.json').read_text())['state']=='pending'
    resumed=b.BudgetedCachedClient(client,tmp_path/'calls','W1')
    with pytest.raises(b.BudgetIntegrityError,match='Unresolved'):await resumed.call('a','candidate_0','Custom',trace)
    assert len(client.calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('usage',[None,8193,True])
async def test_missing_or_excess_usage_blocks_next_call(tmp_path,usage):
    client=FakeClient(usage);trace=Trace(tmp_path/'trace',{})
    wallet=b.BudgetedCachedClient(client,tmp_path/'calls','W1')
    with pytest.raises(b.BudgetIntegrityError,match='Invalid token usage'):await wallet.call('a','candidate_0','Custom',trace)
    with pytest.raises(b.BudgetIntegrityError):await wallet.call('b','candidate_1','Custom',trace)
    assert len(client.calls)==1


@pytest.mark.asyncio
async def test_concurrent_evaluations_have_separate_wallets(tmp_path):
    client=FakeClient(usage=10)
    a=b.BudgetedCachedClient(client,tmp_path/'a','W1')
    c=b.BudgetedCachedClient(client,tmp_path/'b','baseline')
    await asyncio.gather(a.call('a','candidate_0','Custom',Trace(tmp_path/'ta',{})),c.call('b','direct','Custom',Trace(tmp_path/'tb',{})))
    assert sorted(x[1] for x in client.calls)==[8192,131072]
    assert a.accounting()['completion_tokens']==c.accounting()['completion_tokens']==10


def test_compliance_checks_every_condition_and_portfolio():
    rows=[dict(question_id='synthetic',workflow_id=w,completion_tokens=n,generated_token_budget=n,budget_profile=b.PROFILE,usage_complete=True,grading_status='correct') for w,n in b.BUDGETS.items()]
    assert b.compliance(rows)['violations']==0
    rows[1]['completion_tokens']+=1
    with pytest.raises(b.BudgetIntegrityError):b.compliance(rows)
