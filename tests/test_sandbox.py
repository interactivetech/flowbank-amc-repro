"""Optional real container integration tests (AM C_SANDBOX_TESTS=1)."""
import os
import pytest
from amc_repro.sandbox import execute, preflight

pytestmark = pytest.mark.skipif(os.getenv('AMC_SANDBOX_TESTS')!='1',reason='requires built Docker sandbox')

@pytest.mark.asyncio
async def test_real_execution_and_isolation():
    preflight()
    assert (await execute('def solve():\n    return 6*7'))['output']=='42'
    assert (await execute("def solve():\n    open('/blocked','w').write('x')\n    return 1"))['status']=='Error'
    result=await execute("def solve():\n    import socket\n    socket.create_connection(('example.com',80),timeout=1)\n    return 1")
    assert result['status']=='Error'
    assert (await execute('def solve():\n    while True: pass',timeout=1))['status']=='Error'
