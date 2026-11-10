import hashlib
import json
import os
import random
from pathlib import Path
from .grading import extract, parsed


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def dataset_manifest(path, size, seed):
    raw = Path(path).read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    if not 1 <= size <= len(rows):
        raise ValueError(f'sample size must be 1..{len(rows)}')
    indices = random.Random(seed).sample(range(len(rows)), size)
    questions = []
    for i in indices:
        row = rows[i]
        answer = extract(row['solution'], gold=True)
        if not parsed(answer):
            raise ValueError(f'Cannot parse official solution at row {i}; fix extraction before generation')
        questions.append({'question_id': f'amc-row-{i:04d}', 'row_index': i, 'line_number': i + 1,
                          'original_id': row.get('id'), 'row': row, 'gold_answer': answer})
    return {'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'dataset_rows': len(rows),
            'sample_size': size, 'seed': seed, 'questions': questions}


class Trace:
    def __init__(self, path, common):
        self.path, self.common = Path(path), common
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, **event):
        with self.path.open('a') as f:
            f.write(json.dumps({**self.common, **event}, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
