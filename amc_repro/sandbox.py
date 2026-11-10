"""Generated code runs only in a restricted container, never through host exec."""
import asyncio
import json
import subprocess
import uuid
from pathlib import Path

IMAGE = 'amc-repro-sandbox:1'
ROOT = Path(__file__).resolve().parents[1]
RESOLVED_IMAGE = None


def preflight():
    global RESOLVED_IMAGE
    subprocess.run(['docker','info'], check=True, capture_output=True, timeout=15)
    try:
        result = subprocess.run(['docker','image','inspect',IMAGE], check=True, capture_output=True,
                                text=True, timeout=15)
    except subprocess.CalledProcessError as exc:
        if 'No such image' not in (exc.stderr or ''):
            detail = (exc.stderr or '').strip()
            raise RuntimeError(f'Could not inspect sandbox image {IMAGE}: {detail}') from exc
        print(f'Sandbox image {IMAGE} is missing; building it now.', flush=True)
        subprocess.run(['docker','build','-f','Dockerfile.sandbox','-t',IMAGE,'.'],
                       check=True, cwd=ROOT, timeout=900)
        result = subprocess.run(['docker','image','inspect',IMAGE], check=True, capture_output=True,
                                text=True, timeout=15)
    info = json.loads(result.stdout)[0]
    RESOLVED_IMAGE = info['Id']
    return {'tag': IMAGE, 'image_id': info['Id'], 'repo_digests': info.get('RepoDigests', [])}


async def execute(code, timeout=20):
    if not RESOLVED_IMAGE:
        raise RuntimeError('Sandbox preflight must succeed before execution')
    name = 'amc-code-' + uuid.uuid4().hex
    # Code provided through stdin. No host paths, secrets, network, or Docker socket mounted.
    wrapper = ('import resource\nresource.setrlimit(resource.RLIMIT_CPU,(15,15))\n'
               'resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))\n'
               'import json,sys\ncode=json.loads(sys.stdin.read())\nns={}\nexec(code,ns)\n'
               'print("\\n__AMC_RESULT__" + str(ns["solve"]())[:32768])\n')
    args = ['docker','run','--rm','--name',name,'--network=none','--read-only',
            '--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=32',
            '--memory=512m','--memory-swap=512m','--cpus=1','--ulimit','nofile=64:64',
            '--log-driver=none','--tmpfs','/tmp:rw,noexec,nosuid,size=16m',
            '-i',RESOLVED_IMAGE,'python','-I','-c',wrapper]
    proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                                               stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    # Drain output while retaining only bounded prefixes to prevent host memory exhaustion.
    async def drain(stream):
        kept = bytearray()
        while chunk := await stream.read(8192):
            if len(kept) < 65536: kept.extend(chunk[:65536-len(kept)])
        return kept.decode(errors='replace')
    async def communicate():
        proc.stdin.write(json.dumps(code).encode())
        await proc.stdin.drain()
        proc.stdin.close()
        out, err = await asyncio.gather(drain(proc.stdout), drain(proc.stderr))
        await proc.wait()
        return out, err
    try:
        out, err = await asyncio.wait_for(communicate(), timeout)
        if proc.returncode == 0 and '__AMC_RESULT__' in out:
            return {'status':'Success','output':out.rsplit('__AMC_RESULT__',1)[1].strip(), 'stdout':out,'stderr':err}
        return {'status':'Error','output':err or out or f'exit {proc.returncode}', 'stdout':out,'stderr':err}
    except asyncio.TimeoutError:
        return {'status':'Error','output':'Code execution timed out'}
    finally:
        cleanup = await asyncio.create_subprocess_exec('docker','rm','-f',name,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await cleanup.wait()
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
