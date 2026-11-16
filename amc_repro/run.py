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
from .storage import atomic_json, dataset_manifest, Trace
from .workflows import Workflow, WorkflowOutputError
from .sandbox import preflight


class CachedClient:
    """Checkpoint each successful call, including those in unfinished workflows."""
    def __init__(self, client, directory):
        self.client, self.directory = client, directory

    async def call(self, prompt, stage, operator, trace):
        path = self.directory / (stage + '.json')
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        if path.exists():
            saved = json.loads(path.read_text())
            if saved['prompt_sha256'] != digest: raise ValueError('Cached prompt mismatch')
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
    p.add_argument('--limit-items',type=int, help='Schedule only the first K items of the full frozen manifest')
    p.add_argument('--local-runtime',action='store_true', help='Bind the pinned local server identity and tokenizer')
    p.add_argument('--temperature',type=float,default=0)
    p.add_argument('--top-p',type=float,default=1)
    p.add_argument('--inference-seed',type=int,default=42)
    p.add_argument('--max-tokens',type=int,default=131072)
    p.add_argument('--thinking',choices=['on','off','default'],default='on')
    p.add_argument('--concurrency',type=int,default=2)
    p.add_argument('--requests-per-minute',type=float,default=30)
    p.add_argument('--timeout',type=float,default=14400)
    p.add_argument('--retries',type=int,default=3)
    return p


async def _main(args):
    root = Path(args.results_dir)
    workflows = args.workflows.split(',')
    if len(set(workflows)) != len(workflows) or set(workflows)-set(['baseline','W1','W2','W3','W4']):
        raise ValueError('Invalid or duplicate workflows')
    if args.concurrency < 1 or args.requests_per_minute <= 0: raise ValueError('Invalid concurrency/rate')
    if args.limit_items is not None and not 1 <= args.limit_items <= args.sample_size:
        raise ValueError('limit-items must be between 1 and sample-size')
    runtime = None
    if args.local_runtime:
        from .local_runtime import configure_client
        runtime = configure_client()
    manifest = dataset_manifest(args.dataset,args.sample_size,args.seed)
    settings = Settings(args.temperature,args.top_p,args.inference_seed,args.max_tokens,args.thinking,
                        args.concurrency,args.requests_per_minute,args.timeout,args.retries)
    source_hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('amc_repro').glob('*.py'))}
    config = {'settings':asdict(settings),'workflows':workflows,'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
              'source_hashes':source_hashes,
              'upstream_commit':'dde948d9f65cede15e6a3418dde3bf7feffdd087',
              'local_runtime':runtime,
              'runtime_packages':dict(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions() if d.metadata['Name'])),
              'packages':{p:importlib.metadata.version(p) for p in ['openai','math-verify','sympy','latex2sympy2-extended']}}
    if (root/'config.json').exists():
        if not args.resume: raise ValueError('Results exist; use --resume or a fresh results directory')
        if json.loads((root/'manifest.json').read_text()) != manifest: raise ValueError('Saved manifest mismatch')
        if json.loads((root/'config.json').read_text()) != config: raise ValueError('Resume config/source mismatch')
    else:
        atomic_json(root/'manifest.json',manifest)
        atomic_json(root/'config.json',config)
    scheduled = manifest['questions'][:args.limit_items]
    client = Client(settings)
    try:
        await client.discover()
        metadata = client.metadata()
        if runtime: metadata['model_label'] = 'Qwen3.8-27B AutoRound INT4'
        if (root/'metadata.json').exists():
            old = json.loads((root/'metadata.json').read_text())
            if old['model'] != metadata['model'] or old['request_parameters'] != metadata['request_parameters']:
                raise ValueError('Resume model mismatch')
        atomic_json(root/'metadata.json',metadata)
        if set(workflows) & {'W2','W3'}:
            sandbox = preflight()
            if (root/'sandbox.json').exists() and json.loads((root/'sandbox.json').read_text()) != sandbox:
                raise ValueError('Resume executor identity mismatch')
            atomic_json(root/'sandbox.json', sandbox)
        limit = asyncio.Semaphore(args.concurrency)
        async def evaluate(q,w):
            async with limit:
                folder = root/'evaluations'/q['question_id']/w
                completed = folder/'result.json'
                if completed.exists(): return
                trace = Trace(folder/'trace.jsonl', {'question_id':q['question_id'],'workflow_id':w,'model':client.model,
                                                    'inference_parameters':client.parameters()})
                flow = Workflow(CachedClient(client,folder/'calls'),trace)
                start = time.monotonic()
                try:
                    output = await flow.run(w,q['row']['problem'])  # No gold enters graph.
                    grading = grade(output,q['gold_answer'])
                    status = 'completed'
                    error = None
                except WorkflowOutputError as exc:
                    output, grading, status, error = '', {'correct':False,'grading_status':'parse_failure','extracted_answer':None}, 'completed', str(exc)
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
                usages = [e['usage'] for e in calls if e.get('usage')
                          and isinstance(e['usage'].get('prompt_tokens'),int)
                          and isinstance(e['usage'].get('completion_tokens'),int)]
                result.update(llm_calls=len(calls), successful_calls=sum(e['status']=='success' for e in calls),
                              prompt_tokens=sum(u['prompt_tokens'] for u in usages), completion_tokens=sum(u['completion_tokens'] for u in usages),
                              usage_complete=bool(calls) and len(usages)==len(calls),
                              truncated_calls=sum(e.get('finish_reason') == 'length' for e in calls))
                trace.emit(event='retrospective_evaluation',**result)
                atomic_json(completed if status == 'completed' else folder/'failure.json',result)
                if status == 'completed': (folder/'failure.json').unlink(missing_ok=True)
                print(q['question_id'],w,status,grading['grading_status'],flush=True)
        await asyncio.gather(*(evaluate(q,w) for q in scheduled for w in workflows))
        missing = [1 for q in manifest['questions'] for w in workflows
                   if not (root/'evaluations'/q['question_id']/w/'result.json').exists()]
        scheduled_missing = [1 for q in scheduled for w in workflows
                   if not (root/'evaluations'/q['question_id']/w/'result.json').exists()]
        atomic_json(root/'run_status.json', {'status':'incomplete' if missing else 'complete',
                    'missing':len(missing), 'scheduled_missing':len(scheduled_missing),
                    'scheduled_items':len(scheduled), 'total_items':len(manifest['questions'])})
        if scheduled_missing: raise RuntimeError(f'{len(scheduled_missing)} evaluations failed; inspect failure.json and resume')
        (root/'blocked.json').unlink(missing_ok=True)
    except Exception as exc:
        atomic_json(root/'blocked.json', {'error':str(exc),'resolved_model':client.model})
        raise
    finally:
        await client.api.close()

async def main(args):
    import fcntl
    root = Path(args.results_dir)
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.runner.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another runner is using this results directory') from None
        await _main(args)


if __name__ == '__main__': asyncio.run(main(parser().parse_args()))
