import json
from pathlib import Path
import pytest
from amc_repro.grading import grade, extract
from amc_repro.storage import Trace, dataset_manifest, atomic_json
from amc_repro.workflows import Workflow
from amc_repro.run import CachedClient
from amc_repro.analyze import statistics, CONDITIONS

@pytest.mark.parametrize('response,gold',[
    (r'\boxed{\frac{1}{2}}','0.5'), ('42','42'),
    (r'\boxed{(x+1)^2}',r'x^2+2x+1'),
    (r'earlier \boxed{2} final \boxed{\frac{3}{4}}',r'\frac{3}{4}'),
    ('Code:\ndef solve(): return 2\nOutput: 3','3'),
])
def test_grade(response,gold):
    assert grade(response,gold)['correct']

@pytest.mark.parametrize('text',['', 'I do not know.','Reasoning has 42\nbut no answer',r'\boxed{\frac{1}{2}', 'Code:\n# boxed{42}\nOutput: failure'])
def test_malformed(text):
    result=grade(text,'42')
    assert not result['correct']
    assert result['grading_status']=='parse_failure'


def test_wrong():
    assert grade(r'\boxed{3}','4')['grading_status']=='math_error'

class Mock:
    def __init__(self,outputs): self.outputs=iter(outputs); self.calls=[]
    async def call(self,prompt,stage,operator,trace):
        self.calls.append((prompt,stage,operator))
        return next(self.outputs)


@pytest.mark.asyncio
@pytest.mark.parametrize('w',['W1','W2','W3'])
async def test_graphs(tmp_path,w):
    outputs=[r'\boxed{1}',r'\boxed{2}',r'\boxed{1}', '<thought>pick B</thought><solution_letter>B</solution_letter>']
    if w!='W1': outputs += ['def solve():\n    return 9']
    mock=Mock(outputs)
    async def executor(code): return {'status':'Success','output':'9'}
    graph=Workflow(mock,Trace(tmp_path/'trace',{}),executor)
    final=await graph.run(w,'QUESTION_ONLY')
    assert graph.selected==1
    assert mock.calls[3][2]=='ScEnsemble' # an actual additional model call
    assert final==(r'\boxed{2}' if w=='W1' else 'Code:\ndef solve():\n    return 9\nOutput: 9')
    assert len(mock.calls)==(4 if w=='W1' else 5)
    assert all('QUESTION_ONLY' in c[0] for c in mock.calls)
    if w=='W2': assert mock.calls[0][0]==mock.calls[1][0]==mock.calls[2][0]
    else: assert len({c[0] for c in mock.calls[:3]})==3

@pytest.mark.asyncio
async def test_programmer_retry_only_execution(tmp_path):
    outputs=['1','2','3','<solution_letter>A</solution_letter>','def solve():\n    return 1','def solve():\n    return 2']
    executions=iter([{'status':'Error','output':'bad execution'}, {'status':'Success','output':'2'}])
    async def executor(code): return next(executions)
    mock=Mock(outputs)
    result=await Workflow(mock,Trace(tmp_path/'trace',{}),executor).run('W2','q')
    assert result.endswith('Output: 2')
    assert 'bad execution' in mock.calls[-1][0]

@pytest.mark.asyncio
@pytest.mark.parametrize('category,route',[('GEOMETRY','GEOMETRY'),('COMBINATORICS','COMBINATORICS'),('NUMBER_THEORY','NUMBER_THEORY'),('unknown','ALGEBRA')])
async def test_route(tmp_path,category,route):
    mock=Mock([category,'7'])
    graph=Workflow(mock,Trace(tmp_path/'trace',{}))
    assert await graph.run('W4','q')=='7'
    assert graph.category==route
    assert len(mock.calls)==2

@pytest.mark.asyncio
async def test_baseline_and_invalid_selection(tmp_path):
    mock=Mock(['7'])
    assert await Workflow(mock,Trace(tmp_path/'t',{})).run('baseline','q')=='7'
    assert len(mock.calls)==1
    with pytest.raises(ValueError,match='ScEnsemble'):
        await Workflow(Mock(['1','2','3','B']),Trace(tmp_path/'u',{})).run('W1','q')

@pytest.mark.asyncio
async def test_resume_call_cache(tmp_path):
    mock=Mock(['answer'])
    client=CachedClient(mock,tmp_path/'calls')
    trace=Trace(tmp_path/'trace',{})
    assert await client.call('p','s','Custom',trace)=='answer'
    assert await client.call('p','s','Custom',trace)=='answer'
    assert len(mock.calls)==1
    with pytest.raises(ValueError): await client.call('different','s','Custom',trace)


def test_manifest():
    a=dataset_manifest('datasets/amc_test.jsonl',3,42)
    b=dataset_manifest('datasets/amc_test.jsonl',50,42)
    assert [q['question_id'] for q in a['questions']]==[q['question_id'] for q in b['questions'][:3]]
    assert len({q['question_id'] for q in b['questions']})==50


def test_oracle():
    results={(q,w):{'correct': (q,w) in {('a','W1'),('b','W2'),('a','baseline')},'status':'completed','grading_status':'correct'}
             for q in ['a','b','c'] for w in CONDITIONS}
    stats=statistics(results,['a','b','c'])
    assert stats['oracle_coverage']==2/3
    assert stats['complementarity_gain']==1/3
    assert stats['unique_wins']['W1']==1
    assert stats['unsolved_count']==1
    del results['a','W4']
    with pytest.raises(ValueError): statistics(results,['a','b','c'])


def test_offline_analysis_artifacts(tmp_path):
    from amc_repro.analyze import analyze
    atomic_json(tmp_path/'manifest.json',{'questions':[{'question_id':'a'},{'question_id':'b'}]})
    atomic_json(tmp_path/'metadata.json',{'model':'mock-model','request_parameters':{'temperature':0,'top_p':1,'max_tokens':4096}})
    for q in ['a','b']:
        for w in CONDITIONS:
            folder=tmp_path/'evaluations'/q/w
            atomic_json(folder/'result.json',{'question_id':q,'workflow_id':w,'correct':w==('W1' if q=='a' else 'W2'),
                'status':'completed','grading_status':'correct','usage_complete':True,
                'prompt_tokens':10,'completion_tokens':20,'llm_calls':4})
            (folder/'trace.jsonl').write_text('{}\n')
    stats=analyze(tmp_path)
    assert stats['oracle_coverage']==1
    assert (tmp_path/'table2_portfolio.tex').exists()
    assert (tmp_path/'correctness_matrix.csv').read_text().count('\n')==3
    assert json.loads((tmp_path/'summary.json').read_text())['unique_wins']['W2']==1
