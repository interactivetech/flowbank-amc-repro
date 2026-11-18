"""Frozen screened DeepMath input and offline reference preflight. No model calls."""
import argparse
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from .storage import atomic_json
from .grading import grade_typed, parsed, normalize_math

REPOSITORY = 'mendeza-umd/deepmath-103k-qwen-3-8-27b-results'
REVISION = 'e723e4604d862e25fa2c57313a7c37494a674c03'
FILENAME = 'deepmath_completed_questions.csv'
SHA256 = 'd3f12abe7a287a8caa2f76d0136e9fe8b63e9e0d9d65cf0c1624b4993b6728c7'
PILOT = (45570, 3226, 791, 1659, 96)
THRESHOLDS = (1, .75, .5, .25, 0)
COUNTS = (26, 14, 11, 8, 5)
# Logged before inference; references and historical rates are never corrected here.
REFERENCE_NOTES = {
    8166: 'Underdetermined: symmetric matrices satisfying the polynomial can have different multiplicities of the two allowed eigenvalues. Keep supplied reference.',
    1659: 'Derivative reference omits the point at which the function is undefined. Grade the supplied final expression only.',
    12891: 'Proof task reduced to a numeric limit reference; final-answer grading does not assess proof validity.',
    23558: 'Geometric construction wording may be ambiguous. Keep supplied reference.',
    45570: 'Justification requested; categorical grading assesses the final yes/no only.',
}


def require_scratch(path):
    p = Path(path).absolute()
    # Check both the requested location and its resolved target (including symlinks).
    for candidate in (p, p.resolve()):
        if len(candidate.parts) < 3 or not re.fullmatch(r'scratch\d*', candidate.parts[1]):
            raise ValueError('Private DeepMath data/results must be stored on scratch')
    return p


def options(question):
    text = question.replace(r'\n', '\n')
    markers = list(re.finditer(r'\(([A-Ea-e])\)|^([A-E])\.', text, re.M))
    result = {}
    for i, m in enumerate(markers):
        letter = (m.group(1) or m.group(2)).upper()
        value = text[m.end():markers[i+1].start() if i+1 < len(markers) else len(text)].strip()
        # Inline options can sit inside a single math delimiter and a text macro.
        value = re.sub(r'^\s*\}?\s*', '', value)
        value = value.strip().rstrip(' .,')
        value = re.sub(r'\s*\\\)\s*[,\.]?\s*$', '', value)
        value = re.sub(r'^\\\(\s*|^\$|\$$', '', value).strip()
        value = re.sub(r'\\\)\s*,?\s*\\\(\\text\{\s*$', '', value).strip()
        result[letter] = value
    return result


def typed_reference(row):
    gold = row['gold_answer']
    number = int(row['dataset_row'])
    if gold.upper() in 'ABCDE' and len(gold) == 1:
        mapping = options(row['question'])
        if gold not in mapping or len(mapping) < 4:
            raise ValueError(f'Cannot freeze options at row {number}')
        return {'kind':'choice', 'gold':gold, 'options':mapping}
    if gold.lower() in ('yes', 'no'):
        return {'kind':'boolean', 'gold':gold}
    return {'kind':'complex' if number == 503 else 'math', 'gold':gold}


def manifest(path):
    path = require_scratch(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('DeepMath source hash differs from approved pinned CSV')
    rows = list(csv.DictReader(io.StringIO(raw.decode(), newline="")))
    questions = []
    seen = set()
    for index, row in enumerate(rows):
        number = int(row['dataset_row'])
        if number in seen: raise ValueError('Duplicate DeepMath ID')
        seen.add(number)
        count, responses, rate = int(row['correct']), int(row['responses']), float(row['solve_rate'])
        if responses != 32 or not 0 <= count <= responses or not math.isclose(count/responses, rate, abs_tol=1e-12):
            raise ValueError(f'Invalid screening counts at row {number}')
        reference = typed_reference(row)
        questions.append({'question_id':f'deepmath-row-{number}', 'row_index':index,
            'dataset_row':number, 'row':row, 'gold_answer':row['gold_answer'],
            'reference':reference, 'screening':{'correct':count,'responses':responses,'solve_rate':rate},
            'reference_note':REFERENCE_NOTES.get(number)})
    if len(questions) != 26 or not set(PILOT) <= seen: raise ValueError('Expected all 26 approved rows')
    questions.sort(key=lambda q: (0, PILOT.index(q['dataset_row'])) if q['dataset_row'] in PILOT else (1,q['dataset_row']))
    cohorts = {str(t):[q['question_id'] for q in questions if q['screening']['solve_rate'] <= t] for t in THRESHOLDS}
    if [len(cohorts[str(t)]) for t in THRESHOLDS] != list(COUNTS): raise ValueError('Unexpected threshold membership')
    return {'dataset_format':'deepmath-screened','repository':REPOSITORY,'revision':REVISION,
        'source_filename':FILENAME,'dataset_sha256':SHA256,'dataset_rows':26,'sample_size':26,
        'questions':questions,'cohorts':cohorts, 'reference_policy':'Supplied labels retained; notes frozen before inference'}


def preflight(frozen):
    if frozen.get('dataset_format') == 'deepmath-screened-v2':
        from .screening import preflight_reference
        for q in frozen['questions']: preflight_reference(q['reference'])
        return {'status':'passed', 'items':len(frozen['questions'])}
    checks = []
    for q in frozen['questions']:
        ref = q['reference']
        gold = ref['gold']
        cases = [(gold, True), (r'\boxed{' + gold + '}', True), ('not a final expression', False)]
        if ref['kind'] == 'choice':
            expression = ref['options'][gold]
            if not parsed(normalize_math(expression)):
                raise ValueError(f"Unparseable correct option: {q['question_id']}")
            cases += [(expression, True), (f'Option {gold}', True)]
            cases += [(letter, letter == gold) for letter in ref['options']]
            cases += [(expr, letter == gold) for letter,expr in ref['options'].items()]
            cases.append(('(' + expression + ')', True))
        elif ref['kind'] == 'boolean':
            cases += [('Code:\ndef solve(): return True\nOutput: True', True), ('No', False), ('False', False),
                      (r'\boxed{\text{Yes, } a justification follows.}', True),
                      (r'\boxed{\text{No, } a justification follows.}', False)]
        else:
            value = normalize_math(gold, ref['kind'] == 'complex')
            cases += [(value, True), (r'\frac{987654321}{17}', False)]
            # Derive equivalent forms without embedding private reference values in code.
            if ref['kind'] == 'complex':
                cases.append((value.replace('I','j'), True))
            elif r'\pm' in value:
                magnitude = value.replace(r'\pm','').strip()
                cases.append((r'\{' + '-' + magnitude + ',' + magnitude + r'\}', True))
            else:
                cases.append(('(' + value + ')', True))
                if r'\circ' in gold or '°' in gold:
                    cases.append((r'\frac{(' + value + r')\pi}{180}', True))
        for response, expected in cases:
            actual = grade_typed(response, ref)
            checks.append({'question_id':q['question_id'],'response':response,'expected':expected,**actual})
            if actual['correct'] != expected:
                raise ValueError(f"Reference preflight failed: {q['question_id']} {response!r}: {actual}")
    return {'status':'passed', 'items':26,'checks':checks,
            'reference_notes':{q['question_id']:q['reference_note'] for q in frozen['questions'] if q['reference_note']}}


def load_frozen(path):
    path = require_scratch(path)
    saved = json.loads(path.read_text())
    if saved.get('dataset_format') == 'deepmath-screened-v2':
        from .screening import digest, accepted, results, preflight_reference
        evidence_root = require_scratch(saved.get('screening_run',path.parent))
        lock = json.loads((evidence_root/'lock.json').read_text())
        audit = json.loads((evidence_root/'audit.json').read_text())
        if digest(saved) != lock['manifest_sha256'] or digest(audit) != lock['audit_sha256']:
            raise ValueError('Locked screening manifest or audit mismatch')
        if saved['sample_size'] != len(saved['questions']):
            raise ValueError('Manifest size mismatch')
        for q in saved['questions']:
            preflight_reference(q['reference'])
            if not accepted(q, results(evidence_root,q), audit.get(q['question_id'],{})):
                raise ValueError('Audit evidence mismatch')
        return saved
    source = path.parent/FILENAME
    expected = manifest(source)
    if saved != expected: raise ValueError('Frozen manifest mismatch')
    preflight(saved)
    return saved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    output = require_scratch(args.output_dir)
    frozen = manifest(args.source)
    report = preflight(frozen)
    output.mkdir(parents=True, exist_ok=True)
    target = output/'manifest.json'
    if target.exists() and json.loads(target.read_text()) != frozen: raise ValueError('Refusing to replace frozen manifest')
    source = output/FILENAME
    if source.exists() and source.read_bytes() != args.source.read_bytes(): raise ValueError('Frozen CSV mismatch')
    source.write_bytes(args.source.read_bytes())
    atomic_json(target, frozen)
    atomic_json(output/'reference_preflight.json', report)
    print(f'Frozen 26 items; {len(report["checks"])} reference checks passed. No model calls.')

if __name__ == '__main__': main()
