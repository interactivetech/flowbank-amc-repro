import pytest
from amc_repro.client import Client, Settings
from amc_repro.storage import Trace


def test_decoding_metadata(monkeypatch):
    monkeypatch.setenv('OPENAI_BASE_URL','http://localhost:8000/v1')
    monkeypatch.setenv('OPENAI_API_KEY','mock-key')
    c=Client(Settings(thinking='off',max_tokens=123,seed=9))
    c.model='discovered-model'
    p=c.parameters()
    assert p['model']=='discovered-model'
    assert p['seed']==9
    assert p['max_tokens']==123
    assert p['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    c.settings.thinking='default'
    assert 'extra_body' not in c.parameters()

@pytest.mark.asyncio
async def test_auth_failure_not_retried(monkeypatch,tmp_path):
    import httpx2 as httpx
    from openai import AuthenticationError
    monkeypatch.setenv('OPENAI_BASE_URL','http://localhost:8000/v1')
    monkeypatch.setenv('OPENAI_API_KEY','mock-key')
    c=Client(Settings(requests_per_minute=100000))
    c.model='mock'
    attempts=[]
    async def fail(**kwargs):
        attempts.append(kwargs)
        raise AuthenticationError('bad key',response=httpx.Response(401,request=httpx.Request('POST','http://localhost')),body=None)
    monkeypatch.setattr(c.api.chat.completions,'create',fail)
    with pytest.raises(AuthenticationError):
        await c.call('p','s','Custom',Trace(tmp_path/'trace',{}))
    assert len(attempts)==1
    await c.api.close()


def test_deepseek_thinking_parameter(monkeypatch):
    monkeypatch.setenv('OPENAI_BASE_URL','http://localhost:8000/v1')
    monkeypatch.setenv('OPENAI_API_KEY','mock-key')
    c=Client(Settings(thinking='off'))
    c.model='deepseek-v4-flash'
    assert c.parameters()['extra_body']=={'thinking':{'type':'disabled'}}
