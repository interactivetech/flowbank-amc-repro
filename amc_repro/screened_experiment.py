"""Freeze and validate the explicitly provisional 21-item screening snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .deepmath import require_scratch, THRESHOLDS
from .screening import BUCKETS, digest, read, results, preflight_reference, seed, bucket
from .storage import atomic_json

REPOSITORY = 'mendeza-umd/deepmath-103k-qwen-3-8-27b-screened-v1-provisional-21'
REVISION = '5ad55d34498601997f551d5080301648e26e9db6'
SHA256 = '5d1224320c12d9355d6107c3ae6f2f88fe622d795c7341ba5bc3bbf0f5b8b536'
PILOT = (68549, 77420, 11841, 14981, 28981)
FORMAT = 'deepmath-screened-provisional-v1'


def validate_manifest(manifest):
    frozen_root = require_scratch(manifest['frozen_root'])
    evidence_root = require_scratch(manifest['screening_run'])
    if digest(manifest) != read(frozen_root/'freeze_integrity.json')['manifest_sha256']:
        raise ValueError('Provisional manifest integrity mismatch')
    if (manifest['repository'], manifest['revision'], manifest['dataset_sha256']) != (REPOSITORY, REVISION, SHA256):
        raise ValueError('Provisional dataset identity mismatch')
    if hashlib.sha256((frozen_root/'source.parquet').read_bytes()).hexdigest() != SHA256:
        raise ValueError('Provisional source hash mismatch')
    questions = manifest['questions']
    if manifest['sample_size'] != 21 or len(questions) != 21 or len({q['question_id'] for q in questions}) != 21:
        raise ValueError('Expected 21 unique provisional questions')
    if manifest['audit_status'] != 'pending' or [q['dataset_row'] for q in questions[:5]] != list(PILOT):
        raise ValueError('Unexpected audit status or pilot membership')
    expected_cohorts = {str(t):[q['question_id'] for q in questions if q['screening']['solve_rate'] <= t] for t in THRESHOLDS}
    if manifest['cohorts'] != expected_cohorts or [len(expected_cohorts[str(t)]) for t in THRESHOLDS] != [21,16,12,8,5]:
        raise ValueError('Frozen cohort mismatch')
    candidates = {q['question_id']:q for qs in read(evidence_root/'provisional.json').values() for q in qs}
    if set(candidates) != {q['question_id'] for q in questions}:
        raise ValueError('Provisional selection changed')
    for q in questions:
        source = candidates[q['question_id']]
        for field in ('dataset_row','row','gold_answer','reference'):
            if q[field] != source[field]:
                raise ValueError('Question/reference differs from screening evidence')
        preflight_reference(q['reference'])
        sample = results(evidence_root,q)
        if len(sample) != 32 or {r['index'] for r in sample} != set(range(32)):
            raise ValueError('Screening sample incomplete')
        if any(r['grading_status']=='grading_failure' or r['seed'] != seed(q['dataset_row'],r['index']) for r in sample):
            raise ValueError('Invalid screening sample')
        correct = sum(r['correct'] for r in sample)
        if (q['screening']['correct'],q['screening']['responses'],q['screening']['solve_rate'],q['screening']['bucket']) != (correct,32,correct/32,bucket(correct)):
            raise ValueError('Screening counts mismatch')
        if digest(sample) != q['screening']['evidence_sha256']:
            raise ValueError('Screening evidence changed')
        if read(evidence_root/'greedy'/q['question_id']/'00.json')['correct'] != q['screening']['greedy_correct']:
            raise ValueError('Greedy control changed')


def freeze(source, evidence_root, output):
    import pyarrow.parquet as pq
    source, evidence_root, output = map(require_scratch, (source,evidence_root,output))
    if hashlib.sha256(source.read_bytes()).hexdigest() != SHA256:
        raise ValueError('Uploaded dataset source hash mismatch')
    published = pq.read_table(source).to_pylist()
    published_ids = {r['question_id'] for r in published}
    if len(published) != 21 or len(published_ids) != 21:
        raise ValueError('Expected 21 unique uploaded rows')
    selected = read(evidence_root/'provisional.json')
    questions=[]
    for b in BUCKETS:
        for original in selected[b]:
            q = dict(original)
            row = next((r for r in published if r['question_id']==q['question_id']),None)
            if row is None or row['audit_status'] != 'pending':
                raise ValueError('Uploaded selection differs')
            sample = results(evidence_root,q)
            correct = sum(r['correct'] for r in sample)
            if (row['dataset_row'],row['question'],row['final_answer'],json.loads(row['reference_json']),row['screening_correct'],row['screening_samples'],row['screening_solve_rate'],row['screening_bucket'],row['evidence_sha256']) != (q['dataset_row'],q['row']['question'],q['gold_answer'],q['reference'],correct,32,correct/32,b,digest(sample)):
                raise ValueError('Uploaded question or screening metadata differs')
            q['screening'] = dict(correct=correct,responses=32,solve_rate=correct/32,bucket=b,
                greedy_correct=row['greedy_correct'],parse_failures=row['screening_parse_failures'],
                truncated=row['screening_truncated'],evidence_sha256=row['evidence_sha256'])
            q['reference_note'] = None
            questions.append(q)
    if {q['question_id'] for q in questions} != published_ids:
        raise ValueError('Uploaded selection mismatch')
    questions.sort(key=lambda q:(0,PILOT.index(q['dataset_row'])) if q['dataset_row'] in PILOT else (1,q['dataset_row']))
    manifest = dict(dataset_format=FORMAT,repository=REPOSITORY,revision=REVISION,dataset_sha256=SHA256,
        sample_size=21,dataset_rows=21,questions=questions,audit_status='pending',frozen_root=str(output),
        screening_run=str(evidence_root),screening_source_commit=read(evidence_root/'run_manifest.json')['git_commit'],
        cohorts={str(t):[q['question_id'] for q in questions if q['screening']['solve_rate']<=t] for t in THRESHOLDS},
        reference_policy='Supplied labels unchanged; exploratory evaluation pending manual audit')
    output.mkdir(parents=True,exist_ok=True)
    target=output/'manifest.json'
    if target.exists():
        if read(target) != manifest: raise ValueError('Refusing to replace frozen manifest')
        validate_manifest(manifest)
        return manifest
    shutil.copyfile(source,output/'source.parquet')
    atomic_json(target,manifest)
    atomic_json(output/'freeze_integrity.json',dict(manifest_sha256=digest(manifest)))
    validate_manifest(manifest)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--screening-root',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    frozen=freeze(args.source,args.screening_root,args.output_dir)
    print(f"Frozen {frozen['sample_size']} provisional questions; no model calls.")


if __name__ == '__main__': main()
