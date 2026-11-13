#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 || ( "$2" != download && "$2" != quantize-draft ) ]]; then
    echo "Usage: bash $0 recipe-directory {download|quantize-draft} [model-directory]" >&2
    exit 2
fi
runtime_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
recipe_dir=$(cd -- "$1" && pwd)
action=$2
image=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$runtime_dir/runtime.json")
for mount_path in "$runtime_dir" "$recipe_dir" "${3:-$HOME/Models/llm-recipes}"; do
    if [[ "$mount_path" == *","* || "$mount_path" == *$'\n'* ]]; then
        echo "Mount paths must not contain commas or newlines" >&2
        exit 2
    fi
done
model_dir=${3:-"$HOME/Models/llm-recipes"}
mkdir -p -- "$model_dir"
model_dir=$(cd -- "$model_dir" && pwd)
gpu_args=()
if [[ $action == quantize-draft ]]; then
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
    --mount "type=bind,src=$runtime_dir,dst=/runtime,readonly" \
    --mount "type=bind,src=$model_dir,dst=/models" \
    "$image" \
    python3 /runtime/scripts/prepare_models.py --recipe /recipe "$action"
