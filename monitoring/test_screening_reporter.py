"""Synthetic privacy, checkpoint, publishing, and scheduling checks. No inference."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess

import pytest
from monitoring import screening_reporter as r


@pytest.fixture
def source(tmp_path):
    root=tmp_path/'private';root.mkdir()
    r.atomic(root/'run_manifest.json',dict(git_commit='a'*40,spec=dict(dataset='zwhe99/DeepMath-103K',
        dataset_revision='b'*40,model='RedHatAI/Qwen3.8-27B-INT4',model_revision='c'*40,budget_seconds=86400),
        secret='SENSITIVE_MANIFEST'))
    r.atomic(root/'preparation.json',dict(source_rows=100,candidates=90,excluded_rows=list(range(26)),secret='SENSITIVE_PREPARATION'))
    r.atomic(root/'budget.json',dict(sessions=[dict(seconds=120,open=True,reserved_seconds=60)]))
    qs=[dict(question_id=f'deepmath-row-{i}',dataset_row=i,row=dict(question='SENSITIVE_QUESTION'),gold_answer='SENSITIVE_REFERENCE') for i in range(8)]
    r.atomic(root/'candidates.json',qs)
    for i,q in enumerate(qs[:7]):
        n=8 if i==6 else 32
        values=[]
        for j in range(n):
            value=dict(index=j,correct=j<i,grading_status='correct' if j<i else 'math_error',output='SENSITIVE_RESPONSE',trace='SENSITIVE_TRACE')
            values.append(value)
            r.atomic(root/'rollouts'/q['question_id']/f'{j:02d}.json',value)
        if i==0:
            r.atomic(root/'audit.json',{q['question_id']:dict(decision='accept',reviewer='SENSITIVE_REVIEWER',
                reference_checked=True,evidence_sha256=r.digest(values),incorrect_checked=list(range(32)))})
    r.atomic(root/'attempts/rollouts/deepmath-row-7/00-123.request.json',dict(prompt='SENSITIVE_PROMPT'))
    return root


def test_report_privacy_partial_buckets_and_audit(source,tmp_path):
    report=r.collect(source)
    assert 'SENSITIVE' not in json.dumps(report)
    assert report['summary']['questions_fully_screened']==6
    assert report['summary']['questions_triaged']==7
    assert report['summary']['sampled_responses']==200
    assert report['current_questions']==['deepmath-row-7']
    assert report['questions'][6]['bucket'] is None
    assert report['questions'][7]['sampled_completed']==0
    assert report['buckets']['0/32']['audit_accepted']==1
    assert report['buckets']['1-8/32']['provisional']==5
    assert report['budget']['charged_upper_bound_seconds']==180
    r.write_report(tmp_path,report)
    output=tmp_path/r.OUTPUT
    assert len(list((output/'history').glob('*')))==2
    assert (output/'questions.csv').read_text().splitlines()[0]==','.join(r.FIELDS)
    assert all('SENSITIVE' not in p.read_text() for p in output.rglob('*') if p.is_file())


def test_quarantine_and_stale_audit(source):
    sample=source/'rollouts/deepmath-row-0/00.json'
    v=r.read(sample);v['output']='changed private evidence';r.atomic(sample,v)
    r.atomic(source/'reference_quarantine/deepmath-row-1.json',dict(reason='SENSITIVE_ERROR'))
    report=r.collect(source)
    assert report['buckets']['0/32']['audit_accepted']==0
    assert report['questions'][1]['bucket'] is None
    assert report['questions'][1]['phase']=='quarantined'
    assert report['summary']['reference_quarantines']==1
    assert 'SENSITIVE' not in json.dumps(report)


def test_infrastructure_errors_not_completed_samples(source):
    r.atomic(source/'attempts/rollouts/deepmath-row-7/00-123.error.json',dict(error='SENSITIVE_TRANSPORT'))
    report=r.collect(source)
    assert report['summary']['infrastructure_failures']==1
    assert report['summary']['sampled_responses']==200
    assert report['current_questions']==[]


def command(*args,cwd=None):
    return subprocess.check_output(args,cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()


@pytest.fixture
def checkout(tmp_path):
    remote=tmp_path/'remote.git';local=tmp_path/'checkout'
    command('git','init','--bare',str(remote))
    command('git','clone',str(remote),str(local))
    command('git','config','user.email','synthetic@example.invalid',cwd=local)
    command('git','config','user.name','Synthetic test',cwd=local)
    command('git','checkout','-b',r.BRANCH,cwd=local)
    (local/'source.py').write_text('synthetic original source\n')
    command('git','add','source.py',cwd=local)
    command('git','commit','-m','Synthetic initial source',cwd=local)
    command('git','push','origin',r.BRANCH,cwd=local)
    return local,remote


def test_publish_scoped_commit_and_remote(checkout,source):
    local,remote=checkout
    original=(local/'source.py').read_bytes()
    report=r.collect(source)
    sha=r.publish(local,report)
    assert sha==command('git','--git-dir',str(remote),'rev-parse',f'refs/heads/{r.BRANCH}')
    paths=command('git','show','--format=','--name-only',sha,cwd=local).splitlines()
    assert all(p.startswith(str(r.OUTPUT)+'/') for p in paths)
    assert (local/'source.py').read_bytes()==original
    assert command('git','status','--porcelain',cwd=local)==''
    (local/'source.py').write_text('unrelated dirty source\n')
    with pytest.raises(ValueError,match='Unrelated'):r.publish(local,report)
    assert command('git','rev-parse','HEAD',cwd=local)==sha


def test_push_rejects_remote_divergence_without_force(checkout,source,tmp_path):
    local,remote=checkout
    other=tmp_path/'other'
    command('git','clone','--branch',r.BRANCH,str(remote),str(other))
    command('git','config','user.email','synthetic@example.invalid',cwd=other)
    command('git','config','user.name','Synthetic test',cwd=other)
    (other/'other.txt').write_text('remote change\n')
    command('git','add','other.txt',cwd=other);command('git','commit','-m','Remote change',cwd=other)
    command('git','push','origin',r.BRANCH,cwd=other)
    head=command('git','rev-parse','HEAD',cwd=other)
    with pytest.raises(subprocess.CalledProcessError):r.publish(local,r.collect(source))
    assert command('git','--git-dir',str(remote),'rev-parse',f'refs/heads/{r.BRANCH}')==head


def test_hourly_schedule_deduplicates_and_stop_marker(tmp_path,monkeypatch):
    root=tmp_path/'run';(root/'reporting').mkdir(parents=True)
    calls=[]
    def output(args,**kwargs):
        calls.append(args)
        return '42\n' if args[0]=='sbatch' else 'PENDING\n'
    monkeypatch.setattr(r.subprocess,'check_output',output)
    monkeypatch.setenv('SLURM_JOB_ID','41')
    until=datetime.now(timezone.utc)+timedelta(hours=72)
    assert r.schedule(root,tmp_path,until)=='42'
    assert r.schedule(root,tmp_path,until)=='42'
    assert sum(c[0]=='sbatch' for c in calls)==1
    assert '--begin=now+60minutes' in calls[0]
    assert '--nodelist=cml38' in calls[0]
    (root/'reporting/STOP').touch()
    assert r.schedule(root,tmp_path,until) is None


def test_publisher_does_not_stage_extra_files_in_report_folder(checkout,source):
    local,remote=checkout
    secret=local/r.OUTPUT/'unexpected-private.json'
    secret.parent.mkdir(parents=True)
    secret.write_text('SENSITIVE_UNEXPECTED_FILE')
    sha=r.publish(local,r.collect(source))
    tracked=command('git','ls-tree','-r','--name-only',sha,cwd=local)
    assert 'unexpected-private.json' not in tracked
    assert secret.exists()
