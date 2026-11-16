# Source from bash. All large artifacts and caches belong on scratch.
export AMC_ROOT="${AMC_ROOT:-/scratch1/mendeza/flowbank-amc}"
export HF_HOME="$AMC_ROOT/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export HF_DATASETS_CACHE="$HF_HOME/datasets"
unset TRANSFORMERS_CACHE
export XDG_CACHE_HOME="$AMC_ROOT/cache"
export PIP_CACHE_DIR="$AMC_ROOT/cache/pip"
export UV_CACHE_DIR="$AMC_ROOT/cache/uv"
export TORCH_HOME="$AMC_ROOT/cache/torch"
export TORCHINDUCTOR_CACHE_DIR="$AMC_ROOT/cache/torchinductor"
export TRITON_CACHE_DIR="$AMC_ROOT/cache/triton"
export VLLM_CACHE_ROOT="$AMC_ROOT/cache/vllm"
export FLASHINFER_WORKSPACE_BASE="$AMC_ROOT/cache/flashinfer"
export CUTE_DSL_CACHE_DIR="$AMC_ROOT/cache/cute-dsl"
export CUDA_CACHE_PATH="$AMC_ROOT/cache/cuda"
export AMC_TMPDIR="$AMC_ROOT/tmp"
export TMPDIR="$AMC_TMPDIR"
export AMC_EXECUTOR_PYTHON="$AMC_ROOT/executor/bin/python"
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=local-amc
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1

export PATH="$AMC_ROOT/runtime/bin:$PATH"
if [[ -z "${CUDA_HOME:-}" && -d /opt/common/cuda/cuda-13.0.2 ]]; then
    export CUDA_HOME=/opt/common/cuda/cuda-13.0.2
fi
if [[ -n "${CUDA_HOME:-}" ]]; then
    export PATH="$CUDA_HOME/bin:$PATH"
fi
