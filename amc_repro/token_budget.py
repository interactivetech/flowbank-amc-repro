"""Durable, per-evaluation generated-token wallets. Reasoning counts; input does not."""
import hashlib
from pathlib import Path

from .screening import read
from .storage import atomic_json

PROFILE = 'portfolio-128k-generated-v1'
BUDGETS = dict(baseline=131072,W1=32768,W2=32768,W3=32768,W4=32768)
STAGE_CAPS = {
    'baseline':dict(direct=131072),
    'W1':dict(candidate_0=8192,candidate_1=8192,candidate_2=8192,ensemble=8192),
    'W2':dict(candidate_0=8192,candidate_1=8192,candidate_2=8192,ensemble=4096,programmer_0=4096,programmer_1=4096,programmer_2=4096),
    'W3':dict(candidate_0=8192,candidate_1=8192,candidate_2=8192,ensemble=4096,programmer_0=4096,programmer_1=4096,programmer_2=4096),
    'W4':dict(classify=1024,specialist=31744),
}
POLICY = dict(profile=PROFILE,unit='generated_tokens_including_reasoning',budgets=BUDGETS,
    stage_caps=STAGE_CAPS,unused_stage_tokens='Available for later Programmer retries, within stage caps; no transfer between workflows',
    transport_errors='No automatic transport retries; reserve full requested allowance and require operational review',
    interruption='Reuse durable successful responses; an unresolved request is conservatively charged and blocks reissue',
    exhaustion='No more inference; record an unsuccessful budget_exhausted evaluation without oracle fallback')


class BudgetExhausted(Exception):
    pass


class BudgetIntegrityError(RuntimeError):
    pass


class BudgetedCachedClient:
    """A separate wallet per question/condition; never mutate the shared Client settings."""
    def __init__(self,client,directory,workflow):
        self.client,self.directory,self.workflow=client,Path(directory),workflow
        self.limit=BUDGETS[workflow]
        self.directory.mkdir(parents=True,exist_ok=True)

    def entries(self):
        return [read(p) for p in sorted(self.directory.glob('*.json'))]

    def accounting(self):
        entries=self.entries()
        generated=prompt=0
        for entry in entries:
            if entry['state'] != 'success':
                raise BudgetIntegrityError('Unresolved budget request: review required; automatic regeneration is forbidden')
            event=entry['event']
            usage=event.get('usage') or {}
            n=usage.get('completion_tokens');inputs=usage.get('prompt_tokens')
            if type(n) is not int or type(inputs) is not int or not 0 <= n <= entry['requested_max_tokens'] or inputs < 0:
                raise BudgetIntegrityError('Invalid token usage; budget compliance cannot be established')
            generated+=n;prompt+=inputs
        if generated>self.limit: raise BudgetIntegrityError('Generated-token wallet overspent')
        return dict(generated_token_budget=self.limit,completion_tokens=generated,prompt_tokens=prompt,
            llm_calls=len(entries),successful_calls=len(entries),usage_complete=bool(entries),
            truncated_calls=sum(e['event'].get('finish_reason')=='length' for e in entries),
            budget_remaining=self.limit-generated,budget_profile=PROFILE)

    async def call(self,prompt,stage,operator,trace):
        stage_cap=STAGE_CAPS[self.workflow][stage]
        path=self.directory/(stage+'.json')
        prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()
        # Accounting includes calls recovered from successful raw responses, not replay count.
        totals=self.accounting()
        if path.exists():
            saved=read(path)
            if saved['prompt_sha256']!=prompt_hash or saved['profile']!=PROFILE or saved['workflow']!=self.workflow:
                raise BudgetIntegrityError('Cached budget call identity mismatch')
            return saved['event']['output']
        allowance=min(stage_cap,self.limit-totals['completion_tokens'])
        if allowance<=0:
            trace.emit(event='budget_exhausted',stage_id=stage,generated_token_budget=self.limit)
            raise BudgetExhausted(f'{self.workflow} generated-token budget exhausted')
        entry=dict(profile=PROFILE,workflow=self.workflow,stage=stage,prompt_sha256=prompt_hash,
            requested_max_tokens=allowance,state='pending')
        # Durable reservation precedes submission: interruption cannot silently reset the wallet.
        atomic_json(path,entry)
        class Capture:
            def emit(inner,**event):
                if event['event']=='llm_call':
                    entry['event']=event
                    entry['state']='success' if event['status']=='success' else 'error'
                    atomic_json(path,entry)
                trace.emit(**event)
        await self.client.call(prompt,stage,operator,Capture(),max_tokens=allowance,retries=0)
        # The raw event is durable before this method returns, so replay needs no inference.
        self.accounting()
        if entry['state']!='success': raise BudgetIntegrityError('Response was not checkpointed')
        return entry['event']['output']


def compliance(records):
    """Check every wallet, including total portfolio use on each question."""
    groups={}
    for r in records:
        w=r['workflow_id'];n=r['completion_tokens']
        if not r['usage_complete'] or r.get('budget_profile')!=PROFILE or r.get('generated_token_budget')!=BUDGETS[w]:
            raise BudgetIntegrityError('Missing budget evidence')
        if type(n) is not int or not 0<=n<=BUDGETS[w]:
            raise BudgetIntegrityError('Per-condition budget breach')
        q=groups.setdefault(r['question_id'],{})
        if w in q: raise BudgetIntegrityError('Duplicate condition result')
        q[w]=n
    for group in groups.values():
        if sum(v for w,v in group.items() if w!='baseline')>131072:
            raise BudgetIntegrityError('Portfolio budget breach')
    return dict(profile=PROFILE,evaluations=len(records),questions=len(groups),violations=0,
        baseline_allowance=131072,workflow_allowance=32768,portfolio_allowance=131072,
        generated_tokens=sum(r['completion_tokens'] for r in records),
        budget_exhausted_evaluations=sum(r['grading_status']=='budget_exhausted' for r in records))


def report(root,manifest,records):
    """Export independent buckets and measured spending without exposing responses."""
    import csv
    import json
    root=Path(root)
    summary=compliance(records)
    if len(records)!=len(manifest['questions'])*5:
        raise BudgetIntegrityError('Incomplete budgeted result matrix')
    atomic_json(root/'budget_compliance.json',summary)
    matrix={(r['question_id'],r['workflow_id']):r for r in records}
    bucket_rows=[]
    for b in ('0/32','1-8/32','9-16/32','17-24/32','25-32/32'):
        ids=[q['question_id'] for q in manifest['questions'] if q['screening']['bucket']==b]
        n=len(ids)
        baseline=sum(matrix[q,'baseline']['correct'] for q in ids)
        oracle=sum(any(matrix[q,w]['correct'] for w in BUDGETS if w!='baseline') for q in ids)
        bucket_rows.append(dict(screening_bucket=b,N=n,baseline_solved=baseline,oracle_solved=oracle,
            baseline_accuracy_pct=100*baseline/n,oracle_accuracy_pct=100*oracle/n))
    def write(name,rows):
        with (root/'comparison'/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    write('independent_bucket_metrics.csv',bucket_rows)
    cost_rows=[]
    for w in BUDGETS:
        values=[matrix[q['question_id'],w] for q in manifest['questions']]
        cost_rows.append(dict(condition=w,generated_token_allowance=BUDGETS[w],
            mean_generated_tokens=sum(r['completion_tokens'] for r in values)/len(values),
            mean_input_tokens=sum(r['prompt_tokens'] for r in values)/len(values),
            solved=sum(r['correct'] for r in values),N=len(values),
            budget_exhausted=sum(r['grading_status']=='budget_exhausted' for r in values)))
    write('generated_budget_costs.csv',cost_rows)
    path=root/'comparison/RESULTS_REPORT.md'
    text=path.read_text()+'\n## Controlled generated-token allowances\n\n'
    text+='Baseline has 131,072 generated tokens per question. Each complete W1–W4 workflow has 32,768, so the whole portfolio has the same maximum 131,072. Reasoning, selection, verification and code retries all count. Input tokens and executor compute are measured separately and are not controlled. Equal allowances do not imply equal actual spending.\n\n'
    text+='[Budget compliance](../budget_compliance.json) · [Measured costs](generated_budget_costs.csv) · [Independent buckets](independent_bucket_metrics.csv)\n\n'
    text+='| Screening correct / 32 | N | Baseline solved | Oracle solved | Oracle accuracy |\n|---|---:|---:|---:|---:|\n'
    for r in bucket_rows:text+=f"| {r['screening_bucket']} | {r['N']} | {r['baseline_solved']} | {r['oracle_solved']} | {r['oracle_accuracy_pct']:.1f}% |\n"
    text+='\nOracle uses ground truth retrospectively. This comparison does not implement an answer selector or a repeated direct-sampling control. Stage allocations are fixed design choices; truncating intermediate reasoning can affect workflow quality. The selection is small and adaptively screened; manual audit remains pending.\n'
    text+='\nReproduce budgeted analysis: `bash scripts/run_budget21.sh analyze`.\n'
    path.write_text(text)
