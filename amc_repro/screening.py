"""Versioned DeepMath screening. All dataset and response artifacts stay on scratch."""
import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import importlib.metadata as md
import itertools
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time
import unicodedata

from .deepmath import require_scratch, options
from .grading import grade_typed, parsed, normalize_math, boolean_label
from .prompts import GENERAL, custom
from .storage import atomic_json

DATASET = 'zwhe99/DeepMath-103K'
DATA_REV = '5cf055d1fe3d7a2eb19719ac020211469736ae44'
MODEL = 'RedHatAI/Qwen3.8-27B-INT4'
MODEL_REV = 'e45c27e8f463817db788d141a73a3c235a0a7c0c'
VERSION = 'deepmath-typed-screening-v1'
BUCKETS = ('0/32', '1-8/32', '9-16/32', '17-24/32', '25-32/32')
SPEC = dict(version=VERSION, dataset=DATASET, dataset_revision=DATA_REV,
            model=MODEL, model_revision=MODEL_REV, context_length=262144,
            concurrency=2, temperature=.6, top_p=.95, top_k=20,
            max_tokens=131072, presence_penalty=0, frequency_penalty=0,
            repetition_penalty=1, thinking=True, speculative_decoding=False,
            tensor_parallel_size=1, triage=8, samples=32, budget_seconds=86400,
            quota=5, seed=42, prompt=GENERAL, buckets=BUCKETS)
REPO = Path(__file__).resolve().parent.parent


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def seed(row, index):
    if not 0 <= index < 32 or row < 0:
        raise ValueError('Invalid rollout identity')
    return (42 * 1_000_003 + row * 32 + index) & 0x7fffffff


def bucket(correct, completed=32):
    if completed != 32 or not 0 <= correct <= 32:
        raise ValueError('Buckets require 32 completed sampled responses')
    return BUCKETS[0 if correct == 0 else 1 + (correct - 1) // 8]


def canonical(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def reference(question, gold, validate=True):
    """Type labels before parsing; never compare raw strings with SymPy Booleans."""
    value = str(gold).strip().strip('$').strip()
    try:
        truth = boolean_label(value)
        return dict(kind='boolean', gold='yes' if truth else 'no')
    except ValueError:
        pass
    if value.upper() in 'ABCDE' and len(value) == 1:
        mapping = options(question)
        if len(mapping) >= 4 and value.upper() in mapping:
            return dict(kind='choice', gold=value.upper(), options=mapping)
    imaginary = bool(__import__('re').search(r'(?<![A-Za-z])[ij](?![A-Za-z])', value))
    ref = dict(kind='complex' if imaginary else 'math', gold=value)
    if validate and not parsed(normalize_math(value, imaginary)):
        raise ValueError('Unparseable reference')
    return ref


def preflight_reference(ref):
    if not grade_typed(ref['gold'], ref)['correct']:
        raise ValueError('Reference fails identity check')
    if not grade_typed(r'\boxed{' + ref['gold'] + '}', ref)['correct']:
        raise ValueError('Reference fails boxed identity check')


def ordered_candidates(rows, excluded):
    seen = {canonical(q['row']['question']) for q in excluded}
    excluded_ids = {q['dataset_row'] for q in excluded}
    bands, rejected = {}, []
    for index, row in enumerate(rows):
        question = row['question']
        key = canonical(question)
        if index in excluded_ids or key in seen:
            continue
        seen.add(key)
        try:
            gold = row['final_answer']
            ref = reference(question, gold, validate=False)
            if not str(gold).strip(): raise ValueError('Empty reference')
            difficulty = float(row['difficulty'])
            if not math.isfinite(difficulty):
                raise ValueError('Nonfinite difficulty')
            band = math.floor(difficulty)
        except Exception as exc:
            rejected.append(dict(dataset_row=index, reason=type(exc).__name__))
            continue
        q = dict(question_id=f'deepmath-row-{index}', dataset_row=index, row_index=index,
                 row={'question':question}, gold_answer=str(gold), reference=ref,
                 source_difficulty=difficulty, source_band=band)
        bands.setdefault(band, []).append(q)
    rng = random.Random(42)
    for b in sorted(bands, reverse=True):
        rng.shuffle(bands[b])
    result = [q for group in itertools.zip_longest(*(bands[b] for b in sorted(bands, reverse=True)))
              for q in group if q is not None]
    return result, rejected


def prepare(root, old):
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq
    if (root/'candidates.json').exists():
        raise ValueError('Preparation is immutable; use a fresh versioned directory')
    previous = read(require_scratch(old))['questions']
    if len(previous) != 26:
        raise ValueError('Expected 26 previous exclusions')
    rows, sources = [], []
    for i in range(10):
        name = f'data/train-{i:05d}-of-00010.parquet'
        p = Path(hf_hub_download(DATASET, name, repo_type='dataset', revision=DATA_REV))
        sources.append(dict(filename=name, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        rows.extend(pq.read_table(p).to_pylist())
    for q in previous:
        if canonical(rows[q['dataset_row']]['question']) != canonical(q['row']['question']):
            raise ValueError('Previous source row mapping does not match pinned dataset')
    candidates, rejected = ordered_candidates(rows, previous)
    atomic_json(root/'candidates.json', candidates)
    atomic_json(root/'preparation.json', dict(spec=SPEC, sources=sources, source_rows=len(rows),
                candidates=len(candidates), rejected=rejected, excluded_rows=[q['dataset_row'] for q in previous],
                candidates_sha256=digest(candidates), exclusion_manifest_sha256=digest(read(old))))


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def commit_gate():
    if git('branch', '--show-current') != 'slurm_env' or git('status', '--porcelain'):
        raise ValueError('Launch requires clean slurm_env working tree')
    sha = git('rev-parse', 'HEAD')
    remote = git('ls-remote', 'origin', 'refs/heads/slurm_env').split()[0]
    if sha != remote:
        raise ValueError('Remote head does not match local commit')
    return sha


def provenance(root):
    sha = commit_gate()
    if sys.version_info[:3] != (3,12,15):
        raise ValueError('Screening requires Python 3.12.15')
    files = sorted(p for folder in ('amc_repro','scripts','vendor/FlowBank/DiverseFlow/scripts/prompts')
                   for p in (REPO/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files += [REPO/'requirements.screening.txt', REPO/'requirements.screening.lock.txt']
    hashes = {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    packages = dict(sorted((d.metadata['Name'],d.version) for d in md.distributions() if d.metadata['Name']))
    preparation = read(root/'preparation.json')
    if preparation['spec'] != json.loads(json.dumps(SPEC)) or preparation['candidates_sha256'] != digest(read(root/'candidates.json')):
        raise ValueError('Preparation configuration or candidates changed')
    # Check the full pinned environment, excluding only packaging bootstrap tools.
    pins = (REPO/'requirements.screening.lock.txt').read_text().splitlines()
    for line in pins:
        if '==' in line and not line.startswith('#'):
            name, version = line.split('==')
            if md.version(name) != version:
                raise ValueError('Screening dependency mismatch: ' + name)
    from .local_runtime import identity
    runtime = identity()
    if (runtime['model']['repository'],runtime['model']['revision'],runtime['context_length']) != (MODEL,MODEL_REV,262144):
        raise ValueError('Deployment identity differs')
    observed = read(Path(os.environ['AMC_ROOT'])/'deployments/redhat/observed_runtime.json')
    if (observed['tensor_parallel_size'],observed['speculative_decoding'],observed['context_length']) != (1,False,262144):
        raise ValueError('Deployment configuration differs')
    return dict(git_commit=sha, source_hashes=hashes, packages=packages, runtime=runtime,
                observed_runtime=observed, preparation_sha256=digest(preparation), spec=SPEC,
                executable=sys.executable, python=sys.version)


class Budget:
    """Wall time while screening is active; concurrency never doubles the charge.

    Each heartbeat reserves 60 seconds for abrupt termination. Recovery charges
    that conservative tail; graceful shutdown releases it. Downtime is excluded.
    """
    def __init__(self, root, limit=86400, clock=time.monotonic):
        self.path, self.clock, self.limit = root/'budget.json', clock, limit
        self.data = read(self.path) if self.path.exists() else dict(sessions=[])
        self.started = None

    def used(self):
        total=sum(s['seconds'] for s in self.data['sessions'])
        total+=sum(s.get('reserved_seconds',0) for s in self.data['sessions'] if s.get('open'))
        if self.started is not None:
            total-=self.data['sessions'][-1].get('reserved_seconds',0)
            total+=self.clock()-self.started
        return total

    def remaining(self):
        return max(0, self.limit-self.used())

    def begin(self):
        for s in self.data['sessions']:
            if s.get('open'):
                s['seconds'] += s.pop('reserved_seconds',0)
                s['open'] = False
                s['recovered_after_interruption'] = True
        self.data['sessions'].append(dict(seconds=0, open=True, started_unix=time.time(),
                                         job_id=os.environ.get('SLURM_JOB_ID')))
        self.started = self.clock()
        self.base = 0
        self.save()

    def save(self):
        if self.started is not None:
            elapsed = self.clock()-self.started
            self.data['sessions'][-1]['seconds'] = self.base + elapsed
            self.base += elapsed
            self.started = self.clock()
        if self.started is not None:
            self.data['sessions'][-1]['reserved_seconds']=min(60,max(0,self.limit-self.used()))
        atomic_json(self.path, self.data)

    def close(self):
        self.save()
        self.data['sessions'][-1]['open'] = False
        self.data['sessions'][-1]['reserved_seconds'] = 0
        self.started = None
        atomic_json(self.path, self.data)


def results(root, q):
    folder=root/'rollouts'/q['question_id']
    return [read(p) for p in sorted(folder.glob('[0-9][0-9].json'))]


def eligible(sample):
    return len(sample) == 32 and all(r['grading_status'] != 'grading_failure' for r in sample)


def selection(root, candidates):
    chosen = {b:[] for b in BUCKETS}
    reviews = read(root/'audit.json') if (root/'audit.json').exists() else {}
    complete = {p.parent.name for p in (root/'rollouts').glob('*/31.json')}
    for q in candidates:
        if q['question_id'] not in complete: continue
        sample = results(root,q)
        if not eligible(sample) or reviews.get(q['question_id'],{}).get('decision') == 'quarantine':
            continue
        b = bucket(sum(r['correct'] for r in sample))
        if len(chosen[b]) < 5:
            chosen[b].append(q)
    return chosen


def accepted(q, sample, review):
    if review.get('decision') != 'accept' or not review.get('reviewer') or not review.get('reference_checked'):
        return False
    if review.get('evidence_sha256') != digest(sample):
        return False
    b = bucket(sum(r['correct'] for r in sample))
    required = [r['index'] for r in sample if not r['correct']] if b in BUCKETS[:2] else []
    return set(required) <= set(review.get('incorrect_checked',[]))


def export(root, candidates):
    chosen = selection(root,candidates)
    reviews = read(root/'audit.json') if (root/'audit.json').exists() else {}
    packet, counts = [], {}
    for b, qs in chosen.items():
        counts[b] = dict(provisional=len(qs), accepted=0, shortfall=5-len(qs))
        for q in qs:
            sample = results(root,q)
            ok = accepted(q,sample,reviews.get(q['question_id'],{}))
            counts[b]['accepted'] += int(ok)
            packet.append(dict(question=q,bucket=b,evidence_sha256=digest(sample),
                reference_checked=False, incorrect_required=[r['index'] for r in sample if not r['correct']] if b in BUCKETS[:2] else [],
                rollout_directory=str(root/'rollouts'/q['question_id']),audit_passed=ok))
    diagnostics = dict(fully_screened=0, partial=0, grading_failures=0, parse_failures=0, truncated=0,
                       quarantined_references=len(list((root/'reference_quarantine').glob('*.json'))),
                       infrastructure_attempts=len(list((root/'attempts').glob('**/*.error.json'))))
    present = {p.name for p in (root/'rollouts').glob('*') if p.is_dir()}
    for q in candidates:
        if q['question_id'] not in present: continue
        sample = results(root,q)
        diagnostics['fully_screened'] += int(len(sample)==32)
        diagnostics['partial'] += int(0<len(sample)<32)
        diagnostics['grading_failures'] += sum(r['grading_status']=='grading_failure' for r in sample)
        diagnostics['parse_failures'] += sum(r['grading_status']=='parse_failure' for r in sample)
        diagnostics['truncated'] += sum(r.get('finish_reason')=='length' for r in sample)
    report = dict(version=VERSION, counts=counts, diagnostics=diagnostics,
                  active_seconds=Budget(root).used(), locked=(root/'manifest.json').exists(),
                  budget_exhausted=Budget(root).remaining()==0)
    atomic_json(root/'status.json',report)
    atomic_json(root/'review_packet.json',packet)
    atomic_json(root/'provisional.json',chosen)
    return report


def finalize(root, candidates):
    if not (root/'screening_complete.json').exists():
        raise ValueError('Screening must stop before finalization')
    chosen = selection(root,candidates)
    reviews = read(root/'audit.json')
    questions=[]
    for b in BUCKETS:
        for q in chosen[b]:
            sample=results(root,q)
            if not accepted(q,sample,reviews.get(q['question_id'],{})):
                raise ValueError('Manual audit pending: '+q['question_id'])
            count=sum(r['correct'] for r in sample)
            questions.append({**q,'screening':dict(correct=count,responses=32,solve_rate=count/32,bucket=b)})
    if not questions:
        raise ValueError('No audit-accepted questions')
    manifest=dict(dataset_format='deepmath-screened-v2',repository=DATASET,revision=DATA_REV,
        sample_size=len(questions),dataset_rows=read(root/'preparation.json')['source_rows'],
        dataset_sha256=digest(read(root/'preparation.json')['sources']),questions=questions,
        screening_version=VERSION,screening_run=str(root),run_manifest_sha256=digest(read(root/'run_manifest.json')),
        audit_sha256=digest(reviews),cohorts={str(t):[q['question_id'] for q in questions if q['screening']['solve_rate']<=t] for t in (1,.75,.5,.25,0)})
    atomic_json(root/'manifest.json',manifest)
    atomic_json(root/'lock.json',dict(manifest_sha256=digest(manifest),audit_sha256=digest(reviews)))
    return manifest


def priority(sample, missing):
    """Triage estimate only; final bucket always uses all 32 observations."""
    if len(sample)<8 or any(r['grading_status']=='grading_failure' for r in sample):
        return False
    projected=round(sum(r['correct'] for r in sample)*32/len(sample))
    return missing[bucket(projected)]>0


async def run(root):
    from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError
    candidates=read(root/'candidates.json')
    current=provenance(root)
    if (root/'manifest.json').exists() or (root/'screening_complete.json').exists():
        raise ValueError('Run is complete; export and audit before finalization')
    if (root/'run_manifest.json').exists():
        if read(root/'run_manifest.json') != json.loads(json.dumps(current)):
            raise ValueError('Resume provenance mismatch; create a versioned run')
    else:
        atomic_json(root/'run_manifest.json',current)
    client=AsyncOpenAI(base_url=os.environ['OPENAI_BASE_URL'],api_key=os.environ['OPENAI_API_KEY'],max_retries=0,timeout=14400)
    model=current['runtime']['model']['served_model']
    models=(await client.models.list()).model_dump(mode='json')
    match=[m for m in models['data'] if m['id']==model and m.get('max_model_len')==262144]
    if not match:
        raise ValueError('Endpoint identity/context mismatch')
    atomic_json(root/'endpoint.json',models)
    budget=Budget(root)
    budget.begin()
    stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        loop.add_signal_handler(sig,stop.set)

    async def heartbeat():
        while True:
            budget.save()
            await asyncio.sleep(1)

    beat=asyncio.create_task(heartbeat())
    async def call(q,index,greedy=False,calibration=False):
        directory='calibration' if calibration else ('greedy' if greedy else 'rollouts')
        path=root/directory/q['question_id']/f'{index:02d}.json'
        if path.exists():
            saved=read(path)
            if saved['seed'] != (42 if greedy else seed(q['dataset_row'],index)):
                raise ValueError('Saved seed mismatch')
            return saved
        request=dict(model=model,messages=[dict(role='user',content=custom(GENERAL,q['row']['question']))],
            temperature=0 if greedy else .6,top_p=1 if greedy else .95,seed=42 if greedy else seed(q['dataset_row'],index),
            max_tokens=131072,presence_penalty=0,frequency_penalty=0,
            extra_body=dict(top_k=-1 if greedy else 20,repetition_penalty=1,chat_template_kwargs=dict(enable_thinking=True)))
        raw_path=path.with_suffix('.response.json')
        for attempt in range(4):
            if raw_path.exists():
                raw=read(raw_path)
                break
            if stop.is_set() or budget.remaining()<=0:
                return None
            attempt_dir=root/'attempts'/directory/q['question_id']
            attempt_dir.mkdir(parents=True,exist_ok=True)
            stem=attempt_dir/f'{index:02d}-{time.time_ns()}'
            atomic_json(stem.with_suffix('.request.json'),request)
            try:
                task=asyncio.create_task(client.chat.completions.create(**request))
                stopping=asyncio.create_task(stop.wait())
                try:
                    done,_=await asyncio.wait([task,stopping], timeout=min(14400,budget.remaining()),return_when=asyncio.FIRST_COMPLETED)
                    if task not in done:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError): await task
                        if stop.is_set(): return None
                        raise TimeoutError('Active screening budget exhausted')
                    raw=task.result().model_dump(mode='json')
                finally:
                    stopping.cancel()
                    with contextlib.suppress(asyncio.CancelledError): await stopping
                atomic_json(raw_path,raw)
                break
            except (APIConnectionError,APITimeoutError,APIStatusError,TimeoutError) as exc:
                atomic_json(stem.with_suffix('.error.json'),dict(error=str(exc),type=type(exc).__name__,seed=request['seed']))
                if budget.remaining()<=0: return None
                code=getattr(exc,'status_code',None)
                if code and code<500 and code!=429:
                    raise
                if attempt==3:
                    return None
                await asyncio.sleep(min(2**attempt,budget.remaining()))
        output=raw['choices'][0]['message'].get('content') or ''
        try:
            grading=grade_typed(output,q['reference'])
        except Exception as exc:
            grading=dict(correct=False,grading_status='grading_failure',error=type(exc).__name__)
        saved=dict(index=index,seed=request['seed'],output=output,**grading,
                   finish_reason=raw['choices'][0].get('finish_reason'),usage=raw.get('usage'),
                   request_sha256=digest(request),response_sha256=digest(raw),grader=VERSION)
        atomic_json(path,saved)
        print(directory,q['question_id'],index,saved['grading_status'],flush=True)
        return saved

    async def fill(q,start,end,greedy=False,calibration=False):
        for i in range(start,end,2):
            if stop.is_set() or budget.remaining()<=0: return False
            # Complete the separate control before the last sampled pair so that
            # a budget boundary cannot leave a fully screened item without it.
            if end==32 and i==30 and not greedy and not calibration:
                if await call(q,0,greedy=True) is None: return False
            batch=await asyncio.gather(*(call(q,j,greedy,calibration) for j in range(i,min(i+2,end))))
            if any(r is None for r in batch): return False
        return True

    try:
        controls=[dict(question_id='control-arithmetic',dataset_row=200000,row={'question':'Compute 2 + 2.'},reference=dict(kind='math',gold='4')),
                  dict(question_id='control-boolean',dataset_row=200001,row={'question':'Is 2 an even integer? Answer yes or no.'},reference=dict(kind='boolean',gold='yes'))]
        for q in controls:
            if not await fill(q,0,1,calibration=True): return
            if not read(root/'calibration'/q['question_id']/'00.json')['correct']:
                raise ValueError('Known-answer live calibration failed')
        atomic_json(root/'calibration_passed.json',dict(controls=2,excluded_from_selection=True))
        # Recover full candidates whose separate greedy call was interrupted.
        completed_ids = {p.parent.name for p in (root/'rollouts').glob('*/31.json')}
        for q in candidates:
            if q['question_id'] in completed_ids and len(results(root,q))==32:
                if not await fill(q,0,1,greedy=True): return
        deferred=[]
        report=export(root,candidates)
        for q in candidates:
            if stop.is_set() or budget.remaining()<=0: break
            sample=results(root,q)
            if len(sample)==32: continue
            try:
                preflight_reference(q['reference'])
            except Exception as exc:
                atomic_json(root/'reference_quarantine'/f"{q['question_id']}.json",dict(reason=type(exc).__name__))
                continue
            if not await fill(q,0,8):
                deferred.append(q)
                continue
            selected=selection(root,candidates)
            missing={b:5-len(selected[b]) for b in BUCKETS}
            if any(r['grading_status']=='grading_failure' for r in results(root,q)):
                continue
            if priority(results(root,q),missing):
                if await fill(q,8,32): await fill(q,0,1,greedy=True)
                else: deferred.append(q)
            else: deferred.append(q)
            report=export(root,candidates)
            print(json.dumps(report),flush=True)
            if all(v['accepted']==5 for v in report['counts'].values()): break
        # Exhausted the first traversal: complete remaining candidates in frozen order.
        for q in deferred:
            if stop.is_set() or budget.remaining()<=0 or all(v['accepted']==5 for v in report['counts'].values()): break
            if await fill(q,0,32): await fill(q,0,1,greedy=True)
            report=export(root,candidates)
        report=export(root,candidates)
        if not stop.is_set():
            atomic_json(root/'screening_complete.json',dict(reason='budget_exhausted' if budget.remaining()<=0 else 'quotas_audited' if all(v['accepted']==5 for v in report['counts'].values()) else 'candidate_order_exhausted'))
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError): await beat
        budget.close()
        if budget.remaining()<=0:
            atomic_json(root/'screening_complete.json',dict(reason='budget_exhausted'))
        export(root,candidates)
        await client.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','preflight','run','status','audit-export','finalize'])
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--exclude',type=Path)
    args=p.parse_args()
    root=require_scratch(args.root)
    root.mkdir(parents=True,exist_ok=True)
    if args.command in ('status','audit-export'):
        print(json.dumps(export(root,read(root/'candidates.json')),indent=2)); return
    with (root/'.screening.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command=='prepare': prepare(root,args.exclude)
        elif args.command=='preflight':
            for q in read(root/'candidates.json'): preflight_reference(q['reference'])
            print('Offline reference preflight passed')
        elif args.command=='run': asyncio.run(run(root))
        else: finalize(root,read(root/'candidates.json'))


if __name__=='__main__': main()
