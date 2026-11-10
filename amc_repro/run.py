import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import time
from dataclasses import asdict
from pathlib import Path
from .client import Client, Settings
from .grading import grade
from .storage import atomic_json, dataset_manifest, Trace, ProgressLog, response_preview
from .workflows import Workflow
from .sandbox import preflight


class CachedClient:
    """Checkpoint each successful call, including those in unfinished workflows."""
    def __init__(self, client, directory, progress=None):
        self.client, self.directory, self.progress = client, directory, progress

    async def call(self, prompt, stage, operator, trace):
        path = self.directory / (stage + '.json')
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        if path.exists():
            saved = json.loads(path.read_text())
            if saved['prompt_sha256'] != digest: raise ValueError('Cached prompt mismatch')
            if self.progress:
                common = trace.common
                position = ''
                if common.get('evaluation_index') and common.get('evaluation_total'):
                    position = f"[{common['evaluation_index']}/{common['evaluation_total']}] "
                self.progress(f"{position}{common.get('question_id', '?')} {common.get('workflow_id', '?')} "
                              f'{stage} cached: {response_preview(saved["output"])}')
            return saved['output']
        output = await self.client.call(prompt, stage, operator, trace)
        atomic_json(path, {'prompt_sha256':digest, 'output':output})
        return output


def parser():
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', default='datasets/amc_test.jsonl')
    p.add_argument('--sample-size',type=int,default=50)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--workflows',default='baseline,W1,W2,W3,W4')
    p.add_argument('--results-dir',default='results/amc')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--temperature',type=float,default=0)
    p.add_argument('--top-p',type=float,default=1)
    p.add_argument('--inference-seed',type=int,default=42)
    p.add_argument('--max-tokens',type=int,default=4096)
    p.add_argument('--thinking',choices=['on','off','default'],default='off')
    p.add_argument('--concurrency',type=int,default=1)
    p.add_argument('--requests-per-minute',type=float,default=30)
    p.add_argument('--timeout',type=float,default=180)
    p.add_argument('--retries',type=int,default=3)
    return p


async def main(args):
    root = Path(args.results_dir)
    workflows = args.workflows.split(',')
    if len(set(workflows)) != len(workflows) or set(workflows)-set(['baseline','W1','W2','W3','W4']):
        raise ValueError('Invalid or duplicate workflows')
    if args.concurrency < 1 or args.requests_per_minute <= 0: raise ValueError('Invalid concurrency/rate')
    manifest = dataset_manifest(args.dataset,args.sample_size,args.seed)
    settings = Settings(args.temperature,args.top_p,args.inference_seed,args.max_tokens,args.thinking,
                        args.concurrency,args.requests_per_minute,args.timeout,args.retries)
    source_hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('amc_repro').glob('*.py'))}
    provenance = json.loads(Path('sources/provenance.json').read_text())
    config = {'settings':asdict(settings),'workflows':workflows,'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
              'source_hashes':source_hashes,
              'upstream_commit':provenance['commit'],
              'packages':{p:importlib.metadata.version(p) for p in ['openai','math-verify','sympy','latex2sympy2-extended']}}
    if (root/'config.json').exists():
        if not args.resume: raise ValueError('Results exist; use --resume or a fresh results directory')
        if json.loads((root/'config.json').read_text()) != config: raise ValueError('Resume config/source mismatch')
    else:
        atomic_json(root/'manifest.json',manifest)
        atomic_json(root/'config.json',config)
    progress = ProgressLog(root/'run.log')
    total_evaluations = len(manifest['questions']) * len(workflows)
    progress(f"Run starting: {len(manifest['questions'])} question(s), {len(workflows)} workflow(s), "
             f'{total_evaluations} evaluation(s), sample seed={args.seed}')
    client = Client(settings, progress=progress)
    try:
        await client.discover()
        progress(f'Model selected: {client.model}; concurrency={args.concurrency}; max_tokens={args.max_tokens}')
        metadata = client.metadata()
        if (root/'metadata.json').exists():
            old = json.loads((root/'metadata.json').read_text())
            if old['model'] != metadata['model'] or old['request_parameters'] != metadata['request_parameters']:
                raise ValueError('Resume model mismatch')
        atomic_json(root/'metadata.json',metadata)
        if set(workflows) & {'W2','W3'}:
            sandbox = preflight()
            if (root/'sandbox.json').exists() and json.loads((root/'sandbox.json').read_text()) != sandbox:
                raise ValueError('Resume sandbox image mismatch')
            atomic_json(root/'sandbox.json', sandbox)
        limit = asyncio.Semaphore(args.concurrency)
        async def evaluate(q,w,index):
            label = f'[{index}/{total_evaluations}] {q["question_id"]} {w}'
            async with limit:
                folder = root/'evaluations'/q['question_id']/w
                completed = folder/'result.json'
                if completed.exists():
                    progress(f'{label} skipped: already complete')
                    return
                progress(f'{label} started')
                trace = Trace(folder/'trace.jsonl', {'question_id':q['question_id'],'workflow_id':w,'model':client.model,
                                                    'evaluation_index':index,'evaluation_total':total_evaluations,
                                                    'inference_parameters':client.parameters()})
                flow = Workflow(CachedClient(client,folder/'calls',progress),trace)
                start = time.monotonic()
                try:
                    output = await flow.run(w,q['row']['problem'])  # No gold enters graph.
                    grading = grade(output,q['gold_answer'])
                    status = 'completed'
                    error = None
                except Exception as exc:
                    output, grading, status, error = '', {'correct':False,'grading_status':'execution_failure','extracted_answer':None}, 'failed', str(exc)
                # Retrospective grading only after generation/selection has finished.
                candidates = [{'candidate_id':chr(65+i),'solution':s,**grade(s,q['gold_answer'])} for i,s in enumerate(flow.candidates)]
                selected = candidates[flow.selected] if flow.selected is not None else None
                loss = None
                if any(c['correct'] for c in candidates) and not grading['correct']:
                    loss = 'aggregation' if selected and not selected['correct'] else 'verification' if selected else 'selection_parse_failure'
                result = {'question_id':q['question_id'],'workflow_id':w,'output':output,**grading,'status':status,'error':error,
                          'candidates':candidates,'selected_candidate_id':selected['candidate_id'] if selected else None,
                          'selected_solver':flow.category,'intermediate_correct_final_incorrect':bool(loss), 'loss_stage':loss,
                          'latency_this_attempt':time.monotonic()-start}
                events = [json.loads(line) for line in (folder/'trace.jsonl').read_text().splitlines()]
                calls = [e for e in events if e['event']=='llm_call']
                usages = [e['usage'] for e in calls if e.get('usage')]
                result.update(llm_calls=len(calls), successful_calls=sum(e['status']=='success' for e in calls),
                              prompt_tokens=sum(u['prompt_tokens'] for u in usages), completion_tokens=sum(u['completion_tokens'] for u in usages),
                              usage_complete=len(usages)==len(calls))
                trace.emit(event='retrospective_evaluation',**result)
                atomic_json(completed if status == 'completed' else folder/'failure.json',result)
                progress(f'{label} {status}: grade={grading["grading_status"]}; '
                         f'calls={result["llm_calls"]}; elapsed={result["latency_this_attempt"]:.1f}s')
        await asyncio.gather(*(evaluate(q,w,i) for i,(q,w) in enumerate(
            ((q,w) for q in manifest['questions'] for w in workflows), start=1)))
        failures = list(root.glob('evaluations/*/*/failure.json'))
        missing = [1 for q in manifest['questions'] for w in workflows if not (root/'evaluations'/q['question_id']/w/'result.json').exists()]
        atomic_json(root/'run_status.json', {'status':'incomplete' if missing else 'complete','missing':len(missing)})
        if missing:
            progress(f'Run incomplete: {missing} evaluation(s) failed; inspect failure.json and resume')
            raise RuntimeError(f'{len(missing)} evaluations failed; inspect failure.json and resume')
        progress(f'Run complete: {total_evaluations} evaluation(s)')
    except Exception as exc:
        progress(f'Run blocked: {type(exc).__name__}')
        atomic_json(root/'blocked.json', {'error':str(exc),'resolved_model':client.model})
        raise
    finally:
        await client.api.close()

if __name__ == '__main__': asyncio.run(main(parser().parse_args()))
