import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from amc_repro.client import Client, Settings
from amc_repro.storage import Trace
from amc_repro import run
from amc_repro.analyze import analyze


@pytest.mark.asyncio
async def test_reasoning_and_context_guard(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_BASE_URL','http://localhost:8000/v1')
    monkeypatch.setenv('OPENAI_API_KEY','fixture')
    client = Client(Settings())
    client.model='qwen3.8-27b-autoround-int4'
    raw = {'choices':[{'message':{'content':'42','reasoning':'private working'},'finish_reason':'stop'}],
           'usage':{'prompt_tokens':10,'completion_tokens':20}}
    response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='42'))],
                             model_dump=lambda **kw:raw)
    create=AsyncMock(return_value=response)
    monkeypatch.setattr(client.api.chat.completions,'create',create)
    assert await client.call('q','direct','Custom',Trace(tmp_path/'trace',{}))=='42'
    event=json.loads((tmp_path/'trace').read_text())
    assert event['reasoning']=='private working'
    assert event['usage']['completion_tokens']==20
    assert create.call_args.kwargs['max_tokens']==131072
    assert create.call_args.kwargs['extra_body']['chat_template_kwargs']['enable_thinking'] is True
    client.tokenizer=SimpleNamespace(apply_chat_template=lambda *a,**k:list(range(10)))
    client.context_length=131081
    with pytest.raises(ValueError,match='Context overflow'):
        await client.call('q','direct','Custom',Trace(tmp_path/'overflow',{}))
    assert create.call_count==1
    await client.api.close()


@pytest.mark.asyncio
async def test_pilot_full_resume_and_tables(monkeypatch,tmp_path):
    dataset=tmp_path/'dataset.jsonl'
    dataset.write_text('\n'.join(json.dumps({'problem':f'question {i}', 'solution':r'\boxed{42}'}) for i in range(4)))
    root=tmp_path/'results'
    calls=[]
    class FakeClient:
        def __init__(self,settings):
            self.settings=settings
            self.model='qwen3.8-27b-autoround-int4-fixture'
            self.api=SimpleNamespace(close=AsyncMock())
        async def discover(self): pass
        def parameters(self): return {'temperature':0,'top_p':1,'seed':42,'max_tokens':131072}
        def metadata(self): return {'model':self.model,'request_parameters':self.parameters()}
        async def call(self,prompt,stage,operator,trace):
            calls.append(stage)
            output = ('<solution_letter>A</solution_letter>' if operator=='ScEnsemble' else
                      'def solve():\n    return 42' if operator=='Programmer' else
                      'ALGEBRA' if stage=='classify' else r'\boxed{42}')
            trace.emit(event='llm_call',stage_id=stage,status='success',usage={'prompt_tokens':10,'completion_tokens':20})
            return output
    async def execute(code): return {'status':'Success','output':'42'}
    monkeypatch.setattr(run,'Client',FakeClient)
    monkeypatch.setattr(run,'preflight',lambda:{'backend':'fixture'})
    # Workflow's default argument is bound at definition time.
    Original=run.Workflow
    monkeypatch.setattr(run,'Workflow',lambda client,trace:Original(client,trace,execute))
    base=['--dataset',str(dataset),'--sample-size','4','--results-dir',str(root)]
    await run.main(run.parser().parse_args(base+['--limit-items','3']))
    frozen=(root/'manifest.json').read_bytes()
    assert len(json.loads(frozen)['questions'])==4
    assert len(calls)==51
    assert json.loads((root/'run_status.json').read_text())['missing']==5
    with pytest.raises(ValueError,match='Incomplete matrix'): analyze(root)
    pilot=analyze(root,3)
    assert pilot['sample_size']==3
    await run.main(run.parser().parse_args(base+['--resume']))
    assert (root/'manifest.json').read_bytes()==frozen
    assert len(calls)==68
    stats=analyze(root)
    assert stats['sample_size']==4
    assert stats['oracle_coverage']==1
    assert stats['token_usage']['W2']['mean_total']==150
    assert '| Oracle (W1–W4) | 4 | 100.0% | — | — |' in (root/'table2_portfolio.md').read_text()
    assert stats['unique_wins']['W1']==0
    await run.main(run.parser().parse_args(base+['--resume']))
    assert len(calls)==68
    with pytest.raises(ValueError,match='Resume config/source mismatch'):
        await run.main(run.parser().parse_args(base+['--resume','--max-tokens','100']))
    path=next(root.glob('evaluations/*/W2/result.json'))
    record=json.loads(path.read_text()); record['usage_complete']=False
    path.write_text(json.dumps(record))
    assert analyze(root)['token_usage']['W2']['mean_total']=='unavailable'


def test_prepare_pins_revision_and_checks_quantization(monkeypatch,tmp_path):
    from amc_repro import local_runtime as local
    import huggingface_hub
    monkeypatch.setenv('AMC_ROOT',str(tmp_path))
    snapshot=tmp_path/'snapshot'; snapshot.mkdir()
    config={'quantization_config':{'quant_method':'compressed-tensors',
            'config_groups':{'group_0':{'weights':{'num_bits':4}}}}}
    (snapshot/'config.json').write_text(json.dumps(config))
    api=SimpleNamespace(model_info=lambda model:SimpleNamespace(sha='a'*40))
    monkeypatch.setattr(huggingface_hub,'HfApi',lambda:api)
    downloads=[]
    def download(model,revision):
        downloads.append((model,revision))
        return str(snapshot)
    monkeypatch.setattr(huggingface_hub,'snapshot_download',download)
    local.prepare()
    lock=json.loads((tmp_path/'model.lock.json').read_text())
    assert lock['served_model'].endswith('a'*12)
    api.model_info=lambda model:pytest.fail('Existing revision must remain pinned')
    local.prepare()
    assert downloads==[(local.MODEL,'a'*40)]*2
    config['quantization_config']['config_groups']['group_0']['weights']['num_bits']=8
    (snapshot/'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError,match='4-bit'):
        local.prepare()


def test_serve_arguments_without_launching(monkeypatch,tmp_path):
    from amc_repro import local_runtime as local
    from unittest.mock import MagicMock
    import socket
    monkeypatch.setenv('AMC_ROOT',str(tmp_path))
    monkeypatch.setenv('SLURM_JOB_ID','fixture')
    lock={'repository':local.MODEL,'revision':'a'*40,'served_model':'fixture-id',
          'snapshot':str(tmp_path/'model'),'quantization':{'quant_method':'compressed-tensors'}}
    (tmp_path/'model.lock.json').write_text(json.dumps(lock))
    sock=MagicMock(); sock.__enter__.return_value.connect_ex.return_value=1
    monkeypatch.setattr(socket,'socket',lambda *a:sock)
    monkeypatch.setattr(local.os,'setsid',lambda:None)
    captured=[]
    def execv(executable,args):
        captured.extend(args)
        raise SystemExit(0)
    monkeypatch.setattr(local.os,'execv',execv)
    with pytest.raises(SystemExit): local.serve()
    assert captured[captured.index('--quantization')+1]=='compressed-tensors'
    assert captured[captured.index('--max-model-len')+1]=='262144'
    assert captured[captured.index('--reasoning-parser')+1]=='qwen3'
    assert '--speculative-config' not in captured
    assert local.configure_client()['model']==lock
    lock['revision']='b'*40
    (tmp_path/'model.lock.json').write_text(json.dumps(lock))
    with pytest.raises(ValueError,match='lock mismatch'): local.identity()
