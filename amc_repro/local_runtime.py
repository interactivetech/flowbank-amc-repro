"""User-invoked model preparation and serving. Never imported to start a server."""
import argparse
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import sys
from .storage import atomic_json

MODEL = 'MIRALABS/Qwen3.8-27B-W4A16-AutoRound'
SERVED_MODEL = 'qwen3.8-27b-autoround-int4'
MAX_CONTEXT = 262144
REDHAT_MODEL = 'RedHatAI/Qwen3.8-27B-INT4'
REDHAT_REVISION = 'e45c27e8f463817db788d141a73a3c235a0a7c0c'


def profile():
    name = os.environ.get('AMC_MODEL_PROFILE', 'autoround')
    if name not in ('autoround','redhat'): raise ValueError('Unknown AMC_MODEL_PROFILE')
    return name


def deployment_root():
    return root()/'deployments'/'redhat' if profile() == 'redhat' else root()


def model_label(info):
    repository = info['model']['repository']
    if repository == MODEL: return 'Qwen3.8-27B AutoRound INT4'
    if repository == REDHAT_MODEL: return 'Qwen3.8-27B RedHatAI INT4'
    return repository


def root():
    return Path(os.environ.get('AMC_ROOT', '/scratch1/mendeza/flowbank-amc'))


def identity():
    lock = json.loads((deployment_root()/'model.lock.json').read_text())
    runtime = json.loads((deployment_root()/'serving.json').read_text())
    if runtime['model'] != lock:
        raise ValueError('Serving metadata/model lock mismatch')
    return runtime


def configure_client():
    info = identity()
    os.environ['OPENAI_MODEL'] = info['model']['served_model']
    os.environ['AMC_TOKENIZER_PATH'] = info['model']['snapshot']
    os.environ['AMC_MAX_CONTEXT'] = str(info['context_length'])
    return info


def prepare():
    from huggingface_hub import HfApi, snapshot_download
    lock_path = deployment_root()/'model.lock.json'
    repository = REDHAT_MODEL if profile() == 'redhat' else MODEL
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        revision = lock['revision']
        if lock['repository'] != repository: raise ValueError('Unexpected model lock')
    else:
        revision = REDHAT_REVISION if profile() == 'redhat' else HfApi().model_info(MODEL).sha
    if profile() == 'redhat':
        snapshot = snapshot_download(repository, revision=revision,
            allow_patterns=['*.json','*.jinja','README.md','*.safetensors'])
    else:
        snapshot = snapshot_download(repository, revision=revision)
    index_path = Path(snapshot)/'model.safetensors.index.json'
    if index_path.exists():
        indexed_files = set(json.loads(index_path.read_text())['weight_map'].values())
        missing = sorted(name for name in indexed_files if not (Path(snapshot)/name).is_file())
        if missing: raise ValueError('Incomplete model snapshot; missing indexed weights: ' + ', '.join(missing))
    config = json.loads((Path(snapshot)/'config.json').read_text())
    quant = config.get('quantization_config', {})
    if quant.get('quant_method') != 'compressed-tensors':
        raise ValueError('Expected compressed-tensors INT4 export; refusing precision fallback')
    groups = quant.get('config_groups', {}).values()
    if not any(g.get('weights', {}).get('num_bits') == 4 for g in groups):
        raise ValueError('Checkpoint does not declare 4-bit weights')
    prefix = 'qwen3.8-27b-redhat-int4' if profile() == 'redhat' else SERVED_MODEL
    lock = {'repository':repository, 'revision':revision, 'snapshot':snapshot,
            'served_model':prefix+'-'+revision[:12], 'quantization':quant,
            'config_sha256':hashlib.sha256((Path(snapshot)/'config.json').read_bytes()).hexdigest()}
    atomic_json(lock_path, lock)
    print(json.dumps(lock, indent=2))


def serve():
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Start the server inside a GPU Slurm allocation')
    lock = json.loads((deployment_root()/'model.lock.json').read_text())
    expected_repository = REDHAT_MODEL if profile() == 'redhat' else MODEL
    if lock['repository'] != expected_repository: raise ValueError('Serving profile/model mismatch')
    args = [str(Path(sys.executable).parent/'vllm'), 'serve', lock['snapshot'],
        '--served-model-name',lock['served_model'], '--host','127.0.0.1','--port','8000',
        '--tensor-parallel-size','1', '--dtype','bfloat16', '--quantization','compressed-tensors',
        '--max-model-len',str(MAX_CONTEXT), '--gpu-memory-utilization','0.90',
        '--max-num-seqs','2', '--enable-prefix-caching', '--generation-config','vllm',
        '--reasoning-parser','qwen3']
    info = {'model':lock,'command':args, 'context_length':MAX_CONTEXT,
            'packages':{p:md.version(p) for p in ['vllm','torch','transformers','openai','huggingface-hub']},
            'speculative_decoding':False,'kv_cache_dtype':'auto'}
    # Do not overwrite a running server's metadata if the port is occupied.
    import socket
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8000)) == 0:
            raise RuntimeError('Port 8000 already occupied; inspect the existing server')
    atomic_json(deployment_root()/'serving.json',info)
    os.setsid()
    os.execv(args[0],args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare','serve'])
    args = parser.parse_args()
    {'prepare':prepare,'serve':serve}[args.action]()
