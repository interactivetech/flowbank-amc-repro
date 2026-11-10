"""AMC prompts transcribed from Appendix D.1; operator prompts copied verbatim."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Read string literals without importing/executing upstream Python.
_tree = ast.parse((ROOT / 'vendor/FlowBank/DiverseFlow/scripts/prompts/prompt.py').read_text())
_original = {n.targets[0].id: ast.literal_eval(n.value) for n in _tree.body
             if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)}
SC_ENSEMBLE_PROMPT = _original['SC_ENSEMBLE_PROMPT']
PYTHON_CODE_VERIFIER_PROMPT = _original['PYTHON_CODE_VERIFIER_PROMPT']
XML_SUFFIX = '\n# Response format (must be strictly followed) (do not include any other formats except for the given XML format):\n<thought>The thought of the most consistent solution.</thought>\n<solution_letter>The letter of most consistent solution.</solution_letter>'
CODE_SUFFIX = ("\n\nPlease write your code solution in Python. Return ONLY the complete, runnable code without explanations. Use proper Python syntax and formatting. "
               "\nMake sure to include a function named 'solve' in your solution. This function will be the entry point for the program.")
BASE = 'You are a math problem solver. Please solve the following problem step by step, showing all your work and providing a final answer in a box.'
GENERAL = '\n' + BASE + '\n\nProblem:\n{problem}\n\nSolution:\n'
ANALYTICAL = '\n' + BASE + ' Focus on breaking down the problem into smaller parts and analyze each part carefully.\n\nProblem:\n{problem}\n\nSolution:\n'
VERBOSE = '\n' + BASE + ' Be as detailed as possible in your explanation, and make sure to explain the reasoning behind each step.\n\nProblem:\n{problem}\n\nSolution:\n'
ANALYTICAL_W2 = ANALYTICAL.replace('carefully.', 'carefully. Make sure to explain your reasoning and avoid assumptions.')
DIVERSE = [BASE + ' Focus on logical reasoning and clarity.', BASE + ' Be thorough and explain your thought process.', BASE + ' Make sure your solution is concise and well-structured.']
CLASSIFY = '''Analyze this math problem and classify it into exactly one category. Output ONLY the category name, nothing else.

Categories:
- ALGEBRA: equations, inequalities, functions, polynomials, sequences
- GEOMETRY: shapes, angles, areas, volumes, coordinate geometry
- COMBINATORICS: counting, probability, permutations, combinations
- NUMBER_THEORY: divisibility, primes, modular arithmetic, digits
'''
SPECIALISTS = {
'ALGEBRA': '''You are an algebra specialist. Solve this problem using algebraic techniques:
- Set up equations from the problem conditions
- Solve systematically (substitution, elimination, factoring)
- Check your answer satisfies all original conditions

Put your final answer in \\boxed{{}}.
''',
'GEOMETRY': '''You are a geometry specialist. Solve this problem using geometric reasoning:
- Draw a mental picture and label key points/lengths/angles
- Apply relevant theorems (Pythagorean, similar triangles, circle properties)
- Use coordinate geometry if the problem involves positions

Put your final answer in \\boxed{{}}.
''',
'COMBINATORICS': '''You are a combinatorics specialist. Solve this problem using counting techniques:
- Identify what is being counted or the probability space
- Choose the right technique: multiplication principle, combinations, inclusion-exclusion, complementary counting
- Double-check by considering small cases if possible

Put your final answer in \\boxed{{}}.
''',
'NUMBER_THEORY': '''You are a number theory specialist. Solve this problem using number-theoretic techniques:
- Consider divisibility rules, prime factorizations, modular arithmetic
- Look for patterns in small cases
- Apply relevant theorems (CRT, Fermat's little theorem, etc.)

Put your final answer in \\boxed{{}}.
'''}

def custom(instruction, problem):
    if '{problem}' in instruction or '{input}' in instruction:
        return instruction.replace('{problem}', problem).replace('{input}', problem)
    return instruction + problem
