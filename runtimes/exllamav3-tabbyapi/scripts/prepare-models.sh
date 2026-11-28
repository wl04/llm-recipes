#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 || ( "$2" != download && "$2" != quantize-draft && "$2" != upgrade-local ) || ( "$2" != upgrade-local && $# -gt 3 ) ]]; then
    echo "Usage: bash $0 recipe-directory {download|quantize-draft|upgrade-local} [model-directory]" >&2
    exit 2
fi
runtime_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scripts_dir=$(cd -- "$runtime_dir/../../scripts" && pwd)
recipe_dir=$(cd -- "$1" && pwd)
container_recipe="/recipes/${recipe_dir##*/}"
action=$2
image=$(python3 "$runtime_dir/scripts/exl3_layout.py" "$recipe_dir")
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
local_args=()
action_args=()
if [[ $action == quantize-draft || $action == upgrade-local ]]; then
    gpu_access=$(python3 "$scripts_dir/gpu_access.py")
    mapfile -t gpu_args <<<"$gpu_access"
fi
if [[ $action == upgrade-local ]]; then
    local_args=(--network=none --pull=never --env HF_HUB_OFFLINE=1
        --mount "type=bind,src=$scripts_dir,dst=/repo-scripts,readonly")
    action_args=("${@:4}")
fi
sudo docker run --rm \
    --user "$(id -u):$(id -g)" \
    "${gpu_args[@]}" \
    "${local_args[@]}" \
    --env HF_HOME=/models/.cache/huggingface \
    --env XDG_CACHE_HOME=/models/.cache \
    --env TRITON_CACHE_DIR=/models/.cache/triton \
    --env PYTHONUNBUFFERED=1 \
    --mount "type=bind,src=$recipe_dir,dst=$container_recipe,readonly" \
    --mount "type=bind,src=$runtime_dir,dst=/runtime,readonly" \
    --mount "type=bind,src=$model_dir,dst=/models" \
    "$image" \
    python3 /runtime/scripts/prepare_models.py --recipe "$container_recipe" "$action" "${action_args[@]}"
