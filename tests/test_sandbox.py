"""Local executor tests; no containers, GPU, model, or external API needed."""
import asyncio
import os
from pathlib import Path
import sys
import pytest
from amc_repro import sandbox


@pytest.fixture(autouse=True)
def executor(monkeypatch,tmp_path):
    monkeypatch.setattr(sandbox,'RESOLVED_EXECUTOR',sys.executable)
    monkeypatch.setenv('AMC_TMPDIR',str(tmp_path))


@pytest.mark.asyncio
async def test_execution_and_minimal_environment(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','secret-fixture')
    result = await sandbox.execute('def solve():\n    import os\n    assert "OPENAI_API_KEY" not in os.environ\n    return 6*7')
    assert result['status']=='Success'
    assert result['output']=='42'


@pytest.mark.asyncio
async def test_errors_limits_output_and_cleanup(tmp_path):
    assert (await sandbox.execute('def solve():\n    raise RuntimeError("fixture")'))['status']=='Error'
    assert (await sandbox.execute('def solve():\n    while True: pass',timeout=.2))['status']=='Error'
    limited = await sandbox.execute('def solve():\n    return bytearray(3*1024**3)')
    assert limited['status']=='Error'
    bounded = await sandbox.execute('def solve():\n    print("x"*200000)\n    return 42')
    assert len(bounded['stdout']) <= 65536
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_descendants_terminated(tmp_path):
    pidfile=tmp_path/'child.pid'
    code = f'''def solve():
    import subprocess,sys
    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    open({str(pidfile)!r}, 'w').write(str(p.pid))
    return 1
'''
    result = await asyncio.wait_for(sandbox.execute(code),5)
    assert result['status']=='Success'
    pid = int(pidfile.read_text())
    state = Path(f'/proc/{pid}/stat')
    assert not state.exists() or state.read_text().split()[2]=='Z'
