import ast
import re
from . import prompts as p
from .sandbox import execute


class Workflow:
    def __init__(self, client, trace, executor=execute):
        self.client, self.trace, self.execute = client, trace, executor
        self.candidates = []
        self.selected = None
        self.category = None

    async def call(self, prompt, stage, operator='Custom'):
        return await self.client.call(prompt, stage, operator, self.trace)

    async def run(self, workflow, problem):
        if workflow == 'baseline':
            return await self.call(p.custom(p.GENERAL, problem), 'direct')
        if workflow == 'W4':
            category = (await self.call(p.custom(p.CLASSIFY, problem), 'classify')).strip().upper()
            self.category = ('GEOMETRY' if 'GEOMETRY' in category else 'COMBINATORICS' if 'COMBINATORICS' in category
                             else 'NUMBER_THEORY' if 'NUMBER' in category else 'ALGEBRA')
            self.trace.emit(event='routing', stage_id='route', classification=category, selected_solver=self.category)
            return await self.call(p.custom(p.SPECIALISTS[self.category], problem), 'specialist')
        if workflow not in ['W1','W2','W3']: raise ValueError(workflow)
        prompts = {'W1':[p.GENERAL,p.ANALYTICAL,p.VERBOSE], 'W2':[p.ANALYTICAL_W2]*3, 'W3':p.DIVERSE}[workflow]
        for i, prompt in enumerate(prompts):
            output = await self.call(p.custom(prompt, problem), f'candidate_{i}')
            self.candidates.append(output)
            self.trace.emit(event='candidate', stage_id=f'candidate_{i}', candidate_id=chr(65+i), output=output)
        solution_text = ''.join(f'{chr(65+i)}: \n{s}\n\n\n' for i,s in enumerate(self.candidates))
        prompt = p.SC_ENSEMBLE_PROMPT.format(question=problem, solutions=solution_text) + p.XML_SUFFIX
        selection = await self.call(prompt, 'ensemble', 'ScEnsemble')
        match = re.search(r'<solution_letter>(.*?)</solution_letter>', selection, re.S)
        letter = match.group(1).strip().upper() if match else ''
        if letter not in ['A','B','C']:
            raise ValueError('ScEnsemble parsing failure: invalid solution_letter')
        self.selected = ord(letter)-65
        best = self.candidates[self.selected]
        self.trace.emit(event='selection', stage_id='ensemble', selected_candidate_id=letter, selected_solution=best)
        if workflow == 'W1': return best
        feedback = ''
        for i in range(3):
            raw = await self.call(p.PYTHON_CODE_VERIFIER_PROMPT.format(problem=problem, analysis=best, feedback=feedback)
                                  + p.CODE_SUFFIX, f'programmer_{i}', 'Programmer')
            blocks = re.findall(r'```python\s*([\s\S]*?)\s*```', raw) or re.findall(r'```\s*([\s\S]*?)\s*```', raw)
            code = '\n\n'.join(blocks) if blocks else raw
            try:
                tree = ast.parse(code)
                if not any(isinstance(n, (ast.FunctionDef,ast.AsyncFunctionDef)) and n.name == 'solve' for n in tree.body):
                    raise ValueError('Function solve not found')
                execution = await self.execute(code)
            except (SyntaxError,ValueError) as exc:
                execution = {'status':'Error','output':str(exc)}
            self.trace.emit(event='code_execution', stage_id=f'programmer_{i}', operator_type='Programmer',
                            code=code, retry=i, **execution)
            output = execution['output']
            if execution['status'] == 'Success': break
            feedback = (f'\nThe result of the error from the code you wrote in the previous round:\n'
                        f'Code: {code}\n\nStatus: Error, {output}')
        return f'Code:\n{code}\nOutput: {output}'
