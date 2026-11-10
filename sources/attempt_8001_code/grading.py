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
