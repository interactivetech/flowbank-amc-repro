"""Resource-limited subprocess execution; this is not a filesystem sandbox."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile

RESOLVED_EXECUTOR = None
WRAPPER = '''import resource
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_AS, (2147483648, 2147483648))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
import json, sys
code = json.loads(sys.stdin.read())
ns = {}
exec(code, ns)
print("\\n__AMC_RESULT__" + str(ns["solve"]())[:32768])
'''


def executor_python():
    return str(Path(os.environ.get('AMC_EXECUTOR_PYTHON',
        '/scratch1/mendeza/flowbank-amc/executor/bin/python')).absolute())


def preflight():
    global RESOLVED_EXECUTOR
    python = executor_python()
    check = subprocess.run([python, '-I', '-c',
        'import sys,json,importlib.metadata as m; import sympy,numpy,scipy; '
        'print(json.dumps({"python":sys.version,"packages":{p:m.version(p) for p in ["sympy","numpy","scipy"]}}))'],
        check=True, capture_output=True, text=True, timeout=30)
    RESOLVED_EXECUTOR = python
    return {'backend':'python-subprocess', 'executable':python,
            'runtime':json.loads(check.stdout),
            'python_sha256':hashlib.sha256(Path(python).read_bytes()).hexdigest(),
            'wrapper_sha256':hashlib.sha256(WRAPPER.encode()).hexdigest(),
            'limits':{'wall_seconds':20,'cpu_seconds':15,'memory_bytes':2147483648,
                      'output_bytes_per_stream':65536},
            'filesystem_isolation':False}


async def execute(code, timeout=20):
    if not RESOLVED_EXECUTOR:
        raise RuntimeError('Executor preflight must succeed before execution')
    temp_root = Path(os.environ.get('AMC_TMPDIR', '/scratch1/mendeza/flowbank-amc/tmp'))
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='amc-code-', dir=temp_root) as work:
        env = {'PATH':str(Path(RESOLVED_EXECUTOR).parent) + ':/usr/bin:/bin',
               'HOME':work, 'TMPDIR':work, 'OPENBLAS_NUM_THREADS':'1',
               'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1', 'PYTHONHASHSEED':'42'}
        proc = await asyncio.create_subprocess_exec(RESOLVED_EXECUTOR, '-I', '-c', WRAPPER,
            cwd=work, env=env, start_new_session=True, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        async def drain(stream):
            kept = bytearray()
            while chunk := await stream.read(8192):
                kept.extend(chunk[:max(0, 65536-len(kept))])
            return kept.decode(errors='replace')

        async def send():
            try:
                proc.stdin.write(json.dumps(code).encode())
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                proc.stdin.close()

        tasks = [asyncio.create_task(send()), asyncio.create_task(drain(proc.stdout)),
                 asyncio.create_task(drain(proc.stderr))]
        async def exited():
            # asyncio's wait() can wait for inherited pipes after the parent exits.
            while proc.returncode is None:
                await asyncio.sleep(0.01)

        try:
            await asyncio.wait_for(exited(), timeout)
            # Terminate any descendants before waiting for their inherited pipes.
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            _, out, err = await asyncio.gather(*tasks)
            if proc.returncode == 0 and '__AMC_RESULT__' in out:
                return {'status':'Success', 'output':out.rsplit('__AMC_RESULT__',1)[1].strip(),
                        'stdout':out, 'stderr':err}
            return {'status':'Error','output':err or out or f'exit {proc.returncode}',
                    'stdout':out,'stderr':err}
        except asyncio.TimeoutError:
            return {'status':'Error','output':'Code execution timed out'}
        finally:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            await proc.wait()
            await asyncio.gather(*tasks, return_exceptions=True)
