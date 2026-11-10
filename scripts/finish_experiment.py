"""Monitor the active smoke run, then launch full evaluation only on success.

This helper never changes prompts, manifests, or results. It can remain running
if the interactive session ends. Output is written to results/pipeline.log.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--wait-for-pid',type=int)
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
os.chdir(root)
Path('results/pipeline_status.json').write_text(json.dumps({'status':'waiting_for_smoke','smoke_pid':a.wait_for_pid},indent=2))
if a.wait_for_pid:
    while True:
        try: os.kill(a.wait_for_pid,0)
        except ProcessLookupError: break
        time.sleep(30)
status_path=Path('results/smoke/run_status.json')
if not status_path.exists() or json.loads(status_path.read_text())['status']!='complete':
    Path('results/pipeline_status.json').write_text(json.dumps({'status':'blocked','reason':'Smoke test did not complete; full run not started.'},indent=2))
    sys.exit(1)
subprocess.run([sys.executable,'-m','amc_repro.analyze','--results-dir','results/smoke'],check=True)
command=[sys.executable,'-m','amc_repro.run','--sample-size','50','--seed','42',
         '--results-dir','results/amc','--concurrency','2','--timeout','600']
if Path('results/amc/config.json').exists(): command.append('--resume')
Path('results/pipeline_status.json').write_text(json.dumps({'status':'full_run_running','command':command},indent=2))
with open('results/full_run.log','a') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
if result.returncode:
    Path('results/pipeline_status.json').write_text(json.dumps({'status':'blocked','reason':'Full run incomplete; inspect full_run.log and resume.'},indent=2))
    sys.exit(result.returncode)
subprocess.run([sys.executable,'-m','amc_repro.analyze','--results-dir','results/amc'],check=True)
Path('results/pipeline_status.json').write_text(json.dumps({'status':'complete'},indent=2))
