"""Explicit user-invoked check; never launched by setup or tests."""
import argparse
import asyncio
import json
from pathlib import Path
from .client import Client, Settings
from .storage import Trace, atomic_json


async def main(args):
    runtime = None
    if args.local_runtime:
        from .local_runtime import configure_client
        runtime = configure_client()
    root = Path(args.results_dir)
    trace_path = root/'endpoint_trace.jsonl'
    client = Client(Settings())
    try:
        await client.discover()
        if runtime:
            models = client.models['data']
            model = next(m for m in models if m['id'] == client.model)
            if model.get('max_model_len') != runtime['context_length']:
                raise ValueError('Server context length does not match serving metadata')
        output = await client.call(
            'Compute the sum of integers from 1 to 100. Think through the calculation and give the final answer.',
            'connection_test', 'ChatCompletion', Trace(trace_path, {}))
        event = json.loads(trace_path.read_text().splitlines()[-1])
        if not output.strip() or event.get('finish_reason') == 'length':
            raise ValueError('Endpoint returned no complete final answer')
        if runtime and not event.get('reasoning'):
            raise ValueError('No separated reasoning was returned; inspect Qwen reasoning parser')
        usage = event.get('usage') or {}
        if usage.get('prompt_tokens') is None or usage.get('completion_tokens') is None:
            raise ValueError('Endpoint did not return complete token usage')
        result = {'status':'success', **client.metadata(), 'local_runtime':runtime,
                  'completion':output, 'cap_accepted':client.settings.max_tokens,
                  'reasoning_present':bool(event.get('reasoning'))}
    except Exception as exc:
        atomic_json(root/'endpoint_check.json', {'status':'blocked','error':str(exc),'model':client.model})
        raise
    finally:
        await client.api.close()
    atomic_json(root/'endpoint_check.json',result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-runtime',action='store_true')
    parser.add_argument('--results-dir',default='results/endpoint')
    asyncio.run(main(parser.parse_args()))
