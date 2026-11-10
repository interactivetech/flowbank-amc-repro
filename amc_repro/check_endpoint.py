import asyncio
import json
from pathlib import Path
from .client import Client, Settings
from .storage import Trace, atomic_json


async def main():
    path = Path('results/endpoint_check.json')
    client = Client(Settings())
    try:
        await client.discover()
        output = await client.call('Reply with exactly OK.', 'connection_test', 'ChatCompletion',
                                   Trace('results/endpoint_trace.jsonl', {}))
        result = {'status':'success', **client.metadata(), 'minimal_completion':output}
    except Exception as exc:
        result = {'status':'blocked', 'error':str(exc), 'model':client.model}
        atomic_json(path, result)
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    finally:
        await client.api.close()
    atomic_json(path, result)
    print(json.dumps(result, indent=2))

if __name__ == '__main__': asyncio.run(main())
