"""Authorized pilot/full/analysis/archive pipeline for the provisional 21-item run."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import urllib.request

from .storage import atomic_json

REPO = Path(__file__).resolve().parent.parent
BRANCH = 'screened21-flowbank-rerun'
ROOT = Path(os.environ.get('AMC_ROOT','/scratch1/mendeza/flowbank-amc'))
RESULTS = ROOT/'results/deepmath21_screened_redhat_int4'
ARCHIVE = Path('experiment_results/deepmath21_screened_redhat_int4')
child = None


def git(*args):
    return subprocess.check_output(['git',*args],cwd=REPO,text=True).strip()


def gate():
    if git('branch','--show-current') != BRANCH or git('status','--porcelain'):
        raise ValueError('Pipeline requires a clean experiment branch')
    sha=git('rev-parse','HEAD')
    if git('ls-remote','origin',f'refs/heads/{BRANCH}').split()[0] != sha:
        raise ValueError('Push the experiment commit before inference')
    return sha


def status(phase,**extra):
    value=dict(phase=phase,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        slurm_job_id=os.environ.get('SLURM_JOB_ID'),audit_status='pending',**extra)
    atomic_json(RESULTS/'pipeline_status.json',value)
    print(json.dumps(value),flush=True)


def command(*args):
    global child
    child=subprocess.Popen(list(args),cwd=REPO,start_new_session=True)
    try:
        code=child.wait()
        if code: raise subprocess.CalledProcessError(code,args)
    finally:
        child=None


def action(name):
    command('bash','scripts/run_screened21.sh',name)


def interrupt(signum, frame):
    if child is not None and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try: child.wait(timeout=30)
        except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL)
    status('interrupted',signal=signum)
    raise SystemExit(128+signum)


def pilot_flags(report):
    flags={k:report[k] for k in ('context_overflows','failed_evaluations','grading_failures') if report[k]}
    if report['completed'] != report['expected'] or report['expected'] != 25 or not report['usage_complete']:
        flags['pilot_completeness_or_usage']='incomplete'
    return flags


def archive(source_commit):
    # Explicit aggregate allowlist: never copy manifest, references, outputs or traces.
    gate()
    if git('rev-parse','HEAD') != source_commit:
        raise ValueError('Source commit changed during inference')
    target=REPO/ARCHIVE
    if target.exists(): raise ValueError('Results archive already exists; inspect before publishing')
    target.mkdir(parents=True)
    names=['summary.json','correctness_matrix.csv','correctness_matrix.md']
    names += [f'{table}.{ext}' for table in ('table1_baseline','table2_portfolio') for ext in ('csv','md','tex')]
    names += ['comparison/'+name for name in (
        'RESULTS_REPORT.md','all_subset_coverage.csv','complementarity_by_k.csv','cohort_metrics.csv',
        'cohort_membership.csv','per_item_correctness.csv','evaluation_costs.csv','condition_diagnostics.csv',
        'baseline_screening_comparison.csv','plot_environment.json')]
    names += [f'comparison/{name}.{ext}' for name in ('figure1_complementarity','figure2_harder_cohorts') for ext in ('png','pdf','svg')]
    for name in names:
        path=target/name
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(RESULTS/name,path)
    config=json.loads((RESULTS/'config.json').read_text())
    manifest=json.loads((RESULTS/'manifest.json').read_text())
    atomic_json(target/'provenance.json',dict(implementation_commit=source_commit,
        dataset_repository=manifest['repository'],dataset_revision=manifest['revision'],
        dataset_sha256=manifest['dataset_sha256'],manifest_sha256=config['manifest_sha256'],
        model_repository=config['local_runtime']['model']['repository'],
        model_revision=config['local_runtime']['model']['revision'],source_hashes=config['source_hashes'],
        settings=config['settings'],runtime_packages=config['runtime_packages'],audit_status='pending',
        sample_size=21,expected_evaluations=105))
    atomic_json(target/'artifact_sha256.json',{name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in names})
    (target/'README.md').write_text('# Screened DeepMath: 21-question FlowBank rerun\n\n'
        '**Exploratory; dataset audit pending.** Fresh baseline and fixed W1–W4, 105 evaluations.\n\n'
        '[Results report](comparison/RESULTS_REPORT.md) · [Baseline table](table1_baseline.md) · '
        '[Portfolio table](table2_portfolio.md) · [Provenance](provenance.json)\n\n'
        'Reproduce with `bash scripts/run_screened21.sh analyze`. Private questions and raw traces remain on scratch.\n')
    git('add','--',str(ARCHIVE))
    staged=git('diff','--cached','--name-only').splitlines()
    if not staged or any(not p.startswith(str(ARCHIVE)+'/') for p in staged):
        raise ValueError('Unexpected staged files')
    git('diff','--cached','--check')
    git('commit','-m','Archive exploratory screened-21 FlowBank results and complementarity figures')
    commit=git('rev-parse','HEAD')
    git('push','origin',f'HEAD:refs/heads/{BRANCH}')
    return commit


def main():
    os.environ['AMC_MODEL_PROFILE']='redhat'
    if not os.environ.get('SLURM_JOB_ID'): raise ValueError('Run inside a GPU Slurm allocation')
    RESULTS.mkdir(parents=True,exist_ok=True)
    with (RESULTS/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,interrupt)
        try:
            sha=gate()
            launch_path=RESULTS/'launch_provenance.json'
            provenance=dict(implementation_commit=sha,branch=BRANCH)
            if launch_path.exists() and json.loads(launch_path.read_text()) != provenance:
                raise ValueError('Launch commit differs from saved run')
            atomic_json(launch_path,provenance)
            action('prepare')
            status('starting_server',implementation_commit=sha)
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3): pass
            except Exception:
                pidfile=ROOT/'deployments/redhat/vllm.pid'
                if pidfile.exists():
                    pid=int(pidfile.read_text())
                    if Path(f'/proc/{pid}').exists(): raise ValueError('Deployment PID is active but endpoint is unhealthy')
                    pidfile.unlink()
                command('bash','scripts/start_vllm.sh')
            deadline=time.monotonic()+1800
            while True:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3): break
                except Exception:
                    if time.monotonic()>deadline: raise RuntimeError('Server readiness timed out')
                    time.sleep(2)
            status('endpoint_check')
            command(str(ROOT/'runtime/bin/python'),'-m','amc_repro.check_endpoint','--local-runtime',
                    '--results-dir',str(RESULTS/'endpoint_check'))
            status('pilot_running')
            action('pilot')
            action('analyze-pilot')
            report=json.loads((RESULTS/'pilot_inspection.json').read_text())
            flags=pilot_flags(report)
            if flags:
                status('paused_for_operational_review',flags=flags,pilot_inspection=report)
                return
            status('full_running',pilot_inspection=report)
            action('full')
            status('final_analysis')
            action('analyze')
            status('archiving')
            commit=archive(sha)
            status('complete',results_commit=commit)
        except Exception as exc:
            status('failed',error=str(exc))
            raise


if __name__ == '__main__': main()
