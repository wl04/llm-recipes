#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 || ( "$2" != download && "$2" != quantize-draft ) ]]; then
    echo "Usage: bash $0 recipe-directory {download|quantize-draft} [model-directory]" >&2
    exit 2
fi
runtime_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scripts_dir=$(cd -- "$runtime_dir/../../scripts" && pwd)
recipe_dir=$(cd -- "$1" && pwd)
container_recipe="/recipes/${recipe_dir##*/}"
action=$2
image=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$runtime_dir/runtime.json")
image=${LLM_RECIPES_RUNTIME_IMAGE:-$image}
if [[ ! $image =~ ^[a-zA-Z0-9][a-zA-Z0-9_./:@-]*$ ]]; then
    echo "Invalid runtime image reference: $image" >&2
    exit 2
fi
model_dir=${3:-$(python3 "$scripts_dir/paths.py")}
for mount_path in "$runtime_dir" "$recipe_dir" "$model_dir"; do
    if [[ "$mount_path" == *","* || "$mount_path" == *$'\n'* ]]; then
        echo "Mount paths must not contain commas or newlines" >&2
        exit 2
    fi
done
mkdir -p -- "$model_dir"
model_dir=$(cd -- "$model_dir" && pwd)
gpu_args=()
if [[ $action == quantize-draft ]]; then
    gpu_access=$(python3 "$scripts_dir/gpu_access.py")
    mapfile -t gpu_args <<<"$gpu_access"
fi
sudo docker run --rm \
    --user "$(id -u):$(id -g)" \
    "${gpu_args[@]}" \
    --env HF_HOME=/models/.cache/huggingface \
    --env XDG_CACHE_HOME=/models/.cache \
    --env TRITON_CACHE_DIR=/models/.cache/triton \
    --env PYTHONUNBUFFERED=1 \
    --mount "type=bind,src=$recipe_dir,dst=$container_recipe,readonly" \
    --mount "type=bind,src=$runtime_dir,dst=/runtime,readonly" \
    --mount "type=bind,src=$model_dir,dst=/models" \
    "$image" \
    python3 /runtime/scripts/prepare_models.py --recipe "$container_recipe" "$action"
