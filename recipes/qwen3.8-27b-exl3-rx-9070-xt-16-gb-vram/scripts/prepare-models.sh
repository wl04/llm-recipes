#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 || ( "$1" != download && "$1" != quantize-draft ) ]]; then
    echo "Usage: bash $0 {download|quantize-draft} [model-directory]" >&2
    exit 2
fi
recipe_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
model_dir=${2:-"$HOME/Models/llm-recipes"}
mkdir -p -- "$model_dir"
model_dir=$(cd -- "$model_dir" && pwd)
gpu_args=()
if [[ $1 == quantize-draft ]]; then
    gpu_args+=(--device=/dev/kfd --device=/dev/dri)
    gpu_args+=(--group-add "$(stat -c %g /dev/kfd)")
    for render_node in /dev/dri/renderD*; do
        gpu_args+=(--group-add "$(stat -c %g "$render_node")")
    done
fi
sudo docker run --rm \
    --user "$(id -u):$(id -g)" \
    "${gpu_args[@]}" \
    --env HF_HOME=/models/.cache/huggingface \
    --env XDG_CACHE_HOME=/models/.cache \
    --env TRITON_CACHE_DIR=/models/.cache/triton \
    --env PYTHONUNBUFFERED=1 \
    --mount "type=bind,src=$recipe_dir,dst=/recipe,readonly" \
    --mount "type=bind,src=$model_dir,dst=/models" \
    llm-recipes/exl3-rdna4:probe \
    python3 /recipe/scripts/prepare_models.py "$1"
