"""Read scratch checkpoints and publish allowlisted, hourly screening progress."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import time

BUCKETS = ('0/32', '1-8/32', '9-16/32', '17-24/32', '25-32/32')
BRANCH = 'screening-reports'
OUTPUT = Path('screening_reports/deepmath-v1')
QUESTION = re.compile(r'deepmath-row-(\d+)\Z')
FIELDS = ('question_id','dataset_row','candidate_order','phase','sampled_completed',
          'sampled_correct','observed_solve_rate','triage_correct','bucket',
          'provisional_selected','audit_status','greedy_completed','parse_failures',
          'grading_failures','truncated','pending_sampled_slots')


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        import os
        os.fsync(f.fileno())
    tmp.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def bucket(correct):
    return BUCKETS[0 if correct == 0 else 1 + (correct-1)//8]


def audited(sample, review, b):
    required = {r['index'] for r in sample if not r['correct']} if b in BUCKETS[:2] else set()
    return (review.get('decision') == 'accept' and bool(review.get('reviewer'))
            and review.get('reference_checked') is True
            and review.get('evidence_sha256') == digest(sample)
            and required <= set(review.get('incorrect_checked', [])))


def collect(root, now=None):
    """Construct public fields explicitly. Never serialize scratch objects wholesale."""
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    manifest = read(root/'run_manifest.json')
    preparation = read(root/'preparation.json')
    candidates = read(root/'candidates.json')
    ledger = read(root/'budget.json', {'sessions':[]})
    reviews = read(root/'audit.json', {})
    complete = read(root/'screening_complete.json', {})
    present = set()
    for folder in ('rollouts','reference_quarantine','attempts/rollouts'):
        directory = root/folder
        if folder == 'reference_quarantine':
            present.update(p.stem for p in directory.glob('*.json'))
        else:
            present.update(p.name for p in directory.glob('*') if p.is_dir())
    pending = {}
    for identity in present:
        if not QUESTION.fullmatch(identity):
            raise ValueError('Unexpected question identifier; refusing publication')
        indices=set()
        for p in (root/'attempts/rollouts'/identity).glob('*.request.json'):
            match=re.fullmatch(r'(\d{2})-\d+\.request\.json',p.name)
            if not match: continue
            i=int(match.group(1))
            error=p.with_name(p.name.replace('.request.json','.error.json'))
            response=root/'rollouts'/identity/f'{i:02d}.response.json'
            saved=root/'rollouts'/identity/f'{i:02d}.json'
            if not error.exists() and not response.exists() and not saved.exists():
                indices.add(i)
        pending[identity]=sorted(indices)
    rows=[]
    counts={b:dict(fully_screened=0,provisional=0,audit_accepted=0,target=5) for b in BUCKETS}
    for order,q in enumerate(candidates):
        identity=q['question_id']
        if identity not in present: continue
        match=QUESTION.fullmatch(identity)
        if not match or int(match.group(1)) != q['dataset_row']:
            raise ValueError('Question source mapping mismatch')
        sample=[read(p) for p in sorted((root/'rollouts'/identity).glob('[0-9][0-9].json'))]
        indices={r['index'] for r in sample}
        if len(indices)!=len(sample) or not indices <= set(range(32)):
            raise ValueError('Invalid sampled response identities')
        n=len(sample)
        correct=sum(r['correct'] is True for r in sample)
        failures=sum(r.get('grading_status')=='grading_failure' for r in sample)
        quarantined=(root/'reference_quarantine'/f'{identity}.json').exists()
        decision=reviews.get(identity,{})
        eligible=n==32 and not failures and not quarantined
        b=bucket(correct) if eligible else None
        selected=bool(b and decision.get('decision')!='quarantine' and counts[b]['provisional']<5)
        audit_status='quarantined' if quarantined or failures or decision.get('decision')=='quarantine' else 'pending'
        if eligible:
            counts[b]['fully_screened']+=1
            if selected:
                counts[b]['provisional']+=1
                if audited(sample,decision,b):
                    counts[b]['audit_accepted']+=1
                    audit_status='accepted'
        phase='fully_screened' if n==32 else 'triaged' if n==8 else 'partial' if n else 'requested'
        if quarantined or failures: phase='quarantined'
        rows.append(dict(question_id=identity,dataset_row=int(q['dataset_row']),candidate_order=order,
            phase=phase,sampled_completed=n,sampled_correct=correct,
            observed_solve_rate=correct/n if n else None,
            triage_correct=sum(r['correct'] is True for r in sample if r['index']<8) if set(range(8))<=indices else None,
            bucket=b,provisional_selected=selected,audit_status=audit_status,
            greedy_completed=(root/'greedy'/identity/'00.json').exists(),
            parse_failures=sum(r.get('grading_status')=='parse_failure' for r in sample),
            grading_failures=failures,truncated=sum(r.get('finish_reason')=='length' for r in sample),
            pending_sampled_slots=pending.get(identity,[])))
    sessions=ledger['sessions']
    seconds=sum(s['seconds'] for s in sessions)
    reserve=sum(s.get('reserved_seconds',0) for s in sessions if s.get('open'))
    budget_path=root/'budget.json'
    age=max(0,now.timestamp()-budget_path.stat().st_mtime) if budget_path.exists() else None
    recent=bool(sessions and sessions[-1].get('open') and age is not None and age<120)
    reason=complete.get('reason')
    if reason not in (None,'budget_exhausted','quotas_audited','candidate_order_exhausted'):
        reason='other'
    spec=manifest['spec']
    controls=[]
    for identity in ('control-arithmetic','control-boolean'):
        result=read(root/'calibration'/identity/'00.json', {})
        controls.append(dict(control_id=identity,completed=bool(result),correct=result.get('correct') is True))
    report=dict(format_version=1,generated_at_utc=now.isoformat(),run='deepmath-v1',
        screening_commit=manifest['git_commit'],
        dataset=dict(repository=spec['dataset'],revision=spec['dataset_revision'],
                     source_rows=int(preparation['source_rows']),candidates=int(preparation['candidates']),
                     excluded_previous_questions=len(preparation['excluded_rows'])),
        model=dict(repository=spec['model'],revision=spec['model_revision']),
        state=dict(screening_complete=bool(complete),completion_reason=reason,
                   locked=(root/'manifest.json').exists(),heartbeat_recent=recent,
                   heartbeat_age_seconds=round(age,1) if age is not None else None),
        budget=dict(limit_seconds=int(spec['budget_seconds']),checkpointed_active_seconds=round(seconds,2),
                    interruption_reserve_seconds=round(reserve,2),charged_upper_bound_seconds=round(seconds+reserve,2),
                    remaining_seconds_lower_bound=round(max(0,spec['budget_seconds']-seconds-reserve),2)),
        summary=dict(questions_with_activity=len(rows),questions_with_sampled_results=sum(r['sampled_completed']>0 for r in rows),
                     questions_triaged=sum(r['sampled_completed']>=8 for r in rows),
                     questions_fully_screened=sum(r['sampled_completed']==32 for r in rows),
                     sampled_responses=sum(r['sampled_completed'] for r in rows),
                     parse_failures=sum(r['parse_failures'] for r in rows),
                     grading_failures=sum(r['grading_failures'] for r in rows),
                     truncated=sum(r['truncated'] for r in rows),
                     reference_quarantines=len(list((root/'reference_quarantine').glob('*.json'))),
                     infrastructure_failures=len(list((root/'attempts').glob('**/*.error.json')))),
        buckets=counts,calibration=controls,
        current_questions=[r['question_id'] for r in rows if r['pending_sampled_slots']],questions=rows)
    return report


def write_report(checkout, report):
    output=Path(checkout)/OUTPUT
    output.mkdir(parents=True,exist_ok=True)
    stamp=datetime.fromisoformat(report['generated_at_utc']).strftime('%Y-%m-%dT%H00Z')
    csv_data=io.StringIO()
    writer=csv.DictWriter(csv_data,fieldnames=FIELDS,lineterminator='\n')
    writer.writeheader()
    for row in report['questions']:
        writer.writerow({k:json.dumps(v) if isinstance(v,list) else v for k,v in row.items()})
    for path in (output/'latest.json',output/'history'/f'{stamp}.json'):
        atomic(path,report)
    for path in (output/'questions.csv',output/'history'/f'{stamp}-questions.csv'):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(csv_data.getvalue())
    summary=report['summary'];budget=report['budget']
    lines=['# DeepMath screening progress','',f"Updated: {report['generated_at_utc']}",'',
           f"Screening source: `{report['screening_commit']}`.",'',
           f"**{summary['questions_fully_screened']} fully screened; {summary['questions_triaged']} triaged; {summary['sampled_responses']} sampled responses completed.**",'',
           f"Checkpointed active time: {budget['checkpointed_active_seconds']/3600:.2f} hours / 24 hours; interruption reserve: {budget['interruption_reserve_seconds']:g} seconds.",'',
           f"Screening complete: {report['state']['screening_complete']}. Audit lock present: {report['state']['locked']}. Recent heartbeat: {report['state']['heartbeat_recent']}.",'',
           '| Bucket | Fully screened | Provisional | Audit accepted | Target |',
           '|---|---:|---:|---:|---:|']
    for b,c in report['buckets'].items():
        lines.append(f"| {b} | {c['fully_screened']} | {c['provisional']} | {c['audit_accepted']} | {c['target']} |")
    lines += ['', '## Current question requests','']
    lines += [f"- `{q}`" for q in report['current_questions']] or ['No outstanding sampled requests observed.']
    lines += ['', 'See [questions.csv](questions.csv) for every question with activity, [latest.json](latest.json) for diagnostics, and [history/](history/) for hourly snapshots.', '',
              'Only row IDs and derived statistics are published. Question text, references, responses, request bodies, reviewer identities, and traces stay on scratch.', '',
              'Buckets require 32 sampled responses; partial solve rates are descriptive. Selections remain provisional until manual audit. Pending request files may include interrupted calls. Checkpoints are read atomically per file; a report is a near-time snapshot, not a transaction across all files. Hourly Slurm jobs can be delayed by queueing or maintenance.']
    (output/'README.md').write_text('\n'.join(lines)+'\n')
    return [OUTPUT/p for p in ('README.md','latest.json','questions.csv',f'history/{stamp}.json',f'history/{stamp}-questions.csv')]


def git(checkout,*args):
    return subprocess.check_output(['git','-C',str(checkout),*args],text=True).rstrip('\n')


def publish(checkout, report):
    if git(checkout,'branch','--show-current')!=BRANCH:
        raise ValueError('Publisher requires the dedicated screening-reports branch')
    dirty=git(checkout,'status','--porcelain','--untracked-files=all')
    for line in dirty.splitlines():
        if not line[3:].startswith(str(OUTPUT)+'/'):
            raise ValueError('Unrelated working-tree changes; refusing to commit')
    generated=write_report(checkout,report)
    git(checkout,'add','--',*(str(p) for p in generated))
    if subprocess.run(['git','-C',str(checkout),'diff','--cached','--quiet'],check=False).returncode:
        staged=git(checkout,'diff','--cached','--name-only').splitlines()
        if any(not p.startswith(str(OUTPUT)+'/') for p in staged):
            raise ValueError('Unrelated staged files; refusing to commit')
        git(checkout,'diff','--cached','--check')
        git(checkout,'commit','-m',f"Report DeepMath screening progress at {report['generated_at_utc']}")
    # Normal fast-forward push only: never force, reset, merge, or change source branch.
    git(checkout,'push','origin',f'HEAD:refs/heads/{BRANCH}')
    return git(checkout,'rev-parse','HEAD')


def schedule(root, checkout, until):
    state=root/'reporting'
    if (state/'STOP').exists() or (root/'lock.json').exists() or datetime.now(timezone.utc)>=until:
        return None
    previous=read(state/'schedule.json',{})
    job=previous.get('job_id','').split(';')[0]
    import os
    if job.isdigit() and job!=os.environ.get('SLURM_JOB_ID'):
        try:
            status=subprocess.check_output(['squeue','-h','-j',job,'-o','%T'],text=True,stderr=subprocess.DEVNULL).strip()
        except subprocess.CalledProcessError:
            status=''
        if status in ('PENDING','RUNNING','CONFIGURING','SUSPENDED'):
            return job
    script=checkout/'monitoring/hourly_report.sbatch'
    command=['sbatch','--parsable','--begin=now+60minutes',
             '--output='+str(state/'report-%j.log'),str(script),str(root),str(checkout),until.isoformat()]
    job=subprocess.check_output(command,text=True).strip()
    atomic(state/'schedule.json',dict(job_id=job,scheduled_at_utc=datetime.now(timezone.utc).isoformat(),
                                    until_utc=until.isoformat(),interval_minutes=60,command=command))
    return job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['once','schedule','tick','stop'])
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--checkout',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--until',help='UTC ISO timestamp; scheduling stops after this deadline')
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    root=args.run_root.resolve()
    if not re.fullmatch(r'scratch\d*',root.parts[1]):
        raise ValueError('Private screening inputs must remain on scratch')
    state=root/'reporting';state.mkdir(parents=True,exist_ok=True)
    if args.action=='stop':
        (state/'STOP').touch();return
    with (state/'reporter.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (state/'STOP').exists():return
        if args.action in ('schedule','tick'):
            if not args.until:parser.error('--until is required for scheduling')
            until=datetime.fromisoformat(args.until)
            if until.tzinfo is None:parser.error('--until requires a timezone')
            # Schedule first so a push failure does not break the hourly chain.
            print('Next reporting job:',schedule(root,args.checkout,until),flush=True)
        if args.action=='schedule':return
        report=collect(root)
        if args.publish:
            sha=publish(args.checkout,report)
            atomic(state/'last_publication.json',dict(commit=sha,generated_at_utc=report['generated_at_utc']))
            print('Published',sha,flush=True)
        else:
            write_report(args.checkout,report)
            print('Report written locally; no commit or push',flush=True)


if __name__=='__main__':main()
