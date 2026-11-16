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


def root():
    return Path(os.environ.get('AMC_ROOT', '/scratch1/mendeza/flowbank-amc'))


def identity():
    lock = json.loads((root()/'model.lock.json').read_text())
    runtime = json.loads((root()/'serving.json').read_text())
    if runtime['model'] != lock:
        raise ValueError('Serving metadata/model lock mismatch')
    return runtime


def configure_client():
    info = identity()
    os.environ['OPENAI_MODEL'] = info['model']['served_model']
    os.environ['AMC_TOKENIZER_PATH'] = info['model']['snapshot']
    os.environ['AMC_MAX_CONTEXT'] = str(MAX_CONTEXT)
    return info


def prepare():
    from huggingface_hub import HfApi, snapshot_download
    lock_path = root()/'model.lock.json'
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        revision = lock['revision']
        if lock['repository'] != MODEL: raise ValueError('Unexpected model lock')
    else:
        revision = HfApi().model_info(MODEL).sha
    snapshot = snapshot_download(MODEL, revision=revision)
    config = json.loads((Path(snapshot)/'config.json').read_text())
    quant = config.get('quantization_config', {})
    if quant.get('quant_method') != 'compressed-tensors':
        raise ValueError('Expected compressed-tensors AutoRound export; refusing precision fallback')
    groups = quant.get('config_groups', {}).values()
    if not any(g.get('weights', {}).get('num_bits') == 4 for g in groups):
        raise ValueError('Checkpoint does not declare 4-bit weights')
    lock = {'repository':MODEL, 'revision':revision, 'snapshot':snapshot,
            'served_model':SERVED_MODEL+'-'+revision[:12], 'quantization':quant,
            'config_sha256':hashlib.sha256((Path(snapshot)/'config.json').read_bytes()).hexdigest()}
    atomic_json(lock_path, lock)
    print(json.dumps(lock, indent=2))


def serve():
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Start the server inside a GPU Slurm allocation')
    lock = json.loads((root()/'model.lock.json').read_text())
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
    atomic_json(root()/'serving.json',info)
    os.setsid()
    os.execv(args[0],args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare','serve'])
    args = parser.parse_args()
    {'prepare':prepare,'serve':serve}[args.action]()
