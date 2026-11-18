"""Deterministic final-answer extraction; no model judge or answer-dependent retries."""
import re
from math_verify import parse, verify, LatexExtractionConfig, ExprExtractionConfig


def boxed(text):
    answers = []
    for match in re.finditer(r'\\(?:boxed|fbox)\s*\{', text):
        start, depth = match.end(), 1
        for i in range(start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            if depth == 0:
                answers.append(text[start:i].strip())
                break
    return answers


def extract(text, gold=False):
    # Programmer output must take precedence over boxes inside generated code.
    if text.startswith('Code:\n') and '\nOutput: ' in text:
        text = text.rsplit('\nOutput: ', 1)[1].strip()
    boxes = boxed(text)
    if boxes:
        return boxes[-1]
    if '\\boxed' in text or '\\fbox' in text:
        return None  # malformed box, never rescue an unrelated earlier number
    if gold:
        # Official AMC solutions begin with Answer: $(D) ...$ then a derivation.
        m = re.match(r'\s*Answer:\s*\$\s*\(?[A-E]\)?\s*(.*?)\$', text, re.S)
        if m:
            return m.group(1).strip()
    m = re.search(r'(?:final answer|answer)\s*(?:is|:|=)\s*(.+?)(?:\n|$)', text, re.I)
    if m:
        return m.group(1).strip().rstrip('.')
    # Only accept a plain single-line expression, not numbers inside a derivation.
    text = text.strip()
    if '\n' not in text and len(text) < 250:
        return text
    return None


def parsed(answer):
    if not answer:
        return []
    if re.fullmatch(r'[A-Za-z]{2,}', answer.strip()):
        return []
    return parse('$' + answer.strip('$') + '$', extraction_config=[LatexExtractionConfig(), ExprExtractionConfig()], fallback_mode='no_fallback')


def grade(response, gold_answer):
    answer = extract(response)
    prediction, reference = parsed(answer), parsed(gold_answer)
    if not reference:
        raise ValueError('Unparseable ground truth: ' + str(gold_answer))
    ok = bool(prediction) and bool(verify(reference, prediction))
    return {'extracted_answer': answer, 'correct': ok,
            'grading_status': 'correct' if ok else ('math_error' if prediction else 'parse_failure')}


def normalize_math(answer, imaginary=False):
    """Dataset-specific normalization, leaving the AMC grading path unchanged."""
    value = (answer or '').strip().strip('$')
    value = value.replace(r'\(', '').replace(r'\)', '')
    value = value.replace('°', '').replace(r'^\circ', '').replace(r'^{\circ}', '')
    value = re.sub(r'\s*(?:degrees?|deg)\s*$', '', value, flags=re.I)
    value = value.replace('-oo', r'-\infty').replace('+oo', r'\infty')
    if imaginary:
        value = value.replace(r'\mathrm{i}', 'I').replace(r'\mathbf{i}', 'I')
        value = re.sub(r'(?<![A-Za-z])[ij](?![A-Za-z])', 'I', value)
        value = re.sub(r'(\d)I', r'\1*I', value)
    return value


def grade_typed(response, reference):
    kind = reference['kind']
    answer = extract(response)
    value = (answer or '').strip().strip('$').strip()
    def result(ok, valid):
        return {'extracted_answer':answer,'correct':bool(ok),
                'grading_status':'correct' if ok else ('math_error' if valid else 'parse_failure')}
    if kind == 'boolean':
        # The extracted final answer can include a justification after the label.
        match = re.match(r'^(?:\\text\{\s*)?(yes|no|true|false)(?=$|[\s,.;!:}])', value, re.I)
        if not match: return result(False, False)
        prediction = match.group(1).lower() in ('yes','true')
        return result(prediction == (reference['gold'].lower() in ('yes','true')), True)
    if kind == 'choice':
        match = re.fullmatch(r'(?:\\text\{)?(?:option\s+)?\(?([A-E])\)?(?:\})?[.)]?', value, re.I)
        if match: return result(match.group(1).upper() == reference['gold'], True)
        # Explicit letter followed by its expression: require both to agree.
        match = re.fullmatch(r'\(?([A-E])\)?\s*[.:]\s*(.+)', value, re.I)
        if match:
            if match.group(1).upper() != reference['gold']: return result(False, True)
            value = match.group(2)
        gold = reference['options'][reference['gold']]
    else:
        gold = reference['gold']
    prediction_text = normalize_math(value, kind == 'complex')
    gold_text = normalize_math(gold, kind == 'complex')
    angle = any(unit in gold for unit in (r'\circ', '°'))
    radians = angle and (r'\pi' in prediction_text or re.search(r'\b(?:pi|radians?|rad)\b', prediction_text))
    if radians:
        prediction_text = re.sub(r'\\text\{\s*(?:radians?|rad)\s*\}', '', prediction_text)
        prediction_text = re.sub(r'\b(?:radians?|rad)\b', '', prediction_text).strip()
    prediction, target = parsed(prediction_text), parsed(gold_text)
    if radians:
        import sympy as sp
        prediction = [value * 180 / sp.pi for value in prediction if isinstance(value, sp.Expr)]
    if not target: raise ValueError('Unparseable typed reference: ' + gold)
    return result(bool(prediction) and bool(verify(target, prediction)), bool(prediction))
